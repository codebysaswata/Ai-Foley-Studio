
import json
import hashlib
import shutil
import tempfile
from pathlib import Path

import streamlit as st

from ai_foley_studio.config import TEMP_DIR
from ai_foley_studio.intelligence.context_engine import generate_context_output
from ai_foley_studio.pipeline import FoleyPipeline, PipelineConfig
from ai_foley_studio.video.processor import extract_frames, inspect_video
from ai_foley_studio.video.scene_analyzer import analyze_scenes


def _upload_sha256(video_bytes: bytes) -> str:
    """Return a stable source-video identifier for generated JSON artifacts."""
    return hashlib.sha256(video_bytes).hexdigest()


def _persistent_analysis_dir(video_sha256: str) -> Path:
    """Keep inputs and JSON artifacts available for a later pipeline action."""
    directory = TEMP_DIR / "streamlit" / video_sha256
    directory.mkdir(parents=True, exist_ok=True)
    return directory


st.set_page_config(
    page_title="AI Foley Studio",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 AI Foley Studio")
st.caption("Video Scene Analysis and Sound Context Testing")

st.divider()


# --------------------------------------------------
# VIDEO UPLOAD
# --------------------------------------------------

uploaded_video = st.file_uploader(
    "Upload your sample video",
    type=["mp4", "mov", "avi", "mkv"]
)

if uploaded_video is not None:

    video_bytes = uploaded_video.getvalue()

    st.subheader("Original Video")

    st.video(video_bytes)

    st.download_button(
        label="⬇️ Download Original Video",
        data=video_bytes,
        file_name=uploaded_video.name,
        mime=uploaded_video.type
    )

    st.divider()

    if st.button("🚀 Analyze Video", type="primary"):

        try:
            with st.spinner("Processing video... Please wait."):

                # Use a separate temporary directory for each run.
                # This prevents old frames from previous videos mixing in.
                with tempfile.TemporaryDirectory() as work_dir:

                    work_path = Path(work_dir)

                    video_path = work_path / uploaded_video.name

                    video_path.write_bytes(video_bytes)

                    frame_dir = work_path / "extracted_frames"

                    # --------------------------------
                    # STEP 1: VIDEO PROCESSING
                    # --------------------------------

                    st.write("### Step 1: Video Processing")

                    metadata = inspect_video(video_path)

                    st.success("Video metadata extracted.")

                    st.json(metadata)

                    frames = extract_frames(
                        video_path,
                        interval_seconds=1.0,
                        max_frames=30,
                        resize_width=640,
                        output_dir=frame_dir
                    )

                    st.write(f"Extracted frames: {len(frames)}")

                    # --------------------------------
                    # STEP 2: SCENE ANALYSIS
                    # --------------------------------

                    st.write("### Step 2: Scene Analysis")

                    frame_records = [
                        {
                            "timestamp": frame.timestamp_seconds,
                            "path": frame.image_path
                        }
                        for frame in frames
                    ]

                    scene_result = analyze_scenes(frame_records)

                    video_sha256 = _upload_sha256(video_bytes)
                    scene_result["source_video"] = uploaded_video.name
                    scene_result["video_sha256"] = video_sha256

                    st.success("Scene analysis completed.")

                    # --------------------------------
                    # STEP 3: CONTEXT ENGINE
                    # --------------------------------

                    st.write("### Step 3: Context Engine")

                    context_result = generate_context_output(
                        scene_result
                    )

                    st.success("Sound context generated.")

                    # --------------------------------
                    # SAVE RESULTS
                    # --------------------------------

                    scene_json = json.dumps(
                        scene_result,
                        indent=4,
                        ensure_ascii=False
                    )

                    context_json = json.dumps(
                        context_result,
                        indent=4,
                        ensure_ascii=False
                    )

                    persistent_dir = _persistent_analysis_dir(video_sha256)
                    persistent_video = persistent_dir / uploaded_video.name
                    persistent_video.write_bytes(video_bytes)
                    scene_path = persistent_dir / "scene_analysis.json"
                    sound_path = persistent_dir / "sound_context.json"
                    scene_path.write_text(scene_json, encoding="utf-8")
                    sound_path.write_text(context_json, encoding="utf-8")

                    st.session_state["scene_json"] = scene_json
                    st.session_state["context_json"] = context_json
                    st.session_state["metadata"] = metadata
                    st.session_state["video_path"] = str(persistent_video)
                    st.session_state["scene_path"] = str(scene_path)
                    st.session_state["sound_path"] = str(sound_path)
                    st.session_state["video_sha256"] = video_sha256

            st.success("Video analysis completed. Foley audio has not been generated yet.")

        except Exception as e:
            st.error(f"An error occurred: {e}")


# --------------------------------------------------
# DISPLAY GENERATED JSON
# --------------------------------------------------

if "context_json" in st.session_state:

    st.divider()

    st.header("📄 Generated Results")

    tab1, tab2 = st.tabs([
        "Scene Analysis JSON",
        "Sound Context JSON"
    ])

    with tab1:

        st.subheader("Scene Analysis Output")

        st.code(
            st.session_state["scene_json"],
            language="json"
        )

        st.download_button(
            "Download Scene Analysis JSON",
            data=st.session_state["scene_json"],
            file_name="scene_analysis.json",
            mime="application/json"
        )

    with tab2:

        st.subheader("Context Engine Output")

        st.code(
            st.session_state["context_json"],
            language="json"
        )

        st.download_button(
            "Download Sound Context JSON",
            data=st.session_state["context_json"],
            file_name="sound_context.json",
            mime="application/json"
        )

    st.divider()
    st.header("🔊 Generate Foley audio")
    st.caption(
        "MMAudio processes the full video in consecutive chunks. Events are matched to the chunks "
        "they overlap, and a short crossfade joins the generated audio."
    )
    with st.form("foley_generation"):
        duration = st.number_input("Maximum MMAudio chunk length (seconds)", min_value=1.0, max_value=8.0, value=4.0)
        prompt_override = st.text_input("Optional prompt override")
        ffmpeg_available = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
        export_video = st.checkbox(
            "Export final MP4 (requires FFmpeg and FFprobe)",
            value=False,
            disabled=not ffmpeg_available,
        )
        if not ffmpeg_available:
            st.caption("MP4 export is unavailable: install FFmpeg and ensure both ffmpeg and ffprobe are on PATH.")
        submitted = st.form_submit_button("Generate Foley")

    if submitted:
        pipeline = None
        try:
            pipeline = FoleyPipeline()
            with st.spinner("Generating synchronized Foley chunks and assembling the full soundtrack..."):
                result = pipeline.run(
                    st.session_state["video_path"],
                    st.session_state["scene_path"],
                    st.session_state["sound_path"],
                    PipelineConfig(
                        duration=float(duration),
                        prompt_override=prompt_override or None,
                        export_video=export_video,
                    ),
                )
            st.success("Foley generation completed.")
            st.caption(f"Prompt: {result.prompt}")
            metadata_payload = json.loads(result.metadata_path.read_text(encoding="utf-8"))
            chunk_generation = metadata_payload.get("artifacts", {}).get("chunk_generation", {})
            chunk_reports = chunk_generation.get("chunk_reports", [])
            if chunk_reports:
                st.subheader("Chunk quality")
                quality_rows = []
                for report in chunk_reports:
                    accepted = next(
                        (item for item in report.get("attempts", []) if item.get("status") == "accepted"),
                        {},
                    )
                    metrics = accepted.get("metrics", {})
                    quality_rows.append({
                        "Chunk": report.get("chunk_index"),
                        "Status": report.get("status"),
                        "Retries": report.get("retry_count", 0),
                        "Interior RMS": metrics.get("interior_rms"),
                        "Peak": metrics.get("sample_peak"),
                        "Duration (s)": metrics.get("duration_seconds"),
                    })
                st.dataframe(quality_rows, use_container_width=True, hide_index=True)
                with st.expander("Prompts and validation details"):
                    st.json(chunk_reports)
            st.audio(str(result.processed_audio_path))
            st.download_button(
                "Download processed Foley WAV",
                data=result.processed_audio_path.read_bytes(),
                file_name="processed_foley.wav",
                mime="audio/wav",
            )
            if result.final_video_path is not None:
                st.video(str(result.final_video_path))
            st.caption(f"Job metadata: {result.metadata_path}")
        except Exception as exc:
            st.error(f"Foley generation failed: {type(exc).__name__}: {exc}")
        finally:
            if pipeline is not None:
                pipeline.close()
