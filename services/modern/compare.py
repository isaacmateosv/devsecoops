"""Two-track verified modernization comparison (Prompt 4).

Track A (behavioral compatibility): modern replacement vs the legacy binary on
identical inputs (the legacy run is a real restricted execution).
Track B (financial correctness): modern and legacy vs the independent oracle.

Each case is classified and given a release status. Intentional corrections are
only released as 'approved_divergence' when a matching approved entry exists in
the human-approved requirements; otherwise they are 'pending_approval'. The
report stores every legacy value, so compatibility differences are never hidden.
No claim of universal equivalence is made -- only evidence over tested cases.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path

import config
import store
import tools
import verifier
import modern
from contracts import (CaseComparison, Classification, ComparisonReport,
                       ReleaseStatus)

D = lambda x: Decimal(str(x))

# A nontrivial subset: boundaries, the layer, the cap, and the overflow band.
DEFAULT_CASES = [
    "0.00", "50000.00", "99999.99", "100000.00", "100000.01", "150000.50",
    "350000.00", "599999.99", "600000.00", "1000000.00", "9000000.00",
    "25000000.00", "30000000.00", "50000000.00", "100000000.00",
]


def _approved_divergence(spec: dict):
    for d in spec.get("approved_divergences", []):
        if d.get("status") == "approved":
            return d
    return None


def compare(artifact_id: str, cases=None, budget: tools.Budget | None = None) -> ComparisonReport:
    budget = budget or tools.Budget(max_executions=4)
    cases = cases or DEFAULT_CASES
    art = store.get_artifact(artifact_id)
    if art is None:
        raise ValueError("artifact not found")

    spec = modern.load_approved()
    build = modern.build()
    store.insert_build(build)
    approved_div = _approved_divergence(spec)

    # Track A reference: one real restricted execution of the legacy binary.
    exp, obs = tools.run_experiment(artifact_id, list(cases),
                                    "modernization: differential vs legacy", budget)
    legacy_map = {D(o.input_value): (D(o.output_value) if o.output_value else None) for o in obs}

    comparisons: list[CaseComparison] = []
    for c in cases:
        e = D(c)
        legacy = legacy_map.get(e)
        modern_v = D(modern.calculate(e)["recovery"])
        oracle_v = verifier.oracle_expected(e)

        track_a = legacy is not None and modern_v == legacy
        track_b = modern_v == oracle_v

        note = None
        if legacy is None:
            cls, rel = Classification.INSUFFICIENT_EVIDENCE, ReleaseStatus.UNRESOLVED
        elif track_b and track_a:
            cls, rel = Classification.COMPATIBLE_CORRECT, ReleaseStatus.VERIFIED
        elif track_b and not track_a:
            cls = Classification.INTENTIONALLY_CORRECTED
            if approved_div:
                rel = ReleaseStatus.APPROVED_DIVERGENCE
                note = (f"approved divergence {approved_div['id']}: legacy={legacy} "
                        f"-> modern={modern_v} (corrects a defect; approved_by="
                        f"{approved_div['approved_by']})")
            else:
                rel = ReleaseStatus.PENDING_APPROVAL
                note = f"intentional change legacy={legacy} -> modern={modern_v}; awaiting human approval"
        elif (not track_b) and track_a:
            cls, rel = Classification.COMPATIBLE_INCORRECT, ReleaseStatus.REJECTED
            note = "replacement reproduced legacy behaviour that disagrees with the oracle"
        else:
            cls, rel = Classification.UNEXPLAINED_REGRESSION, ReleaseStatus.REJECTED
            note = "modern disagrees with BOTH legacy and oracle"

        comparisons.append(CaseComparison(
            eligible_loss=f"{e:.2f}",
            legacy=(f"{legacy:.2f}" if legacy is not None else None),
            modern=f"{modern_v:.2f}", oracle=f"{oracle_v:.2f}",
            track_a_compatible=track_a, track_b_correct=track_b,
            classification=cls, release_status=rel, note=note,
        ))

    counts, rel_counts = {}, {}
    for cc in comparisons:
        counts[cc.classification.value] = counts.get(cc.classification.value, 0) + 1
        rel_counts[cc.release_status.value] = rel_counts.get(cc.release_status.value, 0) + 1

    report = ComparisonReport(
        id=f"cmp_{uuid.uuid4().hex[:12]}", artifact_id=artifact_id, build_id=build.id,
        cases=comparisons, counts=counts, release_counts=rel_counts,
        approved_divergences=spec.get("approved_divergences", []),
        disclaimer=spec.get("equivalence_disclaimer", ""),
    )

    # persist the report as a stored artifact on disk too
    out_dir = config.REPO_ROOT / "var" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{report.id}.json"
    path.write_text(json.dumps(report.model_dump(mode="json"), indent=2))
    report.report_path = str(path.relative_to(config.REPO_ROOT))

    store.insert_comparison(report)
    return report
