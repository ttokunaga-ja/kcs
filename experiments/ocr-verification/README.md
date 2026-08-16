# OCR native adapters

OCR evaluation is Rust-owned. `kio-eval` parses typed ground truth and OCR
responses, applies table-recall/Japanese-CER/image-count thresholds,
classifies formula output, and creates report data and verdicts. This directory
is not an executable evaluation harness.

The two Python files are deliberately narrow native-runtime boundaries:

- `provider_mistral.py` calls the official `mistralai` SDK. It accepts exactly
  one `kio.ocr.provider-request/v1` JSONL record on stdin and emits exactly one
  `kio.ocr.provider-response/v1` record on stdout. It has no verdict,
  reporting, fixture selection, output discovery, or dry-run mode.
- `fixtures/render_native.py` uses Pillow and reportlab to render explicitly
  named image inputs to one explicitly named create-only PDF. Its request and
  response schemas are `kio.ocr.fixture-render.request/v1` and
  `kio.ocr.fixture-render.response/v1`; its response binds the final PDF's
  byte count and SHA-256. Its parent directory must already exist and output
  creation is exclusive/nofollow, so it cannot replace an archive artifact.

The Rust caller owns absolute-path authorization, adapter subprocess limits,
timeouts, stdout/stderr byte bounds, response identity validation, and all
filesystem/report policy. These adapters are manual lanes only: they are not
run by push/PR CI. `MISTRAL_API_KEY` is required only for the provider and is
never persisted by it.

## Manual Rust-owned flow

The interpreter, adapter, inputs, and outputs are always explicit canonical
absolute paths. The provider command snapshots at most 16 MiB of PDF bytes in
Rust and sends those bytes over the versioned JSONL boundary; Python never
reopens the document path.

```bash
MISTRAL_API_KEY=... kio-eval ocr provider \
  --python /absolute/path/to/venv/bin/python3 \
  --adapter /absolute/path/to/provider_mistral.py \
  --document /absolute/path/to/input.pdf \
  --model mistral-ocr-latest --request-id manual-001 \
  --out /absolute/path/to/normalized-response.json

kio-eval ocr evaluate \
  --ground-truth /absolute/path/to/ground-truth-v1.json \
  --response /absolute/path/to/normalized-response.json \
  --out /absolute/path/to/evaluation-report.json

kio-eval ocr render \
  --python /absolute/path/to/venv/bin/python3 \
  --adapter /absolute/path/to/fixtures/render_native.py \
  --request-id render-001 \
  --image /absolute/path/to/page-1.png \
  --out /absolute/path/to/rendered.pdf
```

All three outputs are create-only. The provider child receives only
`MISTRAL_API_KEY`; the renderer receives no credentials. Rust owns the
normalized OCR response, threshold verdict, and report schemas.

Existing PDFs, PNGs, and `out*/` response/report files are retained as
non-authorizing archive artifacts. They are neither fixture-discovery inputs
nor evidence of a current OCR verdict.
