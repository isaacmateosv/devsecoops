"""Unit tests for the PUBLIC decimal financial model.

Terms are supplied explicitly (no ground-truth leak). This validates the
replacement-service math is exact and overflow-free -- contrast with the legacy
binary's 32-bit defect, which these same large inputs expose (see test_oops / Prompt 3).
"""
from decimal import Decimal

from financial import TreatyTerms, excess_of_loss_recovery

TERMS = TreatyTerms.of("100000.00", "500000.00")


def test_below_attachment():
    assert excess_of_loss_recovery(TERMS, "50000.00") == Decimal("0.00")


def test_at_attachment_boundary():
    assert excess_of_loss_recovery(TERMS, "100000.00") == Decimal("0.00")


def test_within_layer():
    assert excess_of_loss_recovery(TERMS, "350000.00") == Decimal("250000.00")


def test_at_limit_cap():
    assert excess_of_loss_recovery(TERMS, "600000.00") == Decimal("500000.00")


def test_above_limit_caps():
    assert excess_of_loss_recovery(TERMS, "9000000.00") == Decimal("500000.00")


def test_large_value_is_overflow_free():
    # The legacy binary returns 0.00 here (OOPS-001); the correct answer is the cap.
    assert excess_of_loss_recovery(TERMS, "30000000.00") == Decimal("500000.00")


def test_rounding_half_up():
    assert excess_of_loss_recovery(TERMS, "150000.505") == Decimal("50000.51")
