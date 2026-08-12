from pathlib import Path

from model_card_provenance_seal import (
    Decision,
    ModelCardProvenanceSeal,
    ModelCardProvenanceSealRequest,
    _read_cli_input,
)


def _payload(path: str = "weights/model.safetensors") -> dict:
    return {
        "model_id": "glaciereq/demo",
        "revision": "a" * 40,
        "artifacts": [{"path": path, "sha256": "b" * 64}],
        "card": {"license": "apache-2.0", "pipeline_tag": "text-generation"},
    }


def test_seal_is_portable_across_subjects() -> None:
    engine = ModelCardProvenanceSeal()
    first = engine.evaluate(ModelCardProvenanceSealRequest("pipeline-a", _payload(), budget=2.0))
    second = engine.evaluate(ModelCardProvenanceSealRequest("pipeline-b", _payload(), budget=2.0))
    assert first.decision is Decision.ALLOW
    assert second.decision is Decision.ALLOW
    assert first.digest == second.digest
    assert first.manifest == second.manifest
    assert first.metrics["subject_id"] == "pipeline-a"
    assert second.metrics["subject_id"] == "pipeline-b"
    assert "subject_id" not in first.manifest


def test_windows_style_backslash_path_refuses() -> None:
    receipt = ModelCardProvenanceSeal().evaluate(
        ModelCardProvenanceSealRequest("release", _payload(r"..\..\secret.bin"), budget=2.0)
    )
    assert receipt.decision is Decision.REFUSE
    assert "artifact_0_path_invalid" in receipt.reasons


def test_control_character_path_refuses() -> None:
    receipt = ModelCardProvenanceSeal().evaluate(
        ModelCardProvenanceSealRequest("release", _payload("weights/evil\nname.bin"), budget=2.0)
    )
    assert receipt.decision is Decision.REFUSE
    assert "artifact_0_path_invalid" in receipt.reasons


def test_cli_file_input_is_bounded_before_json_parse(tmp_path: Path) -> None:
    original = ModelCardProvenanceSeal.MAX_CLI_INPUT_CHARS
    ModelCardProvenanceSeal.MAX_CLI_INPUT_CHARS = 16
    try:
        path = tmp_path / "oversized.json"
        path.write_text("x" * 17, encoding="utf-8")
        try:
            _read_cli_input(str(path))
        except ValueError as exc:
            assert str(exc) == "input_too_large"
        else:
            raise AssertionError("oversized CLI input was accepted")
    finally:
        ModelCardProvenanceSeal.MAX_CLI_INPUT_CHARS = original
