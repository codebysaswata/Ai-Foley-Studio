"""Load and normalize the video-analysis contract for Foley generation.

The reference video pipeline emits a ``scene_analysis.json`` document with a
``scene_summary`` and ``events``. Its companion context builder emits a
``sound_context.json`` document with ``sound_contexts``. This module accepts
those documented structures while validating them instead of concatenating raw
JSON into a model prompt.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field, replace as dataclass_replace
from pathlib import Path
from typing import Any, Mapping, Optional


class ContextValidationError(ValueError):
    """A context document is unreadable, malformed, or structurally invalid."""


class ContextConflictError(ContextValidationError):
    """Scene and sound documents contain incompatible meaningful facts."""


UNKNOWN_VALUES = {"", "none", "null", "n/a", "na", "unknown", "unspecified"}


def _clean_text(value: Any, default: str = "unknown") -> str:
    if value is None:
        return default
    text = " ".join(str(value).strip().split())
    return default if text.lower() in UNKNOWN_VALUES else text


def _optional_text(value: Any) -> Optional[str]:
    text = _clean_text(value)
    return None if text == "unknown" else text


def _number(value: Any, field_name: str, *, required: bool = False) -> Optional[float]:
    if value is None:
        if required:
            raise ContextValidationError(f"Missing required numeric field: {field_name}.")
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ContextValidationError(f"{field_name} must be numeric; received {value!r}.") from exc
    if not math.isfinite(number):
        raise ContextValidationError(f"{field_name} must be finite.")
    return number


def _event_objects(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ContextValidationError("Event objects must be a string or a list of strings.")
    return tuple(text for item in value if (text := _optional_text(item)) is not None)


def _read_json_object(path: str | Path, label: str) -> tuple[Path, dict[str, Any]]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ContextValidationError(f"{label} file does not exist or is not a file: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ContextValidationError(f"{label} is not UTF-8 text: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ContextValidationError(f"{label} contains invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContextValidationError(f"{label} must contain a JSON object at its root.")
    return source, payload


@dataclass(frozen=True)
class FoleyEvent:
    """One normalized visual/sound observation, retaining its evidence."""

    timestamp_start: Optional[float]
    timestamp_end: Optional[float]
    action: str
    objects: tuple[str, ...] = ()
    source: str = "unknown"
    surroundings: str = "unknown"
    environment: str = "unknown"
    material: str = "unknown"
    intensity: str = "unknown"
    rhythm: str = "unknown"
    texture: str = "unknown"
    potential_sound: str = "unknown"
    confidence: Optional[float] = None
    visual_evidence: str = "unknown"
    raw_scene_event: Optional[dict[str, Any]] = field(default=None, repr=False)
    raw_sound_context: Optional[dict[str, Any]] = field(default=None, repr=False)
    timeline_end_inferred: bool = False

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["objects"] = list(self.objects)
        return result


@dataclass(frozen=True)
class NormalizedFoleyContext:
    """Validated scene-level context consumed by sound and prompt engines."""

    scene_summary: str
    events: tuple[FoleyEvent, ...]
    scene_analysis_path: Path
    sound_context_path: Path
    source_video_references: tuple[str, ...] = ()
    source_video_hashes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_summary": self.scene_summary,
            "events": [event.to_dict() for event in self.events],
            "scene_analysis_path": str(self.scene_analysis_path),
            "sound_context_path": str(self.sound_context_path),
            "source_video_references": list(self.source_video_references),
            "source_video_hashes": list(self.source_video_hashes),
            "warnings": list(self.warnings),
        }


def _normalise_event(payload: Mapping[str, Any], *, source: str) -> FoleyEvent:
    action = _clean_text(payload.get("action"))
    if action == "unknown":
        raise ContextValidationError(f"{source} event is missing a meaningful 'action'.")
    start = _number(payload.get("timestamp_start", payload.get("timestamp")), "timestamp_start")
    end = _number(payload.get("timestamp_end"), "timestamp_end")
    if start is not None and start < 0:
        raise ContextValidationError("timestamp_start cannot be negative.")
    if end is not None and end < 0:
        raise ContextValidationError("timestamp_end cannot be negative.")
    if start is not None and end is not None and end < start:
        raise ContextValidationError("timestamp_end cannot be earlier than timestamp_start.")
    confidence = _number(payload.get("confidence"), "confidence")
    if confidence is not None and not 0 <= confidence <= 1:
        raise ContextValidationError("confidence must be between zero and one.")
    return FoleyEvent(
        timestamp_start=start,
        timestamp_end=end,
        action=action,
        objects=_event_objects(payload.get("objects")),
        source=_clean_text(payload.get("source_object", payload.get("source"))),
        surroundings=_clean_text(payload.get("surroundings")),
        environment=_clean_text(payload.get("environment")),
        material=_clean_text(payload.get("material")),
        intensity=_clean_text(payload.get("intensity")),
        rhythm=_clean_text(payload.get("rhythm")),
        texture=_clean_text(payload.get("texture")),
        potential_sound=_clean_text(payload.get("potential_sound")),
        confidence=confidence,
        visual_evidence=_clean_text(payload.get("visual_evidence")),
        raw_scene_event=dict(payload) if source == "scene_analysis" else None,
        raw_sound_context=dict(payload) if source == "sound_context" else None,
    )


def _get_events(payload: Mapping[str, Any], field_name: str, label: str) -> list[FoleyEvent]:
    values = payload.get(field_name, [])
    if values is None:
        return []
    if not isinstance(values, list):
        raise ContextValidationError(f"{label}.{field_name} must be a list.")
    events: list[FoleyEvent] = []
    for index, value in enumerate(values):
        if not isinstance(value, Mapping):
            raise ContextValidationError(f"{label}.{field_name}[{index}] must be an object.")
        events.append(_normalise_event(value, source=label))
    return events


def _meaningful_conflict(left: str, right: str) -> bool:
    return (
        left.casefold() not in UNKNOWN_VALUES
        and right.casefold() not in UNKNOWN_VALUES
        and left.casefold() != right.casefold()
    )


def _merge_events(scene: FoleyEvent, sound: FoleyEvent) -> FoleyEvent:
    """Merge same-event records while rejecting incompatible observations."""
    if _meaningful_conflict(scene.action, sound.action):
        raise ContextConflictError(
            f"Conflicting action values for one event: {scene.action!r} vs {sound.action!r}."
        )
    for name in ("timestamp_start", "timestamp_end"):
        scene_time = getattr(scene, name)
        sound_time = getattr(sound, name)
        if scene_time is not None and sound_time is not None and abs(scene_time - sound_time) > 0.25:
            raise ContextConflictError(
                f"Conflicting {name} values for action {scene.action!r}: {scene_time} vs {sound_time}."
            )

    def select(name: str) -> Any:
        first, second = getattr(sound, name), getattr(scene, name)
        if isinstance(first, str):
            if _meaningful_conflict(first, second):
                raise ContextConflictError(
                    f"Conflicting {name} values for action {scene.action!r}: {second!r} vs {first!r}."
                )
            return first if first.lower() not in UNKNOWN_VALUES else second
        return first if first is not None else second

    return FoleyEvent(
        timestamp_start=select("timestamp_start"),
        timestamp_end=select("timestamp_end"),
        action=select("action"),
        objects=sound.objects or scene.objects,
        source=select("source"),
        surroundings=select("surroundings"),
        environment=select("environment"),
        material=select("material"),
        intensity=select("intensity"),
        rhythm=select("rhythm"),
        texture=select("texture"),
        potential_sound=select("potential_sound"),
        confidence=sound.confidence if sound.confidence is not None else scene.confidence,
        visual_evidence=select("visual_evidence"),
        raw_scene_event=scene.raw_scene_event,
        raw_sound_context=sound.raw_sound_context,
    )


def _event_match(scene: FoleyEvent, sound: FoleyEvent) -> bool:
    """Match only one unambiguous representation of the same observed event.

    Actions alone are insufficient: repeated footsteps or separate impacts may
    have close timestamps.  Both records therefore need compatible timing and
    non-contradictory source/object identities before their fields can merge.
    """
    if scene.action.casefold() != sound.action.casefold():
        return False
    if scene.timestamp_start is None or sound.timestamp_start is None:
        return False
    if abs(scene.timestamp_start - sound.timestamp_start) > 0.25:
        return False
    if scene.timestamp_end is not None and sound.timestamp_end is not None:
        if abs(scene.timestamp_end - sound.timestamp_end) > 0.25:
            return False
    if _meaningful_conflict(scene.source, sound.source):
        return False
    scene_objects = {object_name.casefold() for object_name in scene.objects}
    sound_objects = {object_name.casefold() for object_name in sound.objects}
    if scene_objects and sound_objects and scene_objects.isdisjoint(sound_objects):
        return False
    return True


def _merge_event_lists(scene_events: list[FoleyEvent], sound_events: list[FoleyEvent]) -> list[FoleyEvent]:
    available = list(sound_events)
    merged: list[FoleyEvent] = []
    for scene in scene_events:
        matching_indices = [i for i, sound in enumerate(available) if _event_match(scene, sound)]
        if len(matching_indices) != 1:
            # Ambiguous candidates are retained independently. This avoids
            # collapsing separate but nearby events into a fabricated event.
            merged.append(scene)
        else:
            merged.append(_merge_events(scene, available.pop(matching_indices[0])))
    merged.extend(available)
    return sorted(merged, key=lambda event: (event.timestamp_start is None, event.timestamp_start or 0.0))


def _source_video_references(payload: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("video_path", "source_video", "video", "input_video"):
        value = _optional_text(payload.get(key))
        if value is not None:
            values.append(value)
    metadata = payload.get("metadata")
    if isinstance(metadata, Mapping):
        values.extend(_source_video_references(metadata))
    return tuple(dict.fromkeys(values))


def _source_video_hashes(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Collect explicit SHA-256 source identifiers without guessing at hashes."""
    values: list[str] = []
    for key in ("video_sha256", "source_video_sha256"):
        value = payload.get(key)
        if value is None:
            continue
        digest = str(value).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ContextValidationError(f"{key} must be a 64-character SHA-256 hex digest.")
        values.append(digest)
    metadata = payload.get("metadata")
    if isinstance(metadata, Mapping):
        values.extend(_source_video_hashes(metadata))
    return tuple(dict.fromkeys(values))


