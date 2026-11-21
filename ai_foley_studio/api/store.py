"""Small SQLite job registry; connections are short-lived and thread-safe."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class JobStore:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=15000")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','cancelled')),
                    stage TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0,
                    current_chunk INTEGER,
                    total_chunks INTEGER,
                    chunk_details_json TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT,
                    error_message TEXT,
                    options_json TEXT NOT NULL,
                    job_dir TEXT NOT NULL,
                    video_path TEXT NOT NULL,
                    scene_path TEXT,
                    sound_path TEXT,
                    artifacts_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL
                )"""
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at)")

    def create(self, record: dict[str, Any], max_queued_jobs: int) -> bool:
        """Atomically reserve a queue slot and persist a new queued job."""
        now = utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            queued = connection.execute("SELECT COUNT(*) FROM jobs WHERE status='queued'").fetchone()[0]
            if queued >= max_queued_jobs:
                connection.rollback()
                return False
            connection.execute(
                """INSERT INTO jobs (
                    job_id,status,stage,progress,created_at,options_json,job_dir,video_path,
                    scene_path,sound_path,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record["job_id"], "queued", "queued", 0.0, now,
                    json.dumps(record["options"], ensure_ascii=False), str(record["job_dir"]),
                    str(record["video_path"]),
                    str(record["scene_path"]) if record.get("scene_path") else None,
                    str(record["sound_path"]) if record.get("sound_path") else None,
                    now,
                ),
            )
            connection.commit()
        return True

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._decode(row) if row else None

    def list(self, *, limit: int, offset: int, status: str | None = None) -> tuple[list[dict[str, Any]], int]:
        where = " WHERE status=?" if status else ""
        values = (status,) if status else ()
        with self._connect() as connection:
            total = int(connection.execute(f"SELECT COUNT(*) FROM jobs{where}", values).fetchone()[0])
            rows = connection.execute(
                f"SELECT * FROM jobs{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (*values, limit, offset),
            ).fetchall()
        return [self._decode(row) for row in rows], total

    def mark_running(self, job_id: str) -> bool:
        now = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE jobs SET status='running',stage='starting',progress=1,
                   started_at=COALESCE(started_at,?),updated_at=?
                   WHERE job_id=? AND status='queued' AND cancel_requested=0""",
                (now, now, job_id),
            )
        return cursor.rowcount == 1

    def update_progress(self, job_id: str, event: dict[str, Any]) -> None:
        now = utc_now()
        chunk_snapshot = json.dumps(event, ensure_ascii=False, default=str) if "chunk_status" in event else None
        with self._connect() as connection:
            connection.execute(
                """UPDATE jobs SET stage=?,progress=?,
                   current_chunk=COALESCE(?,current_chunk),total_chunks=COALESCE(?,total_chunks),
                   chunk_details_json=COALESCE(?,chunk_details_json),updated_at=?
                   WHERE job_id=? AND status='running'""",
                (
                    str(event.get("stage", "running"))[:100],
                    min(99.9, max(0.0, float(event.get("progress", 0)))),
                    event.get("current_chunk"), event.get("total_chunks"),
                    chunk_snapshot, now, job_id,
                ),
            )

    def cancellation_requested(self, job_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return bool(row and row[0])

    def request_cancel(self, job_id: str) -> dict[str, Any] | None:
        now = utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                connection.rollback()
                return None
            if row[0] == "queued":
                connection.execute(
                    """UPDATE jobs SET status='cancelled',stage='cancelled',progress=100,
                       cancel_requested=1,completed_at=?,updated_at=? WHERE job_id=?""",
                    (now, now, job_id),
                )
            elif row[0] == "running":
                connection.execute(
                    """UPDATE jobs SET cancel_requested=1,stage='cancellation_pending',updated_at=?
                       WHERE job_id=?""",
                    (now, job_id),
                )
            connection.commit()
        return self.get(job_id)

    def finish_success(self, job_id: str, artifacts: list[dict[str, Any]]) -> str:
        now = utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT cancel_requested,status FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                connection.rollback()
                return "missing"
            if row[0]:
                connection.execute(
                    """UPDATE jobs SET status='cancelled',stage='cancelled',progress=100,
                       completed_at=?,updated_at=? WHERE job_id=?""",
                    (now, now, job_id),
                )
                outcome = "cancelled"
            elif row[1] == "running":
                connection.execute(
                    """UPDATE jobs SET status='succeeded',stage='completed',progress=100,
                       artifacts_json=?,completed_at=?,updated_at=? WHERE job_id=?""",
                    (json.dumps(artifacts), now, now, job_id),
                )
                outcome = "succeeded"
            else:
                outcome = row[1]
            connection.commit()
        return outcome

    def finish_cancelled(self, job_id: str, message: str = "Job cancelled.") -> None:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """UPDATE jobs SET status='cancelled',stage='cancelled',progress=100,
                   error_code=NULL,error_message=NULL,completed_at=?,updated_at=?
                   WHERE job_id=? AND status IN ('queued','running')""",
                (now, now, job_id),
            )

    def finish_failed(self, job_id: str, code: str, message: str) -> None:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """UPDATE jobs SET status='failed',stage='failed',error_code=?,error_message=?,
                   completed_at=?,updated_at=? WHERE job_id=? AND status='running'""",
                (code, message[:500], now, now, job_id),
            )

    def fail_queued(self, job_id: str, code: str, message: str) -> None:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """UPDATE jobs SET status='failed',stage='failed',error_code=?,error_message=?,
                   completed_at=?,updated_at=? WHERE job_id=? AND status='queued'""",
                (code, message[:500], now, now, job_id),
            )

    def reconcile_after_restart(self) -> list[str]:
        """Fail in-flight jobs without rerunning them; return never-started queue entries."""
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """UPDATE jobs SET status='failed',stage='interrupted',
                   error_code='WORKER_UNAVAILABLE',
                   error_message='The service restarted during processing; this job was not rerun.',
                   completed_at=?,updated_at=? WHERE status='running'""",
                (now, now),
            )
            rows = connection.execute(
                "SELECT job_id FROM jobs WHERE status='queued' ORDER BY created_at ASC"
            ).fetchall()
        return [str(row[0]) for row in rows]

    def expired(self, retention_days: int) -> list[dict[str, Any]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat(timespec="milliseconds")
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM jobs WHERE status IN ('succeeded','failed','cancelled')
                   AND completed_at IS NOT NULL AND completed_at < ?""",
                (cutoff,),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def delete_record(self, job_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM jobs WHERE job_id=? AND status IN ('succeeded','failed','cancelled')", (job_id,))

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        for source, target in (("options_json", "options"), ("artifacts_json", "artifacts"), ("chunk_details_json", "chunk_details")):
            value = result.pop(source, None)
            try:
                result[target] = json.loads(value) if value else ([] if target == "artifacts" else None)
            except (TypeError, json.JSONDecodeError):
                result[target] = [] if target == "artifacts" else None
        result["cancel_requested"] = bool(result["cancel_requested"])
        return result
