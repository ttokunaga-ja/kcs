# V4 accepted profile

`v4-profile.json` is the Rust-consumed frozen result of the completed
2026-07-27 measurement of `Qwen/Qwen3-VL-Embedding-2B` revision `9f2f7e71` on
vLLM 0.26.0. The former Python producer and unconsumed capture/probe/template
artifacts were removed; they remain recoverable from Git history and are not a
runnable reproduction contract.

The accepted Rust identity binds:

- model pin `sha256:c73fa9caeddeb3ff831d46c085a7a5708343248ca777e90f2d486964464509c1`
- prompt-template hash `sha256:7b7f47224b2e5c3fee914cb56bf6c701202dfe2693e4b1160291a81a44389e8b`
- dimensions `768`

Future profile changes require a new typed Rust vector and explicit product
review.
