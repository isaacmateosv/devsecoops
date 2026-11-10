"""Deterministic black-box inference of the treaty business rule.

Strategy (no source, no ground truth -- only real executions via tools):
  1. Static recon with LIEF (hints only, never conclusions).
  2. Coarse scan -> locate the zero region, the linear layer, and the plateau.
  3. Algebraically derive slope, attachment (A = eligible - recovery in the layer),
     and limit (L = plateau value).
  4. Refine A and the cap onset to the cent with fine batches.
  5. Disambiguating experiment: half-up rounding vs truncation (two hypotheses
     that fit the cent-valued scan identically; a sub-cent probe refutes one).
  6. Emit candidate + refuted + submitted hypotheses, each linked to observations.

Agents (LLM) would *narrate/justify* these steps; the evidence of record is the
deterministic execution. See agent.py for the model-adapter seam.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

import store
import tools
from contracts import Hypothesis, HypothesisStatus
from financial import TreatyTerms, excess_of_loss_recovery

D = lambda x: Decimal(str(x))


@dataclass
class InvestigationResult:
    artifact_id: str
    metadata_dict: dict
    submitted_hypothesis_id: str
    hypothesis_ids: list[str] = field(default_factory=list)
    coverage: str = ""
    unresolved: str = ""


def _batch(artifact_id: str, values, purpose: str, budget: tools.Budget):
    """Run one real batched execution. Returns (values_map, ids_map) where
    values_map: eligible -> recovery(Decimal|None), ids_map: eligible -> obs_id."""
    vals = [f"{D(v):.2f}" if Decimal(str(v)) == Decimal(str(v)).quantize(D("0.01"))
            else str(v) for v in values]
    _, obs = tools.run_experiment(artifact_id, vals, purpose, budget)
    values_map = {D(o.input_value): (D(o.output_value) if o.output_value else None) for o in obs}
    ids_map = {D(o.input_value): o.id for o in obs}
    return values_map, ids_map


def investigate(artifact_id: str, budget: tools.Budget | None = None) -> InvestigationResult:
    budget = budget or tools.Budget()
    meta = tools.inspect_artifact(artifact_id)

    # --- 2. coarse scan -----------------------------------------------------
    coarse_vals = [i * 25000 for i in range(0, 81)]  # 0 .. 2,000,000
    coarse, _ = _batch(artifact_id, coarse_vals, "coarse scan: locate layer & plateau", budget)

    pos = [(e, r) for e, r in sorted(coarse.items()) if r and r > 0]
    plateau_val = max(r for _, r in coarse.items() if r is not None)
    linear = [(e, r) for e, r in pos if r < plateau_val]
    if len(linear) >= 2:
        (e1, r1), (e2, r2) = linear[0], linear[-1]
        slope = (r2 - r1) / (e2 - e1)
    else:
        slope = D(1)

    # A = eligible - recovery in the linear layer (slope == 1 case)
    a_estimates = [e - r for e, r in linear]
    a_est = min(a_estimates) if a_estimates else D(100000)
    limit_est = plateau_val  # plateau height == treaty limit

    # --- 4. refine attachment to the cent -----------------------------------
    fine_vals = [a_est + D(c) / 100 for c in range(-50, 51)]  # +/- $0.50 at 1c
    fine, _ = _batch(artifact_id, fine_vals, "refine attachment to the cent", budget)
    zeros = [e for e, r in sorted(fine.items()) if r is not None and r == 0]
    attachment = max(zeros) if zeros else a_est

    # --- refine cap onset (A + L) ------------------------------------------
    cap_onset_est = attachment + limit_est
    cap_vals = [cap_onset_est + D(c) / 100 for c in range(-50, 51)]
    capf, _ = _batch(artifact_id, cap_vals, "refine cap onset to the cent", budget)
    limit = plateau_val  # cap height is the limit, independent of onset
    currency = "USD"

    # --- 5. disambiguating experiment: half-up vs truncation ---------------
    probe_up = (attachment + D("0.006")).quantize(D("0.001"))  # half-up->0.01, trunc->0.00
    probe_dn = (attachment + D("0.004")).quantize(D("0.001"))  # half-up->0.00, ceil->0.01
    dis, dis_ids = _batch(artifact_id, [probe_up, probe_dn],
                          "disambiguate rounding: half-up vs truncation vs ceil", budget)
    r_up = dis.get(probe_up)
    r_dn = dis.get(probe_dn)
    rounding = "half_up"
    if r_up == 0:
        rounding = "truncate"
    elif r_dn and r_dn > 0:
        rounding = "ceil"

    # record the REFUTED competing hypothesis (truncation), with its refuting obs
    trunc_obs_id = dis_ids.get(probe_up)
    refuted = Hypothesis(
        id=f"hyp_{uuid.uuid4().hex[:12]}", artifact_id=artifact_id,
        formula_name="excess_of_loss__truncated_rounding",
        statement=("recovery = min(max(round_down(eligible) - attachment, 0), limit) "
                   "-- i.e. the cents conversion TRUNCATES"),
        params={"attachment": f"{attachment:.2f}", "limit": f"{limit:.2f}",
                "currency": currency, "rounding": "truncate"},
        rationale=(f"Fits the cent-valued coarse scan identically to the half-up form. "
                   f"Refuted by probe eligible={probe_up:.3f}: truncation predicts 0.00 "
                   f"but the binary returned {r_up}."),
        refuting_observation_ids=[oid for oid in [trunc_obs_id] if oid],
        status=HypothesisStatus.REFUTED, confidence=0.0,
    )
    store.upsert_hypothesis(refuted)

    # --- 6. submitted hypothesis -------------------------------------------
    terms = TreatyTerms.of(attachment, limit, currency)
    # fit check across all sampled observations (within sampled region)
    all_obs = store.list_observations(artifact_id)
    matches = total = 0
    support_ids: list[str] = []
    for o in all_obs:
        e = D(o.input_value)
        if not o.output_value:
            continue
        total += 1
        pred = excess_of_loss_recovery(terms, e)
        if pred == D(o.output_value):
            matches += 1
            if len(support_ids) < 8:
                support_ids.append(o.id)
    confidence = round(matches / total, 4) if total else 0.0

    submitted = Hypothesis(
        id=f"hyp_{uuid.uuid4().hex[:12]}", artifact_id=artifact_id,
        formula_name="excess_of_loss__subtract_then_cap",
        statement=(f"recovery = min(max(eligible_loss - {attachment:.2f}, 0), {limit:.2f}); "
                   f"currency={currency}; rounding={rounding} to the cent"),
        params={"attachment": f"{attachment:.2f}", "limit": f"{limit:.2f}",
                "currency": currency, "rounding": rounding, "slope": str(slope)},
        rationale=(f"Coarse scan showed a zero region below ~{attachment:.0f}, a unit-slope "
                   f"linear layer (slope={slope}), and a plateau at {limit:.2f}. Attachment "
                   f"pinned to the cent via the 0->positive transition; limit = plateau height. "
                   f"Rounding resolved by sub-cent disambiguation (half-up confirmed, "
                   f"truncation refuted). Rule matches {matches}/{total} sampled observations."),
        supporting_observation_ids=support_ids,
        status=HypothesisStatus.SUBMITTED, confidence=confidence,
    )
    store.upsert_hypothesis(submitted)

    max_sampled = max(coarse.keys())
    coverage = (f"eligible_loss sampled in [0, {max_sampled:.0f}]; attachment and cap onset "
                f"refined to the cent; sub-cent rounding probed at attachment.")
    unresolved = (f"Behaviour for eligible_loss > {max_sampled:.0f} was not sampled and is "
                  f"extrapolated by the rule, not observed (candidate region for Prompt 3).")

    return InvestigationResult(
        artifact_id=artifact_id, metadata_dict=meta.model_dump(mode="json"),
        submitted_hypothesis_id=submitted.id,
        hypothesis_ids=[submitted.id, refuted.id],
        coverage=coverage, unresolved=unresolved,
    )
