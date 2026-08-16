# Archive: WS2 OCR harness order

This 2026 work order described the retired all-Python OCR harness. It is kept
only to record why the experiment exists; none of its old scripts, schemas,
dry-run commands, or acceptance procedure remains authoritative.

The current boundary is intentionally split:

- `crates/kio-eval/src/ocr_eval.rs` owns provider-independent parsing,
  evaluation, thresholds, verdicts, and report publication.
- `experiments/ocr-verification/provider_mistral.py` owns only calls through the
  official Python-only Mistral SDK.
- `experiments/ocr-verification/fixtures/render_native.py` owns only explicit
  Pillow/reportlab fixture rendering.

Both Python adapters are manual, versioned JSONL boundaries listed exactly in
`eval/python-exceptions.toml`; push/PR CI never runs them. Existing experiment
outputs are historical artifacts, not current evidence.
