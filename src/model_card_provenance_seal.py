"""Content-addressed provenance seals for model artifacts and model-card metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import posixpath
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_REVISION = re.compile(r"^[0-9a-fA-F]{40}$")


class _JsonCounter:
    def __init__(self, *, max_nodes: int, max_depth: int, max_string_chars: int) -> None:
        self.max_nodes = max_nodes
        self.max_depth = max_depth
        self.max_string_chars = max_string_chars
        self.nodes = 0

    def touch(self, path: str, depth: int) -> None:
        self.nodes += 1
        if self.nodes > self.max_nodes:
            raise ValueError(f"{path}_node_limit_exceeded")
        if depth > self.max_depth:
            raise ValueError(f"{path}_depth_limit_exceeded")


def _canonical_json(
    value: Any,
    *,
    path: str = "value",
    counter: _JsonCounter | None = None,
    depth: int = 0,
) -> Any:
    counter = counter or _JsonCounter(max_nodes=4096, max_depth=32, max_string_chars=262_144)
    counter.touch(path, depth)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, str):
        if len(value) > counter.max_string_chars:
            raise ValueError(f"{path}_string_too_large")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path}_non_finite")
        return value
    if isinstance(value, list):
        return [
            _canonical_json(item, path=f"{path}[{i}]", counter=counter, depth=depth + 1)
            for i, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path}_key_not_string")
            if len(key) > counter.max_string_chars:
                raise ValueError(f"{path}_key_too_large")
            out[key] = _canonical_json(
                item,
                path=f"{path}.{key}",
                counter=counter,
                depth=depth + 1,
            )
        return out
    raise ValueError(f"{path}_not_canonical_json")


def _digest(obj: object) -> str:
    payload = json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Decision(str, Enum):
    ALLOW = "ALLOW"
    REFUSE = "REFUSE"


@dataclass(frozen=True)
class ModelCardProvenanceSealRequest:
    """Model revision, artifacts, and card metadata to seal or verify."""

    subject_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    budget: float = 2.0
    grant_id: str | None = None
    not_after: float | None = None


@dataclass(frozen=True)
class ModelCardProvenanceSealReceipt:
    decision: Decision
    reasons: tuple[str, ...]
    digest: str
    metrics: dict[str, Any] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "digest": self.digest,
            "metrics": self.metrics,
            "manifest": self.manifest,
        }


class ModelCardProvenanceSeal:
    """Create deterministic seals for immutable model revisions and cards."""

    VALID_PAYLOAD_KEYS = frozenset(
        {"model_id", "revision", "artifacts", "card", "required_card_fields", "expected_seal"}
    )
    DEFAULT_REQUIRED_FIELDS = ("license", "pipeline_tag")
    BASE_WORK_UNITS = 1.0
    ARTIFACT_WORK_UNITS = 0.05
    CARD_FIELD_WORK_UNITS = 0.01
    MAX_ARTIFACTS = 2048
    MAX_CARD_FIELDS = 256
    MAX_CARD_NODES = 4096
    MAX_CARD_DEPTH = 32
    MAX_STRING_CHARS = 262_144

    @staticmethod
    def _normalize_artifact(raw: Any, index: int) -> tuple[dict[str, Any] | None, str | None]:
        if not isinstance(raw, Mapping):
            return None, f"artifact_{index}_not_object"
        path_raw = raw.get("path")
        if not isinstance(path_raw, str):
            return None, f"artifact_{index}_path_type_invalid"
        path = path_raw.strip()
        if not path:
            return None, f"artifact_{index}_path_missing"
        if path.startswith("/") or "\x00" in path:
            return None, f"artifact_{index}_path_invalid"
        normalized_path = posixpath.normpath(path)
        if normalized_path in {".", ".."} or normalized_path.startswith("../"):
            return None, f"artifact_{index}_path_escape"
        sha_raw = raw.get("sha256")
        if not isinstance(sha_raw, str):
            return None, f"artifact_{normalized_path}_sha256_type_invalid"
        sha = sha_raw.lower()
        if not _SHA256.fullmatch(sha):
            return None, f"artifact_{normalized_path}_sha256_invalid"
        size = raw.get("size")
        if size is not None:
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                return None, f"artifact_{normalized_path}_size_invalid"
        artifact = {"path": normalized_path, "sha256": sha}
        if size is not None:
            artifact["size"] = size
        return artifact, None

    @staticmethod
    def _required_fields(raw: Any) -> tuple[str, ...]:
        if raw is None:
            return ModelCardProvenanceSeal.DEFAULT_REQUIRED_FIELDS
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
            raise ValueError("required_card_fields_invalid")
        values: set[str] = set()
        for item in raw:
            if not isinstance(item, str):
                raise ValueError("required_card_fields_type_invalid")
            item = item.strip()
            if item:
                values.add(item)
        fields = tuple(sorted(values))
        if not fields:
            raise ValueError("required_card_fields_empty")
        return fields

    def evaluate(self, req: ModelCardProvenanceSealRequest) -> ModelCardProvenanceSealReceipt:
        if not isinstance(req, ModelCardProvenanceSealRequest):
            raise TypeError("req must be ModelCardProvenanceSealRequest")

        reasons: list[str] = []
        subject_id = str(req.subject_id or "").strip()
        if not subject_id:
            reasons.append("subject_id_missing")
        try:
            budget = float(req.budget)
            if not math.isfinite(budget) or budget <= 0:
                raise ValueError
        except (TypeError, ValueError):
            budget = 0.0
            reasons.append("budget_non_positive")
        if not isinstance(req.payload, Mapping):
            return self._receipt(req, Decision.REFUSE, reasons + ["payload_invalid"])

        unknown = set(req.payload) - self.VALID_PAYLOAD_KEYS
        if unknown:
            reasons.append("payload_keys_unknown:" + ",".join(sorted(unknown)))

        model_id_raw = req.payload.get("model_id")
        model_id = model_id_raw.strip() if isinstance(model_id_raw, str) else ""
        if not model_id or "/" not in model_id:
            reasons.append("model_id_invalid")

        revision_raw = req.payload.get("revision")
        revision = revision_raw.lower() if isinstance(revision_raw, str) else ""
        if not _REVISION.fullmatch(revision):
            reasons.append("revision_not_immutable_commit")

        artifacts_raw = req.payload.get("artifacts")
        if not isinstance(artifacts_raw, list) or not artifacts_raw:
            reasons.append("artifacts_missing")
            artifacts_raw = []
        elif len(artifacts_raw) > self.MAX_ARTIFACTS:
            reasons.append("artifacts_over_limit")
            artifacts_raw = []

        card_raw = req.payload.get("card")
        if not isinstance(card_raw, Mapping):
            reasons.append("card_missing")
            card_raw = {}
        elif len(card_raw) > self.MAX_CARD_FIELDS:
            reasons.append("card_fields_over_limit")
            card_raw = {}

        # Reject clearly over-budget work before artifact iteration, recursive
        # card traversal, sorting, or hashing.
        preflight_work_units = (
            self.BASE_WORK_UNITS
            + len(artifacts_raw) * self.ARTIFACT_WORK_UNITS
            + len(card_raw) * self.CARD_FIELD_WORK_UNITS
        )
        if preflight_work_units > budget:
            reasons.append("work_budget_exceeded")
            return self._receipt(
                req,
                Decision.REFUSE,
                reasons,
                work_units=preflight_work_units,
            )

        artifacts: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for index, raw in enumerate(artifacts_raw):
            artifact, error = self._normalize_artifact(raw, index)
            if error:
                reasons.append(error)
                continue
            assert artifact is not None
            if artifact["path"] in seen_paths:
                reasons.append(f"artifact_{artifact['path']}_duplicate")
                continue
            seen_paths.add(artifact["path"])
            artifacts.append(artifact)
        artifacts.sort(key=lambda item: item["path"])

        try:
            card = _canonical_json(
                card_raw,
                path="card",
                counter=_JsonCounter(
                    max_nodes=self.MAX_CARD_NODES,
                    max_depth=self.MAX_CARD_DEPTH,
                    max_string_chars=self.MAX_STRING_CHARS,
                ),
            )
        except ValueError as exc:
            reasons.append(str(exc))
            card = {}

        try:
            required_fields = self._required_fields(req.payload.get("required_card_fields"))
        except ValueError as exc:
            reasons.append(str(exc))
            required_fields = self.DEFAULT_REQUIRED_FIELDS
        missing_fields = [field for field in required_fields if card.get(field) in (None, "", [], {})]
        if missing_fields:
            reasons.append("card_required_fields_missing:" + ",".join(missing_fields))

        expected_seal_raw = req.payload.get("expected_seal")
        expected_seal: str | None = None
        if expected_seal_raw is not None:
            if not isinstance(expected_seal_raw, str):
                reasons.append("expected_seal_type_invalid")
            else:
                expected_seal = expected_seal_raw.lower()
                if not _SHA256.fullmatch(expected_seal):
                    reasons.append("expected_seal_invalid")

        work_units = (
            self.BASE_WORK_UNITS
            + len(artifacts) * self.ARTIFACT_WORK_UNITS
            + len(card) * self.CARD_FIELD_WORK_UNITS
        )
        if work_units > budget and "work_budget_exceeded" not in reasons:
            reasons.append("work_budget_exceeded")

        artifacts_root = _digest(artifacts)
        card_digest = _digest(card)
        manifest = {
            "schema": "glaciereq.model-card-provenance.v1",
            "subject_id": subject_id,
            "model_id": model_id,
            "revision": revision,
            "artifacts": artifacts,
            "artifacts_root": artifacts_root,
            "card": card,
            "card_digest": card_digest,
            "required_card_fields": list(required_fields),
        }
        seal = _digest(manifest)
        if expected_seal is not None and expected_seal != seal:
            reasons.append("expected_seal_mismatch")

        decision = Decision.REFUSE if reasons else Decision.ALLOW
        if not reasons:
            reasons = ["model_card_provenance_sealed"]
        return self._receipt(
            req,
            decision,
            reasons,
            manifest=manifest,
            seal=seal,
            work_units=work_units,
        )

    def _receipt(
        self,
        req: ModelCardProvenanceSealRequest,
        decision: Decision,
        reasons: Sequence[str],
        *,
        manifest: Mapping[str, Any] | None = None,
        seal: str | None = None,
        work_units: float = 0.0,
    ) -> ModelCardProvenanceSealReceipt:
        unique = tuple(dict.fromkeys(reasons))
        normalized_manifest = dict(manifest or {})
        digest = seal or _digest(
            {
                "decision": decision.value,
                "reasons": list(unique),
                "subject_id": str(req.subject_id or ""),
            }
        )
        metrics = {
            "artifact_count": len(normalized_manifest.get("artifacts", [])),
            "card_field_count": len(normalized_manifest.get("card", {})),
            "work_units": work_units,
            "budget_units": req.budget,
            "expected_seal_checked": req.payload.get("expected_seal") is not None if isinstance(req.payload, Mapping) else False,
        }
        return ModelCardProvenanceSealReceipt(
            decision=decision,
            reasons=unique,
            digest=digest,
            metrics=metrics,
            manifest=normalized_manifest,
        )

    def verify(
        self,
        req: ModelCardProvenanceSealRequest,
        receipt: ModelCardProvenanceSealReceipt,
    ) -> dict[str, Any]:
        recomputed = self.evaluate(req)
        ok = (
            recomputed.decision is receipt.decision
            and recomputed.digest == receipt.digest
            and recomputed.manifest == receipt.manifest
        )
        return {
            "ok": ok,
            "expected_seal": receipt.digest,
            "computed_seal": recomputed.digest,
            "decision": recomputed.decision.value,
        }


Mechanism = ModelCardProvenanceSeal


def cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seal or verify model-card provenance from JSON.")
    parser.add_argument("--input", "-i", help="request JSON file; defaults to stdin")
    args = parser.parse_args(argv)
    try:
        raw = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
        data = json.loads(raw)
        if not isinstance(data, Mapping):
            raise ValueError("request JSON must be an object")
        request = ModelCardProvenanceSealRequest(
            subject_id=str(data.get("subject_id", "")),
            payload=dict(data.get("payload") or {}),
            budget=data.get("budget", 2.0),
            grant_id=data.get("grant_id"),
            not_after=data.get("not_after"),
        )
        receipt = ModelCardProvenanceSeal().evaluate(request)
    except Exception as exc:
        print(json.dumps({"decision": "REFUSE", "reasons": [f"cli_input_error:{type(exc).__name__}:{exc}"]}, sort_keys=True))
        return 2
    print(json.dumps(receipt.as_dict(), indent=2, sort_keys=True))
    return 0 if receipt.decision is Decision.ALLOW else 2
