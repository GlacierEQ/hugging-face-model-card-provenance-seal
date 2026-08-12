from model_card_provenance_seal import (
    Decision,
    ModelCardProvenanceSeal,
    ModelCardProvenanceSealRequest,
)

REV = "a" * 40
W1 = "b" * 64
W2 = "c" * 64


def payload(artifacts=None, card=None, **extra):
    value = {
        "model_id": "glaciereq/demo-model",
        "revision": REV,
        "artifacts": artifacts or [
            {"path": "model.safetensors", "sha256": W1, "size": 1024},
            {"path": "config.json", "sha256": W2, "size": 128},
        ],
        "card": card or {
            "license": "apache-2.0",
            "pipeline_tag": "text-generation",
            "library_name": "transformers",
        },
    }
    value.update(extra)
    return value


def evaluate(value=None, budget=2.0):
    return ModelCardProvenanceSeal().evaluate(
        ModelCardProvenanceSealRequest(
            subject_id="release-1",
            payload=value or payload(),
            budget=budget,
        )
    )


def test_valid_model_revision_is_sealed():
    receipt = evaluate()
    assert receipt.decision is Decision.ALLOW
    assert receipt.reasons == ("model_card_provenance_sealed",)
    assert len(receipt.digest) == 64
    assert receipt.manifest["revision"] == REV
    assert receipt.manifest["artifacts_root"]
    assert receipt.manifest["card_digest"]


def test_artifact_order_does_not_change_seal():
    a = {"path": "a.safetensors", "sha256": W1, "size": 10}
    b = {"path": "b.json", "sha256": W2, "size": 20}
    first = evaluate(payload(artifacts=[a, b]))
    second = evaluate(payload(artifacts=[b, a]))
    assert first.decision is Decision.ALLOW
    assert first.digest == second.digest
    assert first.manifest == second.manifest


def test_card_change_changes_seal_and_verification_detects_drift():
    engine = ModelCardProvenanceSeal()
    original_request = ModelCardProvenanceSealRequest("release-1", payload(), budget=2.0)
    original = engine.evaluate(original_request)
    changed_card = dict(payload()["card"])
    changed_card["license"] = "mit"
    changed_request = ModelCardProvenanceSealRequest("release-1", payload(card=changed_card), budget=2.0)
    changed = engine.evaluate(changed_request)
    assert original.digest != changed.digest
    assert engine.verify(changed_request, original)["ok"] is False


def test_expected_seal_enforces_promotion_identity():
    first = evaluate()
    verified = evaluate(payload(expected_seal=first.digest))
    assert verified.decision is Decision.ALLOW
    assert verified.metrics["expected_seal_checked"] is True

    changed_card = dict(payload()["card"])
    changed_card["pipeline_tag"] = "image-classification"
    refused = evaluate(payload(card=changed_card, expected_seal=first.digest))
    assert refused.decision is Decision.REFUSE
    assert "expected_seal_mismatch" in refused.reasons


def test_missing_required_card_field_refuses():
    receipt = evaluate(payload(card={"license": "apache-2.0"}))
    assert receipt.decision is Decision.REFUSE
    assert "card_required_fields_missing:pipeline_tag" in receipt.reasons


def test_custom_required_fields_are_enforced():
    receipt = evaluate(payload(required_card_fields=["license", "pipeline_tag", "library_name", "datasets"]))
    assert receipt.decision is Decision.REFUSE
    assert "card_required_fields_missing:datasets" in receipt.reasons


def test_revision_must_be_immutable_commit():
    receipt = evaluate(payload(revision="main"))
    assert receipt.decision is Decision.REFUSE
    assert "revision_not_immutable_commit" in receipt.reasons


def test_artifact_path_escape_refuses():
    receipt = evaluate(payload(artifacts=[{"path": "../secret", "sha256": W1}]))
    assert receipt.decision is Decision.REFUSE
    assert "artifact_0_path_escape" in receipt.reasons


def test_invalid_artifact_digest_refuses():
    receipt = evaluate(payload(artifacts=[{"path": "model.bin", "sha256": "nope"}]))
    assert receipt.decision is Decision.REFUSE
    assert "artifact_model.bin_sha256_invalid" in receipt.reasons


def test_card_values_must_be_canonical_json():
    receipt = evaluate(payload(card={"license": "mit", "pipeline_tag": "text-generation", "bad": {1, 2}}))
    assert receipt.decision is Decision.REFUSE
    assert "card.bad_not_canonical_json" in receipt.reasons


def test_budget_is_real_work_bound():
    receipt = evaluate(budget=1.0)
    assert receipt.decision is Decision.REFUSE
    assert "work_budget_exceeded" in receipt.reasons
