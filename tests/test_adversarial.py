from model_card_provenance_seal import Decision, ModelCardProvenanceSeal, ModelCardProvenanceSealRequest


def _evaluate(payload: dict):
    return ModelCardProvenanceSeal().evaluate(
        ModelCardProvenanceSealRequest("release-adversarial", payload, budget=3.0)
    )


def _base() -> dict:
    return {
        "model_id": "glaciereq/demo",
        "revision": "a" * 40,
        "artifacts": [{"path": "weights/model.safetensors", "sha256": "b" * 64, "size": 100}],
        "card": {"license": "apache-2.0", "pipeline_tag": "text-generation"},
    }


def test_duplicate_artifact_paths_refuse() -> None:
    payload = _base()
    payload["artifacts"] = [
        {"path": "weights/model.safetensors", "sha256": "b" * 64},
        {"path": "weights/model.safetensors", "sha256": "c" * 64},
    ]
    receipt = _evaluate(payload)
    assert receipt.decision is Decision.REFUSE
    assert "artifact_weights/model.safetensors_duplicate" in receipt.reasons


def test_absolute_artifact_path_refuses() -> None:
    payload = _base()
    payload["artifacts"] = [{"path": "/etc/passwd", "sha256": "b" * 64}]
    receipt = _evaluate(payload)
    assert receipt.decision is Decision.REFUSE
    assert "artifact_0_path_invalid" in receipt.reasons


def test_negative_artifact_size_refuses() -> None:
    payload = _base()
    payload["artifacts"] = [{"path": "weights.bin", "sha256": "b" * 64, "size": -1}]
    receipt = _evaluate(payload)
    assert receipt.decision is Decision.REFUSE
    assert "artifact_weights.bin_size_invalid" in receipt.reasons


def test_unknown_payload_field_refuses() -> None:
    payload = _base()
    payload["trust_me"] = True
    receipt = _evaluate(payload)
    assert receipt.decision is Decision.REFUSE
    assert "payload_keys_unknown:trust_me" in receipt.reasons


def test_invalid_expected_seal_refuses() -> None:
    payload = _base()
    payload["expected_seal"] = "not-a-digest"
    receipt = _evaluate(payload)
    assert receipt.decision is Decision.REFUSE
    assert "expected_seal_invalid" in receipt.reasons


def test_model_identity_must_include_namespace() -> None:
    payload = _base()
    payload["model_id"] = "unnamespaced"
    receipt = _evaluate(payload)
    assert receipt.decision is Decision.REFUSE
    assert "model_id_invalid" in receipt.reasons


def test_card_key_order_is_canonical() -> None:
    first = _base()
    second = _base()
    first["card"] = {"license": "apache-2.0", "pipeline_tag": "text-generation", "tags": ["a", "b"]}
    second["card"] = {"tags": ["a", "b"], "pipeline_tag": "text-generation", "license": "apache-2.0"}
    a = _evaluate(first)
    b = _evaluate(second)
    assert a.decision is Decision.ALLOW
    assert a.digest == b.digest
