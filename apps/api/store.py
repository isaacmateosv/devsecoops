"""Postgres-backed provenance store.

Artifacts and execution records are INSERT-ONLY (immutable). Jobs carry mutable
state, which is what makes the worker durable across restarts: the source of
truth is the database, never in-memory.

Production target is PostgreSQL (per the blueprint). We use psycopg3 with plain
SQL and JSONB -- no ORM -- to keep the provenance schema explicit and auditable.
"""
from __future__ import annotations

import json
from typing import Optional

import psycopg
from psycopg.rows import dict_row

import config
from contracts import Artifact, ExecutionRecord, Job, JobKind, JobState

SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    id           TEXT PRIMARY KEY,
    filename     TEXT NOT NULL,
    sha256       TEXT NOT NULL,
    size_bytes   BIGINT NOT NULL,
    media_type   TEXT NOT NULL,
    stored_path  TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS executions (
    id            TEXT PRIMARY KEY,
    artifact_id   TEXT NOT NULL REFERENCES artifacts(id),
    doc           JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    state         TEXT NOT NULL,
    artifact_id   TEXT NOT NULL REFERENCES artifacts(id),
    input_sha256  TEXT,
    input_path    TEXT,
    execution_id  TEXT REFERENCES executions(id),
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Prompt 2 provenance (all insert-only; hypotheses are updated in place while
-- being refined, then frozen on submission).
CREATE TABLE IF NOT EXISTS experiments (
    id          TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifacts(id),
    doc         JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS observations (
    id            TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(id),
    doc           JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS hypotheses (
    id          TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifacts(id),
    doc         JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS verifications (
    id            TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL REFERENCES hypotheses(id),
    doc           JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Prompt 3: red-team attempts (incl. unsuccessful) and verified Oops findings.
CREATE TABLE IF NOT EXISTS redteam_attempts (
    id          TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifacts(id),
    doc         JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS findings (
    id          TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifacts(id),
    doc         JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Prompt 4: modern-service builds and differential/oracle comparison reports.
CREATE TABLE IF NOT EXISTS builds (
    id          TEXT PRIMARY KEY,
    doc         JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS comparison_reports (
    id          TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifacts(id),
    doc         JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def connect():
    return psycopg.connect(config.DATABASE_URL, row_factory=dict_row, autocommit=True)


def init_schema() -> None:
    with connect() as conn:
        conn.execute(SCHEMA)


# --- artifacts (immutable) ---
def insert_artifact(a: Artifact) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO artifacts(id,filename,sha256,size_bytes,media_type,stored_path,created_at)
               VALUES(%s,%s,%s,%s,%s,%s,%s)""",
            (a.id, a.filename, a.sha256, a.size_bytes, a.media_type, a.stored_path, a.created_at),
        )


def get_artifact(artifact_id: str) -> Optional[Artifact]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM artifacts WHERE id=%s", (artifact_id,)).fetchone()
    return Artifact(**row) if row else None


def list_artifacts() -> list[Artifact]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM artifacts ORDER BY created_at DESC").fetchall()
    return [Artifact(**r) for r in rows]


# --- executions (immutable) ---
def insert_execution(rec: ExecutionRecord) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO executions(id,artifact_id,doc) VALUES(%s,%s,%s)",
            (rec.id, rec.artifact_id, json.dumps(rec.model_dump(mode="json"))),
        )


def get_execution(execution_id: str) -> Optional[ExecutionRecord]:
    with connect() as conn:
        row = conn.execute("SELECT doc FROM executions WHERE id=%s", (execution_id,)).fetchone()
    return ExecutionRecord(**row["doc"]) if row else None


# --- jobs (mutable state, durable) ---
def insert_job(j: Job) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO jobs(id,kind,state,artifact_id,input_sha256,input_path,execution_id,error,created_at,updated_at)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (j.id, j.kind.value, j.state.value, j.artifact_id, j.input_sha256,
             j.input_path, j.execution_id, j.error, j.created_at, j.updated_at),
        )


def update_job(job_id: str, *, state: JobState, execution_id: Optional[str] = None,
               error: Optional[str] = None) -> None:
    with connect() as conn:
        conn.execute(
            """UPDATE jobs SET state=%s,
                   execution_id=COALESCE(%s, execution_id),
                   error=%s, updated_at=now() WHERE id=%s""",
            (state.value, execution_id, error, job_id),
        )


def get_job(job_id: str) -> Optional[Job]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=%s", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def list_jobs() -> list[Job]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    return [_row_to_job(r) for r in rows]


def claim_next_queued() -> Optional[Job]:
    """Atomically move one QUEUED job to RUNNING (durable worker pull)."""
    with connect() as conn:
        row = conn.execute(
            """UPDATE jobs SET state=%s, updated_at=now()
               WHERE id = (SELECT id FROM jobs WHERE state=%s
                           ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED)
               RETURNING *""",
            (JobState.RUNNING.value, JobState.QUEUED.value),
        ).fetchone()
    return _row_to_job(row) if row else None


# --- Prompt 2: experiments / observations / hypotheses / verifications ---
from contracts import Experiment, Observation, Hypothesis, VerificationResult  # noqa: E402


def insert_experiment(e: Experiment) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO experiments(id,artifact_id,doc) VALUES(%s,%s,%s)",
                     (e.id, e.artifact_id, json.dumps(e.model_dump(mode="json"))))


def insert_observation(o: Observation) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO observations(id,experiment_id,doc) VALUES(%s,%s,%s)",
                     (o.id, o.experiment_id, json.dumps(o.model_dump(mode="json"))))


def get_observation(obs_id: str) -> Optional[Observation]:
    with connect() as conn:
        row = conn.execute("SELECT doc FROM observations WHERE id=%s", (obs_id,)).fetchone()
    return Observation(**row["doc"]) if row else None


def list_observations(artifact_id: str) -> list[Observation]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT o.doc FROM observations o JOIN experiments e ON o.experiment_id=e.id
               WHERE e.artifact_id=%s""", (artifact_id,)).fetchall()
    return [Observation(**r["doc"]) for r in rows]


def upsert_hypothesis(h: Hypothesis) -> None:
    """Hypotheses are refined in place until submitted (then frozen by status)."""
    with connect() as conn:
        conn.execute(
            """INSERT INTO hypotheses(id,artifact_id,doc) VALUES(%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET doc=EXCLUDED.doc""",
            (h.id, h.artifact_id, json.dumps(h.model_dump(mode="json"))))


def get_hypothesis(hyp_id: str) -> Optional[Hypothesis]:
    with connect() as conn:
        row = conn.execute("SELECT doc FROM hypotheses WHERE id=%s", (hyp_id,)).fetchone()
    return Hypothesis(**row["doc"]) if row else None


def list_hypotheses(artifact_id: str) -> list[Hypothesis]:
    with connect() as conn:
        rows = conn.execute("SELECT doc FROM hypotheses WHERE artifact_id=%s ORDER BY created_at",
                            (artifact_id,)).fetchall()
    return [Hypothesis(**r["doc"]) for r in rows]


def insert_verification(v: VerificationResult) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO verifications(id,hypothesis_id,doc) VALUES(%s,%s,%s)",
                     (v.id, v.hypothesis_id, json.dumps(v.model_dump(mode="json"))))


def get_verification_for(hyp_id: str) -> Optional[VerificationResult]:
    with connect() as conn:
        row = conn.execute("SELECT doc FROM verifications WHERE hypothesis_id=%s ORDER BY created_at DESC LIMIT 1",
                           (hyp_id,)).fetchone()
    return VerificationResult(**row["doc"]) if row else None


# --- Prompt 3: attempts & findings ---
from contracts import AttemptRecord, FindingRecord  # noqa: E402


def insert_attempt(a: AttemptRecord) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO redteam_attempts(id,artifact_id,doc) VALUES(%s,%s,%s)",
                     (a.id, a.artifact_id, json.dumps(a.model_dump(mode="json"))))


def list_attempts(artifact_id: str) -> list[AttemptRecord]:
    with connect() as conn:
        rows = conn.execute("SELECT doc FROM redteam_attempts WHERE artifact_id=%s ORDER BY created_at",
                            (artifact_id,)).fetchall()
    return [AttemptRecord(**r["doc"]) for r in rows]


def insert_finding(f: FindingRecord) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO findings(id,artifact_id,doc) VALUES(%s,%s,%s)",
                     (f.id, f.artifact_id, json.dumps(f.model_dump(mode="json"))))


def get_finding(finding_id: str) -> Optional[FindingRecord]:
    with connect() as conn:
        row = conn.execute("SELECT doc FROM findings WHERE id=%s", (finding_id,)).fetchone()
    return FindingRecord(**row["doc"]) if row else None


def list_findings(artifact_id: str) -> list[FindingRecord]:
    with connect() as conn:
        rows = conn.execute("SELECT doc FROM findings WHERE artifact_id=%s ORDER BY created_at",
                            (artifact_id,)).fetchall()
    return [FindingRecord(**r["doc"]) for r in rows]


# --- Prompt 4: builds & comparison reports ---
from contracts import BuildRecord, ComparisonReport  # noqa: E402


def insert_build(b: BuildRecord) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO builds(id,doc) VALUES(%s,%s)",
                     (b.id, json.dumps(b.model_dump(mode="json"))))


def get_build(build_id: str) -> Optional[BuildRecord]:
    with connect() as conn:
        row = conn.execute("SELECT doc FROM builds WHERE id=%s", (build_id,)).fetchone()
    return BuildRecord(**row["doc"]) if row else None


def insert_comparison(r: ComparisonReport) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO comparison_reports(id,artifact_id,doc) VALUES(%s,%s,%s)",
                     (r.id, r.artifact_id, json.dumps(r.model_dump(mode="json"))))


def get_comparison(report_id: str) -> Optional[ComparisonReport]:
    with connect() as conn:
        row = conn.execute("SELECT doc FROM comparison_reports WHERE id=%s", (report_id,)).fetchone()
    return ComparisonReport(**row["doc"]) if row else None


def list_comparisons(artifact_id: str) -> list[ComparisonReport]:
    with connect() as conn:
        rows = conn.execute("SELECT doc FROM comparison_reports WHERE artifact_id=%s ORDER BY created_at DESC",
                            (artifact_id,)).fetchall()
    return [ComparisonReport(**r["doc"]) for r in rows]


def _row_to_job(row: dict) -> Job:
    return Job(
        id=row["id"], kind=JobKind(row["kind"]), state=JobState(row["state"]),
        artifact_id=row["artifact_id"], input_sha256=row["input_sha256"],
        input_path=row["input_path"], execution_id=row["execution_id"],
        error=row["error"], created_at=row["created_at"], updated_at=row["updated_at"],
    )
