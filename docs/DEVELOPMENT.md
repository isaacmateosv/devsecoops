# Development

## Prerequisites
- Docker (daemon running) — Postgres + the restricted runner.
- Python 3.11+ (tested on 3.9 host venv; 3.12 in the image).
- `gcc:14-bookworm` image is pulled on first binary build.

## Build the synthetic legacy binary
```bash
./scripts/build_demo_binary.sh      # -> demo/artifacts/xol_calc (static linux/arm64 ELF)
```
The source (`evaluation-private/legacy-source/xol_calc.c`) is evaluation
authority only. Never mount `evaluation-private/` into the runner or any agent
tool scope.

## Run
```bash
docker compose -f infra/docker-compose.yml up -d db
export DATABASE_URL=postgresql://devsecoops:devsecoops@localhost:5433/devsecoops
./.venv/bin/python run_workflow.py          # headless end-to-end
./.venv/bin/python -m pytest                 # 14 tests
./.venv/bin/python -m uvicorn app:app --app-dir apps/api --reload  # UI at :8000
```

## Environment variables
See `apps/api/config.py`. Key ones: `DATABASE_URL`, `RUNNER_IMAGE`,
`RUNNER_MEMORY_BYTES`, `RUNNER_CPUS`, `RUNNER_TIMEOUT_S`, `MAX_ARTIFACT_BYTES`.

## Tests requiring infra
`test_isolation.py` skips if the Docker daemon is down; `test_provenance.py`
skips if Postgres is unreachable. `test_financial.py` is pure-unit (always runs).
