"""Prompt 3 acceptance: the authorized red-team / Oops workflow.

Asserts the acceptance gates:
- a deliberately seeded issue is discovered through actual testing,
- the evidence reproduces the defect on the legacy executable,
- the independent oracle supports the expected result,
- unsuccessful attempts are recorded,
- only reproduced + oracle-supported discrepancies become verified findings.
"""
from decimal import Decimal
from pathlib import Path

import pytest

import config
import ingestion
import store
import tools
import inference
import redteam
import verifier
from conftest import requires_docker, requires_db


@pytest.fixture(scope="module")
def scanned():
    store.init_schema()
    with store.connect() as c:
        c.execute("TRUNCATE findings, redteam_attempts, verifications, hypotheses, "
                  "observations, experiments, jobs, executions, artifacts "
                  "RESTART IDENTITY CASCADE")
    art = ingestion.ingest_artifact(config.DEMO_ARTIFACT.read_bytes(), "xol_calc")
    store.insert_artifact(art)
    inv = inference.investigate(art.id, tools.Budget())
    res = redteam.scan(art.id, inv.submitted_hypothesis_id, tools.Budget(max_executions=48))
    return art.id, res


@requires_db
@requires_docker
def test_a_seeded_defect_is_discovered_and_verified(scanned):
    artifact_id, res = scanned
    findings = store.list_findings(artifact_id)
    assert findings, "no verified Oops discovered"
    f = findings[0]
    assert f.defect_class == "integer_overflow"
    assert f.status == "verified"
    assert f.observed_output == "0.00"
    assert f.expected_output == "500000.00"
    assert f.severity.value == "high"


@requires_db
@requires_docker
def test_defect_reproduces_on_the_legacy_executable(scanned):
    artifact_id, res = scanned
    f = store.list_findings(artifact_id)[0]
    # the recorded reproduction points at real isolated executions
    for ex_id in f.reproduction["execution_ids"]:
        rec = store.get_execution(ex_id)
        assert rec is not None and rec.exit_code == 0
        assert rec.isolation.network == "none"
    # and it reproduces again right now on the legacy binary
    _, obs = tools.run_experiment(artifact_id, ["30000000.00"], "test: reproduce", tools.Budget())
    assert obs[0].output_value == "0.00"


@requires_db
@requires_docker
def test_independent_oracle_supports_expected(scanned):
    f = store.list_findings(scanned[0])[0]
    assert verifier.oracle_expected("30000000.00") == Decimal("500000.00")
    assert f.expected_output == "500000.00"


@requires_db
@requires_docker
def test_unsuccessful_attempts_are_recorded(scanned):
    artifact_id, _ = scanned
    attempts = {a.attack_class: a for a in store.list_attempts(artifact_id)}
    assert attempts["negative_and_zero"].outcome == "no_discrepancy"
    assert attempts["malformed_input"].outcome == "no_discrepancy"  # robust: no crash
    assert attempts["large_value_overflow"].outcome == "discrepancy"


@requires_db
@requires_docker
def test_only_reproduced_discrepancies_become_findings(scanned):
    artifact_id, _ = scanned
    # exactly one verified finding (the overflow); benign classes produced none
    assert len(store.list_findings(artifact_id)) == 1


@requires_db
@requires_docker
def test_regression_test_was_generated_and_is_valid(scanned):
    f = store.list_findings(scanned[0])[0]
    assert f.regression_test_path
    path = config.REPO_ROOT / f.regression_test_path
    assert path.exists()
    assert "excess_of_loss_recovery" in path.read_text()
