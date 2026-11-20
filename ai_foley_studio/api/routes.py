"""Versioned REST endpoints for uploads, job status and validated artifacts."""

from __future__ import annotations

import json
import logging
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from ai_foley_studio.api.errors import ApiError
from ai_foley_studio.api.manager import JobManager
from ai_foley_studio.api.media import safe_upload_extension, save_upload_stream, validate_video_media
from ai_foley_studio.api.schemas import (
    ApiErrorBody, ApiErrorResponse, ArtifactListResponse, ArtifactMetadata,
    CancelResponse, ErrorCode, HealthResponse, JobAcceptedResponse, JobListResponse,
    JobOptions, JobStatus, JobStatusResponse, ReadinessResponse,
    SceneAnalysisDocument, SoundContextDocument,
)
from ai_foley_studio.api.security import require_api_token
from ai_foley_studio.intelligence.context_engine import ContextEngine
from ai_foley_studio.audio.synchronizer import inspect_video


log = logging.getLogger("ai_foley_studio.api.http")
router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_token)])


@router.post(
    "/jobs", response_model=JobAcceptedResponse, status_code=202,
    responses={400: {"model": ApiErrorResponse}, 401: {"model": ApiErrorResponse},
               413: {"model": ApiErrorResponse}, 415: {"model": ApiErrorResponse},
               422: {"model": ApiErrorResponse}, 429: {"model": ApiErrorResponse}},
    summary="Upload a video and enqueue Foley generation",
)
async def create_job(
    request: Request,
    video: Annotated[UploadFile, File(description="Required source video upload")],
    scene_analysis: Annotated[UploadFile | None, File(description="Optional scene_analysis.json; provide with sound_context")]=None,
    sound_context: Annotated[UploadFile | None, File(description="Optional sound_context.json; provide with scene_analysis")]=None,
    prompt_override: Annotated[str | None, Form(max_length=1000)] = None,
    negative_prompt: Annotated[str, Form(max_length=500)] = "music, speech",
    chunk_seconds: Annotated[float, Form(ge=0.64, le=8.0)] = 4.0,
    num_steps: Annotated[int, Form(ge=1, le=100)] = 25,
    guidance_scale: Annotated[float, Form(gt=0, le=20)] = 4.5,
    timing_offset_seconds: Annotated[float, Form(ge=-60, le=60)] = 0.0,
    target_lufs: Annotated[float | None, Form(ge=-40, le=0)] = None,
    export_video: Annotated[bool, Form()] = False,
) -> JobAcceptedResponse:
    runtime: JobManager = request.app.state.runtime
    if not runtime.accepting_jobs:
        raise ApiError(503, ErrorCode.WORKER_UNAVAILABLE.value, "The background worker is not ready.")
    if (scene_analysis is None) != (sound_context is None):
        raise ApiError(400, ErrorCode.INVALID_CONTEXT_JSON.value, "Upload both scene_analysis and sound_context JSON files, or upload neither.")
    try:
        options = JobOptions(
            prompt_override=prompt_override, negative_prompt=negative_prompt,
            chunk_seconds=chunk_seconds, num_steps=num_steps, guidance_scale=guidance_scale,
            timing_offset_seconds=timing_offset_seconds, target_lufs=target_lufs,
            export_video=export_video,
        )
    except ValidationError as exc:
        raise ApiError(422, "INVALID_REQUEST", "One or more generation options are outside supported limits.") from exc

    source_ext = safe_upload_extension(video.filename)
    job_id, paths = runtime.storage.create_job()
    pending_video = paths["working"] / f"upload_pending{source_ext}"
    source_path: Path | None = None
    try:
        upload_bytes = await save_upload_stream(video, pending_video, runtime.settings.max_upload_bytes)
        media = await run_in_threadpool(validate_video_media, pending_video, source_ext, runtime.settings)
        source_path = paths["input"] / f"source{media['server_extension']}"
        pending_video.replace(source_path)
        media["size_bytes"] = upload_bytes
        (paths["metadata"] / "media.json").write_text(json.dumps(media, indent=2), encoding="utf-8")

        scene_path = sound_path = None
        if scene_analysis is not None and sound_context is not None:
            scene_raw = await _read_context_upload(scene_analysis, runtime.settings.max_context_bytes)
            sound_raw = await _read_context_upload(sound_context, runtime.settings.max_context_bytes)
            try:
                scene_doc = SceneAnalysisDocument.model_validate_json(scene_raw)
                sound_doc = SoundContextDocument.model_validate_json(sound_raw)
                scene_payload = scene_doc.model_dump(mode="json", exclude_none=False)
                sound_payload = sound_doc.model_dump(mode="json", exclude_none=False)
                _replace_video_references(scene_payload, source_path.name)
                _replace_video_references(sound_payload, source_path.name)
                original_scene = paths["input"] / "scene_analysis.json"
                original_sound = paths["input"] / "sound_context.json"
                original_scene.write_bytes(scene_raw)
                original_sound.write_bytes(sound_raw)
                scene_path = paths["metadata"] / "scene_analysis.json"
                sound_path = paths["metadata"] / "sound_context.json"
                scene_path.write_text(json.dumps(scene_payload, ensure_ascii=False), encoding="utf-8")
                sound_path.write_text(json.dumps(sound_payload, ensure_ascii=False), encoding="utf-8")
                await run_in_threadpool(
                    ContextEngine().load, scene_path, sound_path,
                    video_path=source_path, video_duration_seconds=float(media["duration_seconds"]),
                )
            except ApiError:
                raise
            except Exception as exc:
                raise ApiError(400, ErrorCode.INVALID_CONTEXT_JSON.value, "Scene/context JSON is invalid or does not match the uploaded video.") from exc

        record = {
            "job_id": job_id,
            "job_dir": paths["root"],
            "video_path": source_path,
            "scene_path": scene_path,
            "sound_path": sound_path,
            "options": options.model_dump(mode="json"),
        }
        if not await runtime.submit(record):
            raise ApiError(429, ErrorCode.QUEUE_FULL.value, "The job queue is full; retry after a job finishes.")
    except Exception:
        root = runtime.storage.registered_job_dir(job_id)
        if root is not None:
            import shutil

            shutil.rmtree(root)
        raise
    finally:
        await video.close()
        if scene_analysis is not None:
            await scene_analysis.close()
        if sound_context is not None:
            await sound_context.close()
    row = await run_in_threadpool(runtime.store.get, job_id)
    return JobAcceptedResponse(
        job_id=UUID(job_id), status=JobStatus.queued,
        status_url=f"/api/v1/jobs/{job_id}",
        created_at=datetime.fromisoformat(row["created_at"]),
    )


