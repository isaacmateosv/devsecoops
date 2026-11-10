"""
Independent financial-correctness oracle for the synthetic excess-of-loss treaty.

EVALUATION-AUTHORITY ONLY. This specification is written independently of the
legacy executable and MUST NOT be imported by, or made readable to, any
investigation/runner process. It is the ground truth against which both the
legacy binary and any modern replacement are judged (Track B).

It uses exact Decimal arithmetic with documented rounding, so it has none of
the legacy binary's 32-bit overflow defect (OOPS-001).

Treaty (single-layer per-occurrence excess of loss), USD, settled to the cent:
    recovery = min( max(eligible_loss - attachment, 0), limit )
    attachment = $100,000.00
    limit      = $500,000.00
Rounding: half-up to the cent.
"""
from decimal import Decimal, ROUND_HALF_UP

ATTACHMENT = Decimal("100000.00")
LIMIT = Decimal("500000.00")
CENT = Decimal("0.01")


def recovery(eligible_loss) -> Decimal:
    e = Decimal(str(eligible_loss)).quantize(CENT, rounding=ROUND_HALF_UP)
    excess = e - ATTACHMENT
    if excess < 0:
        excess = Decimal("0.00")
    if excess > LIMIT:
        excess = LIMIT
    return excess.quantize(CENT, rounding=ROUND_HALF_UP)


# Machine-readable description of the treaty terms, so a verifier can report
# the ground-truth rule without importing legacy behaviour.
SPEC = {
    "treaty_type": "per_occurrence_excess_of_loss_single_layer",
    "currency": "USD",
    "attachment": str(ATTACHMENT),
    "limit": str(LIMIT),
    "formula": "recovery = min(max(eligible_loss - attachment, 0), limit)",
    "rounding": "half_up_to_cent",
}


if __name__ == "__main__":
    import sys, csv
    reader = csv.DictReader(sys.stdin)
    writer = csv.writer(sys.stdout)
    writer.writerow(["claim_id", "recovery"])
    for row in reader:
        writer.writerow([row["claim_id"], f"{recovery(row['eligible_loss']):.2f}"])
