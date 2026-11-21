"""Sequential, event-conditioned MMAudio generation for complete videos."""

from __future__ import annotations

import math
import logging
import secrets
import shutil
import subprocess
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Sequence

from ai_foley_studio.audio.mmaudio_service import GenerationResult
from ai_foley_studio.intelligence.context_engine import FoleyEvent, NormalizedFoleyContext


class ChunkGenerationError(RuntimeError):
    """A video/audio chunk could not be generated or assembled."""


class ChunkGenerationCancelled(ChunkGenerationError):
    """Cooperative cancellation observed between MMAudio inference calls."""


@dataclass(frozen=True)
class ChunkQualityPolicy:
    """Conservative waveform acceptance thresholds; no loudness gain is applied."""

    boundary_exclusion_seconds: float = 0.15
    minimum_continuous_interior_rms: float = 0.001
    maximum_clipped_sample_ratio: float = 0.0001
    maximum_retries: int = 2

    def __post_init__(self) -> None:
        if self.boundary_exclusion_seconds < 0:
            raise ValueError("boundary_exclusion_seconds must be non-negative.")
        if self.minimum_continuous_interior_rms < 0:
            raise ValueError("minimum_continuous_interior_rms must be non-negative.")
        if not 0 <= self.maximum_clipped_sample_ratio <= 1:
            raise ValueError("maximum_clipped_sample_ratio must be between zero and one.")
        if self.maximum_retries < 0:
            raise ValueError("maximum_retries must be non-negative.")


@dataclass(frozen=True)
class ChunkWaveformMetrics:
    full_rms: float
    interior_rms: float
    sample_peak: float
    clipped_sample_ratio: float
    duration_seconds: float
    finite_samples: bool
    status: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


MIN_SYNCHFORMER_SECONDS = 16 / 25


@dataclass(frozen=True)
class ChunkWindow:
    """Core timeline range and extracted source range for one inference call."""

    index: int
    core_start: float
    core_end: float
    source_start: float
    source_end: float


@dataclass(frozen=True)
class ChunkedGenerationResult:
    generation: GenerationResult
    chunks: tuple[ChunkWindow, ...]
    chunk_generations: tuple[GenerationResult, ...]
    chunk_reports: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": {
                "audio_path": str(self.generation.audio_path),
                "duration_seconds": self.generation.duration_seconds,
                "sample_rate": self.generation.sample_rate,
                "channels": self.generation.channels,
                "model_variant": self.generation.model_variant,
                "device": self.generation.device,
                "precision": self.generation.precision,
                "inference_seconds": self.generation.inference_seconds,
                "peak_cuda_memory_bytes": self.generation.peak_cuda_memory_bytes,
            },
            "chunks": [chunk.__dict__ for chunk in self.chunks],
            "chunk_generations": [
                {
                    "duration_seconds": item.duration_seconds,
                    "inference_seconds": item.inference_seconds,
                    "peak_cuda_memory_bytes": item.peak_cuda_memory_bytes,
                }
                for item in self.chunk_generations
            ],
            "chunk_reports": list(self.chunk_reports),
        }


_CONTINUOUS_RHYTHMS = {"continuous", "sustained", "ongoing", "steady", "constant"}