@router.get("/jobs", response_model=JobListResponse, summary="List recent jobs")
def list_jobs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: JobStatus | None = None,
) -> JobListResponse:
    runtime: JobManager = request.app.state.runtime
    rows, total = runtime.list_jobs(limit=limit, offset=offset, status=status.value if status else None)
    return JobListResponse(
        items=[_public_job(row) for row in rows], limit=limit, offset=offset, total=total,
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse, summary="Get job status and progress")
def get_job(job_id: str, request: Request) -> JobStatusResponse:
    row = request.app.state.runtime.job_status(job_id)
    if row is None:
        raise ApiError(404, ErrorCode.JOB_NOT_FOUND.value, "Job was not found.")
    return _public_job(row)


@router.post("/jobs/{job_id}/cancel", response_model=CancelResponse, summary="Request safe job cancellation")
def cancel_job(job_id: str, request: Request) -> CancelResponse:
    row = request.app.state.runtime.request_cancel(job_id)
    if row is None:
        raise ApiError(404, ErrorCode.JOB_NOT_FOUND.value, "Job was not found.")
    if row["status"] in {"succeeded", "failed", "cancelled"}:
        raise ApiError(409, ErrorCode.JOB_NOT_READY.value, f"A {row['status']} job cannot be cancelled.")
    pending = row["status"] == "running"
    return CancelResponse(
        job_id=UUID(job_id), status=JobStatus(row["status"]),
        cancellation_requested=row["cancel_requested"],
        message=("Cancellation is pending; an active model or FFmpeg call will finish before it stops." if pending
                 else "Queued job cancelled before inference started."),
    )


@router.get("/jobs/{job_id}/artifacts", response_model=ArtifactListResponse, summary="List validated job artifacts")
def list_artifacts(job_id: str, request: Request) -> ArtifactListResponse:
    row = request.app.state.runtime.job_status(job_id)
    if row is None:
        raise ApiError(404, ErrorCode.JOB_NOT_FOUND.value, "Job was not found.")
    if row["status"] != "succeeded":
        raise ApiError(409, ErrorCode.JOB_NOT_READY.value, "Artifacts are available only after successful completion.")
    artifacts = [_public_artifact(item, job_id) for item in row["artifacts"]]
    return ArtifactListResponse(job_id=UUID(job_id), artifacts=artifacts)


@router.get("/jobs/{job_id}/artifacts/{artifact_name}", summary="Download a validated WAV or MP4")
def download_artifact(job_id: str, artifact_name: str, request: Request) -> FileResponse:
    path, artifact = request.app.state.runtime.artifact_path(job_id, artifact_name)
    return FileResponse(
        path, media_type=artifact["media_type"], filename=artifact["name"],
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


def _public_job(row: dict[str, Any]) -> JobStatusResponse:
    artifacts = [_public_artifact(item, row["job_id"]) for item in row["artifacts"]] if row["status"] == "succeeded" else []
    return JobStatusResponse(
        job_id=UUID(row["job_id"]), status=JobStatus(row["status"]),
        processing_stage=row["stage"], progress_percent=float(row["progress"]),
        current_chunk=row["current_chunk"], total_chunks=row["total_chunks"],
        creation_time=datetime.fromisoformat(row["created_at"]),
        start_time=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
        completion_time=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        cancellation_requested=row["cancel_requested"],
        error_code=row["error_code"], error_message=row["error_message"],
        chunk_details=row["chunk_details"], artifacts=artifacts,
    )


def _public_artifact(item: dict[str, Any], job_id: str) -> ArtifactMetadata:
    return ArtifactMetadata(
        name=item["name"], media_type=item["media_type"], size_bytes=int(item["size_bytes"]),
        duration_seconds=item.get("duration_seconds"),
        download_url=f"/api/v1/jobs/{job_id}/artifacts/{item['name']}",
    )


async def _read_context_upload(upload: UploadFile, max_bytes: int) -> bytes:
    data = await upload.read(max_bytes + 1)
    if not data:
        raise ApiError(400, ErrorCode.INVALID_CONTEXT_JSON.value, "Context JSON upload is empty.")
    if len(data) > max_bytes:
        raise ApiError(413, ErrorCode.FILE_TOO_LARGE.value, "Context JSON exceeds the configured size limit.")
    return data


def _replace_video_references(payload: dict[str, Any], safe_name: str) -> None:
    reference_keys = {"video_path", "source_video", "video", "input_video"}
    if isinstance(payload, dict):
        for key, value in list(payload.items()):
            if key in reference_keys and isinstance(value, str) and value.strip():
                payload[key] = safe_name
            elif isinstance(value, (dict, list)):
                _replace_video_references(value, safe_name)
    elif isinstance(payload, list):
        for value in payload:
            if isinstance(value, (dict, list)):
                _replace_video_references(value, safe_name)
