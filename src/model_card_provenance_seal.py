"""Model Card Provenance Seal — SCAFFOLD STUB.

Company lens: Hugging Face (independent; no affiliation).
Bottleneck: Efficient, predictable, safe discovery and use of open AI artifacts.

IMPLEMENTATION: see DEV_UP_INSTRUCTIONS.md
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


def _digest(obj: object) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Decision(str, Enum):
    ALLOW = "ALLOW"
    REFUSE = "REFUSE"


@dataclass(frozen=True)
class ModelCardProvenanceSealRequest:
    """Input envelope — expand fields as the mechanism solidifies."""

    subject_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    budget: float = 1.0
    # Authority / freshness placeholders for the filling AI:
    grant_id: str | None = None
    not_after: float | None = None


@dataclass(frozen=True)
class ModelCardProvenanceSealReceipt:
    decision: Decision
    reasons: tuple[str, ...]
    digest: str
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "digest": self.digest,
            "metrics": self.metrics,
        }


class ModelCardProvenanceSeal:
    """Central mechanism stub.

    Contract the filling AI must preserve:
    - `evaluate(req)` returns a ModelCardProvenanceSealReceipt
    - invalid/empty subject_id → REFUSE
    - budget <= 0 → REFUSE
    - otherwise ALLOW with a content digest over the request
    Replace body with the real algorithm; keep fail-closed edges.
    """

    # Named constants (no magic numbers)
    MIN_BUDGET: float = 0.0
    MAX_REASON_LEN: int = 240

    def evaluate(self, req: ModelCardProvenanceSealRequest) -> ModelCardProvenanceSealReceipt:
        reasons: list[str] = []
        if not req.subject_id or not str(req.subject_id).strip():
            reasons.append("subject_id_missing")
        if req.budget <= self.MIN_BUDGET:
            reasons.append("budget_non_positive")
        # Scaffold: treat missing grant as soft signal only; real impl may hard-refuse.
        if reasons:
            body = {
                "subject_id": req.subject_id,
                "payload": req.payload,
                "budget": req.budget,
                "decision": Decision.REFUSE.value,
                "reasons": reasons,
            }
            return ModelCardProvenanceSealReceipt(
                decision=Decision.REFUSE,
                reasons=tuple(reasons),
                digest=_digest(body),
                metrics={"scaffold": True, "reason_count": len(reasons)},
            )

        body = {
            "subject_id": req.subject_id,
            "payload": req.payload,
            "budget": req.budget,
            "grant_id": req.grant_id,
            "decision": Decision.ALLOW.value,
        }
        return ModelCardProvenanceSealReceipt(
            decision=Decision.ALLOW,
            reasons=("scaffold_allow",),
            digest=_digest(body),
            metrics={
                "scaffold": True,
                "payload_keys": sorted(req.payload.keys()),
                "budget": req.budget,
            },
        )


# Friendly alias for operate scripts
Mechanism = ModelCardProvenanceSeal
