#!/usr/bin/env python3
"""End-to-end Prompt 3 workflow (headless): infer the rule, then red-team the
legacy binary to discover, reproduce, and independently confirm the seeded Oops."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "apps", "api"))
import bootstrap  # noqa

import config, ingestion, store, tools, inference, redteam


def main() -> int:
    print("== DevSecOops Prompt 3: offensive financial assurance / the Oops ==")
    config.ensure_dirs(); store.init_schema()

    art = ingestion.ingest_artifact(config.DEMO_ARTIFACT.read_bytes(), "xol_calc")
    store.insert_artifact(art)
    res = inference.investigate(art.id, tools.Budget())
    print(f"[setup]   inferred rule hypothesis {res.submitted_hypothesis_id}")

    rt = redteam.scan(art.id, res.submitted_hypothesis_id, tools.Budget(max_executions=48))

    print("---- red-team attempts (incl. unsuccessful) ----")
    for a in store.list_attempts(art.id):
        print(f"[attempt] {a.attack_class:22s} -> {a.outcome:14s} ({a.inputs_summary})"
              + (f"  :: {a.note}" if a.note else ""))

    print("---- verified Oops findings ----")
    if not rt.finding_ids:
        print("[oops]    none verified this run")
    for fid in rt.finding_ids:
        f = store.get_finding(fid)
        print(f"[OOPS]    {f.id}  severity={f.severity.value} confidence={f.confidence}")
        print(f"          {f.title}")
        print(f"          trigger: {f.triggering_input}")
        print(f"          observed={f.observed_output}  expected={f.expected_output}  "
              f"discrepancy={f.discrepancy}")
        print(f"          root cause: {f.root_cause_hypothesis}")
        print(f"          business impact: {f.business_impact}")
        print(f"          regression test: {f.regression_test_path}")
        print(f"          reproduction execution_ids: {f.reproduction['execution_ids']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
