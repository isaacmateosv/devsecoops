#!/usr/bin/env python3
"""End-to-end Prompt 2 workflow (headless): source-blind business-rule inference
+ blinded verification, with real experiments."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "apps", "api"))
import bootstrap  # noqa

import config, ingestion, store, tools, inference, verifier, agent


def main() -> int:
    print("== DevSecOops Prompt 2: black-box business-rule archaeology ==")
    config.ensure_dirs(); store.init_schema()

    art = ingestion.ingest_artifact(config.DEMO_ARTIFACT.read_bytes(), "xol_calc")
    store.insert_artifact(art)
    print(f"[artifact] {art.id} sha256={art.sha256[:16]}…")

    meta = tools.inspect_artifact(art.id)
    print(f"[recon]    {meta.fmt} {meta.machine} static={meta.statically_linked} "
          f"symbols={meta.num_symbols}")
    print(f"[recon]    notable symbols: {meta.notable_symbols}")
    print(f"[recon]    notable strings: {meta.notable_strings[:6]}")

    st = agent.ai_status()
    print(f"[ai]       available={st.available} ({st.detail})")

    budget = tools.Budget()
    res = inference.investigate(art.id, budget)
    print(f"[probe]    real executions used: {budget.used}/{budget.max_executions}")

    for h in store.list_hypotheses(art.id):
        print(f"[hyp]      {h.status.value:9s} conf={h.confidence:<5} {h.formula_name}")
        print(f"             {h.statement}")

    print(f"[coverage] {res.coverage}")
    print(f"[uncertain]{res.unresolved}")

    print("---- blinded verification (oracle read only now, post-submission) ----")
    v = verifier.verify(res.submitted_hypothesis_id)
    print(f"[verify]   precision={v.precision} ({v.matches}/{v.num_cases}) mismatches={len(v.mismatches)}")
    print(f"[verify]   {v.unresolved_uncertainty}")
    print(f"[verify]   oracle_ref={v.oracle_ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
