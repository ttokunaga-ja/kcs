# Cross-session handoff

Use this prompt only after `kio-eval persona plan` has produced an accepted Rust
plan and `kio-eval persona scaffold` has created a fresh workspace. This runbook is operational guidance;
the plan and Rust records remain authoritative.

```text
このリポジトリで `<PERSONA_ID>` 1人分の完全合成 corpus production を担当してください。
最初に tasks/persona-skill-corpus/README.md、COMMON_RULES.md、BATCH_PROTOCOL.md、
PERSONA_INDEX.md、SESSION_HANDOFF.md、tasks/persona-pc-eval-contract.md を読んでください。
accepted Rust plan と Rust が作成した workspace-owner record だけを persona、scope ID、
home path、配分の authority としてください。別の runtime で plan を解析・再生成・scaffold
してはいけません。

workspace は repository 外の absolute root です。親は Rust CLI だけで parent lease を
取得してください。owner record の digest を計算・指定してはいけません:

kio-eval persona lease claim \
  --root <workspace-root> --persona <PERSONA_ID> \
  --session <unique-parent-session>

返された release_token は親だけが保持し、prompt、metadata、home files に書かないでください。
各 worker を spawn する直前に、plan row の Rust scope ID（home path ではない）で scope
lease を取ります:

kio-eval persona lease scope claim \
  --root <workspace-root> --persona <PERSONA_ID> \
  --scope-id <rust-scope-id> \
  --parent-session <parent-session> --worker-session <worker-session>

worker はその plan row の `people/<persona>-<role>/home/<scope-path>/` にだけ final
artifact を置きます。`<scope-path>` は Rust scope ID とは別物です。worker は `_control/`
を編集せず、scope token も受け取りません。Documents/PDF/Spreadsheets/Presentations/
ImageGen の該当 skill を読んで生成・検査し、完了または具体的な blocked checkpoint を親に
報告してください。親は `persona lease scope release` で同じ `--scope-id` と返された
release token を使って lease を解放します。全 scope 完了後に `persona lease release` で
parent lease を解放し、必要なら `persona attest --root <materialized-root> --out <new-report>`
を実行します。

Kio prepare/index/replay/search の実行、chunk 数、history readiness はこの手順の成果では
ありません。Rust filesystem attestation は bounded bytes-only observation であり、Kio
evidence と history readiness の claim を true にしません。
```
