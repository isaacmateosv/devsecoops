#!/usr/bin/env python3
"""End-to-end Prompt 1 workflow, runnable headlessly (no HTTP server needed).

Ingests the compiled synthetic legacy binary + sample claims, queues a durable
job, runs it in the restricted container runner, and prints the real evidence
trail. Proves the Prompt 1 acceptance gates against actual records.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "apps", "api"))
import bootstrap  # noqa

import config, ingestion, orchestrator, store


def main() -> int:
    print("== DevSecOops Prompt 1 workflow ==")
    config.ensure_dirs()
    store.init_schema()

    if not config.DEMO_ARTIFACT.exists():
        print("ERROR: demo artifact missing; build it first (see docs/DEVELOPMENT.md)")
        return 1

    art = ingestion.ingest_artifact(config.DEMO_ARTIFACT.read_bytes(), "xol_calc")
    store.insert_artifact(art)
    print(f"[ingest] artifact {art.id}  sha256={art.sha256}  {art.size_bytes}B  {art.media_type}")

    job = orchestrator.submit_execute_job(art.id, config.DEMO_INPUT.read_bytes())
    print(f"[job]    {job.id}  state={job.state.value} (durable; persisted in Postgres)")

    n = orchestrator.run_pending_once()
    print(f"[worker] processed {n} job(s)")

    job = store.get_job(job.id)
    print(f"[job]    {job.id}  state={job.state.value}  execution={job.execution_id}")

    rec = store.get_execution(job.execution_id)
    print(f"[exec]   {rec.id}  exit={rec.exit_code}  {rec.duration_ms}ms  timed_out={rec.timed_out}")
    print(f"[exec]   isolation: engine={rec.isolation.engine} net={rec.isolation.network} "
          f"user={rec.isolation.user} caps={rec.isolation.cap_drop} "
          f"mem={rec.isolation.memory_bytes}B cpus={rec.isolation.cpus} "
          f"ro_rootfs={rec.isolation.read_only_rootfs}")
    print(f"[exec]   stdout_sha256={rec.stdout_sha256}")
    print("---- legacy binary output (from stored record) ----")
    print(rec.stdout.rstrip())
    print("---------------------------------------------------")
    print("Prompt 1 evidence is persisted. Oracle comparison / Oops are Prompt 2-3.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
