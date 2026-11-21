"""Focused regression coverage for Qwen scene JSON extraction and retry handling."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch

from ai_foley_studio.video.scene_analyzer import (
    _generation_was_truncated,
    analyze_scenes,
    parse_model_response,
)


def _scene(summary="A scene with rain."):
    return {
        "scene_summary": summary,
        "events": [{
            "timestamp_start": 0.0,
            "timestamp_end": 1.25,
            "action": "rain hitting a window",
            "objects": ["window"],
            "source_object": "window",
            "surroundings": "inside a house",
            "environment": "interior",
            "material": "glass",
            "intensity": "medium",
            "rhythm": "irregular",
            "texture": "tapping",
            "potential_sound": "Rain taps on glass",
            "confidence": 0.9,
            "visual_evidence": "Raindrops are visible on the pane.",
        }],
    }


class SceneJsonParserTests(unittest.TestCase):
    def test_plain_json_preserves_scene_schema_and_event_timestamps(self):
        parsed = parse_model_response(json.dumps(_scene(), ensure_ascii=False))
        self.assertEqual(parsed["scene_summary"], "A scene with rain.")
        self.assertEqual(parsed["events"][0]["timestamp_end"], 1.25)
        self.assertEqual(parsed["events"][0]["potential_sound"], "Rain taps on glass")

    def test_markdown_wrapper_and_prefix_are_extracted_safely(self):
        raw = "Here is the analysis:\n```json\n" + json.dumps(_scene()) + "\n```"
        self.assertEqual(parse_model_response(raw)["events"][0]["action"], "rain hitting a window")

    def test_escaped_quotes_unicode_and_newlines_are_decoded(self):
        document = _scene('A sign says "雨" — snow follows.\nThe scene remains quiet.')
        document["events"][0]["visual_evidence"] = 'The sign reads "雨" beside a café.'
        parsed = parse_model_response(json.dumps(document, ensure_ascii=False))
        self.assertEqual(parsed["scene_summary"], document["scene_summary"])
        self.assertEqual(parsed["events"][0]["visual_evidence"], document["events"][0]["visual_evidence"])

    def test_malformed_schema_invalid_and_truncated_json_are_rejected_without_repair(self):
        with self.assertRaisesRegex(ValueError, "malformed JSON"):
            parse_model_response('{"scene_summary":"Rain" "events":[]}')
        with self.assertRaisesRegex(ValueError, "incomplete or truncated"):
            parse_model_response('{"scene_summary":"Rain", "events":[{"action":"rain", "source_object":"')
        with self.assertRaisesRegex(ValueError, "must be a list"):
            parse_model_response('{"scene_summary":"Rain", "events":"rain"}')

    def test_token_limit_detection_checks_eos_before_classifying_truncation(self):
        inputs = torch.tensor([[10, 11]])
        self.assertTrue(_generation_was_truncated(torch.tensor([10, 11, 20, 21]), inputs[0], 2, [99]))
        self.assertFalse(_generation_was_truncated(torch.tensor([10, 11, 20, 99]), inputs[0], 2, [99]))
        self.assertFalse(_generation_was_truncated(torch.tensor([10, 11, 99]), inputs[0], 2, [99]))


class _FakeInputs(dict):
    def __init__(self):
        super().__init__(input_ids=torch.tensor([[10, 11]]))

    @property
    def input_ids(self):
        return self["input_ids"]

    def to(self, _device):
        return self


class _FakeProcessor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def apply_chat_template(self, messages, **_kwargs):
        self.prompts.append(messages[0]["content"][-1]["text"])
        return "formatted prompt"

    def __call__(self, **_kwargs):
        return _FakeInputs()

    def batch_decode(self, sequences, **_kwargs):
        self.last_decoded_ids = sequences[0].tolist()
        return [self.responses.pop(0)]


class _FakeModel:
    device = "cpu"
    generation_config = SimpleNamespace(eos_token_id=[99])

    def __init__(self):
        self.calls = []

    def generate(self, input_ids, **kwargs):
        self.calls.append(kwargs)
        return torch.cat([input_ids, torch.tensor([[20, 99]])], dim=1)


class SceneGenerationRetryTests(unittest.TestCase):
    def _run(self, responses):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        frame = Path(temporary.name) / "frame.jpg"
        frame.write_bytes(b"test frame marker")
        processor = _FakeProcessor(responses)
        model = _FakeModel()
        local_temp = Path(temporary.name) / "diagnostics"
        stack = patch("ai_foley_studio.video.scene_analyzer.TEMP_DIR", local_temp)
        stack.start()
        self.addCleanup(stack.stop)
        vision = patch("ai_foley_studio.video.scene_analyzer.process_vision_info", return_value=([object()], None))
        vision.start()
        self.addCleanup(vision.stop)
        result = None
        error = None
        try:
            result = analyze_scenes([{"timestamp": 0.0, "path": frame}], model=model, processor=processor)
        except ValueError as exc:
            error = exc
        return result, error, model, processor, local_temp

    def test_invalid_first_response_gets_one_controlled_regeneration(self):
        valid = json.dumps(_scene("Rain over café — 夜."), ensure_ascii=False)
        result, error, model, processor, diagnostics = self._run([
            '{"scene_summary":"cut off", "events":[{"action":"rain", "source_object":"', valid,
        ])
        self.assertIsNone(error)
        self.assertEqual(len(model.calls), 2)
        self.assertEqual([call["max_new_tokens"] for call in model.calls], [4096, 8192])
        for call in model.calls:
            self.assertIs(call["do_sample"], False)
            self.assertIsNone(call["temperature"])
            self.assertIsNone(call["top_p"])
            self.assertIsNone(call["top_k"])
        self.assertIn("previous response was incomplete", processor.prompts[1])
        self.assertEqual(processor.last_decoded_ids, [20, 99])  # prompt tokens are not decoded as model output
        self.assertEqual(result["events"][0]["timestamp_end"], 1.25)
        self.assertTrue((diagnostics / "qwen_raw_response_failure.txt").is_file())
        self.assertEqual((diagnostics / "qwen_raw_response.txt").read_text(encoding="utf-8"), valid)

    def test_second_invalid_response_fails_without_a_third_generation(self):
        result, error, model, _processor, _diagnostics = self._run(["{", "{"])
        self.assertIsNone(result)
        self.assertEqual(len(model.calls), 2)
        self.assertIn("after one controlled regeneration", str(error))


if __name__ == "__main__":
    unittest.main()
