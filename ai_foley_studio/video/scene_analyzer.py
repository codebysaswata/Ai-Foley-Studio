import gc
import json
import logging
import math
from pathlib import Path

import torch
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
from qwen_vl_utils import process_vision_info

from ai_foley_studio.config import TEMP_DIR


MODEL_ID = "Qwen/Qwen3-VL-2B-Instruct"
log = logging.getLogger(__name__)


# --------------------------------------------------
# 1. LOAD QWEN MODEL
# --------------------------------------------------

def load_scene_model():
    """
    Load Qwen3-VL for one scene-analysis operation.

    This deliberately is not cached. The Streamlit workflow must release Qwen
    before it initializes MMAudio on a 4 GB GPU.
    """
    print("Loading Qwen3-VL scene analysis model...")

    model = Qwen3VLForConditionalGeneration.from_pretrained(
        MODEL_ID,
        torch_dtype="auto",
        device_map="auto",
    )

    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model.eval()

    print("Qwen3-VL loaded successfully.")
    return model, processor


def cuda_memory_snapshot() -> dict[str, int] | None:
    """Return CUDA allocation and free-memory facts without changing state."""
    if not torch.cuda.is_available():
        return None
    free, total = torch.cuda.mem_get_info()
    return {
        "allocated_bytes": int(torch.cuda.memory_allocated()),
        "reserved_bytes": int(torch.cuda.memory_reserved()),
        "free_bytes": int(free),
        "total_bytes": int(total),
    }


def release_scene_model(model=None, processor=None) -> None:
    """Collect released Qwen objects and reclaim unused CUDA cache.

    The optional arguments are retained for compatibility with existing
    callers. Deleting these local references is not sufficient by itself:
    the caller must also clear its own references before invoking this helper.
    """
    del model
    del processor

    collected = gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        try:
            torch.cuda.ipc_collect()
        except RuntimeError:
            # IPC collection is best-effort and not required for local tensors.
            pass

    log.info(
        "Qwen cleanup completed; gc_collected=%d cuda=%s",
        collected,
        cuda_memory_snapshot(),
    )


# --------------------------------------------------
# 2. NORMALIZE EXTRACTED FRAMES
# --------------------------------------------------

def normalize_frames(frame_records):
    """
    Accept frame records from video/processor.py or the test script.

    Supported dictionary:
        {"timestamp": 0.0, "path": "temp/extracted_frames/frame_000000.jpg"}

    Supported tuple/list:
        (frame_index, timestamp, image_array, saved_path)

    Supported FrameSample object:
        FrameSample(frame_index, timestamp_seconds, image, image_path)
    """
    normalized = []

    for record in frame_records:
        timestamp = None
        frame_path = None

        if isinstance(record, dict):
            timestamp = record.get(
                "timestamp",
                record.get("timestamp_seconds"),
            )
            frame_path = (
                record.get("path")
                or record.get("frame_path")
                or record.get("image_path")
            )

        elif isinstance(record, (tuple, list)):
            if len(record) >= 4:
                timestamp = record[1]
                frame_path = record[3]
            elif len(record) == 2:
                timestamp, frame_path = record
            else:
                raise ValueError(
                    "A frame tuple must contain either 2 or at least 4 values."
                )

        else:
            # Supports FrameSample dataclass instances from processor.py.
            timestamp = getattr(record, "timestamp_seconds", None)
            frame_path = getattr(record, "image_path", None)

        if timestamp is None:
            raise ValueError(f"Frame is missing its timestamp: {record!r}")

        if not frame_path:
            raise ValueError(
                "Frame is missing a saved image path. "
                "Call extract_frames(..., output_dir=...) first."
            )

        path = Path(frame_path).expanduser().resolve()

        if not path.exists():
            raise FileNotFoundError(f"Extracted frame not found: {path}")

        if not path.is_file():
            raise ValueError(f"Frame path is not a file: {path}")

        try:
            timestamp = float(timestamp)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid frame timestamp: {timestamp!r}"
            ) from exc

        if not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError(
                f"Frame timestamp must be a finite non-negative number: {timestamp}"
            )

        normalized.append({
            "timestamp": timestamp,
            "path": path,
        })

    if not normalized:
        raise ValueError("No extracted frames were provided.")

    normalized.sort(key=lambda item: item["timestamp"])

    # Duplicate timestamps can confuse temporal interpretation.
    timestamps = [item["timestamp"] for item in normalized]
    if len(timestamps) != len(set(timestamps)):
        raise ValueError("Duplicate frame timestamps were provided.")

    return normalized


# --------------------------------------------------
# 3. BUILD SCENE ANALYSIS INSTRUCTION
# --------------------------------------------------

