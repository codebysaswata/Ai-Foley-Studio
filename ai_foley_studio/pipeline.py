"""Programmatic and CLI entry point for the post-analysis Foley workflow."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from ai_foley_studio.audio.audio_processor import AudioInspection, AudioProcessor
from ai_foley_studio.audio.chunked_generation import (
    ChunkGenerationCancelled,
    ChunkQualityPolicy,
    generate_chunked,
)
from ai_foley_studio.audio.mmaudio_service import GenerationResult, MMAudioService
from ai_foley_studio.audio.synchronizer import AudioSynchronizer, VideoInspection, inspect_video
from ai_foley_studio.config import FoleySettings, SUPPORTED_VIDEO_EXTENSIONS, get_settings
from ai_foley_studio.export.video_exporter import ExportResult, VideoExporter
from ai_foley_studio.intelligence.context_engine import ContextEngine, NormalizedFoleyContext
from ai_foley_studio.intelligence.prompt_engine import PromptBuildResult, PromptEngine


class PipelineError(RuntimeError):
    """The orchestrated Foley workflow could not reach a valid output."""


class PipelineCancelled(PipelineError):
    """A running pipeline observed a cooperative cancellation request."""


@dataclass(frozen=True)
class PipelineConfig:
    """User-configurable settings for one isolated Foley job."""

    output_dir: Path | None = None
    prompt_override: str | None = None
    negative_prompt: str = "music, speech"
    duration: float | None = None
    num_steps: int | None = None
    guidance_scale: float | None = None
    timing_offset_seconds: float = 0.0
    target_lufs: float | None = None
    true_peak_limit: float = -1.5
    export_video: bool = False
    chunk_quality: ChunkQualityPolicy = field(default_factory=ChunkQualityPolicy)


@dataclass(frozen=True)
class PipelineResult:
    """Paths and verified artifacts from a completed Foley job."""

    job_id: str
    job_dir: Path
    metadata_path: Path
    prompt: str
    raw_audio_path: Path
    processed_audio_path: Path
    final_video_path: Path | None
    generation: GenerationResult
    raw_audio: AudioInspection
    processed_audio: AudioInspection
    source_video: VideoInspection
    export: ExportResult | None


@dataclass
class _JobState:
    job_id: str
    job_dir: Path
    metadata_path: Path
    video_path: Path
    scene_analysis_path: Path
    sound_context_path: Path
    stages: list[dict[str, Any]] = field(default_factory=list)


class FoleyPipeline:
    """Coordinate JSON context, MMAudio, processing, and optional MP4 export."""

    def __init__(
        self,
        settings: FoleySettings | None = None,
        *,
        context_engine: ContextEngine | None = None,
        prompt_engine: PromptEngine | None = None,
        mmaudio_service: MMAudioService | None = None,
        audio_processor: AudioProcessor | None = None,
        video_exporter: VideoExporter | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.context_engine = context_engine or ContextEngine()
        self.prompt_engine = prompt_engine or PromptEngine()
        self.mmaudio_service = mmaudio_service or MMAudioService(self.settings)
        self.audio_processor = audio_processor or AudioProcessor()
        self.synchronizer = AudioSynchronizer(self.audio_processor)
        self.video_exporter = video_exporter or VideoExporter()

    def close(self) -> None:
        """Release the retained MMAudio model after a UI/CLI job boundary."""
        self.mmaudio_service.close()

    def run(
        self,
        video_path: str | Path,
        scene_analysis_path: str | Path,
        sound_context_path: str | Path,
        config: PipelineConfig | None = None,
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> PipelineResult:
        """Run one non-overlapping job and persist diagnostics in ``metadata.json``."""
        config = config or PipelineConfig()
        self._validate_config(config)
        state = self._new_job(video_path, scene_analysis_path, sound_context_path, config)
        logger = self._job_logger(state)

        def report(stage: str, progress: float, **details: Any) -> None:
            if progress_callback is not None:
                try:
                    progress_callback({"stage": stage, "progress": progress, **details})
                except Exception:
                    logger.exception("Progress callback failed.")

        def check_cancelled() -> None:
            if should_cancel is not None and should_cancel():
                raise PipelineCancelled("Cancellation requested by the client.")

        try:
            self._ensure_space(state, config)
            check_cancelled()
            report("inspecting_video", 2.0)
            source_video = self._stage(state, logger, "inspect_video", lambda: inspect_video(state.video_path))
            check_cancelled()
            report("loading_context", 6.0)
            context = self._stage(
                state,
                logger,
                "load_context",
                lambda: self.context_engine.load(
                    state.scene_analysis_path,
                    state.sound_context_path,
                    video_path=state.video_path,
                    video_duration_seconds=source_video.duration_seconds,
                ),
            )
            check_cancelled()
            self._validate_context_timestamps(context, source_video)
            report("building_prompt", 10.0)
            prompt_result = self._stage(
                state,
                logger,
                "build_prompt",
                lambda: self.prompt_engine.build(
                    context,
                    prompt_override=config.prompt_override,
                    negative_prompt=config.negative_prompt,
                ),
            )
            check_cancelled()
            chunk_duration = min(config.duration or self.settings.default_generation_duration,
                                 self.settings.max_generation_duration)
            raw_audio_path = state.job_dir / "generated_foley.flac"

            def chunk_progress(event: dict[str, Any]) -> None:
                current = int(event.get("chunk_index", 0))
                total = max(1, int(event.get("chunk_total", 1)))
                fraction = (current - 1 + (1.0 if event.get("status") == "accepted" else 0.35)) / total
                report(
                    "generating_audio", min(82.0, 15.0 + 67.0 * fraction),
                    current_chunk=current, total_chunks=total,
                    attempt=event.get("attempt"), attempt_limit=event.get("attempt_limit"),
                    chunk_status=event.get("status"), chunk_metrics=event.get("metrics"),
                )

            report("generating_audio", 15.0, current_chunk=0, total_chunks=None)
            chunked_generation = self._stage(
                state,
                logger,
                "generate_chunked_mmaudio",
                lambda: generate_chunked(
                    state.video_path,
                    context,
                    self.prompt_engine,
                    self.mmaudio_service,
                    self.audio_processor,
                    raw_audio_path,
                    video_duration=source_video.duration_seconds,
                    max_chunk_seconds=chunk_duration,
                    prompt_override=config.prompt_override,
                    negative_prompt=prompt_result.negative_prompt,
                    num_steps=config.num_steps,
                    guidance_scale=config.guidance_scale,
                    quality_policy=config.chunk_quality,
                    progress_callback=chunk_progress,
                    should_cancel=should_cancel,
                ),
            )
            check_cancelled()
            generation = chunked_generation.generation
            logger.info("generated_chunks=%d", len(chunked_generation.chunks))
            report("synchronizing_audio", 84.0)
            raw_inspection = self._stage(
                state, logger, "inspect_raw_audio", lambda: self.audio_processor.inspect(generation.audio_path)
            )
            if raw_inspection.is_silent:
                raise PipelineError("MMAudio produced an unexpectedly silent raw waveform.")
            check_cancelled()
            report("processing_audio", 88.0)
            staged_audio = state.job_dir / "timed_foley.wav"
            synchronized = self._stage(
                state,
                logger,
                "synchronize_audio",
                lambda: self.synchronizer.synchronize(
                    state.video_path,
                    generation.audio_path,
                    staged_audio,
                    timing_offset_seconds=config.timing_offset_seconds,
                    duration_policy="match_video",
                ),
            )
            processed_audio_path = state.job_dir / "processed_foley.wav"
            if config.target_lufs is None:
                processed_audio = self._stage(
                    state,
                    logger,
                    "convert_processed_audio",
                    lambda: self.audio_processor.convert(synchronized.audio.path, processed_audio_path),
                )
            else:
                processed_audio = self._stage(
                    state,
                    logger,
                    "normalize_loudness",
                    lambda: self.audio_processor.normalize_loudness(
                        synchronized.audio.path,
                        processed_audio_path,
                        target_lufs=config.target_lufs,
                        true_peak_limit=config.true_peak_limit,
                    ),
                )
            if staged_audio.exists():
                staged_audio.unlink()
            final_video: ExportResult | None = None
            if config.export_video:
                check_cancelled()
                report("exporting_video", 94.0)
                final_video = self._stage(
                    state,
                    logger,
                    "export_video",
                    lambda: self.video_exporter.export(
                        state.video_path, processed_audio.path, state.job_dir / "final_video.mp4"
                    ),
                )
            check_cancelled()
            self._write_metadata(
                state,
                status="completed",
                config=config,
                context=context,
                prompt=prompt_result,
                source_video=source_video,
                generation=generation,
                chunk_generation=chunked_generation,
                raw_audio=raw_inspection,
                processed_audio=processed_audio,
                export=final_video,
            )
            report("completed", 100.0)
            return PipelineResult(
                job_id=state.job_id,
                job_dir=state.job_dir,
                metadata_path=state.metadata_path,
                prompt=prompt_result.prompt,
                raw_audio_path=generation.audio_path,
                processed_audio_path=processed_audio.path,
                final_video_path=final_video.output_path if final_video else None,
                generation=generation,
                raw_audio=raw_inspection,
                processed_audio=processed_audio,
                source_video=source_video,
                export=final_video,
            )
        except Exception as exc:
            logger.exception("Foley pipeline failed: %s", exc)
            self._write_metadata(
                state,
                status="cancelled" if isinstance(exc, (PipelineCancelled, ChunkGenerationCancelled)) else "failed",
                config=config,
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            raise
        finally:
            self._close_job_logger(logger)

    def _new_job(
        self,
        video_path: str | Path,
        scene_analysis_path: str | Path,
        sound_context_path: str | Path,
        config: PipelineConfig,
    ) -> _JobState:
        video = self._require_file(video_path, "video")
        if video.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
            raise PipelineError(
                f"Unsupported video extension {video.suffix!r}; choose one of {sorted(SUPPORTED_VIDEO_EXTENSIONS)}."
            )
        scene = self._require_file(scene_analysis_path, "scene_analysis")
        sound = self._require_file(sound_context_path, "sound_context")
        root = (config.output_dir or self.settings.output_dir).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        job_id = f"job_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        job_dir = root / job_id
        job_dir.mkdir(parents=False, exist_ok=False)
        (job_dir / "logs").mkdir()
        return _JobState(
            job_id=job_id,
            job_dir=job_dir,
            metadata_path=job_dir / "metadata.json",
            video_path=video,
            scene_analysis_path=scene,
            sound_context_path=sound,
        )

    @staticmethod
    def _require_file(path: str | Path, label: str) -> Path:
        candidate = Path(path).expanduser().resolve()
        if not candidate.is_file() or candidate.stat().st_size == 0:
            raise PipelineError(f"{label} path does not exist, is not a file, or is empty: {candidate}")
        return candidate

    def _validate_config(self, config: PipelineConfig) -> None:
        """Reject invalid settings before creating a job directory or loading a model."""
        if config.duration is not None and not 0 < config.duration <= self.settings.max_generation_duration:
            raise PipelineError(
                f"duration must be in (0, {self.settings.max_generation_duration}] seconds; got {config.duration}."
            )
        if config.num_steps is not None and config.num_steps <= 0:
            raise PipelineError("num_steps must be greater than zero.")
        if config.guidance_scale is not None and config.guidance_scale <= 0:
            raise PipelineError("guidance_scale must be greater than zero.")
        if config.target_lufs is not None and not isinstance(config.target_lufs, (int, float)):
            raise PipelineError("target_lufs must be numeric when provided.")

    def _ensure_space(self, state: _JobState, config: PipelineConfig) -> None:
        free = shutil.disk_usage(state.job_dir).free
        minimum = max(state.video_path.stat().st_size * 2, 100 * 1024 * 1024)
        if free < minimum:
            raise PipelineError(
                f"Insufficient free disk space for a Foley job: {free} bytes available, {minimum} required."
            )

    @staticmethod
    def _validate_context_timestamps(context: NormalizedFoleyContext, video: VideoInspection) -> None:
        for event in context.events:
            for label, timestamp in (("timestamp_start", event.timestamp_start), ("timestamp_end", event.timestamp_end)):
                if timestamp is not None and timestamp > video.duration_seconds + 0.25:
                    raise PipelineError(
                        f"Context event {label}={timestamp:.3f}s exceeds video duration "
                        f"{video.duration_seconds:.3f}s."
                    )

    @staticmethod
    def _stage(state: _JobState, logger: logging.Logger, name: str, operation):
        started = time.time()
        logger.info("stage=%s status=started", name)
        try:
            result = operation()
        except Exception as exc:
            state.stages.append(
                {
                    "name": name,
                    "status": "failed",
                    "started_at_epoch": started,
                    "finished_at_epoch": time.time(),
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                }
            )
            raise
        state.stages.append(
            {
                "name": name,
                "status": "completed",
                "started_at_epoch": started,
                "finished_at_epoch": time.time(),
            }
        )
        logger.info("stage=%s status=completed", name)
        return result

    def _write_metadata(self, state: _JobState, *, status: str, config: PipelineConfig, **values: Any) -> None:
        def serialise(value: Any) -> Any:
            if isinstance(value, Path):
                return str(value)
            if hasattr(value, "to_dict"):
                return value.to_dict()
            if hasattr(value, "__dataclass_fields__"):
                return {key: serialise(item) for key, item in asdict(value).items()}
            if isinstance(value, dict):
                return {str(key): serialise(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [serialise(item) for item in value]
            return value

        document = {
            "job_id": state.job_id,
            "status": status,
            "original_video_path": str(state.video_path),
            "scene_analysis_path": str(state.scene_analysis_path),
            "sound_context_path": str(state.sound_context_path),
            "config": serialise(config),
            "stages": state.stages,
            "artifacts": serialise(values),
        }
        state.metadata_path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _job_logger(state: _JobState) -> logging.Logger:
        logger = logging.getLogger(f"ai_foley_studio.job.{state.job_id}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = logging.FileHandler(state.job_dir / "logs" / "pipeline.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        return logger

    @staticmethod
    def _close_job_logger(logger: logging.Logger) -> None:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Foley audio from video analysis JSON artifacts.")
    parser.add_argument("--video", required=True, help="Original source video path")
    parser.add_argument("--scene-json", required=True, help="scene_analysis.json path")
    parser.add_argument("--sound-json", required=True, help="sound_context.json path")
    parser.add_argument("--output-dir", help="Root directory for unique job outputs")
    parser.add_argument("--prompt-override", help="Replace generated MMAudio prompt")
    parser.add_argument("--duration", type=float, help="Maximum duration of each MMAudio chunk in seconds")
    parser.add_argument("--num-steps", type=int, help="MMAudio Euler sampling steps")
    parser.add_argument("--guidance-scale", type=float, help="MMAudio classifier-free guidance scale")
    parser.add_argument("--timing-offset", type=float, default=0.0, help="Positive delays audio; negative advances it")
    parser.add_argument("--target-lufs", type=float, help="Apply FFmpeg loudnorm target LUFS")
    parser.add_argument("--true-peak-limit", type=float, default=-1.5, help="True-peak limit in dBTP")
    parser.add_argument("--chunk-max-retries", type=int, default=2, help="Maximum retries for a failed continuous-ambience chunk")
    parser.add_argument("--chunk-min-interior-rms", type=float, default=0.001, help="Minimum interior RMS for required continuous ambience")
    parser.add_argument("--chunk-max-clipped-ratio", type=float, default=0.0001, help="Maximum allowed full-scale sample ratio")
    parser.add_argument("--chunk-boundary-exclusion", type=float, default=0.15, help="Seconds excluded from each chunk edge for RMS validation")
    parser.add_argument("--export-video", action="store_true", help="Mux processed Foley into a final MP4")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the pipeline CLI and print a JSON summary suitable for PowerShell."""
    args = _parse_args(argv)
    config = PipelineConfig(
        output_dir=Path(args.output_dir) if args.output_dir else None,
        prompt_override=args.prompt_override,
        duration=args.duration,
        num_steps=args.num_steps,
        guidance_scale=args.guidance_scale,
        timing_offset_seconds=args.timing_offset,
        target_lufs=args.target_lufs,
        true_peak_limit=args.true_peak_limit,
        export_video=args.export_video,
        chunk_quality=ChunkQualityPolicy(
            maximum_retries=args.chunk_max_retries,
            minimum_continuous_interior_rms=args.chunk_min_interior_rms,
            maximum_clipped_sample_ratio=args.chunk_max_clipped_ratio,
            boundary_exclusion_seconds=args.chunk_boundary_exclusion,
        ),
    )
    pipeline = FoleyPipeline()
    try:
        result = pipeline.run(args.video, args.scene_json, args.sound_json, config)
    except Exception as exc:
        print(f"Pipeline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        # Release retained MMAudio model objects on both success and failure.
        pipeline.close()
    print(
        json.dumps(
            {
                "job_id": result.job_id,
                "raw_audio_path": str(result.raw_audio_path),
                "processed_audio_path": str(result.processed_audio_path),
                "final_video_path": str(result.final_video_path) if result.final_video_path else None,
                "metadata_path": str(result.metadata_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