_CONTINUOUS_RHYTHMS = {"continuous", "sustained", "ongoing", "steady", "constant"}
_GENERIC_IDENTITY_WORDS = {
    "a", "an", "the", "sound", "sounds", "noise", "movement", "moving", "action",
    "flowing", "running", "continuous", "sustained", "steady", "constant",
}


def _supports_continuous_scene_duration(event: FoleyEvent, scene_summary: str) -> bool:
    """Only infer a continuous event's end when the video analysis ties it to the scene."""
    if event.rhythm.casefold() not in _CONTINUOUS_RHYTHMS:
        return False
    evidence = f"{scene_summary} {event.visual_evidence}".casefold()
    identities = (event.action, event.source, *event.objects)
    for identity in identities:
        normalized = " ".join(identity.casefold().replace("_", " ").split())
        if normalized in UNKNOWN_VALUES:
            continue
        if len(normalized) >= 3 and normalized in evidence:
            return True
        words = [word for word in re.findall(r"[a-z0-9]+", normalized) if word not in _GENERIC_IDENTITY_WORDS]
        if words and any(re.search(rf"\b{re.escape(word)}\b", evidence) for word in words):
            return True
    return False


def _apply_continuous_scene_duration(
    events: list[FoleyEvent], scene_summary: str, video_duration_seconds: float | None
) -> tuple[list[FoleyEvent], list[str]]:
    """Extend only analysis-supported continuous events; never change source JSON."""
    if video_duration_seconds is None:
        return events, []
    normalized: list[FoleyEvent] = []
    warnings: list[str] = []
    for event in events:
        if (
            event.timestamp_start is not None
            and event.timestamp_start < video_duration_seconds
            and (event.timestamp_end is None or event.timestamp_end < video_duration_seconds)
            and _supports_continuous_scene_duration(event, scene_summary)
        ):
            event = dataclass_replace(
                event, timestamp_end=video_duration_seconds, timeline_end_inferred=True
            )
        elif (
            event.rhythm.casefold() in _CONTINUOUS_RHYTHMS
            and (event.timestamp_end is None or event.timestamp_end < video_duration_seconds - 0.25)
        ):
            warnings.append(
                f"Continuous event {event.action!r} ends before the source video and lacks scene evidence "
                "for duration inference; its source timing was retained."
            )
        normalized.append(event)
    return normalized, warnings


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ContextEngine:
    """Parse the reference video-analysis JSON contract into normalized context."""

    def load(
        self,
        scene_analysis_path: str | Path,
        sound_context_path: str | Path,
        *,
        video_path: str | Path | None = None,
        video_duration_seconds: float | None = None,
    ) -> NormalizedFoleyContext:
        scene_path, scene_payload = _read_json_object(scene_analysis_path, "scene_analysis")
        sound_path, sound_payload = _read_json_object(sound_context_path, "sound_context")
        scene_events = _get_events(scene_payload, "events", "scene_analysis")
        sound_events = _get_events(sound_payload, "sound_contexts", "sound_context")
        scene_summary = _clean_text(scene_payload.get("scene_summary"))
        sound_summary = _clean_text(sound_payload.get("scene_summary"))
        if _meaningful_conflict(scene_summary, sound_summary):
            raise ContextConflictError(
                f"Conflicting scene summaries: {scene_summary!r} vs {sound_summary!r}."
            )
        summary = sound_summary if sound_summary.lower() not in UNKNOWN_VALUES else scene_summary
        references = tuple(
            dict.fromkeys(_source_video_references(scene_payload) + _source_video_references(sound_payload))
        )
        hashes = tuple(dict.fromkeys(_source_video_hashes(scene_payload) + _source_video_hashes(sound_payload)))
        warnings: list[str] = []
        if not scene_events:
            warnings.append("scene_analysis contains no events; prompt generation may use ambience only.")
        if not sound_events:
            warnings.append("sound_context contains no sound_contexts; visual events were retained without enrichment.")
        merged_events, inference_warnings = _apply_continuous_scene_duration(
            _merge_event_lists(scene_events, sound_events), summary, video_duration_seconds
        )
        warnings.extend(inference_warnings)
        if video_duration_seconds is not None:
            if not math.isfinite(video_duration_seconds) or video_duration_seconds <= 0:
                raise ContextValidationError("video_duration_seconds must be a finite positive number.")
            timed_ends = [
                event.timestamp_end if event.timestamp_end is not None else event.timestamp_start
                for event in merged_events
                if event.timestamp_end is not None or event.timestamp_start is not None
            ]
            if timed_ends and max(timed_ends) < video_duration_seconds - 0.25:
                warnings.append(
                    "Analysis events end before the source video duration; a single global MMAudio clip "
                    "does not provide a complete event-level Foley timeline."
                )
        if video_path is not None and references:
            supplied_name = Path(video_path).name.lower()
            reference_names = {Path(reference).name.lower() for reference in references}
            if supplied_name not in reference_names:
                raise ContextConflictError(
                    "JSON source-video reference does not match the supplied video filename: "
                    f"{supplied_name!r} not in {sorted(reference_names)!r}."
                )
        if video_path is not None and hashes:
            actual_hash = _file_sha256(Path(video_path).expanduser().resolve())
            if actual_hash not in hashes:
                raise ContextConflictError(
                    "JSON source-video SHA-256 does not match the supplied video. "
                    "Refusing to associate analysis artifacts with a different file."
                )
        return NormalizedFoleyContext(
            scene_summary=summary,
            events=tuple(merged_events),
            scene_analysis_path=scene_path,
            sound_context_path=sound_path,
            source_video_references=references,
            source_video_hashes=hashes,
            warnings=tuple(warnings),
        )


