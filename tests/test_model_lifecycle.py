"""Regression tests for explicit Qwen/MMAudio model lifecycle boundaries."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from ai_foley_studio.audio.mmaudio_service import MMAudioService
from ai_foley_studio.config import FoleySettings
from ai_foley_studio.pipeline import FoleyPipeline
from ai_foley_studio.video import scene_analyzer


class _FakeCuda:
    def __init__(self) -> None:
        self.empty_cache_called = False
        self.ipc_collect_called = False

    def is_available(self) -> bool:
        return True

    def mem_get_info(self) -> tuple[int, int]:
        return 100, 200

    def memory_allocated(self) -> int:
        return 10

    def memory_reserved(self) -> int:
        return 20

    def empty_cache(self) -> None:
        self.empty_cache_called = True

    def ipc_collect(self) -> None:
        self.ipc_collect_called = True


class _FakeTorch:
    def __init__(self) -> None:
        self.cuda = _FakeCuda()


class ModelLifecycleTests(unittest.TestCase):
    def test_release_scene_model_reclaims_cuda_cache_after_references_drop(self) -> None:
        fake_torch = _FakeTorch()
        with patch.object(scene_analyzer, "torch", fake_torch):
            scene_analyzer.release_scene_model(object(), object())
        self.assertTrue(fake_torch.cuda.empty_cache_called)
        self.assertTrue(fake_torch.cuda.ipc_collect_called)

    def test_pipeline_close_delegates_to_mmaudio_service(self) -> None:
        pipeline = object.__new__(FoleyPipeline)
        pipeline.mmaudio_service = Mock()
        pipeline.close()
        pipeline.mmaudio_service.close.assert_called_once_with()

    def test_mmaudio_adapter_imports_the_configured_project_source(self) -> None:
        service = MMAudioService(FoleySettings())
        bindings = service._import_bindings()
        self.assertIsNotNone(bindings.get_my_mmaudio)