def build_scene_instruction(frames):
    """Build the Foley-focused instruction supplied alongside the images."""
    timestamps = [frame["timestamp"] for frame in frames]
    timestamp_text = ", ".join(f"{value:.2f}s" for value in timestamps)

    return f"""
You are a professional visual scene analyst for an AI Foley generation
application. You are given still video frames in chronological order.
The timestamp for each frame, in the same order as the images, is:
{timestamp_text}

Analyze the visual evidence across the complete sequence.

TASK:
1. Describe the overall scene briefly.
2. Identify visible human or animal actions.
3. Identify objects involved in actions and relevant surroundings.
4. Identify actions that could plausibly produce physical Foley sounds.
5. Estimate event start and end times using only the supplied timestamps.
6. Describe material and likely sound qualities where visually supported.

RULES:
- You are analyzing images, not audio. Never claim that a sound was heard.
- Report only actions supported by visible evidence.
- Do not infer an action from an object merely being present.
- Do not invent dialogue, music, or off-screen sounds.
- Use the nearest supplied frame timestamps; do not claim false precision.
- Merge consecutive frames showing the same continuous action into one event.
- Avoid duplicate events.
- If no sound-producing action is visible, return an empty events array.
- Use "unknown" when a property cannot reasonably be inferred.
- Return ONLY valid JSON. Do not use Markdown fences or extra commentary.

Return this structure:
{{
  "scene_summary": "Short description of the visible scene",
  "events": [
    {{
      "timestamp_start": 0.0,
      "timestamp_end": 1.0,
      "action": "walking",
      "objects": ["shoes"],
      "source_object": "person's shoes",
      "surroundings": "outdoor pathway",
      "environment": "outdoor",
      "material": "gravel",
      "intensity": "medium",
      "rhythm": "repeated irregular footsteps",
      "texture": "crunchy",
      "potential_sound": "Footsteps crunching on gravel",
      "confidence": 0.90,
      "visual_evidence": "A person is visibly walking on a gravel pathway."
    }}
  ]
}}

Allowed intensity values: low, medium, high, unknown.
Confidence must be a number from 0 to 1.
Suggested material values: wood, metal, glass, gravel, grass, water,
fabric, plastic, concrete, unknown.
"""


# --------------------------------------------------
# 4. PARSE MODEL RESPONSE
# --------------------------------------------------

def parse_model_response(response):
    """Parse one complete JSON object returned by Qwen."""
    if not isinstance(response, str) or not response.strip():
        raise ValueError("Qwen returned an empty response.")

    cleaned = response.lstrip(" \t\r\n")
    if cleaned.startswith("\ufeff"):
        cleaned = cleaned[1:]
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("Qwen response did not contain a JSON object.")

    try:
        result, end = json.JSONDecoder().raw_decode(cleaned, start)
    except json.JSONDecodeError as exc:
        if exc.pos >= len(cleaned) - 1 or "Unterminated string" in exc.msg:
            reason = "Qwen JSON output is incomplete or truncated."
        else:
            reason = f"Qwen returned malformed JSON at line {exc.lineno}, column {exc.colno}."
        raise ValueError(reason) from exc

    if not isinstance(result, dict):
        raise ValueError("Expected Qwen's response to be a JSON object.")
    trailing = cleaned[end:].strip()
    if trailing.startswith("```"):
        trailing = trailing[3:].strip()
    if trailing:
        raise ValueError("Qwen response contained content after the JSON object.")

    summary = result.get("scene_summary")
    if not isinstance(summary, str):
        raise ValueError("Qwen response field 'scene_summary' must be a string.")
    events = result.get("events", [])
    if not isinstance(events, list):
        raise ValueError("Qwen response field 'events' must be a list.")
    validated_events = validate_events(events)
    if len(validated_events) != len(events):
        raise ValueError("Qwen response contains event entries outside the scene-analysis schema.")

    # Keep extra top-level fields while preserving normalized Foley events.
    return {**result, "scene_summary": summary, "events": validated_events}


def _generation_was_truncated(output_ids, input_ids, max_new_tokens, eos_token_id):
    """Identify generation that exhausted its token budget without EOS."""
    generated_count = int(output_ids.shape[-1] - input_ids.shape[-1])
    if generated_count < max_new_tokens:
        return False
    eos_ids = eos_token_id if isinstance(eos_token_id, (list, tuple, set)) else [eos_token_id]
    eos_ids = {int(token_id) for token_id in eos_ids if token_id is not None}
    return int(output_ids[-1].item()) not in eos_ids


# --------------------------------------------------
# 5. VALIDATE SCENE EVENTS
# --------------------------------------------------

def validate_events(events):
    """Validate and normalize events for the Context Engine."""
    validated = []

    for event in events:
        if not isinstance(event, dict):
            continue

        action = event.get("action")
        if not isinstance(action, str) or not action.strip():
            continue

        try:
            start = float(
                event.get("timestamp_start", event.get("timestamp", 0.0))
            )
            end = float(event.get("timestamp_end", start))
        except (TypeError, ValueError):
            continue

        if (
            not math.isfinite(start)
            or not math.isfinite(end)
            or start < 0
            or end < start
        ):
            continue

        confidence = event.get("confidence", 0.0)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0

        if not math.isfinite(confidence):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        objects = event.get("objects", [])
        if not isinstance(objects, list):
            objects = [str(objects)] if objects else []

        surroundings = event.get("surroundings", "unknown")

        validated.append({
            "timestamp_start": start,
            "timestamp_end": end,
            "timestamp": start,
            "action": action.strip(),
            "objects": objects,
            "source_object": event.get("source_object", "unknown"),
            "surroundings": surroundings,
            "environment": event.get("environment", surroundings),
            "material": event.get("material", "unknown"),
            "intensity": event.get("intensity", "unknown"),
            "rhythm": event.get("rhythm", "unknown"),
            "texture": event.get("texture", "unknown"),
            "potential_sound": event.get("potential_sound", "unknown"),
            "confidence": confidence,
            "visual_evidence": event.get("visual_evidence", ""),
        })

    validated.sort(key=lambda item: item["timestamp_start"])
    return validated


