"""Typed data contracts shared across DevSecOops services.

These are the immutable provenance records required by the blueprint:
Artifact, ExecutionRecord, Job, EvidenceReference. Everything an operator or
auditor sees in the UI must trace back to one of these records.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobKind(str, enum.Enum):
    EXECUTE = "execute"  # run an artifact against an input and capture evidence


class JobState(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Artifact(BaseModel):
    """Immutable record of an ingested artifact (content-addressed)."""
    id: str
    filename: str
    sha256: str
    size_bytes: int
    media_type: str
    stored_path: str
    created_at: datetime = Field(default_factory=utcnow)


class IsolationProfile(BaseModel):
    """The restrictions applied to an execution. Recorded as evidence so the
    isolation claim is auditable, not assumed."""
    engine: str = "docker"
    runner_image: str
    network: str = "none"
    read_only_rootfs: bool = True
    user: str = "65534:65534"  # nobody:nogroup
    cap_drop: str = "ALL"
    no_new_privileges: bool = True
    memory_bytes: int
    cpus: float
    pids_limit: int
    wall_clock_timeout_s: int


class ExecutionRecord(BaseModel):
    """Immutable record of a single restricted execution of an artifact."""
    id: str
    artifact_id: str
    artifact_sha256: str
    input_sha256: Optional[str] = None
    argv: list[str]
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    stdout_sha256: Optional[str] = None
    duration_ms: int = 0
    timed_out: bool = False
    isolation: IsolationProfile
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = None
    status: str = "completed"  # completed | error


class Job(BaseModel):
    """A durable unit of work. State lives in Postgres, so it survives restart
    and is not tied to an HTTP request lifetime."""
    id: str
    kind: JobKind
    state: JobState = JobState.QUEUED
    artifact_id: str
    input_sha256: Optional[str] = None
    input_path: Optional[str] = None
    execution_id: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class EvidenceReference(BaseModel):
    """A pointer from a UI claim / finding back to a concrete stored record."""
    kind: str  # artifact | execution | job | experiment | observation
    id: str
    sha256: Optional[str] = None
    note: Optional[str] = None


# --------------------------------------------------------------------------
# Prompt 2 -- black-box business-rule archaeology
# --------------------------------------------------------------------------

class ArtifactMetadata(BaseModel):
    """Static evidence recovered from the binary (no source, no ground truth)."""
    artifact_id: str
    artifact_sha256: str
    fmt: str
    machine: str
    entrypoint: int
    statically_linked: bool
    num_symbols: int
    notable_symbols: list[str] = Field(default_factory=list)
    notable_strings: list[str] = Field(default_factory=list)
    libraries: list[str] = Field(default_factory=list)
    inspected_with: str = "lief"


class Experiment(BaseModel):
    """A bounded, purposeful execution of the artifact on chosen inputs.
    Backed by exactly one real ExecutionRecord."""
    id: str
    artifact_id: str
    purpose: str
    inputs: list[str]  # eligible_loss values probed in this batch
    execution_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class Observation(BaseModel):
    """One (input -> output) fact derived from a real execution."""
    id: str
    experiment_id: str
    execution_id: str
    input_value: str   # eligible_loss
    output_value: str  # recovery (as emitted by the binary)
    note: Optional[str] = None


class HypothesisStatus(str, enum.Enum):
    CANDIDATE = "candidate"
    REFINED = "refined"
    REFUTED = "refuted"
    SUBMITTED = "submitted"   # frozen; eligible for blinded verification


class Hypothesis(BaseModel):
    """A falsifiable candidate business rule with provenance to observations."""
    id: str
    artifact_id: str
    kind: str = "treaty_rule"
    formula_name: str              # e.g. "subtract_then_cap"
    statement: str                 # human-readable
    params: dict = Field(default_factory=dict)  # {attachment, limit, currency}
    rationale: str = ""
    supporting_observation_ids: list[str] = Field(default_factory=list)
    refuting_observation_ids: list[str] = Field(default_factory=list)
    status: HypothesisStatus = HypothesisStatus.CANDIDATE
    confidence: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)


class Severity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AttemptRecord(BaseModel):
    """A red-team probe class and its outcome. Unsuccessful attempts are recorded
    too (no discrepancy == the binary behaved correctly for that class)."""
    id: str
    artifact_id: str
    attack_class: str
    description: str
    inputs_summary: str
    outcome: str  # no_discrepancy | discrepancy | error
    execution_id: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class FindingRecord(BaseModel):
    """A verified 'Oops': a reproduced defect backed by independent expectation.
    Only created when the discrepancy reproduced AND the independent oracle
    supports the expected result. Carries every field the blueprint requires."""
    id: str
    artifact_id: str
    artifact_sha256: str            # affected executable version/hash
    title: str
    defect_class: str
    triggering_input: str
    observed_output: str
    expected_output: str
    discrepancy: str
    reproduction: dict = Field(default_factory=dict)  # steps, environment, execution_ids
    root_cause_hypothesis: str
    evidence_strength: str
    technical_impact: str
    business_impact: str
    assumptions: str
    severity: Severity
    confidence: float
    rationale: str
    remediation: str
    regression_test_path: Optional[str] = None
    status: str = "verified"
    created_at: datetime = Field(default_factory=utcnow)


class BuildRecord(BaseModel):
    """A build of the modern replacement service, bound to an approved spec."""
    id: str
    service: str = "modern-xol"
    version: str
    approved_spec_sha256: str
    supported_subset: str
    created_at: datetime = Field(default_factory=utcnow)


class Classification(str, enum.Enum):
    COMPATIBLE_CORRECT = "compatible_and_correct"
    COMPATIBLE_INCORRECT = "compatible_but_incorrect"
    INTENTIONALLY_CORRECTED = "intentionally_corrected"
    UNEXPLAINED_REGRESSION = "unexplained_regression"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ReleaseStatus(str, enum.Enum):
    VERIFIED = "verified"                 # compatible and correct
    APPROVED_DIVERGENCE = "approved_divergence"   # intentional change, human-approved
    PENDING_APPROVAL = "pending_approval"         # intentional change, not yet approved
    REJECTED = "rejected"                 # replacement reproduced a bug / wrong
    UNRESOLVED = "unresolved"             # insufficient evidence


class CaseComparison(BaseModel):
    """One input compared across legacy binary, modern replacement, and oracle."""
    eligible_loss: str
    legacy: Optional[str] = None     # Track A reference (may be None if legacy errored)
    modern: str
    oracle: str                      # Track B reference (independent correctness)
    track_a_compatible: bool         # modern == legacy
    track_b_correct: bool            # modern == oracle
    classification: Classification
    release_status: ReleaseStatus
    note: Optional[str] = None


class ComparisonReport(BaseModel):
    """Stored artifact of a differential + oracle comparison run."""
    id: str
    artifact_id: str
    build_id: str
    cases: list[CaseComparison] = Field(default_factory=list)
    counts: dict = Field(default_factory=dict)      # classification -> n
    release_counts: dict = Field(default_factory=dict)  # release status -> n
    approved_divergences: list[dict] = Field(default_factory=list)
    disclaimer: str = ""
    report_path: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class VerificationResult(BaseModel):
    """Blinded evaluation of a SUBMITTED hypothesis against private ground truth.
    Produced only after the hypothesis is frozen."""
    id: str
    hypothesis_id: str
    precision: float               # fraction of evaluated cases matching the oracle
    num_cases: int
    matches: int
    mismatches: list[dict] = Field(default_factory=list)
    coverage: str = ""             # the input region the inference actually sampled
    unresolved_uncertainty: str = ""
    oracle_ref: str = ""
    created_at: datetime = Field(default_factory=utcnow)
