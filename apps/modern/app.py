"""Standalone modern replacement service (Prompt 4 deliverable).

A small, self-contained FastAPI service implementing the APPROVED excess-of-loss
subset with Decimal arithmetic, robust validation, deterministic output, and a
transparent calculation trace. Containerized via infra/Dockerfile.modern.

It depends only on packages/financial and the approved-requirements file -- no
database, no legacy binary, no oracle -- so it is a clean, auditable deployable.
"""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "financial"))

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from financial import TreatyTerms, excess_of_loss_recovery  # noqa: E402

CENT = Decimal("0.01")
APPROVED = Path(os.environ.get("APPROVED_REQUIREMENTS", ROOT / "demo" / "approved-requirements.json"))

app = FastAPI(title="DevSecOops modern XoL service", version="0.1.0")


def _spec() -> dict:
    return json.loads(APPROVED.read_text())


def _terms() -> TreatyTerms:
    t = _spec()["treaty"]
    return TreatyTerms.of(t["attachment"], t["limit"], t["currency"])


class Claim(BaseModel):
    claim_id: Optional[str] = None
    eligible_loss: str


@app.get("/health")
def health():
    return {"status": "ok", "service": "modern-xol", "supported_subset": _spec()["supported_subset"]}


@app.post("/calculate")
def calculate(claim: Claim):
    terms = _terms()
    try:
        e = Decimal(str(claim.eligible_loss))
    except Exception:
        raise HTTPException(status_code=422, detail="eligible_loss is not a number")
    if e < 0:
        raise HTTPException(status_code=422, detail="eligible_loss must be >= 0")
    if e > Decimal("1e12"):
        raise HTTPException(status_code=422, detail="eligible_loss exceeds supported subset")
    e_q = e.quantize(CENT, rounding=ROUND_HALF_UP)
    excess = e_q - terms.attachment
    floored = excess if excess > 0 else Decimal("0.00")
    capped = floored if floored < terms.limit else terms.limit
    recovery = excess_of_loss_recovery(terms, e)
    return {
        "claim_id": claim.claim_id, "eligible_loss": str(e),
        "recovery": f"{recovery:.2f}", "currency": terms.currency, "overflow_safe": True,
        "trace": [
            {"step": "input", "rounded_to_cent": f"{e_q:.2f}"},
            {"step": "subtract_attachment", "attachment": f"{terms.attachment:.2f}", "excess": f"{excess:.2f}"},
            {"step": "floor_at_zero", "value": f"{floored:.2f}"},
            {"step": "cap_at_limit", "limit": f"{terms.limit:.2f}", "value": f"{capped:.2f}"},
            {"step": "recovery", "value": f"{recovery:.2f}"},
        ],
    }
