# V4 archived result artifacts

These files record the completed 2026-07-27 measurement of
`Qwen/Qwen3-VL-Embedding-2B` revision `9f2f7e71` on vLLM 0.26.0.

- `v4-capture.json` and `v4-probe*.json` are immutable raw observations.
- `chat_template.confirmed.jinja` is the confirmed template witness.
- `v4-profile.json` is the accepted derived profile.

The accepted Rust identity binds:

- model pin `sha256:c73fa9caeddeb3ff831d46c085a7a5708343248ca777e90f2d486964464509c1`
- prompt-template hash `sha256:7b7f47224b2e5c3fee914cb56bf6c701202dfe2693e4b1160291a81a44389e8b`
- dimensions `768`

The former Python producer was deliberately removed.  These artifacts are an
archive, not a runnable product contract; future profile changes require a new
typed Rust vector and explicit product review.
