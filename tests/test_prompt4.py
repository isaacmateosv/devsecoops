"""Prompt 4 acceptance: verified financial modernization (Track A + Track B).

- the modern replacement is financially correct across the supported subset
  (property-based vs the independent oracle),
- differential + oracle comparison runs and stores an artifact,
- the seeded defect is corrected under approved rules WITHOUT hiding the
  compatibility difference,
- the release workflow distinguishes verified / approved / pending / rejected,
- no universal-equivalence claim is made.
"""
from decimal import Decimal

import pytest
from hypothesis import given, settings, strategies as st

import config
import ingestion
import store
import tools
import modern
import verifier
import compare
from contracts import Classification, ReleaseStatus
from conftest import requires_docker, requires_db


# ---- pure unit / property-based (no docker/db) -----------------------------
def test_modern_validation_and_trace():
    out = modern.calculate("350000.00")
    assert out["recovery"] == "250000.00"
    assert out["overflow_safe"] is True
    assert [s["step"] for s in out["trace"]][0] == "input"
    with pytest.raises(modern.ValidationError):
        modern.calculate("-1")
    with pytest.raises(modern.ValidationError):
        modern.calculate("not_a_number")


def test_modern_fixes_overflow_class():
    # the exact input that defeats the legacy binary
    assert modern.calculate("30000000.00")["recovery"] == "500000.00"


@settings(max_examples=200, deadline=None)
@given(cents=st.integers(min_value=0, max_value=200_000_000))  # $0 .. $2,000,000
def test_modern_matches_oracle_property_based(cents):
    e = (Decimal(cents) / 100).quantize(Decimal("0.01"))
    assert Decimal(modern.calculate(e)["recovery"]) == verifier.oracle_expected(e)


# ---- differential (needs docker + db) --------------------------------------
@pytest.fixture(scope="module")
def report():
    store.init_schema()
    with store.connect() as c:
        c.execute("TRUNCATE comparison_reports, builds, findings, redteam_attempts, "
                  "verifications, hypotheses, observations, experiments, jobs, "
                  "executions, artifacts RESTART IDENTITY CASCADE")
    art = ingestion.ingest_artifact(config.DEMO_ARTIFACT.read_bytes(), "xol_calc")
    store.insert_artifact(art)
    rep = compare.compare(art.id, budget=tools.Budget(max_executions=4))
    return art.id, rep


@requires_db
@requires_docker
def test_subset_is_verified_and_nontrivial(report):
    _, rep = report
    assert rep.counts.get("compatible_and_correct", 0) >= 10  # nontrivial subset
    # Track A + Track B both ran for every case
    for c in rep.cases:
        assert c.oracle is not None and c.modern is not None


@requires_db
@requires_docker
def test_report_artifact_is_stored(report):
    _, rep = report
    assert rep.report_path
    assert (config.REPO_ROOT / rep.report_path).exists()
    assert store.get_comparison(rep.id) is not None  # also in the db


@requires_db
@requires_docker
def test_seeded_defect_corrected_without_hiding_difference(report):
    _, rep = report
    big = [c for c in rep.cases if c.eligible_loss == "30000000.00"][0]
    assert big.classification == Classification.INTENTIONALLY_CORRECTED
    assert big.release_status == ReleaseStatus.APPROVED_DIVERGENCE
    assert big.modern == "500000.00" and big.oracle == "500000.00"
    assert big.legacy == "0.00"          # compatibility difference is NOT hidden
    assert big.track_a_compatible is False and big.track_b_correct is True


@requires_db
@requires_docker
def test_release_workflow_distinguishes_states(report):
    _, rep = report
    assert "verified" in rep.release_counts
    assert "approved_divergence" in rep.release_counts
    assert rep.disclaimer and "not a mathematical proof" in rep.disclaimer


@requires_db
@requires_docker
def test_unapproved_divergence_is_pending(report, monkeypatch):
    """With no approved divergence in policy, the same correction must surface as
    pending_approval (the agent never self-approves its inferred semantics)."""
    artifact_id, _ = report
    spec = modern.load_approved()
    spec = {**spec, "approved_divergences": []}
    monkeypatch.setattr(modern, "load_approved", lambda: spec)
    rep2 = compare.compare(artifact_id, cases=["30000000.00", "350000.00"],
                           budget=tools.Budget(max_executions=4))
    big = [c for c in rep2.cases if c.eligible_loss == "30000000.00"][0]
    assert big.classification == Classification.INTENTIONALLY_CORRECTED
    assert big.release_status == ReleaseStatus.PENDING_APPROVAL
