"""Persistent single-worker job lifecycle for one local inference GPU."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import mimetypes
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from ai_foley_studio.api.errors import ApiError
from ai_foley_studio.api.schemas import ErrorCode, JobOptions
from ai_foley_studio.api.settings import ApiSettings
from ai_foley_studio.api.storage import JobStorage, SingleProcessLock, StorageError
from ai_foley_studio.api.store import JobStore
from ai_foley_studio.config import FoleySettings
from ai_foley_studio.intelligence.context_engine import generate_context_output
from ai_foley_studio.pipeline import FoleyPipeline, PipelineCancelled, PipelineConfig


log = logging.getLogger("ai_foley_studio.api.jobs")
_STOP = object()


class JobManager:
    def __init__(
        self,
        settings: ApiSettings,
        *,
        pipeline_factory: Any = None,
    ) -> None:
        self.settings = settings
        self.storage = JobStorage(settings)
        self.store = JobStore(settings.database_path)
        self.pipeline_factory = pipeline_factory or (lambda: FoleyPipeline(FoleySettings()))
        self.pipeline: Any = None
        self.queue: asyncio.Queue[str | object] | None = None
        self.worker_task: asyncio.Task[None] | None = None
        self.lock = SingleProcessLock(settings.lock_path)
        self.accepting_jobs = False
        self.worker_online = False
        self.start_error: str | None = None

    async def start(self) -> None:
        self.settings.validate()
        self.lock.acquire()
        try:
            await asyncio.to_thread(self.storage.initialize)
            await asyncio.to_thread(self.store.initialize)
            await asyncio.to_thread(self.storage.remove_expired, self.store)
            queued = await asyncio.to_thread(self.store.reconcile_after_restart)
            self.pipeline = self.pipeline_factory()
            self.queue = asyncio.Queue(maxsize=self.settings.max_queued_jobs)
            for job_id in queued:
                root = self.storage.registered_job_dir(job_id)
                row = await asyncio.to_thread(self.store.get, job_id)
                if root is None or row is None or not Path(row["video_path"]).is_file():
                    await asyncio.to_thread(
                        self.store.fail_queued, job_id, ErrorCode.WORKER_UNAVAILABLE.value,
                        "Queued job files are unavailable after service restart.",
                    )
                    continue
                if self.queue.full():
                    await asyncio.to_thread(
                        self.store.fail_queued, job_id, ErrorCode.QUEUE_FULL.value,
                        "Queued job could not be restored within the configured queue capacity.",
                    )
                    continue
                self.queue.put_nowait(job_id)
            self.worker_online = True
            self.accepting_jobs = True
            self.worker_task = asyncio.create_task(self._worker_loop(), name="ai-foley-gpu-worker")
            log.info("event=worker_started restored_queue=%d queue_limit=%d", self.queue.qsize(), self.settings.max_queued_jobs)
        except Exception:
            self.lock.release()
            raise

    async def stop(self) -> None:
        self.accepting_jobs = False
        if self.queue is not None and self.worker_task is not None and not self.worker_task.done():
            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                    self.queue.task_done()
                except asyncio.QueueEmpty:
                    break
            self.queue.put_nowait(_STOP)
            await self.worker_task
        self.worker_online = False
        if self.pipeline is not None:
            try:
                await asyncio.to_thread(self.pipeline.close)
            except Exception:
                log.exception("event=pipeline_close_failed")
            self.pipeline = None
        self.lock.release()

    async def submit(self, record: dict[str, Any]) -> bool:
        if not self.accepting_jobs or self.queue is None:
            raise ApiError(503, ErrorCode.WORKER_UNAVAILABLE.value, "The background worker is not accepting jobs.")
        created = await asyncio.to_thread(self.store.create, record, self.settings.max_queued_jobs)
        if not created:
            return False
        try:
            self.queue.put_nowait(record["job_id"])
        except asyncio.QueueFull:
            await asyncio.to_thread(
                self.store.fail_queued, record["job_id"], ErrorCode.QUEUE_FULL.value,
                "The service queue filled while registering the job.",
            )
            raise ApiError(429, ErrorCode.QUEUE_FULL.value, "The job queue is full; retry after a job finishes.")
        log.info("event=job_accepted job_id=%s", record["job_id"])
        return True

    async def _worker_loop(self) -> None:
        assert self.queue is not None
        while True:
            item = await self.queue.get()
            try:
                if item is _STOP:
                    return
                job_id = str(item)
                await asyncio.to_thread(self._process_job, job_id)
            except Exception:
                log.exception("event=worker_loop_error")
            finally:
                self.queue.task_done()
                try:
                    await asyncio.to_thread(self.storage.remove_expired, self.store)
                except Exception:
                    log.exception("event=retention_cleanup_failed")

    def _process_job(self, job_id: str) -> None:
        row = self.store.get(job_id)
        if row is None or row["status"] != "queued":
            return
        if row["cancel_requested"]:
            self.store.finish_cancelled(job_id)
            return
        if not self.store.mark_running(job_id):
            return
        root = self.storage.registered_job_dir(job_id)
        if root is None:
            self.store.finish_failed(job_id, ErrorCode.WORKER_UNAVAILABLE.value, "Job storage is unavailable.")
            return
        log.info("event=job_started job_id=%s", job_id)
        try:
            video_path = Path(row["video_path"])
            scene_path = Path(row["scene_path"]) if row.get("scene_path") else root / "metadata" / "scene_analysis.json"
            sound_path = Path(row["sound_path"]) if row.get("sound_path") else root / "metadata" / "sound_context.json"
            if row.get("scene_path") is None:
                self.store.update_progress(job_id, {
                    "stage": "analyzing_scene", "progress": 5,
                    "current_chunk": None, "total_chunks": None,
                })
                self._run_scene_analysis(job_id, video_path, root, scene_path, sound_path)
            if self.store.cancellation_requested(job_id):
                self.store.finish_cancelled(job_id)
                return
            options = JobOptions.model_validate(row["options"])

            def progress(event: dict[str, Any]) -> None:
                self.store.update_progress(job_id, event)

            def should_cancel() -> bool:
                return self.store.cancellation_requested(job_id)

            pipeline_config = PipelineConfig(
                output_dir=root / "output",
                prompt_override=options.prompt_override,
                negative_prompt=options.negative_prompt,
                duration=options.chunk_seconds,
                num_steps=options.num_steps,
                guidance_scale=options.guidance_scale,
                timing_offset_seconds=options.timing_offset_seconds,
                target_lufs=options.target_lufs,
                export_video=options.export_video,
            )
            result = self.pipeline.run(
                video_path, scene_path, sound_path, pipeline_config,
                progress_callback=progress, should_cancel=should_cancel,
            )
            artifacts = self._collect_artifacts(job_id, root, result)
            outcome = self.store.finish_success(job_id, artifacts)
            if outcome == "cancelled":
                log.info("event=job_cancelled_after_pipeline job_id=%s", job_id)
            elif outcome == "succeeded":
                log.info("event=job_succeeded job_id=%s artifact_count=%d", job_id, len(artifacts))
        except PipelineCancelled:
            self.store.finish_cancelled(job_id)
            log.info("event=job_cancelled job_id=%s", job_id)
        except Exception as exc:
            if self.store.cancellation_requested(job_id):
                self.store.finish_cancelled(job_id)
                log.info("event=job_cancelled_after_operation job_id=%s", job_id)
                return
            code, safe_message = _map_failure(exc)
            self.store.finish_failed(job_id, code, safe_message)
            log.exception("event=job_failed job_id=%s code=%s", job_id, code)

    def _run_scene_analysis(
        self, job_id: str, video_path: Path, root: Path, scene_path: Path, sound_path: Path,
    ) -> None:
        from ai_foley_studio.video.processor import extract_frames
        from ai_foley_studio.video.scene_analyzer import analyze_scenes

        frame_dir = root / "working" / "frames"
        samples = extract_frames(
            video_path, interval_seconds=1.0, max_frames=30, resize_width=640, output_dir=frame_dir,
        )
        records = [
            {"timestamp": item.timestamp_seconds, "path": item.image_path}
            for item in samples
        ]
        scene = analyze_scenes(records)
        scene["source_video"] = video_path.name
        scene["video_sha256"] = _sha256_file(video_path)
        sound = generate_context_output(scene)
        scene_path.write_text(json.dumps(scene, indent=2, ensure_ascii=False), encoding="utf-8")
        sound_path.write_text(json.dumps(sound, indent=2, ensure_ascii=False), encoding="utf-8")
        self.store.update_progress(job_id, {
            "stage": "scene_analysis_complete", "progress": 10,
            "current_chunk": None, "total_chunks": None,
        })

    def _collect_artifacts(self, job_id: str, root: Path, result: Any) -> list[dict[str, Any]]:
        produced: list[tuple[str, Path, str, float | None]] = [
            ("processed_foley.wav", Path(result.processed_audio_path), "audio/wav", result.processed_audio.duration_seconds),
        ]
        if result.final_video_path is not None:
            produced.append(("final_video.mp4", Path(result.final_video_path), "video/mp4", result.export.duration_seconds))
        artifacts = []
        for name, path, media_type, duration in produced:
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(f"Expected validated output artifact is missing: {name}")
            relative = self.storage.relative_path(path, job_id)
            artifacts.append({
                "name": name,
                "media_type": media_type,
                "size_bytes": path.stat().st_size,
                "duration_seconds": duration,
                "relative_path": relative,
            })
        return artifacts

    def job_status(self, job_id: str) -> dict[str, Any] | None:
        return self.store.get(job_id)

    def list_jobs(self, *, limit: int, offset: int, status: str | None) -> tuple[list[dict[str, Any]], int]:
        return self.store.list(limit=limit, offset=offset, status=status)

    def request_cancel(self, job_id: str) -> dict[str, Any] | None:
        return self.store.request_cancel(job_id)

    def artifact_path(self, job_id: str, artifact_name: str) -> tuple[Path, dict[str, Any]]:
        row = self.store.get(job_id)
        if row is None:
            raise ApiError(404, ErrorCode.JOB_NOT_FOUND.value, "Job was not found.")
        if row["status"] != "succeeded":
            raise ApiError(409, ErrorCode.JOB_NOT_READY.value, "Artifacts are available only after successful completion.")
        allowed = {"processed_foley.wav", "final_video.mp4"}
        if artifact_name not in allowed:
            raise ApiError(404, ErrorCode.JOB_NOT_FOUND.value, "Artifact was not found.")
        artifact = next((item for item in row["artifacts"] if item["name"] == artifact_name), None)
        if artifact is None:
            raise ApiError(404, ErrorCode.JOB_NOT_FOUND.value, "Artifact is not available for this job.")
        try:
            path = self.storage.artifact_path(job_id, artifact["relative_path"])
        except StorageError as exc:
            raise ApiError(404, ErrorCode.JOB_NOT_FOUND.value, "Artifact is unavailable.") from exc
        return path, artifact

    def readiness(self) -> tuple[bool, dict[str, Any]]:
        checks: dict[str, Any] = {
            "storage": self.settings.data_dir.is_dir(),
            "database": False,
            "worker": self.worker_online,
            "authentication_configured": bool(self.settings.bearer_token),
            "mmaudio_checkpoints": [],
        }
        try:
            self.store.list(limit=1, offset=0)
            checks["database"] = True
        except Exception:
            pass
        if self.pipeline is not None:
            service = getattr(self.pipeline, "mmaudio_service", None)
            try:
                checks["mmaudio_checkpoints"] = [
                    {"purpose": item.purpose, "available": item.nonempty}
                    for item in service.checkpoint_status()
                ]
            except Exception:
                log.exception("event=readiness_checkpoint_probe_failed")
        checkpoint_ready = bool(checks["mmaudio_checkpoints"]) and all(
            item["available"] for item in checks["mmaudio_checkpoints"]
        )
        checks["mmaudio_ready"] = checkpoint_ready
        checks["qwen_model"] = "lazy-loaded when scene analysis is requested"
        ready = all((checks["storage"], checks["database"], checks["worker"], checks["authentication_configured"], checkpoint_ready))
        return ready, checks


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _map_failure(exc: Exception) -> tuple[str, str]:
    detail = f"{type(exc).__name__}: {exc}".casefold()
    if "out of memory" in detail or "cuda oom" in detail:
        return ErrorCode.GPU_OUT_OF_MEMORY.value, "GPU memory was insufficient to process this job."
    if "videoexporterror" in detail or "ffmpeg muxing failed" in detail:
        return ErrorCode.VIDEO_EXPORT_FAILED.value, "Video export failed. Check that FFmpeg and FFprobe are installed and the input is valid."
    if any(name in detail for name in ("chunkgenerationerror", "audiogenerationerror", "mmaudio")):
        return ErrorCode.AUDIO_GENERATION_FAILED.value, "Audio generation failed validation. Diagnostic files were retained with this job."
    if "scene" in detail or "qwen" in detail or "frame" in detail:
        return ErrorCode.WORKER_UNAVAILABLE.value, "Scene analysis could not be completed. Check local Qwen model availability."
    return ErrorCode.INTERNAL_SERVER_ERROR.value, "The job failed unexpectedly. Check the server log for its job ID."
