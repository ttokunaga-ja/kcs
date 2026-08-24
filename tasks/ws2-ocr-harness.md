# Archive: WS2 OCR harness order

This 2026 work order described the retired all-Python OCR harness. It is kept
only to record why the experiment exists; its old scripts, SDK boundary,
JSONL provider schemas, dry-run commands, and acceptance procedure are not
authoritative.

The current boundary is intentionally split:

- `crates/kio-eval/src/ocr_eval.rs` owns provider-independent parsing,
  evaluation, thresholds, verdicts, direct provider HTTP, and report
  publication.
- The manual provider call is a bounded POST to
  `https://api.mistral.ai/v1/ocr`, authenticated by an explicit
  `MISTRAL_API_KEY` and pinned to `mistral-ocr-4-1`. It has no retry, redirect,
  or proxy inheritance; normal push/PR CI never makes a live call.
- `experiments/ocr-verification/fixtures/render_native.py` owns only explicit
  Pillow/reportlab fixture rendering.

The provider's create-only normalized `kio.ocr.response/v2` binds request ID,
document SHA-256, and model, and persists only image count. Pages must arrive
with unique increasing provider indices; Rust normalizes their array order to
canonical zero-based artifact indices. Missing required fields, duplicate or
decreasing indices, and changed required-field types fail closed. The official
Mistral API documentation is the wire reference; additive provider metadata is
ignored rather than persisted, and there is no SDK parity commitment.

`eval/python-exceptions.toml` lists exactly the reference-model and fixture
renderer Python boundaries. Existing experiment outputs are historical,
non-authorizing artifacts, not current evidence.
