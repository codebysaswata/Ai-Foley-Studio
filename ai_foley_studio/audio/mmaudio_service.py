"""Reusable adapter for the original MMAudio video-to-audio inference path."""

from __future__ import annotations

import copy
import dataclasses
import gc
import logging
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ai_foley_studio.config import FoleySettings, SUPPORTED_AUDIO_EXTENSIONS, get_settings


log = logging.getLogger(__name__)


class MMAudioServiceError(RuntimeError):
    """Base error for failures at the MMAudio integration boundary."""


class ModelCheckpointError(MMAudioServiceError):
    """An official MMAudio file is absent or implausibly small."""


class ModelInitializationError(MMAudioServiceError):
    """Model dependencies, device selection, or weight loading failed."""


class VideoInferenceError(MMAudioServiceError):
    """MMAudio could not decode/prepare the source video."""


class AudioGenerationError(MMAudioServiceError):
    """Sampling, vocoding, or audio serialization failed."""


@dataclass(frozen=True)
class CheckpointStatus:
    """Local presence check for one required official checkpoint."""

    path: Path
    purpose: str
    exists: bool
    nonempty: bool


@dataclass(frozen=True)
class GenerationResult:
    """A verified MMAudio audio artifact and generation metadata."""

    audio_path: Path
    format: str
    sample_rate: int
    channels: int
    duration_seconds: float
    model_variant: str
    device: str
    precision: str
    inference_seconds: float
    peak_cuda_memory_bytes: int | None


@dataclass(frozen=True)
class _UpstreamBindings:
    torch: Any
    torchaudio: Any
    all_model_cfg: Any
    generate: Any
    load_video: Any
    FlowMatching: Any
    get_my_mmaudio: Any
    FeaturesUtils: Any


