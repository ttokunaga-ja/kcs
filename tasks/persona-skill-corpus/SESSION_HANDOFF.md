# Cross-session handoff

Use this prompt only after `kio-eval persona plan` has produced an accepted Rust
plan and `kio-eval persona scaffold` has created a fresh workspace. This runbook is operational guidance;
the plan and Rust records remain authoritative.

```text
このリポジトリで `<PERSONA_ID>` 1人分の完全合成 corpus production を担当してください。
最初に tasks/persona-skill-corpus/README.md、COMMON_RULES.md、BATCH_PROTOCOL.md、
PERSONA_INDEX.md、SESSION_HANDOFF.md、tasks/persona-pc-eval-contract.md を読んでください。
accepted Rust plan と Rust が作成した workspace-owner record だけを persona、scope ID、
home path、配分の authority としてください。Python で plan を解析・再生成・scaffold しては
いけません。

workspace は repository 外の absolute root です。親は owner record の正確な bytes の
SHA-256 を `sha256:<hex>` 形式で取得し、すべての lease command に同じ
`--owner-digest <sha256:hex>` を渡します。まず次で親 lease を取得してください:

python3 -m eval.persona_skill_corpus_lease claim \
  --root <workspace-root> --persona <PERSONA_ID> \
  --owner-digest <sha256:hex> --session <unique-parent-session>

返された release_token は親だけが保持し、prompt、metadata、home files に書かないでください。
各 worker を spawn する直前に、plan row の Rust scope ID（home path ではない）で scope
lease を取ります:

python3 -m eval.persona_skill_corpus_lease scope-claim \
  --root <workspace-root> --persona <PERSONA_ID> \
  --scope-id <rust-scope-id> --owner-digest <sha256:hex> \
  --parent-session <parent-session> --worker-session <worker-session>

worker はその plan row の `people/<persona>-<role>/home/<scope-path>/` にだけ final
artifact を置きます。`<scope-path>` は Rust scope ID とは別物です。worker は `_control/`
を編集せず、scope token も受け取りません。Documents/PDF/Spreadsheets/Presentations/
ImageGen の該当 skill を読んで生成・検査し、完了または具体的な blocked checkpoint を親に
報告してください。親は scope-release で同じ `--scope-id` と `--owner-digest` を使って
lease を解放します。

Kio prepare/index/replay/search の実行、chunk 数、history readiness はこの手順の成果では
ありません。filesystem attestation は `persona-materialization.json` の正確な digest に結合した
bytes-only observation であり、それらの claim を true にしません。
```
