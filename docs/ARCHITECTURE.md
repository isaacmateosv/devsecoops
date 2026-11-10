# Architecture (Prompt 1)

```
            ingest (hash, quota,          durable job            restricted
            validate, immutable)          (Postgres)             execution
 upload ───────────────▶ Artifact ──▶ Job(queued) ──▶ Worker ──▶ Docker runner ──▶ ExecutionRecord
   │                       │                             │        (--network none,      │ (immutable)
   │                       │                             │         read-only, nobody,   │
   ▼                       ▼                             ▼         caps dropped)         ▼
 FastAPI  ◀────────────  Postgres (artifacts, jobs, executions)  ◀──────────────────────┘
   │
   ▼
 Console (reads /api/* only — no simulated state)

 evaluation-private/   (legacy-source, oracle, hidden-tests)
   └── NEVER mounted into the runner or agent tool scope. Nothing is bind-mounted
       into the runner except the compiled artifact (ro) and the input (ro), and
       the root fs is read-only — so the ground truth is unreachable by construction.
```

## Boundaries & why
- **Deterministic tools execute; agents hypothesize.** Hashing, execution,
  financial math, and tests are plain code. LLM agents (Prompt 2+) only propose
  hypotheses and interpretations; they never produce the evidence of record.
- **Ground truth isolation.** The runner container has no host mounts besides
  the two read-only files it needs, so it cannot read `evaluation-private/`. The
  future verifier (Prompt 2) runs as a separate process with its own scope.
- **Provenance.** `packages/contracts` defines immutable `Artifact`,
  `ExecutionRecord`, and `EvidenceReference`. The UI can only cite these.

## Module map
| Path | Role |
|---|---|
| `packages/contracts/contracts.py` | typed immutable records |
| `packages/financial/financial.py` | public decimal XoL interface (no secrets) |
| `apps/api/ingestion.py` | hashing, quotas, immutable storage |
| `apps/api/store.py` | Postgres provenance store (insert-only artifacts/executions) |
| `apps/api/orchestrator.py` | durable job worker |
| `services/runner/runner.py` | hardened Docker execution (single source of isolation config) |
| `apps/api/app.py` + `static/` | API + live console |
| `evaluation-private/` | legacy source, oracle, scoring key (eval authority only) |
| `infra/` | compose (Postgres) + k8s runner Job (gVisor/NetworkPolicy path) |
