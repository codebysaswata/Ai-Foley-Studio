
from pathlib import Path
import shutil


def clean_previous_outputs():
    """
    Remove temporary outputs from the previous video test.
    Preserve source videos and project files.
    """

    temp_dir = Path("temp")

    # 1. Remove previously extracted frames
    frame_dir = temp_dir / "extracted_frames"

    if frame_dir.exists():
        shutil.rmtree(frame_dir)
        print("Old extracted frames deleted.")

    # 2. Remove previous generated output files
    old_files = [
        "scene_analysis.json",
        "sound_context.json",
        "qwen_raw_response.txt",
    ]

    for filename in old_files:
        file_path = temp_dir / filename

        if file_path.exists():
            file_path.unlink()
            print(f"Old file deleted: {filename}")

    # 3. Recreate the temporary directory
    temp_dir.mkdir(parents=True, exist_ok=True)

    print("Previous outputs cleaned successfully.")
