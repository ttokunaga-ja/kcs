# Normalized corpus archive

This directory is a non-authorizing archive of 1,015 normalized Markdown
documents recovered from a paid OCR fixture in July 2026. It is retained to
explain historical V3/V4 result artifacts and to avoid paying to recover the
same text again.

The executable V3/V4 Python experiments and their extraction command have been
retired. This corpus is not a current producer input, is not a reproducible Kio
fixture, and must not establish product Recall, embedding, or persona evidence.
Current external-fixture registration and rerank dumps are Rust-owned
`kio-eval fixture register` and `kio-eval rerank dump` operations; they bind
their own explicit inputs and reports.

Archive layout:

```text
corpus/<persona>/<scope path>/<original filename>.md
```

The original extension is intentionally retained before `.md` because the
historical fixture-B expected paths named the pre-normalized file. No current
regeneration command is provided. Git history preserves the retired procedure
if historical investigation is ever necessary.
