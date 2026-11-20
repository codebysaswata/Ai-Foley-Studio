"""Audio inspection, duration fitting, offset, conversion, and loudness tools."""

from __future__ import annotations

import json
import logging
import math
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ai_foley_studio.config import SUPPORTED_AUDIO_EXTENSIONS


log = logging.getLogger(__name__)


class AudioProcessingError(RuntimeError):
    """An audio file is invalid or a processing operation could not complete."""


@dataclass(frozen=True)
class AudioInspection:
    """Read-back facts about an audio artifact."""

    path: Path
    format: str
    duration_seconds: float
    sample_rate: int
    channels: int
    frames: int
    peak_amplitude: float
    rms_amplitude: float
    finite_samples: bool
    is_silent: bool

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["path"] = str(self.path)
        return result


class AudioProcessor:
    """Perform deterministic operations without deleting raw MMAudio artifacts."""

    def __init__(self, ffmpeg_executable: str = "ffmpeg") -> None:
        self.ffmpeg_executable = ffmpeg_executable

    def inspect(self, audio_path: str | Path) -> AudioInspection:
        """Load and validate an audio file through TorchAudio."""
        source = self._validate_audio_path(audio_path)
        torch, torchaudio = self._audio_bindings()
        try:
            waveform, sample_rate = torchaudio.load(str(source))
        except Exception as exc:
            raise AudioProcessingError(f"Could not decode audio file: {source}") from exc
        if waveform.ndim != 2 or waveform.shape[0] <= 0 or waveform.shape[1] <= 0 or sample_rate <= 0:
            raise AudioProcessingError("Decoded audio has an invalid shape or sample rate.")
        finite = bool(torch.isfinite(waveform).all().item())
        if not finite:
            raise AudioProcessingError("Decoded audio contains NaN or infinite samples.")
        peak = float(waveform.abs().max().item())
        rms = float(torch.sqrt(torch.mean(waveform.square())).item())
        return AudioInspection(
            path=source,
            format=source.suffix.lower().lstrip("."),
            duration_seconds=float(waveform.shape[1] / sample_rate),
            sample_rate=int(sample_rate),
            channels=int(waveform.shape[0]),
            frames=int(waveform.shape[1]),
            peak_amplitude=peak,
            rms_amplitude=rms,
            finite_samples=finite,
            is_silent=peak < 1e-5,
        )

    def trim_to_duration(
        self,
        input_path: str | Path,
        output_path: str | Path,
        target_duration: float,
        *,
        pad_if_short: bool = False,
    ) -> AudioInspection:
        """Trim, optionally pad, and save audio to an exact target duration."""
        if target_duration <= 0 or not math.isfinite(target_duration):
            raise ValueError("target_duration must be a finite value greater than zero.")
        waveform, sample_rate = self._load(input_path)
        target_frames = max(1, round(target_duration * sample_rate))
        waveform = self._fit_frames(waveform, target_frames, pad=pad_if_short)
        return self._save_and_inspect(waveform, sample_rate, output_path)

    def apply_timing_offset(
        self,
        input_path: str | Path,
        output_path: str | Path,
        offset_seconds: float,
        *,
        target_duration: float | None = None,
    ) -> AudioInspection:
        """Shift audio once while retaining a defined output duration.

        Positive offsets prepend silence and trim/pad the end. Negative offsets
        remove leading samples and pad the end. Without an explicit target, the
        source duration is retained, preventing an accidental duration change.
        """
        if not math.isfinite(offset_seconds):
            raise ValueError("offset_seconds must be finite.")
        waveform, sample_rate = self._load(input_path)
        source_frames = waveform.shape[1]
        target_frames = (
            max(1, round(target_duration * sample_rate))
            if target_duration is not None
            else source_frames
        )
        if target_duration is not None and target_duration <= 0:
            raise ValueError("target_duration must be greater than zero when supplied.")
        torch, _ = self._audio_bindings()
        offset_frames = round(abs(offset_seconds) * sample_rate)
        if offset_seconds > 0:
            shifted = torch.cat((torch.zeros_like(waveform[:, :offset_frames]), waveform), dim=1)
        elif offset_seconds < 0:
            shifted = waveform[:, min(offset_frames, source_frames):]
        else:
            shifted = waveform
        shifted = self._fit_frames(shifted, target_frames, pad=True)
        return self._save_and_inspect(shifted, sample_rate, output_path)

    def convert(self, input_path: str | Path, output_path: str | Path) -> AudioInspection:
        """Convert FLAC/WAV while preserving decoded channel count and sample rate."""
        waveform, sample_rate = self._load(input_path)
        return self._save_and_inspect(waveform, sample_rate, output_path)

    def normalize_loudness(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        target_lufs: float = -16.0,
        true_peak_limit: float = -1.5,
        loudness_range: float = 11.0,
    ) -> AudioInspection:
        """Apply two-pass FFmpeg EBU R128 loudness normalization.

        FFmpeg's ``loudnorm`` filter measures integrated loudness in the first
        pass and uses those measurements in a second pass. The source remains
        untouched and the output is read back before it is returned.
        """
        if not all(math.isfinite(value) for value in (target_lufs, true_peak_limit, loudness_range)):
            raise ValueError("Loudness parameters must be finite.")
        source = self._validate_audio_path(input_path)
        destination = self._prepare_destination(output_path)
        executable = shutil.which(self.ffmpeg_executable)
        if executable is None:
            raise AudioProcessingError("FFmpeg is required for loudness normalization but was not found on PATH.")
        measure_filter = (
            f"loudnorm=I={target_lufs}:TP={true_peak_limit}:LRA={loudness_range}:print_format=json"
        )
        measured = subprocess.run(
            [executable, "-hide_banner", "-nostdin", "-i", str(source), "-af", measure_filter, "-f", "null", "-"],
            capture_output=True,
            text=True,
            check=False,
        )
        if measured.returncode != 0:
            raise AudioProcessingError(f"FFmpeg loudness measurement failed: {measured.stderr.strip()}")
        match = re.search(r"\{\s*\"input_i\".*?\}", measured.stderr, flags=re.DOTALL)
        if match is None:
            raise AudioProcessingError("FFmpeg did not return loudnorm measurement JSON.")
        try:
            stats = json.loads(match.group(0))
            second_filter = (
                f"loudnorm=I={target_lufs}:TP={true_peak_limit}:LRA={loudness_range}:"
                f"measured_I={stats['input_i']}:measured_LRA={stats['input_lra']}:"
                f"measured_TP={stats['input_tp']}:measured_thresh={stats['input_thresh']}:"
                f"offset={stats['target_offset']}:linear=true:print_format=summary"
            )
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise AudioProcessingError("FFmpeg returned incomplete loudness measurements.") from exc
        rendered = subprocess.run(
            [executable, "-hide_banner", "-nostdin", "-y", "-i", str(source), "-af", second_filter, str(destination)],
            capture_output=True,
            text=True,
            check=False,
        )
        if rendered.returncode != 0:
            raise AudioProcessingError(f"FFmpeg loudness rendering failed: {rendered.stderr.strip()}")
        return self.inspect(destination)

    def _load(self, input_path: str | Path):
        source = self._validate_audio_path(input_path)
        _torch, torchaudio = self._audio_bindings()
        try:
            waveform, sample_rate = torchaudio.load(str(source))
        except Exception as exc:
            raise AudioProcessingError(f"Could not decode audio file: {source}") from exc
        if waveform.ndim != 2 or waveform.shape[1] <= 0 or sample_rate <= 0:
            raise AudioProcessingError("Decoded audio is empty or invalid.")
        return waveform, int(sample_rate)

    def _save_and_inspect(self, waveform, sample_rate: int, output_path: str | Path) -> AudioInspection:
        destination = self._prepare_destination(output_path)
        torch, torchaudio = self._audio_bindings()
        if waveform.ndim != 2 or waveform.shape[1] <= 0:
            raise AudioProcessingError("Refusing to write empty audio.")
        if not bool(torch.isfinite(waveform).all().item()):
            raise AudioProcessingError("Refusing to write audio containing NaN or infinite samples.")
        try:
            torchaudio.save(str(destination), waveform, sample_rate)
        except Exception as exc:
            raise AudioProcessingError(f"Could not write processed audio: {destination}") from exc
        return self.inspect(destination)

    @staticmethod
    def _fit_frames(waveform, target_frames: int, *, pad: bool):
        if waveform.shape[1] > target_frames:
            return waveform[:, :target_frames]
        if waveform.shape[1] < target_frames and pad:
            torch = __import__("torch")
            zeros = torch.zeros(
                (waveform.shape[0], target_frames - waveform.shape[1]),
                dtype=waveform.dtype,
                device=waveform.device,
            )
            return torch.cat((waveform, zeros), dim=1)
        return waveform

    def _validate_audio_path(self, path: str | Path) -> Path:
        source = Path(path).expanduser().resolve()
        if not source.is_file() or source.stat().st_size == 0:
            raise AudioProcessingError(f"Audio path does not exist, is not a file, or is empty: {source}")
        if source.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
            raise AudioProcessingError(f"Unsupported audio format: {source.suffix}")
        return source

    def _prepare_destination(self, path: str | Path) -> Path:
        destination = Path(path).expanduser().resolve()
        if destination.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
            raise AudioProcessingError(f"Output audio must use one of {sorted(SUPPORTED_AUDIO_EXTENSIONS)}.")
        if destination.exists() and destination.is_dir():
            raise AudioProcessingError("Output audio path must be a file, not a directory.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination

    @staticmethod
    def _audio_bindings():
        try:
            import torch
            import torchaudio
        except (ImportError, OSError) as exc:
            raise AudioProcessingError("Torch and TorchAudio are required for audio processing.") from exc
        return torch, torchaudio
