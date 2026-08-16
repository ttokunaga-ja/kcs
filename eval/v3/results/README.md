# V3 archived measurement artifacts

This directory preserves non-authorizing measurements from the completed V3
MRL-width experiment.  The executable Python experiment was removed after the
product decision was frozen in Rust.

- `v3-mrl.json` and `v3-tie-diagnostic.json` are the original exploratory
  measurements.
- `v3b-mrl.json` and `v3b-v8a-mrl.json` are the 24-query fixture measurements.
- Native 2048 recall@10 was `0.5417`; MRL 768 recall@10 was `0.5833`.

These files do not authorize a product run and are not a current reproduction
procedure.  The accepted product contract is the frozen
`LOCAL_EMBEDDING_DIMENSIONS` constant and its Rust tests.  Any future model or
width comparison must introduce a typed Rust evaluator and new frozen vectors
instead of reviving the removed scripts.
