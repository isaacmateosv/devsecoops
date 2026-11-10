"""Central configuration, driven by environment variables so the same code runs
locally (host orchestrator + dockerised runner/db) and in k8s."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# --- persistence ---
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://devsecoops:devsecoops@localhost:5433/devsecoops",
)

# --- artifact storage (immutable, content-addressed) ---
ARTIFACT_STORE = Path(os.environ.get("ARTIFACT_STORE", REPO_ROOT / "var" / "artifacts"))
INPUT_STORE = Path(os.environ.get("INPUT_STORE", REPO_ROOT / "var" / "inputs"))

# --- ingestion limits ---
MAX_ARTIFACT_BYTES = int(os.environ.get("MAX_ARTIFACT_BYTES", 25 * 1024 * 1024))  # 25 MiB
MAX_INPUT_BYTES = int(os.environ.get("MAX_INPUT_BYTES", 5 * 1024 * 1024))  # 5 MiB

# --- restricted runner ---
RUNNER_IMAGE = os.environ.get("RUNNER_IMAGE", "debian:bookworm-slim")
RUNNER_MEMORY_BYTES = int(os.environ.get("RUNNER_MEMORY_BYTES", 256 * 1024 * 1024))
RUNNER_CPUS = float(os.environ.get("RUNNER_CPUS", "1.0"))
RUNNER_PIDS_LIMIT = int(os.environ.get("RUNNER_PIDS_LIMIT", "64"))
RUNNER_TIMEOUT_S = int(os.environ.get("RUNNER_TIMEOUT_S", "15"))

# --- demo fixture (the one-click known synthetic artifact) ---
DEMO_ARTIFACT = REPO_ROOT / "demo" / "artifacts" / "xol_calc"
DEMO_INPUT = REPO_ROOT / "demo" / "sample-data" / "claims_sample.csv"


def ensure_dirs() -> None:
    ARTIFACT_STORE.mkdir(parents=True, exist_ok=True)
    INPUT_STORE.mkdir(parents=True, exist_ok=True)
