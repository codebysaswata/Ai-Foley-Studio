from video.processor import inspect_video, extract_frames
from utils.cleanup import clean_previous_outputs

video_path = r"E:\AI video Editor\ai_foley_studio\ai_foley_studio\testing video\test_video.mp4"

# Step 1: Clean previous outputs
clean_previous_outputs()

# Step 2: Inspect video
metadata = inspect_video(video_path)

print("\nVIDEO METADATA:")
print(metadata)

# Step 3: Extract frames
frames = extract_frames(
    video_path,
    interval_seconds=1.0,
    max_frames=20,
    output_dir="temp/extracted_frames",
)

print("\nEXTRACTED FRAMES:")

for frame in frames:
    print(
        frame.frame_index,
        frame.timestamp_seconds,
        frame.image.shape,
        frame.image_path,
    )
