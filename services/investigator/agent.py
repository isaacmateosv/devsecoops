"""Model/provider adapter seam.

Deterministic tools do the real work; an LLM would only narrate hypotheses and
justify experiment choices. Per the blueprint, if no model is configured we run
the deterministic baseline and label AI-only steps as *unavailable* rather than
fabricating agent prose or findings.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AIStatus:
    available: bool
    provider: str
    detail: str

    def dict(self) -> dict:
        return {"available": self.available, "provider": self.provider, "detail": self.detail}


def ai_status() -> AIStatus:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AIStatus(True, "anthropic", "ANTHROPIC_API_KEY present")
    if os.environ.get("OPENAI_API_KEY"):
        return AIStatus(True, "openai", "OPENAI_API_KEY present")
    return AIStatus(False, "none",
                    "No model API key configured; AI narration unavailable. "
                    "Deterministic inference ran in full (this is a labelled gap, not a mock).")


def narrate(context: str) -> str | None:
    """Return model narration, or None when unavailable. Never invents output."""
    st = ai_status()
    if not st.available:
        return None
    # A real provider call would go here (Claude Messages API, etc.). The POC
    # keeps the deterministic path authoritative and does not depend on it.
    return None
