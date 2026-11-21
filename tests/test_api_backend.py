"""Isolated API and persistent job-manager integration tests (mocked inference only)."""

from __future__ import annotations

import tempfile
import time
import unittest
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from ai_foley_studio.api.manager import JobManager
from ai_foley_studio.api.main import create_app
from ai_foley_studio.api.media import safe_upload_extension, save_upload_stream
from ai_foley_studio.api.schemas import JobOptions, SceneEventDocument
from ai_foley_studio.api.settings import ApiSettings
from ai_foley_studio.api.storage import JobStorage, StorageError
from ai_foley_studio.api.store import JobStore


class _FakePipeline:
    def close(self):
        pass

    def run(self, video, scene, sound, config, *, progress_callback=None, should_cancel=None):
        output = Path(config.output_dir) / "processed_foley.wav"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"mock-wav")
        if progress_callback:
            progress_callback({"stage": "generating_audio", "progress": 66, "current_chunk": 1, "total_chunks": 1})
        return SimpleNamespace(
            processed_audio_path=output,
            processed_audio=SimpleNamespace(duration_seconds=1.0),
            final_video_path=None,
            export=None,
        )


class _ByteUpload:
    def __init__(self, content: bytes):
        self.content = content
        self.offset = 0

    async def read(self, size: int) -> bytes:
        result = self.content[self.offset:self.offset + size]
        self.offset += len(result)
        return result


class ApiBackendTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.settings = ApiSettings(
            data_dir=self.root / "data", bearer_token="unit-test-token-that-is-long-enough",
            cors_origins=("http://localhost:3000",), ffmpeg="ffmpeg", ffprobe="ffprobe",
        )
        self.app = create_app(self.settings)

    def tearDown(self):
        self.temporary.cleanup()

    def test_health_auth_cors_and_openapi(self):
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                async with AsyncClient(transport=ASGITransport(app=self.app), base_url="http://test") as client:
                    self.assertEqual((await client.get("/health/live")).status_code, 200)
                    with patch.object(self.app.state.runtime, "readiness", return_value=(False, {"worker": True})):
                        readiness = await client.get("/health/ready")
                    self.assertEqual(readiness.status_code, 503)
                    self.assertEqual(readiness.json()["status"], "not_ready")
                    self.assertIn("/api/v1/jobs", (await client.get("/openapi.json")).json()["paths"])
                    self.assertEqual((await client.get("/api/v1/jobs")).status_code, 401)
                    response = await client.options(
                        "/api/v1/jobs", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"}
                    )
                    self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:3000")
        asyncio.run(scenario())

    def test_upload_job_status_listing_and_artifact_security(self):
        client_token = {"Authorization": f"Bearer {self.settings.bearer_token}"}
        async def scenario():
          with patch("ai_foley_studio.api.routes.validate_video_media", return_value={
            "duration_seconds": 1.0, "width": 640, "height": 360, "video_codec": "h264",
            "container": ["mov", "mp4"], "server_extension": ".mp4",
          }):
            app = create_app(self.settings, manager=JobManager(self.settings, pipeline_factory=_FakePipeline))
            async with app.router.lifespan_context(app):
              async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # Exercise supplied context so mocked inference does not invoke Qwen/FFmpeg.
                accepted = client.post(
                    "/api/v1/jobs", headers=client_token,
                    files={
                        "video": ("../../client.mp4", b"mock-video", "video/mp4"),
                        "scene_analysis": ("scene.json", b'{"scene_summary":"forest waterfall","events":[{"action":"waterfall","timestamp_start":0,"timestamp_end":1}]}', "application/json"),
                        "sound_context": ("sound.json", b'{"scene_summary":"forest waterfall","sound_contexts":[{"action":"waterfall","timestamp_start":0,"timestamp_end":1}]}', "application/json"),
                    },
                    data={"export_video": "false"},
                )
                accepted = await accepted
                self.assertEqual(accepted.status_code, 202, accepted.text)
                job_id = accepted.json()["job_id"]
                status = None
                for _ in range(500):
                    status = (await client.get(f"/api/v1/jobs/{job_id}", headers=client_token)).json()
                    if status["status"] in {"succeeded", "failed", "cancelled"}:
                        break
                    time.sleep(0.02)
                self.assertEqual(status["status"], "succeeded", status)
                self.assertEqual(status["artifacts"][0]["name"], "processed_foley.wav")
                listing = await client.get("/api/v1/jobs?limit=5&offset=0", headers=client_token)
                self.assertEqual(listing.status_code, 200)
                self.assertEqual(listing.json()["total"], 1)
                artifact = await client.get(status["artifacts"][0]["download_url"], headers=client_token)
                self.assertEqual(artifact.content, b"mock-wav")
                self.assertEqual((await client.get(f"/api/v1/jobs/{job_id}/artifacts/..%2F..%2Fsecret", headers=client_token)).status_code, 404)
                self.assertEqual((await client.post("/api/v1/jobs", headers=client_token, files={})).status_code, 422)
        asyncio.run(scenario())

    def test_sqlite_restart_reconciliation_and_path_containment(self):
        store = JobStore(self.root / "test.sqlite3")
        store.initialize()
        record = {
            "job_id": "2db621d0-f7fd-468f-a29c-6cad8c21bd04", "job_dir": self.root / "job",
            "video_path": self.root / "job" / "video.mp4", "options": {},
        }
        self.assertTrue(store.create(record, max_queued_jobs=1))
        self.assertFalse(store.create({**record, "job_id": "3db621d0-f7fd-468f-a29c-6cad8c21bd04"}, max_queued_jobs=1))
        self.assertTrue(store.mark_running(record["job_id"]))
        queued = store.reconcile_after_restart()
        self.assertEqual(queued, [])
        self.assertEqual(store.get(record["job_id"])["status"], "failed")

    def test_schema_limits_and_upload_filename_handling(self):
        with self.assertRaises(ValueError):
            SceneEventDocument(action="rain", timestamp_start=3, timestamp_end=2)
        with self.assertRaises(ValueError):
            JobOptions(chunk_seconds=20)
        self.assertEqual(safe_upload_extension("../../clip.MP4"), ".mp4")
        with self.assertRaises(Exception):
            safe_upload_extension("../../payload.exe")

    def test_streamed_upload_limit_and_storage_containment(self):
        async def over_limit():
            destination = self.root / "large.bin"
            with self.assertRaises(Exception):
                await save_upload_stream(_ByteUpload(b"123456"), destination, max_bytes=5)
            self.assertFalse(destination.exists())
        asyncio.run(over_limit())

        storage = JobStorage(self.settings)
        storage.initialize()
        job_id, _ = storage.create_job()
        with self.assertRaises(StorageError):
            storage.artifact_path(job_id, "../../outside.txt")

    def test_cancellation_state_transitions(self):
        store = JobStore(self.root / "cancel.sqlite3")
        store.initialize()
        queued_id = "4db621d0-f7fd-468f-a29c-6cad8c21bd04"
        record = {"job_id": queued_id, "job_dir": self.root / "job", "video_path": self.root / "job" / "v.mp4", "options": {}}
        self.assertTrue(store.create(record, max_queued_jobs=3))
        queued = store.request_cancel(queued_id)
        self.assertEqual(queued["status"], "cancelled")

        running_id = "5db621d0-f7fd-468f-a29c-6cad8c21bd04"
        self.assertTrue(store.create({**record, "job_id": running_id}, max_queued_jobs=3))
        self.assertTrue(store.mark_running(running_id))
        pending = store.request_cancel(running_id)
        self.assertEqual(pending["status"], "running")
        self.assertTrue(pending["cancel_requested"])
        store.finish_cancelled(running_id)
        self.assertEqual(store.get(running_id)["status"], "cancelled")

    def test_chunk_progress_survives_later_non_chunk_stages(self):
        store = JobStore(self.root / "progress.sqlite3")
        store.initialize()
        job_id = "6db621d0-f7fd-468f-a29c-6cad8c21bd04"
        record = {"job_id": job_id, "job_dir": self.root / "job", "video_path": self.root / "job" / "v.mp4", "options": {}}
        self.assertTrue(store.create(record, max_queued_jobs=2))
        self.assertTrue(store.mark_running(job_id))
        store.update_progress(job_id, {
            "stage": "generating_audio", "progress": 82, "current_chunk": 4,
            "total_chunks": 4, "chunk_status": "accepted", "chunk_metrics": {"interior_rms": 0.1},
        })
        store.update_progress(job_id, {"stage": "exporting_video", "progress": 94})
        row = store.get(job_id)
        self.assertEqual((row["current_chunk"], row["total_chunks"]), (4, 4))
        self.assertEqual(row["chunk_details"]["chunk_status"], "accepted")


if __name__ == "__main__":
    unittest.main()
