"""AUTO-GENERATED regression test for the integer_overflow Oops (OOPS-001 class).

The legacy binary returns $0.00 for a $30000000.00 eligible loss due to a
32-bit cents overflow. The correct recovery is the treaty limit. This test
encodes the correct behaviour so the modern replacement cannot regress.
"""
from decimal import Decimal
from financial import TreatyTerms, excess_of_loss_recovery

TERMS = TreatyTerms.of("100000.00", "500000.00")


def test_large_claim_pays_the_limit_not_zero():
    # legacy (defective) observed: 0.00  |  correct:
    assert excess_of_loss_recovery(TERMS, "30000000.00") == Decimal("500000.00")


def test_overflow_boundary_region_is_correct():
    for e in ["21574836.48", "25000000.00", "100000000.00"]:
        assert excess_of_loss_recovery(TERMS, e) == Decimal("500000.00")
