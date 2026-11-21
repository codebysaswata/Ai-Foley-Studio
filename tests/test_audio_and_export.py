"""Unit tests for audio timing, video metadata fallback, mux commands, and metadata."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_foley_studio.audio.audio_processor import AudioProcessor
from ai_foley_studio.audio.synchronizer import inspect_video
from ai_foley_studio.export.video_exporter import build_mux_command
from ai_foley_studio.pipeline import FoleyPipeline, PipelineConfig, _JobState


@unittest.skipUnless(
    importlib.util.find_spec("torch") and importlib.util.find_spec("torchaudio"),
    "requires torch and torchaudio",
)
class AudioProcessorTests(unittest.TestCase):
    def _write_tone(self, root: Path) -> Path:
        import torch
        import torchaudio

        sample_rate = 16_000
        path = root / "tone.wav"
        waveform = torch.full((1, sample_rate), 0.2, dtype=torch.float32)
        torchaudio.save(str(path), waveform, sample_rate)
        return path

    def test_inspection_trim_and_offsets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_tone(root)
            processor = AudioProcessor()
            initial = processor.inspect(source)
            self.assertAlmostEqual(initial.duration_seconds, 1.0, places=3)
            trimmed = processor.trim_to_duration(source, root / "trimmed.wav", 0.25)
            self.assertAlmostEqual(trimmed.duration_seconds, 0.25, places=3)
            delayed = processor.apply_timing_offset(source, root / "delayed.wav", 0.25, target_duration=1.0)
            advanced = processor.apply_timing_offset(source, root / "advanced.wav", -0.25, target_duration=1.0)
            self.assertAlmostEqual(delayed.duration_seconds, 1.0, places=3)
            self.assertAlmostEqual(advanced.duration_seconds, 1.0, places=3)

    def test_loudness_reports_missing_ffmpeg_clearly(self) -> None:
        from ai_foley_studio.audio.audio_processor import AudioProcessingError

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_tone(root)
            processor = AudioProcessor(ffmpeg_executable="ffmpeg-not-installed-for-test")
            with self.assertRaises(AudioProcessingError):
                processor.normalize_loudness(source, root / "normalized.wav")


class VideoAndOutputTests(unittest.TestCase):
    def test_build_mux_command_has_explicit_stream_mapping(self) -> None:
        command = build_mux_command("source.mp4", "foley.wav", "result.mp4")
        self.assertIn("0:v:0", command)
        self.assertIn("1:a:0", command)
        self.assertNotIn("-shortest", command)
        self.assertIn("copy", command)

    def test_pipeline_metadata_is_serializable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = _JobState(
                job_id="job_test",
                job_dir=root,
                metadata_path=root / "metadata.json",
                video_path=root / "input.mp4",
                scene_analysis_path=root / "scene_analysis.json",
                sound_context_path=root / "sound_context.json",
            )
            pipeline = object.__new__(FoleyPipeline)
            pipeline._write_metadata(
                state,
                status="failed",
                config=PipelineConfig(duration=4.0),
                error={"type": "Example", "message": "expected"},
            )
            payload = json.loads(state.metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["config"]["duration"], 4.0)

    def test_inspect_video_rejects_missing_input(self) -> None:
        with self.assertRaises(Exception):
            inspect_video("this-file-does-not-exist.mp4")
