"""FFmpeg MP4 export with explicit stream mapping and post-export validation."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_foley_studio.audio.synchronizer import VideoInspection, inspect_video


class VideoExportError(RuntimeError):
    """FFmpeg/FFprobe export operation failed or produced an invalid file."""


@dataclass(frozen=True)
class ExportResult:
    """Verified final video facts."""

    output_path: Path
    duration_seconds: float
    video_codec: str
    audio_codec: str
    video: VideoInspection

    def to_dict(self) -> dict:
        result = asdict(self)
        result["output_path"] = str(self.output_path)
        result["video"] = self.video.to_dict()
        return result


def build_mux_command(
    video_path: str | Path,
    audio_path: str | Path,
    output_path: str | Path,
    *,
    ffmpeg_executable: str = "ffmpeg",
) -> list[str]:
    """Build a non-destructive MP4 mux command with no blind ``-shortest``."""
    return [
        ffmpeg_executable,
        "-hide_banner",
        "-nostdin",
        "-i",
        str(Path(video_path)),
        "-i",
        str(Path(audio_path)),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-map_metadata",
        "0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(Path(output_path)),
    ]


class VideoExporter:
    """Mux duration-matched audio into an MP4 while preserving video frames."""

    def __init__(self, ffmpeg_executable: str = "ffmpeg", ffprobe_executable: str = "ffprobe") -> None:
        self.ffmpeg_executable = ffmpeg_executable
        self.ffprobe_executable = ffprobe_executable

    def export(
        self,
        video_path: str | Path,
        audio_path: str | Path,
        output_path: str | Path,
    ) -> ExportResult:
        """Create a new MP4; input files are never overwritten."""
        source_video = Path(video_path).expanduser().resolve()
        source_audio = Path(audio_path).expanduser().resolve()
        destination = Path(output_path).expanduser().resolve()
        if not source_video.is_file() or not source_audio.is_file():
            raise VideoExportError("Both an existing source video and processed source audio are required.")
        if destination.suffix.lower() != ".mp4":
            raise VideoExportError("Final video output must use the .mp4 extension.")
        if destination == source_video or destination == source_audio:
            raise VideoExportError("Refusing to overwrite an input source file.")
        if destination.exists():
            raise VideoExportError(f"Refusing to overwrite existing output: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        executable = shutil.which(self.ffmpeg_executable)
        if executable is None:
            raise VideoExportError("FFmpeg executable was not found on PATH.")
        command = build_mux_command(source_video, source_audio, destination, ffmpeg_executable=executable)
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise VideoExportError(f"FFmpeg muxing failed: {completed.stderr.strip()}")
        return self.inspect(destination, expected_video=inspect_video(source_video, self.ffprobe_executable))

    def inspect(self, output_path: str | Path, *, expected_video: VideoInspection | None = None) -> ExportResult:
        """Confirm the final file has both streams and retains video duration."""
        output = Path(output_path).expanduser().resolve()
        if not output.is_file() or output.stat().st_size == 0:
            raise VideoExportError(f"Final video was not created: {output}")
        executable = shutil.which(self.ffprobe_executable)
        if executable is None:
            raise VideoExportError("FFprobe is required to validate the final video but was not found on PATH.")
        command = [
            executable,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-show_entries",
            "stream=codec_type,codec_name",
            "-of",
            "json",
            str(output),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise VideoExportError(f"FFprobe could not validate final video: {completed.stderr.strip()}")
        try:
            payload = json.loads(completed.stdout)
            duration = float(payload["format"]["duration"])
            streams = payload["streams"]
            video_stream = next(stream for stream in streams if stream.get("codec_type") == "video")
            audio_stream = next(stream for stream in streams if stream.get("codec_type") == "audio")
        except (KeyError, TypeError, ValueError, StopIteration, json.JSONDecodeError) as exc:
            raise VideoExportError("Final MP4 does not contain readable video and audio streams.") from exc
        if duration <= 0:
            raise VideoExportError("Final MP4 has an invalid duration.")
        video = inspect_video(output, self.ffprobe_executable)
        if expected_video is not None and abs(duration - expected_video.duration_seconds) > 0.25:
            raise VideoExportError(
                f"Final video duration ({duration:.3f}s) differs from source video "
                f"({expected_video.duration_seconds:.3f}s)."
            )
        return ExportResult(
            output_path=output,
            duration_seconds=duration,
            video_codec=str(video_stream.get("codec_name", "unknown")),
            audio_codec=str(audio_stream.get("codec_name", "unknown")),
            video=video,
        )


def mux_audio_video(video_path: str | Path, audio_path: str | Path, output_path: str | Path) -> ExportResult:
    """Compatibility helper for exporting a duration-matched audio/video pair."""
    return VideoExporter().export(video_path, audio_path, output_path)
