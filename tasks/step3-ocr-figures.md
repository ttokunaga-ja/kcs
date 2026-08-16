# Archive: OCR figure-risk investigation

This task was completed in July 2026 and is retained only as historical context.
Its former Python harness and executable reproduction instructions are not a
current product contract and were removed during the Rust evaluator cutover.

The archived measurement found that native text, tables, formulae, scans, and
document photos were generally recovered, while text embedded in chart/diagram
regions could be returned as image content and therefore remain unsearchable.
That result motivated the current typed Rust OCR evaluator and its explicit
image-count and text-recall evidence.

Current authority:

- Rust owns typed ground-truth/response parsing, metrics, thresholds, verdicts,
  and create-only reports in `crates/kio-eval/src/ocr_eval.rs`.
- `experiments/ocr-verification/provider_mistral.py` is only the official
  Mistral-SDK adapter.
- `experiments/ocr-verification/fixtures/render_native.py` is only the
  Pillow/reportlab fixture-rendering adapter.
- Existing PDFs, PNGs, and `out*/` files under the experiment directory are
  non-authorizing archives and are not consumed implicitly.

Any future paid OCR measurement must be initiated manually through the
versioned adapter schemas documented in `experiments/ocr-verification/README.md`.
It is never part of push/PR CI.
