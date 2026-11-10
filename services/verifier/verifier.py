"""Blinded verifier.

This is the ONLY module permitted to read `evaluation-private/` ground truth,
and it does so ONLY for a hypothesis whose status is SUBMITTED (frozen). This
enforces the blueprint rule: the harness reads ground truth *after* rule
submission, never during investigation. The investigator packages never import
this module or the oracle.

It evaluates the submitted rule against the independent oracle on an independent
set of cases (precision/coverage), records mismatches, and surfaces the region
the investigation did not sample as explicit unresolved uncertainty.
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from decimal import Decimal
from pathlib import Path

import config  # from apps/api (on path)
import store
from contracts import Hypothesis, HypothesisStatus, VerificationResult
from financial import TreatyTerms, excess_of_loss_recovery

D = lambda x: Decimal(str(x))
_EVAL = config.REPO_ROOT / "evaluation-private"


def _load_oracle():
    spec = importlib.util.spec_from_file_location("eval_oracle", _EVAL / "oracle" / "oracle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _test_values(max_sampled: Decimal) -> list[Decimal]:
    """Independent evaluation cases inside the sampled region, incl. boundaries."""
    vals = [D(0), D("0.01"), D("99999.99"), D("100000.00"), D("100000.01"),
            D("250000.00"), D("350000.50"), D("599999.99"), D("600000.00"),
            D("600000.01"), D("750000.00"), D("1000000.00")]
    # deterministic spread up to the sampled ceiling
    step = max_sampled / 17
    vals += [(step * k).quantize(D("0.01")) for k in range(1, 17)]
    return [v for v in sorted(set(vals)) if v <= max_sampled]


def oracle_expected(eligible) -> Decimal:
    """Independent correct recovery from the private oracle. Used by the red-team
    Oops workflow as the authoritative 'expected output' (the blueprint's
    'independently specified financial rules'). Oracle authority only."""
    return _load_oracle().recovery(eligible)


class NotSubmitted(RuntimeError):
    pass


def verify(hypothesis_id: str, max_sampled=Decimal("2000000"),
           persist: bool = True) -> VerificationResult:
    hyp = store.get_hypothesis(hypothesis_id)
    if hyp is None:
        raise ValueError("hypothesis not found")
    if hyp.status != HypothesisStatus.SUBMITTED:
        raise NotSubmitted("hypothesis must be SUBMITTED (frozen) before blinded verification")

    oracle = _load_oracle()
    gt_path = _EVAL / "hidden-tests" / "ground_truth.json"
    gt = json.loads(gt_path.read_text())

    terms = TreatyTerms.of(hyp.params["attachment"], hyp.params["limit"],
                           hyp.params.get("currency", "USD"))

    cases = _test_values(D(max_sampled))
    matches = 0
    mismatches = []
    for e in cases:
        predicted = excess_of_loss_recovery(terms, e)
        truth = oracle.recovery(e)
        if predicted == truth:
            matches += 1
        else:
            mismatches.append({"eligible_loss": f"{e:.2f}",
                               "hypothesis": f"{predicted:.2f}", "oracle": f"{truth:.2f}"})

    precision = round(matches / len(cases), 4) if cases else 0.0
    seeded = gt.get("seeded_defects", [{}])[0]
    unresolved = (f"Inference sampled eligible_loss <= {D(max_sampled):.0f}. The oracle's "
                  f"ground truth records a seeded defect ({seeded.get('id','?')}) outside this "
                  f"region (trigger ~{seeded.get('trigger_threshold_eligible_loss','?')}); "
                  f"that region is unverified by this run and is the Prompt 3 target.")

    v = VerificationResult(
        id=f"ver_{uuid.uuid4().hex[:12]}", hypothesis_id=hyp.id,
        precision=precision, num_cases=len(cases), matches=matches, mismatches=mismatches,
        coverage=f"independent oracle on {len(cases)} cases in [0, {D(max_sampled):.0f}]",
        unresolved_uncertainty=unresolved,
        oracle_ref=f"evaluation-private/oracle/oracle.py; ground_truth={gt_path.name}",
    )
    if persist:
        store.insert_verification(v)
    return v