class MMAudioService:
    """Keep a genuine MMAudio model loaded for serialized generation requests.

    The implementation intentionally mirrors the upstream ``demo.py`` flow:
    ``get_my_mmaudio -> load_weights -> FeaturesUtils -> load_video ->
    FlowMatching -> eval_utils.generate -> torchaudio.save``. It does not call
    checkpoint download helpers and never substitutes mock or synthetic audio.
    """

    def __init__(self, settings: FoleySettings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.validate()
        self._lock = threading.RLock()
        self._bindings: _UpstreamBindings | None = None
        self._model_config: Any = None
        self._network: Any = None
        self._features: Any = None
        self._sequence_config: Any = None
        self._device: str | None = None
        self._dtype: Any = None

    @property
    def initialized(self) -> bool:
        return self._network is not None and self._features is not None

    @property
    def device(self) -> str | None:
        return self._device

    def checkpoint_status(self) -> list[CheckpointStatus]:
        """Report required paths without downloading or loading model tensors."""
        paths = self._checkpoint_paths()
        return [
            CheckpointStatus(
                path=path,
                purpose=purpose,
                exists=path.is_file(),
                nonempty=path.is_file() and path.stat().st_size > 1024,
            )
            for purpose, path in paths
        ]

    def initialize(self) -> None:
        """Initialize upstream weights once; repeated calls reuse the loaded model."""
        with self._lock:
            if self.initialized:
                return
            self._require_checkpoints()
            bindings = self._import_bindings()
            model_config = self._resolved_model_config(bindings)
            device, dtype = self._resolve_device_dtype(bindings.torch)
            self._log_cuda_memory(bindings.torch, "before_mmaudio_initialize")
            try:
                network = bindings.get_my_mmaudio(model_config.model_name).to(device, dtype).eval()
                weights = bindings.torch.load(model_config.model_path, map_location="cpu", weights_only=True)
                network.load_weights(weights)
                del weights
                features = bindings.FeaturesUtils(
                    tod_vae_ckpt=model_config.vae_path,
                    synchformer_ckpt=model_config.synchformer_ckpt,
                    enable_conditions=True,
                    mode=model_config.mode,
                    bigvgan_vocoder_ckpt=model_config.bigvgan_16k_path,
                    need_vae_encoder=False,
                ).to(device, dtype).eval()
            except Exception as exc:
                gc.collect()
                if device.startswith("cuda"):
                    bindings.torch.cuda.empty_cache()
                detail = "CUDA out of memory during model initialization." if self._is_cuda_oom(exc) else "Could not initialize MMAudio model components."
                raise ModelInitializationError(detail) from exc
            self._bindings = bindings
            self._model_config = model_config
            self._network = network
            self._features = features
            self._sequence_config = copy.deepcopy(model_config.seq_cfg)
            self._device = str(device)
            self._dtype = dtype
            log.info(
                "Initialized MMAudio variant=%s device=%s precision=%s",
                model_config.model_name,
                self._device,
                str(dtype).replace("torch.", ""),
            )
            self._log_cuda_memory(bindings.torch, "after_mmaudio_initialize")

    def generate(
        self,
        video_path: str | Path,
        prompt: str,
        output_path: str | Path,
        *,
        negative_prompt: str = "",
        seed: int = -1,
        duration: float | None = None,
        num_steps: int | None = None,
        guidance_scale: float | None = None,
    ) -> GenerationResult:
        """Generate, save, and read back a real MMAudio FLAC/WAV artifact."""
        source, destination, effective_duration, steps, guidance = self._validate_request(
            video_path, prompt, output_path, duration, num_steps, guidance_scale
        )
        with self._lock:
            self.initialize()
            assert self._bindings is not None and self._network is not None
            assert self._features is not None and self._sequence_config is not None
            assert self._device is not None and self._model_config is not None
            torch = self._bindings.torch
            if self._device.startswith("cuda"):
                torch.cuda.reset_peak_memory_stats()
            self._log_cuda_memory(torch, "before_mmaudio_generate")
            started = time.perf_counter()
            try:
                video_info = self._bindings.load_video(source, effective_duration, load_all_frames=False)
            except Exception as exc:
                raise VideoInferenceError(f"MMAudio could not load video: {source}") from exc
            if video_info.duration_sec <= 0:
                raise VideoInferenceError("MMAudio decoded a zero-duration video.")
            try:
                self._sequence_config.duration = video_info.duration_sec
                self._network.update_seq_lengths(
                    self._sequence_config.latent_seq_len,
                    self._sequence_config.clip_seq_len,
                    self._sequence_config.sync_seq_len,
                )
                rng = torch.Generator(device=self._device)
                if seed >= 0:
                    rng.manual_seed(seed)
                else:
                    rng.seed()
                flow = self._bindings.FlowMatching(min_sigma=0, inference_mode="euler", num_steps=steps)
                with torch.inference_mode():
                    waveform = self._bindings.generate(
                        video_info.clip_frames.unsqueeze(0),
                        video_info.sync_frames.unsqueeze(0),
                        [prompt.strip()],
                        negative_text=[negative_prompt.strip()],
                        feature_utils=self._features,
                        net=self._network,
                        fm=flow,
                        rng=rng,
                        cfg_strength=guidance,
                    ).float().cpu()[0]
            except Exception as exc:
                if self._is_cuda_oom(exc):
                    raise AudioGenerationError(
                        "MMAudio CUDA inference ran out of memory; no automatic CPU retry was attempted."
                    ) from exc
                raise AudioGenerationError("MMAudio waveform generation failed.") from exc
            elapsed = time.perf_counter() - started
            try:
                self._bindings.torchaudio.save(
                    str(destination), waveform, int(self._sequence_config.sampling_rate)
                )
                info = self._bindings.torchaudio.info(str(destination))
            except Exception as exc:
                raise AudioGenerationError(f"Could not save/read generated audio: {destination}") from exc
            if not destination.is_file() or destination.stat().st_size == 0 or info.num_frames <= 0:
                raise AudioGenerationError("Audio serialization produced an empty or unreadable output.")
            peak = int(torch.cuda.max_memory_allocated()) if self._device.startswith("cuda") else None
            result = GenerationResult(
                audio_path=destination.resolve(),
                format=destination.suffix.lower().lstrip("."),
                sample_rate=int(info.sample_rate),
                channels=int(info.num_channels),
                duration_seconds=float(info.num_frames / info.sample_rate),
                model_variant=self._model_config.model_name,
                device=self._device,
                precision=str(self._dtype).replace("torch.", ""),
                inference_seconds=elapsed,
                peak_cuda_memory_bytes=peak,
            )
            log.info("Generated MMAudio output=%s duration=%.3fs", result.audio_path, result.duration_seconds)
            self._log_cuda_memory(torch, "after_mmaudio_generate")
            return result

    def close(self) -> None:
        """Release retained model objects; only explicit close clears CUDA cache."""
        with self._lock:
            bindings, device = self._bindings, self._device
            self._network = self._features = self._sequence_config = self._model_config = None
            self._bindings = None
            self._device = self._dtype = None
            gc.collect()
            if bindings is not None and device and device.startswith("cuda"):
                bindings.torch.cuda.empty_cache()
                try:
                    bindings.torch.cuda.ipc_collect()
                except RuntimeError:
                    pass
                self._log_cuda_memory(bindings.torch, "after_mmaudio_close")

    @staticmethod
    def _log_cuda_memory(torch: Any, phase: str) -> None:
        """Log actual CUDA allocator and driver facts without changing allocation state."""
        if not torch.cuda.is_available():
            return
        free, total = torch.cuda.mem_get_info()
        log.info(
            "%s allocated=%d reserved=%d peak=%d free=%d total=%d",
            phase,
            torch.cuda.memory_allocated(),
            torch.cuda.memory_reserved(),
            torch.cuda.max_memory_allocated(),
            free,
            total,
        )

    def _checkpoint_paths(self) -> list[tuple[str, Path]]:
        suffixes = {
            "small_16k": ("mmaudio_small_16k.pth", "v1-16.pth", "best_netG.pt"),
            "small_44k": ("mmaudio_small_44k.pth", "v1-44.pth", None),
            "medium_44k": ("mmaudio_medium_44k.pth", "v1-44.pth", None),
            "large_44k": ("mmaudio_large_44k.pth", "v1-44.pth", None),
            "large_44k_v2": ("mmaudio_large_44k_v2.pth", "v1-44.pth", None),
        }
        model, vae, vocoder = suffixes[self.settings.model_variant]
        paths = [
            ("flow prediction model", self.settings.weights_dir / model),
            ("VAE", self.settings.external_weights_dir / vae),
            ("Synchformer visual encoder", self.settings.external_weights_dir / "synchformer_state_dict.pth"),
        ]
        if vocoder:
            paths.append(("16 kHz BigVGAN vocoder", self.settings.external_weights_dir / vocoder))
        return paths

    def _require_checkpoints(self) -> None:
        failures = [
            f"{status.purpose}: {status.path}"
            for status in self.checkpoint_status()
            if not status.exists or not status.nonempty
        ]
        if failures:
            raise ModelCheckpointError("Required official MMAudio files are unavailable:\n- " + "\n- ".join(failures))

    def _import_bindings(self) -> _UpstreamBindings:
        if self._bindings is not None:
            return self._bindings
        repository_root = str(self.settings.repository_root)
        if repository_root not in sys.path:
            sys.path.insert(0, repository_root)
        try:
            import mmaudio
            import torch
            import torchaudio
            from mmaudio.eval_utils import all_model_cfg, generate, load_video
            from mmaudio.model.flow_matching import FlowMatching
            from mmaudio.model.networks import get_my_mmaudio
            from mmaudio.model.utils.features_utils import FeaturesUtils
        except (ImportError, OSError) as exc:
            raise ModelInitializationError(
                "MMAudio dependencies could not be imported. Install compatible project dependencies first."
            ) from exc
        local_source = (self.settings.repository_root / "mmaudio").resolve()
        imported_source = Path(mmaudio.__file__).resolve()
        try:
            imported_source.relative_to(local_source)
        except ValueError as exc:
            raise ModelInitializationError(
                "MMAudio was imported from outside the configured project repository: "
                f"{imported_source}. Expected a module under {local_source}."
            ) from exc
        return _UpstreamBindings(
            torch=torch,
            torchaudio=torchaudio,
            all_model_cfg=all_model_cfg,
            generate=generate,
            load_video=load_video,
            FlowMatching=FlowMatching,
            get_my_mmaudio=get_my_mmaudio,
            FeaturesUtils=FeaturesUtils,
        )

    def _resolved_model_config(self, bindings: _UpstreamBindings) -> Any:
        try:
            upstream = bindings.all_model_cfg[self.settings.model_variant]
        except KeyError as exc:
            raise ModelInitializationError(f"Upstream MMAudio lacks {self.settings.model_variant!r}.") from exc

        def resolve(path: Path | None) -> Path | None:
            if path is None:
                return None
            return path if path.is_absolute() else self.settings.checkpoint_root / path

        return dataclasses.replace(
            upstream,
            model_path=resolve(upstream.model_path),
            vae_path=resolve(upstream.vae_path),
            synchformer_ckpt=resolve(upstream.synchformer_ckpt),
            bigvgan_16k_path=resolve(upstream.bigvgan_16k_path),
        )

    def _resolve_device_dtype(self, torch: Any) -> tuple[str, Any]:
        requested = self.settings.device.lower()
        device = "cuda" if requested == "auto" and torch.cuda.is_available() else (
            "cpu" if requested == "auto" else self.settings.device
        )
        try:
            device_type = torch.device(device).type
        except (TypeError, RuntimeError) as exc:
            raise ModelInitializationError(f"Invalid Torch device: {device!r}.") from exc
        if device_type == "cuda" and not torch.cuda.is_available():
            raise ModelInitializationError("CUDA was requested but is unavailable to PyTorch.")
        precision = self.settings.precision.lower()
        if precision not in {"auto", "float16", "bfloat16", "float32"}:
            raise ModelInitializationError(f"Unsupported precision setting: {self.settings.precision!r}.")
        if precision == "auto":
            dtype = torch.float16 if device_type == "cuda" else torch.float32
        else:
            dtype = getattr(torch, precision)
        if device_type == "cpu" and dtype is not torch.float32:
            raise ModelInitializationError("CPU MMAudio inference requires float32 precision.")
        return str(device), dtype

    def _validate_request(
        self,
        video_path: str | Path,
        prompt: str,
        output_path: str | Path,
        duration: float | None,
        num_steps: int | None,
        guidance_scale: float | None,
    ) -> tuple[Path, Path, float, int, float]:
        source = Path(video_path).expanduser().resolve()
        if not source.is_file() or source.stat().st_size == 0:
            raise VideoInferenceError(f"Input video does not exist, is not a file, or is empty: {source}")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("MMAudio requires a non-empty prompt.")
        destination = Path(output_path).expanduser().resolve()
        if destination.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
            raise ValueError(f"Output audio must use one of {sorted(SUPPORTED_AUDIO_EXTENSIONS)}.")
        if destination.exists() and destination.is_dir():
            raise ValueError("Output audio path must be a file, not a directory.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        effective_duration = self.settings.default_generation_duration if duration is None else float(duration)
        if not 0 < effective_duration <= self.settings.max_generation_duration:
            raise ValueError(
                f"duration must be in (0, {self.settings.max_generation_duration}] seconds; got {effective_duration}."
            )
        steps = self.settings.default_num_steps if num_steps is None else int(num_steps)
        guidance = self.settings.default_guidance_scale if guidance_scale is None else float(guidance_scale)
        if steps <= 0 or guidance <= 0:
            raise ValueError("num_steps and guidance_scale must be greater than zero.")
        return source, destination, effective_duration, steps, guidance

    @staticmethod
    def _is_cuda_oom(exc: BaseException) -> bool:
        return "cuda" in str(exc).lower() and "out of memory" in str(exc).lower()
