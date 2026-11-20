"""Bounded upload persistence and actual FFprobe/FFmpeg video validation."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ai_foley_studio.api.errors import ApiError
from ai_foley_studio.api.schemas import ErrorCode
from ai_foley_studio.api.settings import ApiSettings
from ai_foley_studio.config import SUPPORTED_VIDEO_EXTENSIONS


class MediaValidationError(ApiError):
    pass


async def save_upload_stream(upload: Any, destination: Path, max_bytes: int) -> int:
    """Copy an upload in bounded chunks; client filename never becomes a path."""
    total = 0
    with destination.open("xb") as output:
        while True:
            block = await upload.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > max_bytes:
                output.close()
                destination.unlink(missing_ok=True)
                raise ApiError(413, ErrorCode.FILE_TOO_LARGE.value, "Video exceeds the configured upload limit.")
            output.write(block)
    if total == 0:
        destination.unlink(missing_ok=True)
        raise ApiError(400, ErrorCode.INVALID_UPLOAD.value, "The uploaded video is empty.")
    return total


def safe_upload_extension(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in SUPPORTED_VIDEO_EXTENSIONS:
        raise ApiError(415, ErrorCode.UNSUPPORTED_MEDIA.value, "Supported video containers are MP4, MOV, MKV, AVI and WebM.")
    return suffix


def validate_video_media(path: Path, original_extension: str, settings: ApiSettings) -> dict[str, Any]:
    """Probe container/stream facts and decode a frame before queue registration."""
    ffprobe = shutil.which(settings.ffprobe) if not Path(settings.ffprobe).is_absolute() else settings.ffprobe
    ffmpeg = shutil.which(settings.ffmpeg) if not Path(settings.ffmpeg).is_absolute() else settings.ffmpeg
    if not ffprobe or not ffmpeg:
        raise ApiError(503, ErrorCode.WORKER_UNAVAILABLE.value, "FFmpeg and FFprobe must be available on the backend host.")
    probe_cmd = [
        str(ffprobe), "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=codec_type,codec_name,width,height:format=format_name,duration", "-of", "json", str(path),
    ]
    try:
        probe = subprocess.run(
            probe_cmd, capture_output=True, text=True, check=False,
            timeout=settings.media_probe_timeout_seconds,
        )
        if probe.returncode != 0:
            raise ApiError(415, ErrorCode.UNSUPPORTED_MEDIA.value, "FFprobe could not read a supported video stream.")
        payload = json.loads(probe.stdout)
        streams = payload.get("streams", [])
        stream = streams[0] if streams else None
        duration = float(payload.get("format", {}).get("duration", 0))
        width = int(stream.get("width", 0)) if stream else 0
        height = int(stream.get("height", 0)) if stream else 0
        codec = str(stream.get("codec_name", "unknown")) if stream else "unknown"
        format_names = str(payload.get("format", {}).get("format_name", "")).lower().split(",")
    except subprocess.TimeoutExpired as exc:
        raise ApiError(415, ErrorCode.UNSUPPORTED_MEDIA.value, "Video inspection exceeded the allowed time.") from exc
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ApiError(415, ErrorCode.UNSUPPORTED_MEDIA.value, "Video metadata is invalid or unreadable.") from exc

    if not stream or stream.get("codec_type") != "video":
        raise ApiError(415, ErrorCode.UNSUPPORTED_MEDIA.value, "The upload does not contain a video stream.")
    if duration <= 0 or width <= 0 or height <= 0:
        raise ApiError(415, ErrorCode.UNSUPPORTED_MEDIA.value, "The video has invalid duration or dimensions.")
    if duration < 16 / 25:
        raise ApiError(422, ErrorCode.UNSUPPORTED_MEDIA.value, "Video must be at least 0.64 seconds for MMAudio synchronization.")
    if duration > settings.max_video_seconds:
        raise ApiError(413, ErrorCode.FILE_TOO_LARGE.value, "Video duration exceeds the configured limit.")
    if width * height > settings.max_video_pixels:
        raise ApiError(413, ErrorCode.FILE_TOO_LARGE.value, "Video resolution exceeds the configured pixel limit.")

    actual_ext = _extension_for_container(format_names, original_extension)
    decode_cmd = [
        str(ffmpeg), "-hide_banner", "-v", "error", "-nostdin", "-i", str(path),
        "-map", "0:v:0", "-frames:v", "1", "-f", "null", "-",
    ]
    try:
        decoded = subprocess.run(
            decode_cmd, capture_output=True, text=True, check=False,
            timeout=settings.media_probe_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise ApiError(415, ErrorCode.UNSUPPORTED_MEDIA.value, "Video frame decoding exceeded the allowed time.") from exc
    if decoded.returncode != 0:
        raise ApiError(415, ErrorCode.UNSUPPORTED_MEDIA.value, "The uploaded video is corrupt or cannot be decoded.")
    return {
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "video_codec": codec,
        "container": format_names,
        "server_extension": actual_ext,
    }


def _extension_for_container(format_names: list[str], fallback: str) -> str:
    names = set(format_names)
    if names & {"mp4", "mov", "3gp", "3g2", "mj2"}:
        return ".mp4"
    if "matroska" in names or "webm" in names:
        return ".webm" if fallback == ".webm" else ".mkv"
    if "avi" in names:
        return ".avi"
    raise ApiError(415, ErrorCode.UNSUPPORTED_MEDIA.value, "The video container is not supported by this service.")
