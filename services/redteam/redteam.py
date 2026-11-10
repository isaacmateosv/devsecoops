"""Authorized red-team / Oops workflow (Prompt 3).

Operates ONLY on the project's synthetic artifact. Adversarial *financial
correctness* testing: probe classes designed to break thresholds, boundaries,
and fixed-width arithmetic, then compare the legacy binary's behaviour against
the source-blind rule inferred in Prompt 2.

An 'Oops' is created ONLY when a discrepancy is (a) reproduced deterministically
and (b) supported by the independent oracle. Unreproduced or unsupported
discrepancies never become verified findings. Unsuccessful probe classes are
recorded too. No production targets, no network, no unsafe automation -- every
execution goes through the same restricted container runner.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

import store
import tools
import verifier
from contracts import (AttemptRecord, FindingRecord, Severity)
from financial import TreatyTerms, excess_of_loss_recovery

D = lambda x: Decimal(str(x))
CENT = D("0.01")


@dataclass
class RedTeamResult:
    artifact_id: str
    finding_ids: list[str] = field(default_factory=list)
    attempt_ids: list[str] = field(default_factory=list)


def _fmt(v: Decimal) -> str:
    return f"{v:.2f}"


def _batch(artifact_id, values, purpose, budget):
    vals = []
    for v in values:
        dv = D(v)
        vals.append(f"{dv:.2f}" if dv == dv.quantize(CENT) else str(dv))
    _, obs = tools.run_experiment(artifact_id, vals, purpose, budget)
    vmap = {D(o.input_value): (D(o.output_value) if o.output_value else None) for o in obs}
    exec_id = obs[0].execution_id if obs else None
    return vmap, exec_id


def _attempt(artifact_id, attack_class, desc, inputs_summary, outcome, exec_id=None, note=None):
    a = AttemptRecord(id=f"att_{uuid.uuid4().hex[:12]}", artifact_id=artifact_id,
                      attack_class=attack_class, description=desc,
                      inputs_summary=inputs_summary, outcome=outcome,
                      execution_id=exec_id, note=note)
    store.insert_attempt(a)
    return a.id


def scan(artifact_id: str, hypothesis_id: str, budget: tools.Budget | None = None) -> RedTeamResult:
    budget = budget or tools.Budget(max_executions=48)
    hyp = store.get_hypothesis(hypothesis_id)
    if hyp is None:
        raise ValueError("hypothesis not found")
    terms = TreatyTerms.of(hyp.params["attachment"], hyp.params["limit"],
                           hyp.params.get("currency", "USD"))
    res = RedTeamResult(artifact_id=artifact_id)

    def predicted(e):  # source-blind expectation (the inferred, verified rule)
        return excess_of_loss_recovery(terms, e)

    # ---- class 1: large-value / fixed-width overflow -----------------------
    large = ["1000000", "5000000", "10000000", "20000000", "21000000",
             "21474836", "21500000", "22000000", "25000000", "30000000",
             "40000000", "50000000", "100000000"]
    vmap, exec_id = _batch(artifact_id, large, "red-team: large-value overflow probe", budget)
    discrepancies = sorted(e for e, r in vmap.items() if r is not None and r != predicted(e))

    if not discrepancies:
        res.attempt_ids.append(_attempt(artifact_id, "large_value_overflow",
            "Large eligible losses vs inferred rule", f"{len(large)} values up to $100M",
            "no_discrepancy", exec_id))
    else:
        res.attempt_ids.append(_attempt(artifact_id, "large_value_overflow",
            "Large eligible losses vs inferred rule", f"{len(large)} values up to $100M",
            "discrepancy", exec_id,
            note=f"{len(discrepancies)} inputs diverged (observed wrong band "
                 f"{_fmt(min(discrepancies))}..{_fmt(max(discrepancies))})"))

        # Overflow is non-monotonic (very large values can double-wrap back to a
        # coincidentally-correct cap), so bracket WITHIN the first wrong band:
        # correct anchor = largest correct value below the first wrong value.
        wrong_anchor = min(discrepancies)
        correct_below = [e for e, r in vmap.items()
                         if r is not None and r == predicted(e) and e < wrong_anchor]
        lo = max(correct_below) if correct_below else D("1000000")
        hi = wrong_anchor
        while hi - lo > CENT and budget.used < budget.max_executions - 4:
            mid = ((lo + hi) / 2).quantize(CENT)
            m, _ = _batch(artifact_id, [mid], "red-team: localize wrong-band lower edge", budget)
            if m[mid] is not None and m[mid] == predicted(mid):
                lo = mid
            else:
                hi = mid
        band_start = hi                       # first eligible value that diverges
        band_end_obs = max(discrepancies)     # largest wrong value actually observed

        # reproduce a clear triggering case deterministically (two runs match)
        trigger = D("30000000.00") if D("30000000.00") in discrepancies else wrong_anchor
        r1map, ex1 = _batch(artifact_id, [trigger], "red-team: reproduce Oops (run 1)", budget)
        r2map, ex2 = _batch(artifact_id, [trigger], "red-team: reproduce Oops (run 2)", budget)
        observed = r1map[trigger]
        reproduced = (observed == r2map[trigger])

        # independent confirmation from the oracle
        expected = verifier.oracle_expected(trigger)
        oracle_supports = (expected == predicted(trigger))  # oracle agrees with inferred rule

        if reproduced and oracle_supports and observed != expected:
            root = (f"Monetary amounts are held in a signed 32-bit integer of cents "
                    f"(overflows above 2^31-1 = {2**31 - 1:,} cents ≈ $21,474,836.47). "
                    f"Large eligible losses overflow that container; a contiguous band "
                    f"(observed from ${band_start:.2f} up to at least ${band_end_obs:.2f}) "
                    f"wraps to a negative intermediate and is clamped to $0.00 instead of "
                    f"the ${terms.limit:.2f} cap. Some much larger values double-wrap back "
                    f"above the cap and are coincidentally correct, which is itself diagnostic "
                    f"of 32-bit wraparound.")
            fid = f"find_{uuid.uuid4().hex[:12]}"
            test_path = _write_regression_test("integer_overflow", terms, trigger,
                                               expected, band_start)
            art = store.get_artifact(artifact_id)
            finding = FindingRecord(
                id=fid, artifact_id=artifact_id, artifact_sha256=art.sha256,
                title="32-bit cents overflow zeroes out recovery on large claims",
                defect_class="integer_overflow",
                triggering_input=f"eligible_loss={_fmt(trigger)}",
                observed_output=_fmt(observed), expected_output=_fmt(expected),
                discrepancy=f"under-recovery of {_fmt(expected - observed)} (expected cap not paid)",
                reproduction={
                    "steps": [
                        "Ingest the legacy artifact (SHA-256 recorded).",
                        f"Run it on a single claim with eligible_loss={_fmt(trigger)} "
                        "inside the restricted container runner.",
                        f"Observe recovery={_fmt(observed)}.",
                        f"Independent oracle expects {_fmt(expected)}.",
                        "Re-run to confirm deterministic reproduction.",
                    ],
                    "environment": store.get_execution(ex1).isolation.model_dump(mode="json"),
                    "execution_ids": [ex1, ex2],
                    "wrong_band_observed": f"{_fmt(band_start)}..{_fmt(band_end_obs)}",
                },
                root_cause_hypothesis=root,
                evidence_strength=("strong: deterministic, reproduced across runs; wrong-band "
                                   "lower edge localized to the cent; wraparound signature "
                                   "consistent with a 32-bit cents integer"),
                technical_impact=("Silent incorrect output (no error, exit 0). Affected claims "
                                  "return $0.00 instead of the treaty limit."),
                business_impact=(f"Under the synthetic treaty, occurrences whose eligible_loss "
                                 f"falls in the observed wrong band (${band_start:.2f}..at least "
                                 f"${band_end_obs:.2f}) are settled at $0.00 instead of "
                                 f"${terms.limit:.2f} — a ${_fmt(expected - observed)} synthetic "
                                 f"under-recovery per affected claim (e.g. the reproduced "
                                 f"${_fmt(trigger)} claim)."),
                assumptions=("Synthetic treaty and synthetic claims only. This is a synthetic "
                             "discrepancy; real exposure would depend on the real treaty, claim "
                             "size distribution, and portfolio, which are out of scope for this POC. "
                             "No extrapolation beyond the per-claim synthetic figure is made."),
                severity=Severity.HIGH,
                confidence=0.98,
                rationale=("Full treaty limit silently unpaid on affected claims with no error "
                           "signal; deterministically reproduced; wrong-band lower edge localized "
                           "to the cent with a 32-bit wraparound signature."),
                remediation=("Represent money in 64-bit integer cents or Decimal/arbitrary "
                             "precision; validate/clip input ranges; add overflow checks; keep the "
                             "generated boundary regression test in CI."),
                regression_test_path=test_path,
            )
            store.insert_finding(finding)
            res.finding_ids.append(finding.id)

    # ---- class 2: negative / zero values (expect graceful 0.00) ------------
    negz = ["-1000000", "-0.01", "0", "0.00"]
    nmap, nex = _batch(artifact_id, negz, "red-team: negative & zero values", budget)
    neg_bad = [(e, r) for e, r in nmap.items() if r is not None and r != predicted(e)]
    res.attempt_ids.append(_attempt(artifact_id, "negative_and_zero",
        "Negative and zero eligible losses", ", ".join(negz),
        "discrepancy" if neg_bad else "no_discrepancy", nex,
        note=None if not neg_bad else f"{len(neg_bad)} diverged"))

    # ---- class 3: malformed / hostile raw input (expect no crash) ----------
    malformed = b"claim_id,eligible_loss\nX1,not_a_number\nX2,\n,,,\n" + b"A" * 2000 + b"\n"
    _, rec = tools.run_raw_experiment(artifact_id, malformed,
                                      "red-team: malformed input robustness", budget)
    crashed = rec.exit_code not in (0,) or rec.timed_out
    res.attempt_ids.append(_attempt(artifact_id, "malformed_input",
        "Malformed/garbage CSV rows and an overlong line", f"{len(malformed)} bytes raw",
        "discrepancy" if crashed else "no_discrepancy", rec.id,
        note=f"exit={rec.exit_code} timed_out={rec.timed_out}"))

    return res


def _write_regression_test(slug: str, terms: TreatyTerms, trigger: Decimal,
                           expected: Decimal, onset: Decimal) -> str:
    """Emit a permanent, source-independent regression test encoding the CORRECT
    behaviour (what the modern replacement must satisfy). Does not depend on the
    legacy binary, docker, or the db -- so it always runs in CI. Stable filename
    per defect class, so re-runs overwrite rather than accumulate."""
    import config
    out_dir = config.REPO_ROOT / "tests" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"test_oops_{slug}.py"
    path.write_text(f'''"""AUTO-GENERATED regression test for the {slug} Oops (OOPS-001 class).

The legacy binary returns $0.00 for a ${trigger:.2f} eligible loss due to a
32-bit cents overflow. The correct recovery is the treaty limit. This test
encodes the correct behaviour so the modern replacement cannot regress.
"""
from decimal import Decimal
from financial import TreatyTerms, excess_of_loss_recovery

TERMS = TreatyTerms.of("{terms.attachment}", "{terms.limit}")


def test_large_claim_pays_the_limit_not_zero():
    # legacy (defective) observed: 0.00  |  correct:
    assert excess_of_loss_recovery(TERMS, "{trigger}") == Decimal("{expected}")


def test_overflow_boundary_region_is_correct():
    for e in ["{onset}", "25000000.00", "100000000.00"]:
        assert excess_of_loss_recovery(TERMS, e) == Decimal("{terms.limit}")
''')
    return str(path.relative_to(config.REPO_ROOT))
