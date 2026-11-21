"""Public request and response models for API version 1."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class ApiErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class ApiErrorResponse(BaseModel):
    error: ApiErrorBody


class JobAcceptedResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    status_url: str
    created_at: datetime


class ArtifactMetadata(BaseModel):
    name: str
    media_type: str
    size_bytes: int
    duration_seconds: float | None = None
    download_url: str


class JobStatusResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    processing_stage: str
    progress_percent: float = Field(ge=0, le=100)
    current_chunk: int | None = None
    total_chunks: int | None = None
    creation_time: datetime
    start_time: datetime | None = None
    completion_time: datetime | None = None
    cancellation_requested: bool = False
    chunk_details: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    artifacts: list[ArtifactMetadata] = Field(default_factory=list)


class JobListResponse(BaseModel):
    items: list[JobStatusResponse]
    limit: int
    offset: int
    total: int


class ArtifactListResponse(BaseModel):
    job_id: UUID
    artifacts: list[ArtifactMetadata]


class CancelResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    cancellation_requested: bool
    message: str


class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, Any]


class SceneEventDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    action: str = Field(min_length=1, max_length=300)
    timestamp_start: float | None = Field(default=None, ge=0)
    timestamp_end: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_event_interval(self) -> "SceneEventDocument":
        if (
            self.timestamp_start is not None
            and self.timestamp_end is not None
            and self.timestamp_end < self.timestamp_start
        ):
            raise ValueError("timestamp_end cannot be earlier than timestamp_start")
        return self


class SceneAnalysisDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    scene_summary: str | None = Field(default=None, max_length=10_000)
    events: list[SceneEventDocument] = Field(default_factory=list, max_length=500)


class SoundContextDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    scene_summary: str | None = Field(default=None, max_length=10_000)
    sound_contexts: list[SceneEventDocument] = Field(default_factory=list, max_length=500)


class JobOptions(BaseModel):
    prompt_override: str | None = Field(default=None, max_length=1000)
    negative_prompt: str = Field(default="music, speech", max_length=500)
    chunk_seconds: float = Field(default=4.0, ge=0.64, le=8.0)
    num_steps: int = Field(default=25, ge=1, le=100)
    guidance_scale: float = Field(default=4.5, gt=0, le=20)
    timing_offset_seconds: float = Field(default=0.0, ge=-60, le=60)
    target_lufs: float | None = Field(default=None, ge=-40, le=0)
    export_video: bool = False


class ErrorCode(StrEnum):
    INVALID_UPLOAD = "INVALID_UPLOAD"
    UNSUPPORTED_MEDIA = "UNSUPPORTED_MEDIA"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    INVALID_CONTEXT_JSON = "INVALID_CONTEXT_JSON"
    QUEUE_FULL = "QUEUE_FULL"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    JOB_NOT_READY = "JOB_NOT_READY"
    UNAUTHORIZED = "UNAUTHORIZED"
    WORKER_UNAVAILABLE = "WORKER_UNAVAILABLE"
    GPU_OUT_OF_MEMORY = "GPU_OUT_OF_MEMORY"
    AUDIO_GENERATION_FAILED = "AUDIO_GENERATION_FAILED"
    VIDEO_EXPORT_FAILED = "VIDEO_EXPORT_FAILED"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
