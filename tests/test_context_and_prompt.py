"""Contract tests for context validation, sound rules, and prompt construction."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai_foley_studio.intelligence.context_engine import (
    ContextConflictError,
    ContextEngine,
    generate_context_output,
)
from ai_foley_studio.intelligence.prompt_engine import PromptEngine
from ai_foley_studio.intelligence.sound_rules import build_sound_plan


def _scene_document() -> dict:
    return {
        "scene_summary": "A person walks through a quiet park and closes a metal gate.",
        "events": [
            {
                "timestamp_start": 0.0,
                "timestamp_end": 1.2,
                "action": "walking",
                "objects": ["person", "path"],
                "source_object": "person",
                "environment": "park",
                "material": "gravel",
                "intensity": "soft",
                "texture": "crisp",
                "confidence": 0.91,
            },
            {
                "timestamp_start": 1.3,
                "timestamp_end": 1.8,
                "action": "door closing",
                "objects": ["gate"],
                "source_object": "gate",
                "environment": "park",
                "material": "metal",
                "intensity": "medium",
                "confidence": 0.86,
            },
        ],
    }


def _sound_document() -> dict:
    return {
        "scene_summary": "A person walks through a quiet park and closes a metal gate.",
        "total_events": 2,
        "sound_contexts": [
            {
                "timestamp_start": 0.0,
                "timestamp_end": 1.2,
                "action": "walking",
                "source": "person",
                "objects": ["person", "path"],
                "environment": "park",
                "material": "gravel",
                "intensity": "soft",
                "texture": "crisp",
                "confidence": 0.91,
            },
            {
                "timestamp_start": 1.3,
                "timestamp_end": 1.8,
                "action": "door closing",
                "source": "gate",
                "objects": ["gate"],
                "environment": "park",
                "material": "metal",
                "intensity": "medium",
                "confidence": 0.86,
            },
        ],
    }


class ContextAndPromptTests(unittest.TestCase):
    def _write_contract(self, root: Path) -> tuple[Path, Path]:
        scene = root / "scene_analysis.json"
        sound = root / "sound_context.json"
        scene.write_text(json.dumps(_scene_document()), encoding="utf-8")
        sound.write_text(json.dumps(_sound_document()), encoding="utf-8")
        return scene, sound

    def test_normalizes_reference_contract_and_builds_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            scene, sound = self._write_contract(Path(directory))
            context = ContextEngine().load(scene, sound)
        self.assertEqual(len(context.events), 2)
        self.assertEqual(context.events[0].action, "walking")
        plan = build_sound_plan(context)
        self.assertEqual(plan.primary[0].category, "footsteps")
        prompt = PromptEngine().build(context)
        self.assertIn("footsteps", prompt.prompt)
        self.assertIn("door closing", prompt.prompt)
        self.assertIn("park ambience", prompt.prompt)

    def test_reports_conflicting_documents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scene, sound = self._write_contract(root)
            payload = json.loads(sound.read_text(encoding="utf-8"))
            payload["sound_contexts"][0]["material"] = "wood"
            sound.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ContextConflictError):
                ContextEngine().load(scene, sound)

    def test_prompt_override_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            scene, sound = self._write_contract(Path(directory))
            context = ContextEngine().load(scene, sound)
        result = PromptEngine().build(context, prompt_override="dry footsteps and a metal gate")
        self.assertTrue(result.used_override)
        self.assertEqual(result.prompt, "dry footsteps and a metal gate")

    def test_nearby_same_action_with_different_objects_is_not_merged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scene = root / "scene_analysis.json"
            sound = root / "sound_context.json"
            scene.write_text(
                json.dumps({"events": [{"action": "impact", "timestamp_start": 1.0, "objects": ["ball"]}]}),
                encoding="utf-8",
            )
            sound.write_text(
                json.dumps({"sound_contexts": [{"action": "impact", "timestamp_start": 1.1, "objects": ["door"]}]}),
                encoding="utf-8",
            )
            context = ContextEngine().load(scene, sound)
        self.assertEqual(len(context.events), 2)

    def test_rejects_mismatched_source_video_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "source.mp4"
            video.write_bytes(b"not-a-real-video-but-a-stable-test-identity")
            scene, sound = self._write_contract(root)
            payload = json.loads(scene.read_text(encoding="utf-8"))
            payload["video_sha256"] = "0" * 64
            scene.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ContextConflictError):
                ContextEngine().load(scene, sound, video_path=video)

    def test_context_output_preserves_explicit_source_identity(self) -> None:
        document = _scene_document()
        document["source_video"] = "clip.mp4"
        document["video_sha256"] = "a" * 64
        output = generate_context_output(document)
        self.assertEqual(output["source_video"], "clip.mp4")
        self.assertEqual(output["video_sha256"], "a" * 64)

    def test_infers_supported_continuous_event_end_without_changing_source_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document = {
                "scene_summary": "A continuous waterfall cascades into a forest pool.",
                "events": [{
                    "timestamp_start": 0.0, "timestamp_end": 1.0,
                    "action": "waterfall", "objects": ["waterfall"],
                    "rhythm": "continuous", "potential_sound": "Water rushing and splashing",
                    "visual_evidence": "A waterfall remains visible, flowing into a pool.",
                }],
            }
            scene = root / "scene.json"
            sound = root / "sound.json"
            scene.write_text(json.dumps(document), encoding="utf-8")
            sound.write_text(json.dumps({
                "scene_summary": document["scene_summary"],
                "sound_contexts": document["events"],
            }), encoding="utf-8")
            original_scene = scene.read_text(encoding="utf-8")
            original_sound = sound.read_text(encoding="utf-8")

            context = ContextEngine().load(scene, sound, video_duration_seconds=12.0)

            self.assertEqual(context.events[0].timestamp_end, 12.0)
            self.assertTrue(context.events[0].timeline_end_inferred)
            self.assertEqual(scene.read_text(encoding="utf-8"), original_scene)
            self.assertEqual(sound.read_text(encoding="utf-8"), original_sound)

    def test_does_not_infer_continuous_end_without_matching_visual_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scene = root / "scene.json"
            sound = root / "sound.json"
            scene.write_text(json.dumps({
                "scene_summary": "A quiet indoor room with a person standing still.",
                "events": [{"timestamp_start": 0, "timestamp_end": 1,
                            "action": "waterfall", "rhythm": "continuous"}],
            }), encoding="utf-8")
            sound.write_text(json.dumps({"sound_contexts": []}), encoding="utf-8")
            context = ContextEngine().load(scene, sound, video_duration_seconds=12.0)
        self.assertEqual(context.events[0].timestamp_end, 1.0)
        self.assertFalse(context.events[0].timeline_end_inferred)
