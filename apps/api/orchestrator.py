"""Durable job orchestration.

Jobs are persisted in Postgres (QUEUED -> RUNNING -> SUCCEEDED/FAILED). A worker
pulls queued jobs, runs the restricted execution, stores the immutable
ExecutionRecord, and links it to the job. Because all state is in the database,
the worker is decoupled from HTTP and survives process restarts: a job left
RUNNING can be requeued and re-run, and SUCCEEDED jobs keep their evidence.
"""
from __future__ import annotations

import threading
import time
import uuid

import config
import ingestion
import store
import runner
from contracts import Job, JobKind, JobState


def submit_execute_job(artifact_id: str, input_bytes: bytes | None) -> Job:
    """Create a durable EXECUTE job (does not run it inline)."""
    input_sha = input_path = None
    if input_bytes is not None:
        input_sha, input_path = ingestion.ingest_input(input_bytes)
    job = Job(
        id=f"job_{uuid.uuid4().hex[:12]}", kind=JobKind.EXECUTE,
        artifact_id=artifact_id, input_sha256=input_sha, input_path=input_path,
    )
    store.insert_job(job)
    return job


def process_job(job: Job) -> None:
    """Execute one job to completion and persist all evidence."""
    try:
        art = store.get_artifact(job.artifact_id)
        if art is None:
            store.update_job(job.id, state=JobState.FAILED, error="artifact not found")
            return
        rec = runner.run(
            artifact_id=art.id, artifact_sha256=art.sha256,
            artifact_host_path=art.stored_path,
            input_host_path=job.input_path, input_sha256=job.input_sha256,
        )
        store.insert_execution(rec)
        if rec.status == "error":
            store.update_job(job.id, state=JobState.FAILED,
                             execution_id=rec.id, error=rec.stderr[:500])
        else:
            store.update_job(job.id, state=JobState.SUCCEEDED, execution_id=rec.id)
    except Exception as e:  # noqa: BLE001
        store.update_job(job.id, state=JobState.FAILED, error=str(e)[:500])


def run_pending_once() -> int:
    """Process all currently-queued jobs once. Returns count processed.
    Used by the CLI workflow and tests (synchronous, deterministic)."""
    n = 0
    while True:
        job = store.claim_next_queued()
        if job is None:
            break
        process_job(job)
        n += 1
    return n


class Worker(threading.Thread):
    """Background polling worker for the API process (async, not HTTP-bound)."""
    def __init__(self, interval: float = 0.5):
        super().__init__(daemon=True)
        self.interval = interval
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                if run_pending_once() == 0:
                    time.sleep(self.interval)
            except Exception:
                time.sleep(self.interval)

    def stop(self) -> None:
        self._stop.set()
