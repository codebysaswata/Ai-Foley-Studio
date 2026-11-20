"""Server-owned storage layout and single-process GPU service guard."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from uuid import UUID, uuid4

from ai_foley_studio.api.settings import ApiSettings
from ai_foley_studio.api.store import JobStore


class StorageError(RuntimeError):
    pass


class SingleProcessLock:
    """OS-level lock prevents multiple API workers sharing one local GPU/SQLite DB."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._stream = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("a+b")
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            stream.close()
            raise StorageError("Another AI Foley API process already owns the local worker lock.") from exc
        self._stream = stream

    def release(self) -> None:
        stream, self._stream = self._stream, None
        if stream is None:
            return
        try:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()


class JobStorage:
    def __init__(self, settings: ApiSettings) -> None:
        self.settings = settings
        self.root = settings.data_dir.resolve()
        self.jobs_root = settings.jobs_dir.resolve()

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir() or not self.jobs_root.is_dir():
            raise StorageError("Configured API data storage is not a directory.")

    def create_job(self) -> tuple[str, dict[str, Path]]:
        job_id = str(uuid4())
        root = self.job_dir(job_id)
        root.mkdir(parents=False, exist_ok=False)
        paths = {
            "root": root,
            "input": root / "input",
            "working": root / "working",
            "output": root / "output",
            "metadata": root / "metadata",
        }
        for name in ("input", "working", "output", "metadata"):
            paths[name].mkdir()
        (paths["metadata"] / "job.json").write_text(
            json.dumps({"job_id": job_id, "storage_version": 1}, indent=2), encoding="utf-8"
        )
        return job_id, paths

    def job_dir(self, job_id: str) -> Path:
        try:
            canonical_id = str(UUID(job_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise StorageError("Invalid job identifier.") from exc
        candidate = (self.jobs_root / canonical_id).resolve()
        if not candidate.is_relative_to(self.jobs_root):
            raise StorageError("Job path escaped the configured storage root.")
        return candidate

    def registered_job_dir(self, job_id: str) -> Path | None:
        root = self.job_dir(job_id)
        marker = root / "metadata" / "job.json"
        if not marker.is_file():
            return None
        try:
            value = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return root if value.get("job_id") == job_id else None

    def remove_expired(self, store: JobStore) -> int:
        removed = 0
        for row in store.expired(self.settings.retention_days):
            root = self.registered_job_dir(row["job_id"])
            if root is None or root.parent != self.jobs_root:
                continue
            shutil.rmtree(root)
            store.delete_record(row["job_id"])
            removed += 1
        return removed

    def relative_path(self, path: Path, job_id: str) -> str:
        root = self.job_dir(job_id)
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise StorageError("Artifact path is outside its job directory.")
        return str(resolved.relative_to(root))

    def artifact_path(self, job_id: str, relative_path: str) -> Path:
        root = self.registered_job_dir(job_id)
        if root is None:
            raise StorageError("Job storage is unavailable.")
        candidate = (root / relative_path).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise StorageError("Artifact path is invalid or unavailable.")
        return candidate