def load_context(
    scene_analysis_path: str | Path,
    sound_context_path: str | Path,
    *,
    video_path: str | Path | None = None,
    video_duration_seconds: float | None = None,
) -> NormalizedFoleyContext:
    """Convenience entry point for loading both external analysis artifacts."""
    return ContextEngine().load(
        scene_analysis_path,
        sound_context_path,
        video_path=video_path,
        video_duration_seconds=video_duration_seconds,
    )


# ------------------------------------------------------------------
# COMPATIBILITY API
# Preserves the original video-analysis / Streamlit workflow.
# ------------------------------------------------------------------

@dataclass
class SoundContext:
    """Structured representation of a detected Foley event."""

    action: str
    source: str = "unknown"
    objects: list[str] = field(default_factory=list)
    material: str = "unknown"
    environment: str = "unknown"
    surroundings: str = "unknown"
    intensity: str = "medium"
    rhythm: str = "unknown"
    texture: str = "unknown"
    potential_sound: str = "unknown"
    timestamp_start: float | None = None
    timestamp_end: float | None = None
    confidence: float | None = None
    visual_evidence: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clean_text(value: Any, default: str = "unknown") -> str:
    return _clean_text(value, default)


def clean_timestamp(value: Any) -> float | None:
    if value is None:
        return None
    try:
        timestamp = float(value)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(timestamp) or timestamp < 0:
        return None
    return timestamp


