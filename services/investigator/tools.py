"""Explicit, typed investigation tools (the blueprint's tool contracts).

These are the ONLY ways an investigation touches the artifact. Critically, this
module never imports the oracle or ground truth, and `read_evidence` enforces an
allowlist so the investigation cannot read `evaluation-private/`. Ground-truth
isolation is therefore a property of the code path, not a convention.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import lief

import config
import ingestion
import runner
import store
from contracts import (ArtifactMetadata, Experiment, Observation)

# Finance-relevant signal we look for in symbols/strings (pure pattern evidence).
# Kept tight so libc internals (getrlimit, _IO_file_attach, ...) don't match.
_KEYWORDS = ("recovery", "claim", "treaty", "xol", "excess", "premium",
             "dollar", "cent", "deduct", "eligible", "reinsur", "loss")
# Markers that a symbol belongs to the static libc, not the user's program.
_LIBC_MARKERS = ("_IO_", "GI_", "_dl_", "getrlimit", ".o", "arena", "tcache",
                 "tls_", "__", "narenas")
_CSV_HEADER = re.compile(r"^[a-zA-Z][a-zA-Z_]*(,[a-zA-Z][a-zA-Z_]*)+$")


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    """Caps real executions so an investigation cannot run unbounded."""
    max_executions: int = 12
    used: int = 0

    def spend(self) -> None:
        if self.used >= self.max_executions:
            raise BudgetExceeded(f"execution budget of {self.max_executions} exhausted")
        self.used += 1


# --- ground-truth isolation -------------------------------------------------
def _allowed_roots() -> list[Path]:
    return [config.ARTIFACT_STORE.resolve(), config.INPUT_STORE.resolve()]


def read_evidence(path: str) -> bytes:
    """Read a file ONLY if it lives in an allowlisted evidence root. Any attempt
    to read legacy source / oracle / hidden tests raises PermissionError."""
    p = Path(path).resolve()
    if not any(str(p).startswith(str(root) + "/") or p == root for root in _allowed_roots()):
        raise PermissionError(f"evidence path not in allowed scope: {p}")
    return p.read_bytes()


# --- inspect_artifact(artifact_id) -> ArtifactMetadata ----------------------
def inspect_artifact(artifact_id: str) -> ArtifactMetadata:
    art = store.get_artifact(artifact_id)
    if art is None:
        raise ValueError("artifact not found")
    b = lief.parse(art.stored_path)
    if b is None:
        raise ValueError("artifact is not a parseable binary")

    sym_names = [s.name for s in b.symbols if s.name]
    notable_syms = sorted({s for s in sym_names
                           if any(k in s.lower() for k in _KEYWORDS)
                           and not any(m in s for m in _LIBC_MARKERS)})
    strings = []
    try:
        for s in b.strings:
            if not s:
                continue
            if isinstance(s, (bytes, bytearray)):
                s = s.decode("utf-8", "replace")
            strings.append(str(s))
    except Exception:
        pass
    notable_strs = []
    seen = set()
    for s in strings:
        low = s.lower()
        if (any(k in low for k in _KEYWORDS) or _CSV_HEADER.match(s)) \
                and s not in seen and 2 <= len(s) <= 64:
            seen.add(s)
            notable_strs.append(s)
        if len(notable_strs) >= 20:
            break

    return ArtifactMetadata(
        artifact_id=art.id, artifact_sha256=art.sha256,
        fmt=str(b.format), machine=str(b.header.machine_type),
        entrypoint=int(b.entrypoint),
        statically_linked=(len(list(b.libraries)) == 0),
        num_symbols=len(sym_names),
        notable_symbols=notable_syms,
        notable_strings=notable_strs,
        libraries=[str(x) for x in b.libraries],
    )


# --- run_experiment(artifact_id, inputs, budget) -> (Experiment, [Observation]) ---
_NUM = re.compile(r"-?\d+\.\d{2}")


def run_experiment(artifact_id: str, inputs: list[str], purpose: str,
                   budget: Budget, persist: bool = True) -> tuple[Experiment, list[Observation]]:
    art = store.get_artifact(artifact_id)
    if art is None:
        raise ValueError("artifact not found")
    budget.spend()

    # build a single CSV batch (one real execution probes many inputs)
    rows = ["claim_id,eligible_loss"] + [f"p{i},{v}" for i, v in enumerate(inputs)]
    csv_bytes = ("\n".join(rows) + "\n").encode()
    input_sha, input_path = ingestion.ingest_input(csv_bytes)

    rec = runner.run(
        artifact_id=art.id, artifact_sha256=art.sha256,
        artifact_host_path=art.stored_path,
        input_host_path=input_path, input_sha256=input_sha,
    )
    store.insert_execution(rec)

    exp = Experiment(id=f"exp_{uuid.uuid4().hex[:12]}", artifact_id=art.id,
                     purpose=purpose, inputs=list(inputs), execution_id=rec.id)

    # parse "pN,recovery" lines into a claim_id -> recovery map
    out = {}
    for line in rec.stdout.splitlines():
        if "," not in line or line.startswith("claim_id"):
            continue
        cid, _, val = line.partition(",")
        out[cid.strip()] = val.strip()

    observations: list[Observation] = []
    for i, v in enumerate(inputs):
        observations.append(Observation(
            id=f"obs_{uuid.uuid4().hex[:12]}", experiment_id=exp.id,
            execution_id=rec.id, input_value=v, output_value=out.get(f"p{i}", ""),
        ))

    if persist:
        store.insert_experiment(exp)
        for o in observations:
            store.insert_observation(o)
    return exp, observations


def run_raw_experiment(artifact_id: str, raw_input: bytes, purpose: str, budget: Budget):
    """Run the artifact on arbitrary (possibly malformed/hostile) raw input.
    Returns (Experiment, ExecutionRecord). Used by red-team robustness probes."""
    art = store.get_artifact(artifact_id)
    if art is None:
        raise ValueError("artifact not found")
    budget.spend()
    input_sha, input_path = ingestion.ingest_input(raw_input)
    rec = runner.run(artifact_id=art.id, artifact_sha256=art.sha256,
                     artifact_host_path=art.stored_path,
                     input_host_path=input_path, input_sha256=input_sha)
    store.insert_execution(rec)
    exp = Experiment(id=f"exp_{uuid.uuid4().hex[:12]}", artifact_id=art.id,
                     purpose=purpose, inputs=["<raw>"], execution_id=rec.id)
    store.insert_experiment(exp)
    return exp, rec
