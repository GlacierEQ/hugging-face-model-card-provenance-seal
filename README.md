# Model Card Provenance Seal

A vendor-neutral content-addressed provenance runtime for binding immutable model artifacts to the metadata that describes them.

> Independent GlacierEQ implementation. Not affiliated with, endorsed by, employed by, or deployed at Hugging Face.

## Purpose

A model card can drift while weights remain unchanged, and weights can change while familiar metadata remains in place. Promotion and consumption should be able to bind both sides to one reproducible identity.

Model Card Provenance Seal creates a deterministic **content-only seal** over:

- model repository identity
- immutable 40-hex revision commit
- normalized artifact paths, SHA-256 digests, and optional sizes
- canonical model-card fields
- the explicit required-card-field policy

`subject_id` identifies the caller/request and is recorded in receipt metrics, but it is deliberately excluded from the manifest and seal. The same model content therefore has the same seal across CI pipelines, release jobs, or consumers using different subject identifiers.

## Capabilities

- immutable revision enforcement
- strict artifact path and digest types, with no string coercion
- artifact digest validation
- duplicate artifact-path refusal
- relative POSIX artifact paths only; absolute paths, traversal, backslashes, and control characters are refused
- deterministic artifact ordering and aggregate artifact root
- strict canonical JSON model-card data
- bounded card depth, node count, top-level field count, and string size
- bounded artifact count
- preflight work refusal before artifact normalization or recursive card traversal
- bounded CLI input before JSON parsing
- configurable required card fields, with `license` and `pipeline_tag` required by default
- deterministic card digest
- deterministic portable provenance seal
- expected-seal verification for promotion or deployment pipelines
- drift detection when card fields or artifact identities change
- fail-closed handling of unknown payload fields
- executable CLI and library API

## Input

```json
{
  "subject_id": "release-42",
  "budget": 2.0,
  "payload": {
    "model_id": "org/model",
    "revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "artifacts": [
      {
        "path": "model.safetensors",
        "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "size": 4096
      }
    ],
    "card": {
      "license": "apache-2.0",
      "pipeline_tag": "text-generation",
      "library_name": "transformers"
    }
  }
}
```

Seal it:

```bash
model-card-seal --input request.json
```

The resulting receipt includes the normalized manifest, `artifacts_root`, `card_digest`, and final seal in `digest`.

To prove that a candidate still matches a previously trusted seal, include that value as `payload.expected_seal`. Any artifact or card drift then produces `REFUSE` with `expected_seal_mismatch`.

## Verify the repository

```bash
python -m pip install .
python -m pytest -q
python scripts/operate.py
```

The operate smoke seals one model/card pair, verifies the expected seal, changes the card, and proves the changed candidate is refused. Tests also prove seal portability across subjects, cross-platform path containment, strict field types, bounded nested cards, and CLI input limits.

## Integration boundary

This package accepts artifact digests and card metadata supplied by the caller. A Hub adapter can fetch a repository commit, enumerate files, hash downloaded artifacts, and parse model-card metadata before calling this engine. Those provider credentials and network calls belong in the consuming integration, not in a fake embedded connection here.
