from dataclasses import dataclass
from pathlib import Path

import cv2
from ai_foley_studio.config import SUPPORTED_VIDEO_EXTENSIONS

@dataclass
class FrameSample:
    """A sampled video frame and its original timestamp."""
    frame_index: int
    timestamp_seconds: float
    image: object
    image_path: str | None = None


def validate_video(video_path: str | Path) -> Path:
    """Validate the video file before processing."""
    path = Path(video_path)

    if not path.exists():
        raise FileNotFoundError(f"Video not found: {path}")

    if not path.is_file():
        raise ValueError("The provided path is not a file.")

    if path.stat().st_size == 0:
        raise ValueError("The uploaded video is empty.")

    if path.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_VIDEO_EXTENSIONS))
        raise ValueError(
            f"Unsupported video format: {path.suffix}. "
            f"Supported formats: {supported}"
        )

    return path


def inspect_video(video_path: str | Path) -> dict:
    """Return basic video metadata using OpenCV."""
    path = validate_video(video_path)

    capture = cv2.VideoCapture(str(path))

    if not capture.isOpened():
        capture.release()
        raise ValueError("OpenCV could not open this video.")

    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if fps <= 0 or frame_count <= 0 or width <= 0 or height <= 0:
            raise ValueError("Video metadata is invalid or incomplete.")

        # Confirm that at least one frame can actually be decoded.
        success, _ = capture.read()
        if not success:
            raise ValueError("The video contains no readable frames.")

        duration = frame_count / fps

        return {
            "filename": path.name,
            "width": width,
            "height": height,
            "fps": round(fps, 3),
            "frame_count": frame_count,
            "duration_seconds": round(duration, 3),
        }

    finally:
        capture.release()
def extract_frames(
    video_path: str | Path,
    interval_seconds: float = 1.0,
    max_frames: int = 12,
    resize_width: int = 640,
    output_dir: str | Path | None = None,
) -> list[FrameSample]:
    """
    Sample frames at regular time intervals.

    Frames are returned as OpenCV BGR images. If output_dir is provided,
    each sampled frame is also saved as a JPEG file.
    """
    path = validate_video(video_path)

    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than zero.")

    if max_frames < 1:
        raise ValueError("max_frames must be at least 1.")

    if resize_width < 1:
        raise ValueError("resize_width must be at least 1.")

    capture = cv2.VideoCapture(str(path))

    if not capture.isOpened():
        capture.release()
        raise ValueError("OpenCV could not open this video.")

    samples = []
    save_dir = Path(output_dir) if output_dir is not None else None

    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)

    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))

        if fps <= 0 or frame_count <= 0:
            raise ValueError("Cannot sample frames: invalid video metadata.")

        duration = frame_count / fps

        timestamps = []
        current_time = 0.0

        while current_time < duration and len(timestamps) < max_frames:
            timestamps.append(current_time)
            current_time += interval_seconds

        for timestamp in timestamps:
            frame_index = min(int(timestamp * fps), frame_count - 1)

            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            success, frame = capture.read()

            if not success:
                continue

            height, width = frame.shape[:2]

            if width > resize_width:
                new_height = int(height * resize_width / width)
                frame = cv2.resize(
                    frame,
                    (resize_width, new_height),
                    interpolation=cv2.INTER_AREA,
                )

            image_path = None

            if save_dir is not None:
                filename = f"frame_{frame_index:06d}.jpg"
                destination = save_dir / filename

                if not cv2.imwrite(str(destination), frame):
                    raise IOError(f"Could not save frame: {destination}")

                image_path = str(destination)

            samples.append(
                FrameSample(
                    frame_index=frame_index,
                    timestamp_seconds=round(timestamp, 3),
                    image=frame,
                    image_path=image_path,
                )
            )

        if not samples:
            raise ValueError("No frames could be extracted from this video.")

        return samples

    finally:
        capture.release()
