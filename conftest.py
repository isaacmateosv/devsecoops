"""Pytest bootstrap: make monorepo packages importable and provide shared
docker/db availability checks + a clean-db fixture."""
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "apps", "api"))
import bootstrap  # noqa: E402,F401


def _docker_ok() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0
    except Exception:
        return False


def _db_ok() -> bool:
    try:
        import store  # noqa
        store.init_schema()
        return True
    except Exception:
        return False


requires_docker = pytest.mark.skipif(not _docker_ok(), reason="docker daemon not available")
requires_db = pytest.mark.skipif(not _db_ok(), reason="postgres not available (run infra/docker-compose up -d db)")


@pytest.fixture()
def clean_db():
    import store
    store.init_schema()
    with store.connect() as conn:
        conn.execute("TRUNCATE comparison_reports, builds, findings, redteam_attempts, "
                     "verifications, hypotheses, observations, experiments, jobs, "
                     "executions, artifacts RESTART IDENTITY CASCADE")
    yield store
