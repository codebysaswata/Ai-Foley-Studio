"""Conservative mappings from visible events to Foley sound categories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ai_foley_studio.intelligence.context_engine import FoleyEvent, NormalizedFoleyContext


@dataclass(frozen=True)
class SoundCandidate:
    """A sound instruction derived from an observed event, not an asserted fact."""

    category: str
    description: str
    timestamp_start: float | None
    timestamp_end: float | None
    importance: str
    event: FoleyEvent


@dataclass(frozen=True)
class SoundPlan:
    """Primary, secondary, and ambient candidates for prompt generation."""

    primary: tuple[SoundCandidate, ...]
    secondary: tuple[SoundCandidate, ...]
    ambience: tuple[str, ...]


_ACTION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("walk", "walking", "footstep", "footsteps"), "footsteps"),
    (("run", "running", "jog"), "running footsteps"),
    (("door open", "opening door", "open door"), "door opening and hinge movement"),
    (("door close", "door closing", "closing door", "close door", "slam"), "door closing and latch impact"),
    # Check water before the broad "fall" keyword so "waterfall" is not
    # incorrectly categorized as an object impact.
    (("waterfall", "water", "flowing", "pouring", "splash"), "water movement"),
    (("fall", "dropping", "drop"), "object impact"),
    (("impact", "hit", "strike", "collision"), "impact sound"),
    (("vehicle", "driving", "moving car", "driving car"), "vehicle engine and tire movement"),
    (("paper", "page turn", "handling paper"), "paper rustling"),
    (("metal", "clank", "metal object"), "metallic movement"),
    (("wind", "blowing"), "wind movement"),
)

_AMBIENCE_BY_ENVIRONMENT = {
    "outdoor": "subtle outdoor ambience",
    "street": "light street ambience",
    "road": "light road ambience",
    "forest": "soft natural outdoor ambience",
    "park": "soft park ambience",
    "indoor": "subtle indoor room tone",
    "room": "subtle indoor room tone",
    "kitchen": "subtle indoor kitchen ambience",
    "office": "quiet office room tone",
    "rain": "light rain ambience",
    "beach": "gentle coastal ambience",
}

_SURFACE_WORDS = ("gravel", "grass", "wood", "metal", "concrete", "water", "fabric", "glass", "plastic")


def _clean(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").split())


def _category_for(event: FoleyEvent) -> str | None:
    searchable = " ".join((event.action, event.potential_sound, event.source, *event.objects)).lower()
    for keywords, category in _ACTION_RULES:
        if any(keyword in searchable for keyword in keywords):
            return category
    return None


def _material_phrase(event: FoleyEvent) -> str:
    material = _clean(event.material)
    if material in _SURFACE_WORDS:
        return f"on {material}"
    return ""


def candidate_from_event(event: FoleyEvent) -> SoundCandidate | None:
    """Return a candidate only for an observable sound-producing action."""
    category = _category_for(event)
    if category is None:
        return None
    description = " ".join(part for part in (category, _material_phrase(event)) if part).strip()
    if event.texture.lower() != "unknown":
        description = f"{event.texture} {description}"
    if event.intensity.lower() != "unknown":
        description = f"{event.intensity} {description}"
    importance = "primary" if (event.confidence or 0.0) >= 0.65 else "secondary"
    return SoundCandidate(
        category=category,
        description=description,
        timestamp_start=event.timestamp_start,
        timestamp_end=event.timestamp_end,
        importance=importance,
        event=event,
    )


def ambience_from_events(events: Iterable[FoleyEvent]) -> tuple[str, ...]:
    """Derive only broad ambience directly indicated by environment labels."""
    ambience: list[str] = []
    for event in events:
        searchable = " ".join((event.environment, event.surroundings)).lower()
        for key, phrase in _AMBIENCE_BY_ENVIRONMENT.items():
            if key in searchable and phrase not in ambience:
                ambience.append(phrase)
    return tuple(ambience)


def build_sound_plan(context: NormalizedFoleyContext) -> SoundPlan:
    """Map normalized visual context into ordered, conservative sound candidates."""
    candidates = [candidate for event in context.events if (candidate := candidate_from_event(event))]
    candidates.sort(key=lambda candidate: (candidate.timestamp_start is None, candidate.timestamp_start or 0.0))
    primary = tuple(candidate for candidate in candidates if candidate.importance == "primary")
    secondary = tuple(candidate for candidate in candidates if candidate.importance != "primary")
    if not primary and secondary:
        primary, secondary = secondary[:1], secondary[1:]
    return SoundPlan(primary=primary, secondary=secondary, ambience=ambience_from_events(context.events))


def suggest_sound(action: str, material: str = "unknown") -> str:
    """Compatibility helper for callers that only have action/material strings."""
    event = FoleyEvent(timestamp_start=None, timestamp_end=None, action=action, material=material)
    candidate = candidate_from_event(event)
    return candidate.description if candidate else ""
