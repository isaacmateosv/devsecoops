"""Make the monorepo packages importable without a build step.

Adds packages/contracts, packages/financial, services/runner, and apps/api to
sys.path. Imported first by the API entrypoint, the CLI, and tests (via
conftest.py). A production build would install these as real wheels instead.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for rel in ("packages/contracts", "packages/financial", "services/runner",
            "services/investigator", "services/verifier", "services/redteam",
            "services/modern", "apps/api"):
    p = str(ROOT / rel)
    if p not in sys.path:
        sys.path.insert(0, p)