# --------------------------------------------------
# 6. MAIN SCENE ANALYSIS FUNCTION
# --------------------------------------------------

def analyze_scenes(
    frame_records,
    model=None,
    processor=None,
    max_new_tokens=4096,
):
    """
    Analyze extracted video frames using Qwen3-VL.

    frame_records:
        Dicts from the test script, tuples, or FrameSample objects
        returned by video/processor.py.

    Returns:
        {
            "scene_summary": str,
            "events": list
        }

    Important:
        This implementation sends each sampled frame as an individual
        image. It deliberately does not send a Windows file:// video URI,
        avoiding the path-decoding issue in qwen-vl-utils on Windows.
    """
    frames = normalize_frames(frame_records)
    owns_model = model is None and processor is None
    if (model is None) != (processor is None):
        raise ValueError("Provide both model and processor together, or neither.")
    if owns_model:
        loaded_model, loaded_processor = load_scene_model()
        model, processor = loaded_model, loaded_processor
    else:
        loaded_model = loaded_processor = None

    log.info("Qwen scene analysis starting; cuda_before=%s", cuda_memory_snapshot())
    content = messages = images = inputs = generated_ids = generated_ids_trimmed = None
    try:
        content = [{"type": "image", "image": str(frame["path"])} for frame in frames]
        content.append({"type": "text", "text": build_scene_instruction(frames)})
        messages = [{"role": "user", "content": content}]
        for attempt in range(2):
            prompt_text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            images, _ = process_vision_info(messages)
            if not images:
                raise RuntimeError("Qwen vision processor did not return any images. Check extracted JPEG files.")
            inputs = processor(text=[prompt_text], images=images, return_tensors="pt").to(model.device)
            token_limit = int(max_new_tokens) if attempt == 0 else min(int(max_new_tokens) * 2, 8192)
            with torch.inference_mode():
                generated_ids = model.generate(
                    **inputs,
                    max_new_tokens=token_limit,
                    do_sample=False,
                    temperature=None,
                    top_p=None,
                    top_k=None,
                )
            if generated_ids.shape[0] != inputs.input_ids.shape[0]:
                raise RuntimeError("Qwen returned a different number of sequences than the input batch.")
            generated_ids_trimmed = [
                output_ids[len(input_ids):]
                for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
            ]
            response = processor.batch_decode(
                generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
            )[0]
            TEMP_DIR.mkdir(parents=True, exist_ok=True)
            (TEMP_DIR / "qwen_raw_response.txt").write_text(str(response), encoding="utf-8")
            eos_token_id = getattr(getattr(model, "generation_config", None), "eos_token_id", None)
            if eos_token_id is None:
                eos_token_id = getattr(getattr(model, "config", None), "eos_token_id", None)
            try:
                if _generation_was_truncated(
                    generated_ids[0], inputs.input_ids[0], token_limit, eos_token_id
                ):
                    raise ValueError("Qwen exhausted its new-token limit before emitting an EOS token.")
                result = parse_model_response(response)
            except ValueError as exc:
                (TEMP_DIR / "qwen_raw_response_failure.txt").write_text(str(response), encoding="utf-8")
                if attempt == 1:
                    raise ValueError(
                        f"Qwen scene response remained invalid after one controlled regeneration: {exc}"
                    ) from exc
                log.warning("Qwen scene JSON was incomplete or invalid; regenerating once with a larger output budget.")
                content[-1]["text"] += (
                    "\nYour previous response was incomplete or invalid JSON. Retry once and return one complete "
                    "JSON object only. Be concise in the summary and evidence strings, but preserve every event, "
                    "timestamp, and required event field."
                )
                # Release first-attempt tensors before repeating visual preprocessing and generation.
                images = inputs = generated_ids = generated_ids_trimmed = None
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                continue
            return {"scene_summary": result["scene_summary"], "events": result["events"]}
        raise RuntimeError("Qwen generation loop ended without a scene result.")
    finally:
        # Drop references to frame payloads and generated CUDA tensors first.
        content = messages = images = inputs = generated_ids = generated_ids_trimmed = None

        if owns_model:
            # Clear every local alias before garbage collection. Passing the
            # objects to release_scene_model() would only delete the helper's
            # references, not these references held by analyze_scenes().
            model = processor = loaded_model = loaded_processor = None
            release_scene_model()