def inspect_chunk_waveform(
    waveform: Any,
    sample_rate: int,
    expected_duration_seconds: float,
    *,
    continuous_required: bool,
    policy: ChunkQualityPolicy = ChunkQualityPolicy(),
) -> ChunkWaveformMetrics:
    """Measure a generated chunk and reject near-silence only when ambience is required."""
    import torch

    if waveform.ndim != 2 or waveform.shape[0] <= 0 or waveform.shape[1] <= 0 or sample_rate <= 0:
        return ChunkWaveformMetrics(0.0, 0.0, 0.0, 0.0, 0.0, False, "rejected", "empty or malformed waveform")
    finite = bool(torch.isfinite(waveform).all().item())
    if not finite:
        return ChunkWaveformMetrics(0.0, 0.0, 0.0, 0.0, waveform.shape[1] / sample_rate,
                                    False, "rejected", "waveform contains NaN or infinite samples")
    audio = waveform.detach().to(dtype=torch.float32)
    full_rms = float(torch.sqrt(torch.mean(audio.square())).item())
    exclusion = min(int(round(policy.boundary_exclusion_seconds * sample_rate)), audio.shape[1] // 4)
    interior = audio[:, exclusion: audio.shape[1] - exclusion] if exclusion else audio
    if interior.shape[1] == 0:
        interior = audio
    interior_rms = float(torch.sqrt(torch.mean(interior.square())).item())
    sample_peak = float(audio.abs().max().item())
    clipped_ratio = float((audio.abs() >= 0.9999).to(torch.float32).mean().item())
    duration = audio.shape[1] / sample_rate
    reason = None
    if duration < expected_duration_seconds - 0.05:
        reason = f"unexpectedly short audio ({duration:.3f}s; expected {expected_duration_seconds:.3f}s)"
    elif clipped_ratio > policy.maximum_clipped_sample_ratio:
        reason = f"clipped sample ratio {clipped_ratio:.6f} exceeds {policy.maximum_clipped_sample_ratio:.6f}"
    elif continuous_required and interior_rms < policy.minimum_continuous_interior_rms:
        reason = (
            f"continuous ambience is near-silent in the interior ({interior_rms:.6f} RMS; "
            f"minimum {policy.minimum_continuous_interior_rms:.6f})"
        )
    return ChunkWaveformMetrics(
        full_rms, interior_rms, sample_peak, clipped_ratio, duration, finite,
        "rejected" if reason else "accepted", reason,
    )


def calculate_chunks(
    duration_seconds: float,
    max_chunk_seconds: float,
    crossfade_seconds: float = 0.1,
) -> tuple[ChunkWindow, ...]:
    """Split a timeline; adjacent source segments overlap for a short crossfade."""
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("Video duration must be finite and greater than zero.")
    if not math.isfinite(max_chunk_seconds) or max_chunk_seconds <= 0:
        raise ValueError("Maximum chunk duration must be finite and greater than zero.")
    if not math.isfinite(crossfade_seconds) or crossfade_seconds < 0:
        raise ValueError("Crossfade duration must be finite and non-negative.")
    if duration_seconds < MIN_SYNCHFORMER_SECONDS:
        raise ValueError(
            f"Video is shorter than MMAudio's minimum sync window ({MIN_SYNCHFORMER_SECONDS:.2f}s)."
        )
    core_size = max_chunk_seconds - crossfade_seconds
    if core_size <= 0:
        raise ValueError("Maximum chunk duration must exceed the crossfade duration.")
    count = math.ceil(duration_seconds / core_size)
    # Keep the requested maximum while avoiding a tiny last remainder that is
    # shorter than the Synchformer window (16 frames at 25 fps).
    core_size = duration_seconds / count
    windows = []
    for index in range(count):
        core_start = index * core_size
        core_end = duration_seconds if index == count - 1 else (index + 1) * core_size
        source_start = core_start
        source_end = min(duration_seconds, core_end + (crossfade_seconds if index < count - 1 else 0))
        windows.append(ChunkWindow(index, core_start, core_end, source_start, source_end))
    return tuple(windows)


def assign_events_to_chunks(
    events: Sequence[FoleyEvent], chunks: Sequence[ChunkWindow]
) -> tuple[tuple[FoleyEvent, ...], ...]:
    """Assign overlapping events with timestamps clipped to each core interval."""
    assigned = []
    for chunk in chunks:
        chunk_events = []
        for event in events:
            start = event.timestamp_start
            end = event.timestamp_end if event.timestamp_end is not None else start
            if start is None:
                chunk_events.append(event)
                continue
            if end is None:
                end = start
            if end == start:
                in_chunk = chunk.core_start <= start < chunk.core_end or (
                    chunk.index == len(chunks) - 1 and start == chunk.core_end
                )
                if in_chunk:
                    chunk_events.append(event)
                continue
            if end <= chunk.core_start or start >= chunk.core_end:
                continue
            clipped_start = max(start, chunk.core_start)
            clipped_end = min(end, chunk.core_end)
            chunk_events.append(replace(event, timestamp_start=clipped_start, timestamp_end=clipped_end))
        assigned.append(tuple(chunk_events))
    return tuple(assigned)


def build_chunk_prompt(
    context: NormalizedFoleyContext,
    events: Sequence[FoleyEvent],
    prompt_engine: Any,
    *,
    prompt_override: str | None = None,
    negative_prompt: str = "music, speech",
) -> tuple[str, str]:
    """Build a chunk prompt while retaining free-form event sound descriptions."""
    chunk_context = replace(context, events=tuple(events))
    built = prompt_engine.build(
        chunk_context, prompt_override=prompt_override, negative_prompt=negative_prompt
    )
    prompt = built.prompt
    clauses: list[str] = []
    if prompt_override and events:
        for event in events:
            sound = event.potential_sound if event.potential_sound != "unknown" else event.action
            cue = f"{event.action}: {sound}"
            if cue.casefold() not in prompt.casefold():
                clauses.append(cue)
    if prompt_override:
        clauses.extend(built.sound_plan.ambience)
    if prompt_override:
        # The override remains the user's lead instruction; add only scene-supported
        # event cues not already covered by it, so later chunks keep their context.
        prompt = prompt_override.strip()
    elif events:
        cues = []
        for event in events:
            sound = event.potential_sound if event.potential_sound != "unknown" else event.action
            cue = f"{event.action}: {sound}"
            if cue.casefold() not in prompt.casefold():
                cues.append(cue)
        clauses.extend(cues[:3])
    elif context.scene_summary.strip():
        prompt = (
            "Quiet, sparse natural ambience matching this visual scene: "
            f"{context.scene_summary.strip()}. Clear Foley detail, no narration."
        )
    if clauses:
        additions = []
        existing_words = set(prompt.casefold().replace(";", " ").replace(",", " ").split())
        for clause in clauses[:3]:
            tokens = [word.strip(".,:;()") for word in clause.casefold().split()]
            tokens = [word for word in tokens if len(word) > 3]
            overlap = sum(word in existing_words for word in tokens) / max(len(tokens), 1)
            if overlap < 0.7 and clause not in additions:
                additions.append(clause)
        if additions:
            prompt = f"{prompt.rstrip('.; ')}; scene cues: {'; '.join(additions)}."
    return prompt, built.negative_prompt


def merge_waveforms(
    waveforms: Sequence[Any],
    chunks: Sequence[ChunkWindow],
    sample_rate: int,
    target_duration: float,
    crossfade_seconds: float = 0.1,
):
    """Crossfade overlapping generated waveforms, then enforce exact timeline length."""
    import torch

    if not waveforms or len(waveforms) != len(chunks):
        raise ChunkGenerationError("Every expected chunk must have one generated waveform.")
    expected = [round((chunk.source_end - chunk.source_start) * sample_rate) for chunk in chunks]
    fitted_waveforms = []
    for index, (waveform, frames) in enumerate(zip(waveforms, expected)):
        if waveform.ndim != 2 or waveform.shape[1] <= 0:
            raise ChunkGenerationError(f"Generated audio chunk {index + 1} is empty or malformed.")
        difference = waveform.shape[1] - frames
        if difference < -round(0.05 * sample_rate):
            raise ChunkGenerationError(
                f"Generated audio chunk {index + 1} is short by {-difference / sample_rate:.3f}s."
            )
        waveform = waveform[:, :frames]
        if waveform.shape[1] < frames:
            waveform = torch.nn.functional.interpolate(
                waveform.unsqueeze(0), size=frames, mode="linear", align_corners=False
            ).squeeze(0)
        fitted_waveforms.append(waveform)
    channels = fitted_waveforms[0].shape[0]
    if any(item.shape[0] != channels for item in fitted_waveforms):
        raise ChunkGenerationError("Generated audio chunks have inconsistent channel counts.")
    result = fitted_waveforms[0]
    for index in range(1, len(fitted_waveforms)):
        if fitted_waveforms[index].shape[1] != expected[index]:
            raise ChunkGenerationError(f"Generated audio chunk {index + 1} has an invalid frame count.")
        overlap = min(
            round(crossfade_seconds * sample_rate),
            result.shape[1],
            fitted_waveforms[index].shape[1],
            round(max(0.0, chunks[index - 1].source_end - chunks[index].source_start) * sample_rate),
        )
        if overlap:
            left = torch.linspace(1.0, 0.0, overlap, dtype=result.dtype, device=result.device).unsqueeze(0)
            right = 1.0 - left
            blended = result[:, -overlap:] * left + fitted_waveforms[index][:, :overlap] * right
            result = torch.cat((result[:, :-overlap], blended, fitted_waveforms[index][:, overlap:]), dim=1)
        else:
            result = torch.cat((result, fitted_waveforms[index]), dim=1)
    target_frames = round(target_duration * sample_rate)
    mismatch = target_frames - result.shape[1]
    if abs(mismatch) > max(2, round(0.05 * sample_rate)):
        raise ChunkGenerationError(
            f"Assembled audio differs from video duration by {abs(mismatch) / sample_rate:.3f}s."
        )
    if mismatch:
        # Tiny duration discrepancies are corrected by resampling the full signal,
        # never by appending silence or repeating the last sample.
        result = torch.nn.functional.interpolate(
            result.unsqueeze(0), size=target_frames, mode="linear", align_corners=False
        ).squeeze(0)
    return result


def generate_chunked(
    video_path: str | Path,
    context: NormalizedFoleyContext,
    prompt_engine: Any,
    service: Any,
    audio_processor: Any,
    output_path: str | Path,
    *,
    video_duration: float,
    max_chunk_seconds: float,
    prompt_override: str | None = None,
    negative_prompt: str = "music, speech",
    num_steps: int | None = None,
    guidance_scale: float | None = None,
    crossfade_seconds: float = 0.1,
    ffmpeg_executable: str = "ffmpeg",
    quality_policy: ChunkQualityPolicy = ChunkQualityPolicy(),
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ChunkedGenerationResult:
    """Extract video chunks, generate sequentially, and write a full-length track."""
    import torchaudio

    executable = shutil.which(ffmpeg_executable)
    if executable is None:
        raise ChunkGenerationError("FFmpeg is required to prepare video chunks but was not found on PATH.")
    chunks = calculate_chunks(video_duration, max_chunk_seconds, crossfade_seconds)
    event_groups = assign_events_to_chunks(context.events, chunks)
    source_video = Path(video_path).resolve()
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    generated: list[GenerationResult] = []
    waveforms = []
    chunk_reports: list[dict[str, Any]] = []
    for chunk, events in zip(chunks, event_groups):
        if should_cancel and should_cancel():
            raise ChunkGenerationCancelled(f"Cancellation requested before chunk {chunk.index + 1}.")
        prompt, effective_negative_prompt = build_chunk_prompt(
            context,
            events,
            prompt_engine,
            prompt_override=prompt_override,
            negative_prompt=negative_prompt,
        )
        segment_path = destination.parent / f".foley-video-chunk-{chunk.index:04d}.mp4"
        audio_path = destination.parent / f".foley-audio-chunk-{chunk.index:04d}.flac"
        expected_duration = chunk.source_end - chunk.source_start
        continuous_required = any(
            event.rhythm.casefold() in _CONTINUOUS_RHYTHMS for event in events
        )
        report: dict[str, Any] = {
            "chunk_index": chunk.index + 1,
            "core_start": chunk.core_start,
            "core_end": chunk.core_end,
            "duration_requested_seconds": expected_duration,
            "prompt": prompt,
            "continuous_ambience_required": continuous_required,
            "status": "pending",
            "attempts": [],
            "retry_count": 0,
        }
        command = [
            executable, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-ss", f"{chunk.source_start:.6f}", "-i", str(source_video),
            "-t", f"{chunk.source_end - chunk.source_start:.6f}", "-an",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(segment_path),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            if completed.returncode or not segment_path.is_file() or segment_path.stat().st_size == 0:
                raise ChunkGenerationError(
                    f"Could not prepare video chunk {chunk.index + 1}: {completed.stderr.strip()}"
                )
            attempt_limit = 1 + (quality_policy.maximum_retries if continuous_required else 0)
            attempted_seeds: set[int] = set()
            accepted_generation = None
            accepted_waveform = None
            accepted_sample_rate = None
            diagnostics_dir = destination.parent / "chunk_diagnostics"
            for attempt_index in range(attempt_limit):
                if should_cancel and should_cancel():
                    raise ChunkGenerationCancelled(
                        f"Cancellation requested before chunk {chunk.index + 1} attempt {attempt_index + 1}."
                    )
                seed = -1 if attempt_index == 0 else secrets.randbelow(2**31 - 1)
                while seed in attempted_seeds:
                    seed = secrets.randbelow(2**31 - 1)
                attempted_seeds.add(seed)
                attempt_record: dict[str, Any] = {"attempt": attempt_index + 1, "seed": seed}
                _emit_chunk_progress(progress_callback, {
                    "chunk_index": chunk.index + 1, "chunk_total": len(chunks),
                    "attempt": attempt_index + 1, "attempt_limit": attempt_limit,
                    "status": "generating", "metrics": None,
                })
                audio_path.unlink(missing_ok=True)
                try:
                    generation = service.generate(
                        segment_path, prompt, audio_path, negative_prompt=effective_negative_prompt,
                        duration=expected_duration, num_steps=num_steps,
                        guidance_scale=guidance_scale, seed=seed,
                    )
                    if should_cancel and should_cancel():
                        attempt_record["status"] = "cancelled"
                        attempt_record["reason"] = "cancellation requested during inference; inference returned"
                        raise ChunkGenerationCancelled(
                            f"Cancellation requested after chunk {chunk.index + 1} inference returned."
                        )
                    if not audio_path.is_file() or audio_path.stat().st_size == 0:
                        raise ChunkGenerationError("MMAudio did not create a nonempty audio file.")
                    waveform, sample_rate = torchaudio.load(str(audio_path))
                    if generated and sample_rate != generated[0].sample_rate:
                        raise ChunkGenerationError("MMAudio returned inconsistent sample rates across chunks.")
                    metrics = inspect_chunk_waveform(
                        waveform, sample_rate, expected_duration,
                        continuous_required=continuous_required, policy=quality_policy,
                    )
                    attempt_record["metrics"] = metrics.to_dict()
                    attempt_record["status"] = metrics.status
                    _emit_chunk_progress(progress_callback, {
                        "chunk_index": chunk.index + 1, "chunk_total": len(chunks),
                        "attempt": attempt_index + 1, "attempt_limit": attempt_limit,
                        "status": metrics.status, "metrics": metrics.to_dict(),
                    })
                    if metrics.status == "accepted":
                        accepted_generation = generation
                        accepted_waveform = waveform.cpu()
                        accepted_sample_rate = sample_rate
                        report["accepted_attempt"] = attempt_index + 1
                        break
                    attempt_record["reason"] = metrics.reason
                except Exception as exc:
                    if isinstance(exc, ChunkGenerationCancelled):
                        raise
                    attempt_record["status"] = "error"
                    root_cause = exc
                    while root_cause.__cause__ is not None:
                        root_cause = root_cause.__cause__
                    detail = f"{type(exc).__name__}: {exc}"
                    if root_cause is not exc and str(root_cause):
                        detail += f" (root cause: {type(root_cause).__name__}: {root_cause})"
                    attempt_record["reason"] = detail
                finally:
                    if attempt_record.get("status") != "accepted" and audio_path.is_file() and audio_path.stat().st_size:
                        diagnostics_dir.mkdir(parents=True, exist_ok=True)
                        diagnostic_path = diagnostics_dir / (
                            f"chunk_{chunk.index + 1:04d}_attempt_{attempt_index + 1:02d}.flac"
                        )
                        shutil.copy2(audio_path, diagnostic_path)
                        attempt_record["diagnostic_audio_path"] = str(diagnostic_path)
                    report["attempts"].append(attempt_record)
                if attempt_index + 1 < attempt_limit:
                    report["retry_count"] += 1
            if accepted_generation is None or accepted_waveform is None or accepted_sample_rate is None:
                report["status"] = "failed"
                chunk_reports.append(report)
                attempt_details = "; ".join(
                    f"attempt {item['attempt']}: {item.get('reason', 'rejected')}"
                    + (f", metrics={item['metrics']}" if "metrics" in item else "")
                    for item in report["attempts"]
                )
                diagnostic_detail = (
                    f"Rejected audio was retained in {diagnostics_dir}."
                    if diagnostics_dir.is_dir()
                    else "No rejected audio artifact was produced for diagnostics."
                )
                raise ChunkGenerationError(
                    f"chunk {chunk.index + 1}/{len(chunks)} failed quality validation after "
                    f"{len(report['attempts'])} attempt(s); continuous ambience required="
                    f"{continuous_required}; {attempt_details}. {diagnostic_detail}"
                )
            report["status"] = "accepted"
            chunk_reports.append(report)
            waveforms.append(accepted_waveform)
            generated.append(accepted_generation)
            _emit_chunk_progress(progress_callback, {
                "chunk_index": chunk.index + 1, "chunk_total": len(chunks),
                "attempt": report["accepted_attempt"], "attempt_limit": attempt_limit,
                "status": "accepted", "metrics": report["attempts"][-1].get("metrics"),
            })
        except Exception as exc:
            if isinstance(exc, ChunkGenerationCancelled):
                raise
            cause = exc
            while cause.__cause__ is not None:
                cause = cause.__cause__
            detail = str(exc)
            if cause is not exc and str(cause) and str(cause) not in detail:
                detail = f"{detail} (root cause: {type(cause).__name__}: {cause})"
            raise ChunkGenerationError(
                f"Foley generation failed for chunk {chunk.index + 1}/{len(chunks)}: {detail}"
            ) from exc
        finally:
            segment_path.unlink(missing_ok=True)
            audio_path.unlink(missing_ok=True)
    sample_rate = generated[0].sample_rate
    merged = merge_waveforms(waveforms, chunks, sample_rate, video_duration, crossfade_seconds)
    torchaudio.save(str(destination), merged, sample_rate)
    inspection = audio_processor.inspect(destination)
    if abs(inspection.duration_seconds - video_duration) > 1 / sample_rate:
        raise ChunkGenerationError("Merged Foley duration does not match the source video duration.")
    peak = max((item.peak_cuda_memory_bytes or 0) for item in generated) or None
    total_time = sum(item.inference_seconds for item in generated)
    combined = replace(generated[0], audio_path=destination, duration_seconds=inspection.duration_seconds,
                       inference_seconds=total_time, peak_cuda_memory_bytes=peak)
    return ChunkedGenerationResult(combined, chunks, tuple(generated), tuple(chunk_reports))


def _emit_chunk_progress(callback: Callable[[dict[str, Any]], None] | None, payload: dict[str, Any]) -> None:
    if callback is None:
        return
    try:
        callback(payload)
    except Exception:
        logging.getLogger(__name__).exception("Chunk progress callback failed.")
