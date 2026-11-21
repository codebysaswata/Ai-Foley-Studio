"""Unit coverage for full-duration chunk planning and audio assembly."""

from __future__ import annotations

import unittest
import tempfile
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ai_foley_studio.audio.chunked_generation import (
    ChunkQualityPolicy,
    ChunkGenerationError,
    assign_events_to_chunks,
    build_chunk_prompt,
    calculate_chunks,
    generate_chunked,
    inspect_chunk_waveform,
    merge_waveforms,
)
from ai_foley_studio.audio.mmaudio_service import GenerationResult
from ai_foley_studio.intelligence.context_engine import FoleyEvent, NormalizedFoleyContext
from ai_foley_studio.intelligence.prompt_engine import PromptEngine


class ChunkPlanningTests(unittest.TestCase):
    def test_chunk_ranges_cover_video_and_respect_call_limit(self) -> None:
        chunks = calculate_chunks(20.0, 4.0, 0.1)
        self.assertEqual(chunks[0].core_start, 0.0)
        self.assertAlmostEqual(chunks[-1].core_end, 20.0)
        self.assertEqual(len(chunks), 6)
        for chunk in chunks:
            self.assertLessEqual(chunk.source_end - chunk.source_start, 4.0 + 1e-9)
        for left, right in zip(chunks, chunks[1:]):
            self.assertAlmostEqual(left.core_end, right.core_start)
            self.assertAlmostEqual(left.source_end - right.source_start, 0.1)

    def test_rejects_invalid_chunk_inputs(self) -> None:
        for values in ((0.0, 4.0, 0.1), (5.0, 0.1, 0.1), (5.0, 4.0, -0.1)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                calculate_chunks(*values)

    def test_balances_short_tail_to_fit_synchformer_window(self) -> None:
        chunks = calculate_chunks(12.027937, 4.0, 0.1)
        self.assertEqual(len(chunks), 4)
        self.assertGreater(chunks[-1].source_end - chunks[-1].source_start, 16 / 25)
        for chunk in chunks:
            self.assertGreaterEqual(chunk.source_end - chunk.source_start, 16 / 25)
            self.assertLessEqual(chunk.source_end - chunk.source_start, 4.0 + 1e-9)
        self.assertAlmostEqual(chunks[0].core_start, 0.0)
        self.assertAlmostEqual(chunks[-1].core_end, 12.027937)
        for left, right in zip(chunks, chunks[1:]):
            self.assertAlmostEqual(left.core_end, right.core_start)
            self.assertAlmostEqual(left.source_end - right.source_start, 0.1)

    def test_rejects_video_shorter_than_mmaudio_sync_window(self) -> None:
        with self.assertRaisesRegex(ValueError, "minimum sync window"):
            calculate_chunks(0.5, 4.0, 0.1)

    def test_events_are_assigned_to_every_overlapping_core(self) -> None:
        chunks = calculate_chunks(8.0, 8.0, 0.1)
        crossing = FoleyEvent(3.8, 4.2, "gate closes")
        first_only = FoleyEvent(0.5, 1.0, "footsteps")
        unlocated = FoleyEvent(None, None, "ambient action")
        assigned = assign_events_to_chunks((crossing, first_only, unlocated), chunks)
        self.assertEqual(len(assigned[0]), 3)
        self.assertEqual(assigned[0][1], first_only)
        self.assertEqual(assigned[0][2], unlocated)
        self.assertEqual(assigned[1][1], unlocated)
        self.assertEqual((assigned[0][0].timestamp_start, assigned[0][0].timestamp_end), (3.8, 4.0))
        self.assertEqual((assigned[1][0].timestamp_start, assigned[1][0].timestamp_end), (4.0, 4.2))

    def test_transient_at_boundary_keeps_original_time_and_is_assigned_once(self) -> None:
        chunks = calculate_chunks(8.0, 8.0, 0.1)
        transient = FoleyEvent(4.0, 4.0, "metal gate slam")
        assigned = assign_events_to_chunks((transient,), chunks)
        self.assertEqual(assigned[0], ())
        self.assertEqual(assigned[1][0].timestamp_start, 4.0)
        self.assertEqual(assigned[1][0].timestamp_end, 4.0)


class ChunkAssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            import torch
        except ImportError:
            raise unittest.SkipTest("requires torch")
        cls.torch = torch

    def test_waveform_quality_measures_interior_and_short_transient_silence(self) -> None:
        torch = self.torch
        waveform = torch.full((1, 16_000), 0.02)
        metrics = inspect_chunk_waveform(
            waveform, 16_000, 1.0, continuous_required=True,
        )
        self.assertAlmostEqual(metrics.full_rms, 0.02, places=5)
        self.assertAlmostEqual(metrics.interior_rms, 0.02, places=5)
        self.assertAlmostEqual(metrics.sample_peak, 0.02, places=6)
        self.assertEqual(metrics.status, "accepted")

        transient_then_silence = torch.zeros((1, 16_000))
        transient_then_silence[0, :100] = 0.5
        metrics = inspect_chunk_waveform(
            transient_then_silence, 16_000, 1.0, continuous_required=True,
        )
        self.assertGreater(metrics.full_rms, 0.0)
        self.assertAlmostEqual(metrics.interior_rms, 0.0)
        self.assertEqual(metrics.sample_peak, 0.5)
        self.assertEqual(metrics.status, "rejected")

    def test_quiet_noncontinuous_audio_is_not_forced_louder_or_rejected(self) -> None:
        quiet = self.torch.full((1, 16_000), 0.0002)
        metrics = inspect_chunk_waveform(quiet, 16_000, 1.0, continuous_required=False)
        self.assertEqual(metrics.status, "accepted")
        self.assertAlmostEqual(metrics.interior_rms, 0.0002, places=6)
        self.assertAlmostEqual(float(quiet.max().item()), 0.0002, places=7)
        chunks = calculate_chunks(1.0, 1.1)
        merged = merge_waveforms([quiet], chunks, 16_000, 1.0)
        self.assertTrue(self.torch.equal(merged, quiet))

    def test_continuous_event_context_reaches_every_chunk_prompt(self) -> None:
        chunks = calculate_chunks(12.0, 4.0)
        event = FoleyEvent(
            0.0, 12.0, "river", rhythm="continuous",
            potential_sound="steady flowing water", environment="forest",
        )
        groups = assign_events_to_chunks((event,), chunks)
        self.assertEqual(len(groups), 4)
        for chunk, group in zip(chunks, groups):
            self.assertEqual(len(group), 1)
            self.assertEqual(group[0].timestamp_start, chunk.core_start)
            self.assertEqual(group[0].timestamp_end, chunk.core_end)
            prompt, _ = build_chunk_prompt(
                NormalizedFoleyContext("A river in a forest", (event,), Path("scene"), Path("sound")),
                group, PromptEngine(),
            )
            self.assertIn("river", prompt.lower())
            self.assertIn("flowing water", prompt.lower())

    def test_rejects_invalid_duration_and_clipped_samples(self) -> None:
        torch = self.torch
        short = inspect_chunk_waveform(
            torch.ones((1, 8_000)) * 0.1, 16_000, 1.0, continuous_required=True,
        )
        self.assertIn("short", short.reason)
        clipped = torch.full((1, 16_000), 0.1)
        clipped[0, :10] = 1.0
        metrics = inspect_chunk_waveform(clipped, 16_000, 1.0, continuous_required=True)
        self.assertGreater(metrics.clipped_sample_ratio, 0)
        self.assertEqual(metrics.status, "rejected")

    def test_quality_policy_validates_retry_configuration(self) -> None:
        with self.assertRaises(ValueError):
            ChunkQualityPolicy(maximum_retries=-1)

    def _run_retry_case(self, candidates, maximum_retries=2):
        import torchaudio

        root = Path(tempfile.mkdtemp())
        event = FoleyEvent(
            0.0, 1.0, "waterfall", rhythm="continuous",
            potential_sound="rushing water and splashing", environment="forest",
        )
        context = NormalizedFoleyContext(
            "A waterfall flowing through a forest", (event,), root / "scene.json", root / "sound.json"
        )

        class FakeService:
            def __init__(self):
                self.seeds = []

            def generate(self, _video, _prompt, output, *, seed, **_kwargs):
                index = len(self.seeds)
                self.seeds.append(seed)
                torchaudio.save(str(output), candidates[index], 16_000)
                return GenerationResult(
                    audio_path=Path(output), format="flac", sample_rate=16_000,
                    channels=1, duration_seconds=1.0, model_variant="test",
                    device="cpu", precision="float32", inference_seconds=0.1,
                    peak_cuda_memory_bytes=None,
                )

        def extract_segment(command, **_kwargs):
            Path(command[-1]).write_bytes(b"video segment")
            return SimpleNamespace(returncode=0, stderr="")

        service = FakeService()
        with patch("ai_foley_studio.audio.chunked_generation.shutil.which", return_value="ffmpeg"), \
             patch("ai_foley_studio.audio.chunked_generation.subprocess.run", side_effect=extract_segment):
            result = generate_chunked(
                root / "source.mp4", context, PromptEngine(), service,
                SimpleNamespace(inspect=lambda _path: SimpleNamespace(duration_seconds=1.0)),
                root / "combined.flac", video_duration=1.0, max_chunk_seconds=1.1,
                prompt_override="Continuous waterfall sound",
                quality_policy=ChunkQualityPolicy(maximum_retries=maximum_retries),
            )
        return root, result, service

    def test_retries_rejected_continuous_chunk_and_accepts_valid_candidate(self) -> None:
        torch = self.torch
        failed = torch.zeros((1, 16_000))
        failed[0, :100] = 0.4
        valid = torch.full((1, 16_000), 0.02)
        root, result, service = self._run_retry_case([failed, valid])
        report = result.chunk_reports[0]
        self.assertEqual(report["status"], "accepted")
        self.assertEqual(report["retry_count"], 1)
        self.assertEqual(report["attempts"][0]["status"], "rejected")
        self.assertEqual(report["attempts"][1]["status"], "accepted")
        self.assertNotEqual(service.seeds[0], service.seeds[1])
        self.assertAlmostEqual(report["attempts"][1]["metrics"]["interior_rms"], 0.02, places=4)
        self.assertEqual(result.generation.duration_seconds, 1.0)
        shutil.rmtree(root)

    def test_exhausted_retries_fail_and_preserve_rejected_audio(self) -> None:
        torch = self.torch
        failed = torch.zeros((1, 16_000))
        failed[0, :100] = 0.4
        root = None
        try:
            root, _result, _service = self._run_retry_case([failed, failed.clone(), failed.clone()])
        except ChunkGenerationError as exc:
            self.assertIn("chunk 1/1 failed quality validation", str(exc))
            diagnostic_directory = Path(str(exc).split("retained in ", 1)[1].rstrip("."))
            root = diagnostic_directory.parent
            self.assertEqual(len(list(diagnostic_directory.glob("chunk_0001_attempt_*.flac"))), 3)
        else:
            self.fail("near-silent continuous chunk should fail after bounded retries")
        finally:
            if root is not None:
                shutil.rmtree(root)

    def test_chronological_crossfade_matches_video_duration(self) -> None:
        torch = self.torch
        chunks = calculate_chunks(2.0, 1.1, 0.1)
        # First segment contains 1.1 seconds of value 1; the next contains one
        # second of value 0, so the 100 ms overlap has a visible midpoint mix.
        waveforms = [torch.ones((1, 110)), torch.zeros((1, 100))]
        merged = merge_waveforms(waveforms, chunks, 100, 2.0, 0.1)
        self.assertEqual(merged.shape, (1, 200))
        self.assertAlmostEqual(float(merged[0, 95].item()), 1.0, places=5)
        self.assertAlmostEqual(float(merged[0, 105].item()), 0.444, places=2)
        self.assertAlmostEqual(float(merged[0, -1].item()), 0.0, places=5)

    def test_missing_failed_or_short_chunks_are_not_silence_padded(self) -> None:
        torch = self.torch
        chunks = calculate_chunks(2.0, 1.1, 0.1)
        with self.assertRaisesRegex(ChunkGenerationError, "one generated waveform"):
            merge_waveforms([torch.ones((1, 110))], chunks, 100, 2.0, 0.1)
        with self.assertRaisesRegex(ChunkGenerationError, "short by"):
            merge_waveforms(
                [torch.ones((1, 110)), torch.ones((1, 80))], chunks, 100, 2.0, 0.1
            )

    def test_model_failure_is_reported_with_chunk_number(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = NormalizedFoleyContext(
                "A quiet room", (), root / "scene.json", root / "sound.json"
            )

            def extract_segment(command, **_kwargs):
                Path(command[-1]).write_bytes(b"video segment")
                return SimpleNamespace(returncode=0, stderr="")

            class FailedService:
                def generate(self, *_args, **_kwargs):
                    raise RuntimeError("inference failed")

            with patch("ai_foley_studio.audio.chunked_generation.shutil.which", return_value="ffmpeg"), \
                 patch("ai_foley_studio.audio.chunked_generation.subprocess.run", side_effect=extract_segment):
                with self.assertRaisesRegex(ChunkGenerationError, "chunk 1/1 failed quality validation.*inference failed"):
                    generate_chunked(
                        root / "source.mp4", context,
                        SimpleNamespace(build=lambda *_args, **_kwargs: SimpleNamespace(
                            prompt="quiet ambience", negative_prompt="speech"
                        )),
                        FailedService(), SimpleNamespace(), root / "combined.flac",
                        video_duration=1.0, max_chunk_seconds=1.1,
                    )

    def test_mmaudio_prompt_covers_waterfall_sound(self) -> None:
        from ai_foley_studio.intelligence.context_engine import FoleyEvent

        event = FoleyEvent(
            timestamp_start=0.0,
            timestamp_end=1.0,
            action="waterfall",
            material="water",
            intensity="high",
            texture="smooth",
            potential_sound="Water splashing and flowing",
            confidence=0.95,
        )
        context = NormalizedFoleyContext(
            "A waterfall in a forest", (event,), Path("scene.json"), Path("sound.json")
        )
        prompt = PromptEngine().build(context).prompt.lower()
        self.assertIn("water", prompt)
        self.assertIn("water movement", prompt)

    def test_unmapped_event_uses_its_free_form_potential_sound(self) -> None:
        event = FoleyEvent(
            timestamp_start=1.0,
            timestamp_end=2.0,
            action="fire burning",
            potential_sound="Dry fire crackling and popping",
            confidence=0.9,
        )
        context = NormalizedFoleyContext(
            "A campfire outdoors", (event,), Path("scene.json"), Path("sound.json")
        )
        prompt, _negative = build_chunk_prompt(context, (event,), PromptEngine())
        self.assertIn("Dry fire crackling and popping", prompt)

    def test_wrapped_generation_error_surfaces_root_cause(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = NormalizedFoleyContext(
                "A quiet room", (), root / "scene.json", root / "sound.json"
            )

            def extract_segment(command, **_kwargs):
                Path(command[-1]).write_bytes(b"video segment")
                return SimpleNamespace(returncode=0, stderr="")

            class FailedService:
                def generate(self, *_args, **_kwargs):
                    try:
                        raise RuntimeError("stack expects a non-empty TensorList")
                    except RuntimeError as cause:
                        raise RuntimeError("MMAudio waveform generation failed") from cause

            with patch("ai_foley_studio.audio.chunked_generation.shutil.which", return_value="ffmpeg"), \
                 patch("ai_foley_studio.audio.chunked_generation.subprocess.run", side_effect=extract_segment):
                with self.assertRaisesRegex(
                    ChunkGenerationError, "root cause: RuntimeError: stack expects a non-empty TensorList"
                ):
                    generate_chunked(
                        root / "source.mp4", context,
                        SimpleNamespace(build=lambda *_args, **_kwargs: SimpleNamespace(
                            prompt="quiet ambience", negative_prompt="speech"
                        )),
                        FailedService(), SimpleNamespace(), root / "combined.flac",
                        video_duration=1.0, max_chunk_seconds=1.1,
                    )


if __name__ == "__main__":
    unittest.main()
