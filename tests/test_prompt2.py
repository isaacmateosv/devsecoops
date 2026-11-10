"""Prompt 2 acceptance: source-blind business-rule inference + blinded verification.

Runs one real investigation (module-scoped) and asserts the acceptance gates:
- a previously hidden rule is inferred and evaluated,
- every inference links to real experiments/executions,
- a disambiguating experiment refuted a competing hypothesis,
- failed guesses and uncertainty remain visible.
"""
from decimal import Decimal

import pytest

import config
import ingestion
import store
import tools
import inference
import verifier
from contracts import HypothesisStatus
from conftest import requires_docker, requires_db


@pytest.fixture(scope="module")
def investigated():
    store.init_schema()
    with store.connect() as c:
        c.execute("TRUNCATE verifications, hypotheses, observations, experiments, "
                  "jobs, executions, artifacts RESTART IDENTITY CASCADE")
    art = ingestion.ingest_artifact(config.DEMO_ARTIFACT.read_bytes(), "xol_calc")
    store.insert_artifact(art)
    result = inference.investigate(art.id, tools.Budget())
    return art.id, result


@requires_db
@requires_docker
def test_hidden_rule_is_inferred(investigated):
    artifact_id, result = investigated
    sub = store.get_hypothesis(result.submitted_hypothesis_id)
    assert sub.status == HypothesisStatus.SUBMITTED
    assert sub.params["attachment"] == "100000.00"
    assert sub.params["limit"] == "500000.00"
    assert sub.params["rounding"] == "half_up"
    assert sub.confidence == 1.0


@requires_db
@requires_docker
def test_inference_links_to_real_experiments(investigated):
    artifact_id, result = investigated
    sub = store.get_hypothesis(result.submitted_hypothesis_id)
    assert sub.supporting_observation_ids, "no provenance"
    for oid in sub.supporting_observation_ids:
        obs = store.get_observation(oid)
        assert obs is not None
        rec = store.get_execution(obs.execution_id)       # real execution of record
        assert rec is not None and rec.exit_code == 0
        assert rec.isolation.network == "none"            # produced under isolation


@requires_db
@requires_docker
def test_disambiguating_experiment_refuted_a_competitor(investigated):
    artifact_id, result = investigated
    hyps = store.list_hypotheses(artifact_id)
    refuted = [h for h in hyps if h.status == HypothesisStatus.REFUTED]
    assert refuted, "expected at least one refuted competing hypothesis"
    r = refuted[0]
    assert r.refuting_observation_ids
    # the refuting observation is a real sub-cent probe that returned 0.01
    obs = store.get_observation(r.refuting_observation_ids[0])
    assert Decimal(obs.output_value) == Decimal("0.01")


@requires_db
@requires_docker
def test_uncertainty_remains_visible(investigated):
    _, result = investigated
    assert "2000000" in result.coverage
    assert "not sampled" in result.unresolved or "unverified" in result.unresolved.lower()


@requires_db
@requires_docker
def test_blinded_verification_scores_against_oracle(investigated):
    _, result = investigated
    v = verifier.verify(result.submitted_hypothesis_id)
    assert v.precision == 1.0
    assert v.num_cases >= 20
    assert v.mismatches == []
    assert "OOPS-001" in v.unresolved_uncertainty  # honest about the unsampled defect region


@requires_db
@requires_docker
def test_verifier_refuses_unsubmitted_hypothesis(investigated):
    artifact_id, _ = investigated
    # craft a non-submitted candidate and ensure the blinded verifier refuses it
    from contracts import Hypothesis
    h = Hypothesis(id="hyp_candidate_x", artifact_id=artifact_id,
                   formula_name="x", statement="x",
                   params={"attachment": "1", "limit": "2"},
                   status=HypothesisStatus.CANDIDATE)
    store.upsert_hypothesis(h)
    with pytest.raises(verifier.NotSubmitted):
        verifier.verify(h.id)
