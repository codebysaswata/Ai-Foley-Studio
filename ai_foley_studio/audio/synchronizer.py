"""Explicit audio/video duration policy and one-time timing offset handling."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from ai_foley_studio.audio.audio_processor import AudioInspection, AudioProcessor


log = logging.getLogger(__name__)
DurationPolicy = Literal["match_video", "preserve_audio"]


class SynchronizationError(RuntimeError):
    """Video metadata is invalid or a synchronization policy cannot be applied."""


@dataclass(frozen=True)
class VideoInspection:
    """Duration and stream facts needed for muxing without changing the video."""

    path: Path
    duration_seconds: float
    width: int | None
    height: int | None
    fps: float | None
    has_audio: bool | None
    probe_backend: str

    def to_dict(self) -> dict:
        result = asdict(self)
        result["path"] = str(self.path)
        return result


@dataclass(frozen=True)
class SynchronizationResult:
    """The processed audio fitted to an explicit duration policy."""

    audio: AudioInspection
    video: VideoInspection
    timing_offset_seconds: float
    policy: str


def inspect_video(video_path: str | Path, ffprobe_executable: str = "ffprobe") -> VideoInspection:
    """Read duration with FFprobe when available, otherwise use OpenCV metadata."""
    source = Path(video_path).expanduser().resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise SynchronizationError(f"Video does not exist, is not a file, or is empty: {source}")
    executable = shutil.which(ffprobe_executable)
    if executable is not None:
        command = [
            executable,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-show_entries",
            "stream=codec_type,width,height,avg_frame_rate",
            "-of",
            "json",
            str(source),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode == 0:
            try:
                payload = json.loads(completed.stdout)
                duration = float(payload["format"]["duration"])
                streams = payload.get("streams", [])
                video = next(stream for stream in streams if stream.get("codec_type") == "video")
                fps_text = video.get("avg_frame_rate", "0/0")
                numerator, denominator = fps_text.split("/", 1)
                fps = float(numerator) / float(denominator) if float(denominator) else None
                if duration > 0:
                    return VideoInspection(
                        path=source,
                        duration_seconds=duration,
                        width=int(video["width"]) if video.get("width") else None,
                        height=int(video["height"]) if video.get("height") else None,
                        fps=fps,
                        has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
                        probe_backend="ffprobe",
                    )
            except (KeyError, TypeError, ValueError, StopIteration, json.JSONDecodeError):
                log.warning("FFprobe returned incomplete metadata for %s; using OpenCV fallback.", source)
        else:
            log.warning("FFprobe could not inspect %s: %s", source, completed.stderr.strip())
    try:
        import cv2
    except ImportError as exc:
        raise SynchronizationError("Neither usable FFprobe nor OpenCV is available for video metadata.") from exc
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise SynchronizationError(f"OpenCV could not open video: {source}")
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = frames / fps if fps > 0 else 0.0
        if duration <= 0:
            raise SynchronizationError("Video duration could not be determined.")
        return VideoInspection(
            path=source,
            duration_seconds=duration,
            width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0) or None,
            height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0) or None,
            fps=fps or None,
            has_audio=None,
            probe_backend="opencv",
        )
    finally:
        capture.release()


class AudioSynchronizer:
    """Apply offset once and produce audio ready for an explicit export policy."""

    def __init__(self, processor: AudioProcessor | None = None) -> None:
        self.processor = processor or AudioProcessor()

    def synchronize(
        self,
        video_path: str | Path,
        audio_path: str | Path,
        output_path: str | Path,
        *,
        timing_offset_seconds: float = 0.0,
        duration_policy: DurationPolicy = "match_video",
    ) -> SynchronizationResult:
        """Shift and fit audio according to the selected policy exactly once."""
        if duration_policy not in {"match_video", "preserve_audio"}:
            raise ValueError("duration_policy must be 'match_video' or 'preserve_audio'.")
        video = inspect_video(video_path)
        target = video.duration_seconds if duration_policy == "match_video" else None
        audio = self.processor.apply_timing_offset(
            audio_path,
            output_path,
            timing_offset_seconds,
            target_duration=target,
        )
        if duration_policy == "match_video" and abs(audio.duration_seconds - video.duration_seconds) > 1 / audio.sample_rate:
            raise SynchronizationError("Audio duration does not match video duration after synchronization.")
        return SynchronizationResult(
            audio=audio,
            video=video,
            timing_offset_seconds=timing_offset_seconds,
            policy=duration_policy,
        )


def apply_timing_offset(
    audio_path: str | Path,
    output_path: str | Path,
    offset_seconds: float,
) -> AudioInspection:
    """Compatibility wrapper; pipeline code should use :class:`AudioSynchronizer`."""
    return AudioProcessor().apply_timing_offset(audio_path, output_path, offset_seconds)
