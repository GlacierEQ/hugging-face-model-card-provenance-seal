#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from model_card_provenance_seal import (
    Decision,
    ModelCardProvenanceSeal,
    ModelCardProvenanceSealRequest,
)


def main() -> int:
    engine = ModelCardProvenanceSeal()
    base_payload = {
        "model_id": "glaciereq/demo-model",
        "revision": "a" * 40,
        "artifacts": [
            {"path": "model.safetensors", "sha256": "b" * 64, "size": 4096},
            {"path": "config.json", "sha256": "c" * 64, "size": 256},
        ],
        "card": {
            "license": "apache-2.0",
            "pipeline_tag": "text-generation",
            "library_name": "transformers",
        },
    }
    request = ModelCardProvenanceSealRequest("release-demo", base_payload, budget=2.0)
    receipt = engine.evaluate(request)
    if receipt.decision is not Decision.ALLOW:
        print(json.dumps(receipt.as_dict(), indent=2, sort_keys=True))
        return 2

    verified_payload = dict(base_payload)
    verified_payload["expected_seal"] = receipt.digest
    verified_request = ModelCardProvenanceSealRequest("release-demo", verified_payload, budget=2.0)
    verified = engine.evaluate(verified_request)

    changed_payload = dict(base_payload)
    changed_card = dict(base_payload["card"])
    changed_card["license"] = "mit"
    changed_payload["card"] = changed_card
    changed_payload["expected_seal"] = receipt.digest
    drifted = engine.evaluate(ModelCardProvenanceSealRequest("release-demo", changed_payload, budget=2.0))

    output = {
        "sealed": receipt.as_dict(),
        "expected_seal_verified": verified.as_dict(),
        "drifted_promotion": drifted.as_dict(),
        "receipt_verification": engine.verify(request, receipt),
    }
    print(json.dumps(output, indent=2, sort_keys=True))

    if verified.decision is not Decision.ALLOW:
        return 3
    if drifted.decision is not Decision.REFUSE or "expected_seal_mismatch" not in drifted.reasons:
        return 4
    if not engine.verify(request, receipt)["ok"]:
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