def clean_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        confidence = float(value)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        return None
    return confidence


def build_sound_context(observation: dict) -> SoundContext:
    if not isinstance(observation, dict):
        raise TypeError("Observation must be a dictionary.")

    source = observation.get(
        "source_object",
        observation.get("source", "unknown"),
    )

    raw_objects = observation.get("objects", [])
    if isinstance(raw_objects, str):
        raw_objects = [raw_objects]
    if not isinstance(raw_objects, (list, tuple)):
        raw_objects = []

    objects = [
        text
        for item in raw_objects
        if (text := _optional_text(item)) is not None
    ]

    start = clean_timestamp(
        observation.get("timestamp_start", observation.get("timestamp"))
    )
    end = clean_timestamp(observation.get("timestamp_end"))

    if start is not None and end is not None and end < start:
        start = None
        end = None

    return SoundContext(
        action=clean_text(observation.get("action")),
        source=clean_text(source),
        objects=objects,
        material=clean_text(observation.get("material")),
        environment=clean_text(observation.get("environment")),
        surroundings=clean_text(observation.get("surroundings")),
        intensity=clean_text(observation.get("intensity"), default="medium"),
        rhythm=clean_text(observation.get("rhythm")),
        texture=clean_text(observation.get("texture")),
        potential_sound=clean_text(observation.get("potential_sound")),
        timestamp_start=start,
        timestamp_end=end,
        confidence=clean_confidence(observation.get("confidence")),
        visual_evidence=clean_text(observation.get("visual_evidence")),
    )


def build_sound_contexts(scene_analysis: dict) -> list[SoundContext]:
    if not isinstance(scene_analysis, dict):
        raise TypeError("Scene analysis must be a dictionary.")

    events = scene_analysis.get("events", [])
    if not isinstance(events, list):
        raise ValueError("'events' must be a list.")

    contexts = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f"Event at index {index} must be a dictionary.")
        contexts.append(build_sound_context(event))

    return contexts


def generate_context_output(scene_analysis: dict) -> dict:
    if not isinstance(scene_analysis, dict):
        raise TypeError("Scene analysis must be a dictionary.")

    contexts = build_sound_contexts(scene_analysis)

    output = {
        "scene_summary": clean_text(scene_analysis.get("scene_summary")),
        "total_events": len(contexts),
        "sound_contexts": [context.to_dict() for context in contexts],
    }
    # Preserve an explicit source identity when the analysis producer supplied
    # one, so the consuming pipeline can reject unrelated uploads safely.
    for key in ("video_path", "source_video", "video", "input_video", "video_sha256", "source_video_sha256"):
        if key in scene_analysis:
            output[key] = scene_analysis[key]
    return output
