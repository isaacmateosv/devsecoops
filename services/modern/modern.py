"""Modern replacement service logic (Prompt 4).

Decimal, overflow-free implementation of the APPROVED treaty subset, with a
transparent, step-by-step calculation trace. Built from the human-approved
requirements file (policy input) -- NOT from the legacy binary and NOT from the
private oracle. The oracle independently checks correctness (Track B).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import config
from contracts import BuildRecord
from financial import TreatyTerms, excess_of_loss_recovery

CENT = Decimal("0.01")
APPROVED_REQUIREMENTS = config.REPO_ROOT / "demo" / "approved-requirements.json"


def load_approved() -> dict:
    return json.loads(APPROVED_REQUIREMENTS.read_text())


def approved_terms() -> TreatyTerms:
    t = load_approved()["treaty"]
    return TreatyTerms.of(t["attachment"], t["limit"], t["currency"])


def approved_spec_sha256() -> str:
    return hashlib.sha256(APPROVED_REQUIREMENTS.read_bytes()).hexdigest()


class ValidationError(ValueError):
    pass


def calculate(eligible_loss) -> dict:
    """Return the recovery plus a transparent trace. Robust validation; the
    output is deterministic and uses exact Decimal arithmetic (no fixed-width
    integers, so the legacy overflow class cannot occur)."""
    spec = load_approved()
    terms = approved_terms()
    try:
        e = Decimal(str(eligible_loss))
    except Exception:
        raise ValidationError(f"eligible_loss is not a number: {eligible_loss!r}")
    if e < 0:
        raise ValidationError("eligible_loss must be >= 0")
    if e > Decimal("1e12"):
        raise ValidationError("eligible_loss exceeds supported subset ceiling (1e12)")

    e_q = e.quantize(CENT, rounding=ROUND_HALF_UP)
    excess = e_q - terms.attachment
    excess_floored = excess if excess > 0 else Decimal("0.00")
    capped = excess_floored if excess_floored < terms.limit else terms.limit
    recovery = excess_of_loss_recovery(terms, e)  # authoritative value

    trace = [
        {"step": "input", "eligible_loss": str(e), "rounded_to_cent": f"{e_q:.2f}"},
        {"step": "subtract_attachment", "attachment": f"{terms.attachment:.2f}",
         "excess": f"{excess:.2f}"},
        {"step": "floor_at_zero", "value": f"{excess_floored:.2f}"},
        {"step": "cap_at_limit", "limit": f"{terms.limit:.2f}", "value": f"{capped:.2f}"},
        {"step": "recovery", "value": f"{recovery:.2f}", "currency": terms.currency},
    ]
    return {"eligible_loss": str(e), "recovery": f"{recovery:.2f}",
            "currency": terms.currency, "trace": trace,
            "spec_version": spec.get("treaty"), "overflow_safe": True}


def build() -> BuildRecord:
    spec = load_approved()
    return BuildRecord(
        id=f"build_{uuid.uuid4().hex[:12]}",
        version="0.1.0",
        approved_spec_sha256=approved_spec_sha256(),
        supported_subset=spec["supported_subset"],
    )
