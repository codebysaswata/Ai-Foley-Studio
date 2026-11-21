"""Build concise scene-level prompts for the original MMAudio text condition."""

from __future__ import annotations

from dataclasses import dataclass

from ai_foley_studio.intelligence.context_engine import NormalizedFoleyContext
from ai_foley_studio.intelligence.sound_rules import SoundPlan, build_sound_plan


@dataclass(frozen=True)
class PromptBuildResult:
    """Prompt text together with the sound plan used to construct it."""

    prompt: str
    negative_prompt: str
    sound_plan: SoundPlan
    used_override: bool


class PromptValidationError(ValueError):
    """Prompt generation could not produce a usable MMAudio text condition."""


def _join_descriptions(descriptions: list[str]) -> str:
    if len(descriptions) == 1:
        return descriptions[0]
    if len(descriptions) == 2:
        return f"{descriptions[0]} and {descriptions[1]}"
    return ", ".join(descriptions[:-1]) + f", and {descriptions[-1]}"


class PromptEngine:
    """Create a single coherent prompt; timestamps remain metadata for future use."""

    def build(
        self,
        context: NormalizedFoleyContext,
        *,
        prompt_override: str | None = None,
        negative_prompt: str = "music, speech",
    ) -> PromptBuildResult:
        if prompt_override is not None and prompt_override.strip():
            return PromptBuildResult(
                prompt=prompt_override.strip(),
                negative_prompt=negative_prompt.strip(),
                sound_plan=build_sound_plan(context),
                used_override=True,
            )
        plan = build_sound_plan(context)
        primary = [
            self._event_description(candidate.event.action, candidate.description)
            for candidate in plan.primary[:3]
        ]
        secondary = [
            self._event_description(candidate.event.action, candidate.description)
            for candidate in plan.secondary[:2]
        ]
        clauses: list[str] = []
        if primary:
            clauses.append(_join_descriptions(primary))
        if secondary:
            clauses.append(f"subtle secondary sounds of {_join_descriptions(secondary)}")
        if plan.ambience:
            clauses.append(_join_descriptions(list(plan.ambience[:2])))
        if not clauses:
            clauses.append("quiet, sparse natural ambience matching the visible scene")
        prompt = "; ".join(clauses) + ". Clear Foley detail, no narration."
        if not prompt.strip():  # Defensive guard if future rules become configurable.
            raise PromptValidationError("No usable MMAudio prompt could be generated from the context.")
        return PromptBuildResult(
            prompt=prompt,
            negative_prompt=negative_prompt.strip(),
            sound_plan=plan,
            used_override=False,
        )

    @staticmethod
    def _event_description(action: str, sound_description: str) -> str:
        """Keep the visible sound source explicit alongside its acoustic category."""
        normalized_action = " ".join(action.split())
        if normalized_action.casefold() in sound_description.casefold():
            return sound_description
        return f"{normalized_action} ({sound_description})"


def create_audio_prompt(context: NormalizedFoleyContext) -> str:
    """Compatibility shortcut returning only the generated scene-level prompt."""
    return PromptEngine().build(context).prompt
