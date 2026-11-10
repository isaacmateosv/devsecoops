# DevSecOops

> AI-native financial legacy intelligence. Upload a forgotten financial
> executable; watch deterministic tools + agents interrogate it, recover its
> business rules, uncover an *Oops*, rebuild the capability, and prove what
> changed — with **real evidence, never theater**.

**Status: all five milestones complete and verified (41 tests passing).**
P1 foundation + restricted execution · P2 source-blind rule inference + blinded
verification · P3 authorized red-team that discovers/reproduces/confirms the
seeded Oops + regression test · P4 verified modern replacement (Track A vs
legacy, Track B vs oracle, approved-divergence workflow) · P5 polished Next.js +
React Flow five-act reveal over the real records. See [docs/STATUS.md](docs/STATUS.md).

## What works today (all executed, not mocked)

- A synthetic legacy **excess-of-loss claims calculator** compiled to a static
  Linux ELF. Its source, the independent oracle, and the scoring key live in
  `evaluation-private/` and are **never** mounted into the runner or agent paths.
- **Ingestion**: SHA-256 content-addressing, size quotas, media-type detection,
  immutable storage, provenance metadata in Postgres.
- **Restricted execution runner**: runs the untrusted artifact in an ephemeral
  hardened Docker container — `--network none`, read-only rootfs, non-root
  (`nobody`), `--cap-drop ALL`, `no-new-privileges`, memory/CPU/PID caps,
  wall-clock timeout. Captures exit code, stdout/stderr, duration, hashes.
- **Durable jobs**: state lives in Postgres (`queued → running → succeeded/failed`),
  processed by an async worker decoupled from HTTP — survives restart.
- **Immutable evidence**: every displayed value traces to a stored
  `ExecutionRecord`; the isolation profile is recorded per execution.
- **API + live console**: FastAPI + a real dashboard that reads only backend state.
- **Tests (14 passing)**: isolation is *enforced* (network/rootfs/user proven at
  runtime, not assumed), reports *derive from saved records*, financial math is exact.

## The seeded defect (OOPS-001, hidden from investigation)

The legacy binary stores monetary cents in a **32-bit int**. Claims with
eligible loss above **$21,474,836.47** overflow and return a wrong/negative
recovery instead of the correct $500,000 limit cap. Normal-range claims are
exact, so the correct rule stays recoverable by black-box inference. This is the
`Oops` the Prompt 3 red-team workflow must *rediscover* through testing.
Verified by construction today (`CLM-1007` $30M → legacy `0.00`, oracle `500000.00`).

## Quick start

```bash
# 1. Postgres
docker compose -f infra/docker-compose.yml up -d db

# 2. Python env
python3 -m venv .venv && ./.venv/bin/pip install -r apps/api/requirements.txt

# 3. (Re)build the synthetic legacy binary  (see docs/DEVELOPMENT.md)
./scripts/build_demo_binary.sh

# 4. End-to-end workflows (headless)
DATABASE_URL=postgresql://devsecoops:devsecoops@localhost:5433/devsecoops \
  ./.venv/bin/python run_workflow.py         # Prompt 1: ingest + restricted run
DATABASE_URL=postgresql://devsecoops:devsecoops@localhost:5433/devsecoops \
  ./.venv/bin/python run_investigation.py    # Prompt 2: infer rule + blinded verify
DATABASE_URL=postgresql://devsecoops:devsecoops@localhost:5433/devsecoops \
  ./.venv/bin/python run_redteam.py          # Prompt 3: red-team + verified Oops
DATABASE_URL=postgresql://devsecoops:devsecoops@localhost:5433/devsecoops \
  ./.venv/bin/python run_modernize.py        # Prompt 4: modern replacement + Track A/B

# 5. Tests
DATABASE_URL=postgresql://devsecoops:devsecoops@localhost:5433/devsecoops \
  ./.venv/bin/python -m pytest

# 6. API + lightweight console
DATABASE_URL=postgresql://devsecoops:devsecoops@localhost:5433/devsecoops \
  ./.venv/bin/python -m uvicorn app:app --app-dir apps/api --port 8000
# open http://localhost:8000  -> click "Run known synthetic demo fixture"

# 7. Prompt 5 — the polished Next.js five-act reveal
cd apps/web && npm install && npm run build && npm start   # http://localhost:3000
# click "Run live investigation" (calls POST /api/demo/run; set NEXT_PUBLIC_API_BASE if the API is elsewhere)

# 8. Standalone modern replacement service (Prompt 4 deliverable)
docker compose -f infra/docker-compose.yml up -d modern    # http://localhost:8001/health
```

## Honest deviations from the blueprint (POC constraints)

| Blueprint target | POC choice | Why / path forward |
|---|---|---|
| Postgres | Postgres (via compose) | ✅ as specified |
| VM-level isolation for hostile uploads | hardened Docker | Docker is a strong-but-not-absolute boundary; `infra/k8s/runner-job.yaml` shows the gVisor/Kata path. |
| Next.js + React Flow UI | minimal real HTML console | Per instruction, engine prioritized over UI; full UI is Prompt 5. |
| Ghidra/radare2, LangGraph | not yet wired | Added only when a real requirement justifies it (Prompt 2). |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/STATUS.md](docs/STATUS.md).
