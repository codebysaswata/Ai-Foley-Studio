
import json
from pathlib import Path

from video.scene_analyzer import analyze_scenes


# Folder containing your extracted frames
FRAME_DIR = Path("temp/extracted_frames")

# Your video FPS from the metadata
VIDEO_FPS = 30.0

frame_records = []

for frame_path in sorted(
    FRAME_DIR.glob("frame_*.jpg")
):

    frame_index = int(
        frame_path.stem.split("_")[-1]
    )

    timestamp = frame_index / VIDEO_FPS

    frame_records.append({
        "timestamp": timestamp,
        "path": str(frame_path)
    })


print("Total frames:", len(frame_records))

# Run Qwen scene analysis
result = analyze_scenes(frame_records)

print("\nSCENE SUMMARY:")
print(result["scene_summary"])

print("\nDETECTED FOLEY EVENTS:")

for event in result["events"]:
    print(json.dumps(event, indent=4))

# Save the result
output_path = Path("temp/scene_analysis.json")

output_path.parent.mkdir(
    parents=True,
    exist_ok=True
)

output_path.write_text(
    json.dumps(result, indent=4),
    encoding="utf-8"
)

print("\nAnalysis saved to:", output_path)
