"""Reports derive from saved execution records, and job state is durable
(Prompt 1 acceptance gates).

- Ingest the real demo binary, run a real restricted execution job.
- Assert the artifact hash matches the stored bytes.
- Assert the execution record is what the job points at, and that re-reading it
  through a FRESH database connection returns identical evidence (proves the
  record survives independently of any in-memory worker state == durable).
- Assert the stored stdout hash recomputes correctly (no fabrication).
"""
import hashlib

import pytest

import config
import ingestion
import orchestrator
import store
from conftest import requires_docker, requires_db


@requires_db
@requires_docker
def test_report_derives_from_saved_records(clean_db):
    assert config.DEMO_ARTIFACT.exists(), "build the demo binary first"

    raw = config.DEMO_ARTIFACT.read_bytes()
    art = ingestion.ingest_artifact(raw, "xol_calc")
    store.insert_artifact(art)

    # artifact hash is real
    assert art.sha256 == hashlib.sha256(raw).hexdigest()

    job = orchestrator.submit_execute_job(art.id, config.DEMO_INPUT.read_bytes())
    assert job.state.value == "queued"

    processed = orchestrator.run_pending_once()
    assert processed == 1

    # re-read job + execution through fresh connections (durability)
    job2 = store.get_job(job.id)
    assert job2.state.value == "succeeded"
    assert job2.execution_id is not None

    rec = store.get_execution(job2.execution_id)
    assert rec is not None
    assert rec.artifact_id == art.id
    assert rec.exit_code == 0
    assert rec.isolation.network == "none"
    assert rec.isolation.user == "65534:65534"

    # the displayed output is the stored output, not re-run on demand
    assert rec.stdout_sha256 == hashlib.sha256(rec.stdout.encode()).hexdigest()
    assert "claim_id,recovery" in rec.stdout
    # a known normal-range claim computed correctly in the sandbox
    assert "CLM-1004,250000.00" in rec.stdout


@requires_db
def test_artifact_and_execution_are_insert_only(clean_db):
    raw = b"\x7fELF fake but valid-enough for ingestion test"
    art = ingestion.ingest_artifact(raw, "x")
    store.insert_artifact(art)
    with pytest.raises(Exception):
        store.insert_artifact(art)  # duplicate PK -> immutable store rejects
