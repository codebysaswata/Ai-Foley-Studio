"""Environment-backed settings for the independently run HTTP service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ApiSettings:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8000
    bearer_token: str | None = None
    cors_origins: tuple[str, ...] = ()
    max_upload_bytes: int = 512 * 1024 * 1024
    max_context_bytes: int = 2 * 1024 * 1024
    max_video_seconds: float = 300.0
    max_video_pixels: int = 3840 * 2160
    max_queued_jobs: int = 3
    retention_days: int = 14
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    media_probe_timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls) -> "ApiSettings":
        raw_origins = os.getenv("AI_FOLEY_CORS_ORIGINS", "")
        origins = tuple(dict.fromkeys(item.strip().rstrip("/") for item in raw_origins.split(",") if item.strip()))
        return cls(
            data_dir=Path(os.getenv("AI_FOLEY_API_DATA_DIR", "ai_foley_studio/data")).expanduser().resolve(),
            host=os.getenv("AI_FOLEY_API_HOST", "127.0.0.1").strip(),
            port=int(os.getenv("AI_FOLEY_API_PORT", "8000")),
            bearer_token=os.getenv("AI_FOLEY_API_TOKEN") or None,
            cors_origins=origins,
            max_upload_bytes=int(os.getenv("AI_FOLEY_API_MAX_UPLOAD_BYTES", str(512 * 1024 * 1024))),
            max_context_bytes=int(os.getenv("AI_FOLEY_API_MAX_CONTEXT_BYTES", str(2 * 1024 * 1024))),
            max_video_seconds=float(os.getenv("AI_FOLEY_API_MAX_VIDEO_SECONDS", "300")),
            max_video_pixels=int(os.getenv("AI_FOLEY_API_MAX_VIDEO_PIXELS", str(3840 * 2160))),
            max_queued_jobs=int(os.getenv("AI_FOLEY_API_MAX_QUEUED_JOBS", "3")),
            retention_days=int(os.getenv("AI_FOLEY_API_RETENTION_DAYS", "14")),
            ffmpeg=os.getenv("AI_FOLEY_FFMPEG", "ffmpeg"),
            ffprobe=os.getenv("AI_FOLEY_FFPROBE", "ffprobe"),
            media_probe_timeout_seconds=float(os.getenv("AI_FOLEY_API_MEDIA_TIMEOUT_SECONDS", "20")),
        )

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "jobs.sqlite3"

    @property
    def lock_path(self) -> Path:
        return self.data_dir / "api.lock"

    def validate(self, *, require_token: bool = True) -> None:
        if require_token and (not self.bearer_token or len(self.bearer_token) < 24):
            raise ValueError("AI_FOLEY_API_TOKEN must be set to a secret of at least 24 characters.")
        if not 1 <= self.port <= 65535:
            raise ValueError("API port must be between 1 and 65535.")
        if self.max_upload_bytes <= 0 or self.max_context_bytes <= 0:
            raise ValueError("Upload size limits must be positive.")
        if self.max_video_seconds <= 0 or self.max_video_pixels <= 0:
            raise ValueError("Video duration and pixel limits must be positive.")
        if self.max_queued_jobs < 1:
            raise ValueError("At least one queued job must be permitted.")
        if self.retention_days < 1:
            raise ValueError("Retention must be at least one day.")
        if any(origin == "*" for origin in self.cors_origins):
            raise ValueError("Wildcard CORS origins are not supported.")
