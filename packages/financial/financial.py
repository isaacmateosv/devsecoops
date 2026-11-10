"""Public financial model interfaces for DevSecOops.

This is the PUBLIC, non-secret financial interface. It defines *how* an
excess-of-loss recovery is computed given explicitly-supplied treaty terms.
It deliberately contains NO treaty constants and NO knowledge of the legacy
binary's behaviour or seeded defects -- those live only in
`evaluation-private/` and are never imported here.

The modern replacement service (Prompt 4) builds on this interface; operators
and verifiers supply the terms they are testing against.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


@dataclass(frozen=True)
class TreatyTerms:
    """Single-layer per-occurrence excess-of-loss terms. USD, to the cent."""
    attachment: Decimal
    limit: Decimal
    currency: str = "USD"

    @classmethod
    def of(cls, attachment, limit, currency: str = "USD") -> "TreatyTerms":
        return cls(Decimal(str(attachment)), Decimal(str(limit)), currency)


def excess_of_loss_recovery(terms: TreatyTerms, eligible_loss) -> Decimal:
    """recovery = min(max(eligible_loss - attachment, 0), limit), half-up to cent.

    Uses exact Decimal arithmetic -- no floating point, no fixed-width integer
    containers -- so it is immune to the legacy binary's overflow class.
    """
    e = Decimal(str(eligible_loss)).quantize(CENT, rounding=ROUND_HALF_UP)
    excess = e - terms.attachment
    if excess < 0:
        excess = Decimal("0")
    if excess > terms.limit:
        excess = terms.limit
    return excess.quantize(CENT, rounding=ROUND_HALF_UP)
