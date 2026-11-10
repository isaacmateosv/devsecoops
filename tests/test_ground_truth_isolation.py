"""Ground-truth isolation is TESTED, not assumed (Prompt 2 acceptance gate).

The investigation side must not be able to read legacy source / oracle / hidden
tests, and must not import the oracle. Only the blinded verifier may.
"""
import sys
from pathlib import Path

import pytest

import config
import ingestion
import runner
import tools


EVAL = config.REPO_ROOT / "evaluation-private"


def test_read_evidence_refuses_evaluation_private():
    for p in [EVAL / "oracle" / "oracle.py",
              EVAL / "legacy-source" / "xol_calc.c",
              EVAL / "hidden-tests" / "ground_truth.json"]:
        with pytest.raises(PermissionError):
            tools.read_evidence(str(p))


def test_read_evidence_allows_artifact_store():
    art = ingestion.ingest_artifact(config.DEMO_ARTIFACT.read_bytes(), "xol_calc")
    data = tools.read_evidence(art.stored_path)  # inside ARTIFACT_STORE
    assert data[:4] == b"\x7fELF"


def test_investigator_modules_do_not_import_oracle():
    # importing the investigation stack must not load the oracle module, and the
    # investigator source must not contain an *import* of it (prose mentions in
    # docstrings are fine; an actual dependency is not).
    import inference, agent  # noqa: F401
    assert "eval_oracle" not in sys.modules
    import ast
    for mod in (tools, inference, agent):
        tree = ast.parse(Path(mod.__file__).read_text())
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        assert not any("oracle" in (name or "").lower() for name in imported), \
            f"{mod.__name__} imports the oracle"


def test_only_verifier_reaches_ground_truth():
    # the verifier is the component that actually reads the private oracle file
    import verifier
    src = Path(verifier.__file__).read_text()
    assert "oracle.py" in src and "evaluation-private" in src


def test_runner_mounts_nothing_from_evaluation_private():
    argv = runner.docker_run_argv("/var/artifacts/abc", "/var/inputs/xyz.input")
    assert not any("evaluation-private" in a for a in argv)
    # exactly two read-only mounts: the artifact and the input
    assert argv.count("-v") == 2
    assert all(a.endswith(":ro") for a in argv if a.startswith("/") and ":/" in a)
