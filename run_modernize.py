#!/usr/bin/env python3
"""End-to-end Prompt 4 workflow (headless): build the modern replacement and run
Track A (vs legacy) + Track B (vs oracle) differential verification."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "apps", "api"))
import bootstrap  # noqa

import config, ingestion, store, tools, compare, modern


def main() -> int:
    print("== DevSecOops Prompt 4: verified financial modernization ==")
    config.ensure_dirs(); store.init_schema()

    art = ingestion.ingest_artifact(config.DEMO_ARTIFACT.read_bytes(), "xol_calc")
    store.insert_artifact(art)
    print(f"[artifact] {art.id} sha256={art.sha256[:16]}…")
    print(f"[build]    modern spec sha256={modern.approved_spec_sha256()[:16]}…")

    rep = compare.compare(art.id, budget=tools.Budget(max_executions=4))
    print(f"[report]   {rep.id}  build={rep.build_id}  artifact={rep.report_path}")
    print(f"{'eligible':>16} {'legacy':>12} {'modern':>12} {'oracle':>12}  A  B  classification / release")
    for c in rep.cases:
        print(f"{c.eligible_loss:>16} {str(c.legacy):>12} {c.modern:>12} {c.oracle:>12}  "
              f"{'Y' if c.track_a_compatible else 'n'}  {'Y' if c.track_b_correct else 'n'}  "
              f"{c.classification.value} / {c.release_status.value}")
    print(f"[counts]   {rep.counts}")
    print(f"[release]  {rep.release_counts}")
    for d in rep.approved_divergences:
        print(f"[approved] {d['id']} ({d['status']}) by {d['approved_by']}")
    print(f"[disclaimer] {rep.disclaimer}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
