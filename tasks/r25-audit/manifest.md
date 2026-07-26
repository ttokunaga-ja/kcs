# R25 実装監査 manifest (2026-07-25)

対象 = 直近の replication + write-through 変更を含む作業ツリー全体。
`crates/kio-cli/src/main.rs` 24,688 行 / `tasks/step4b-backlog.md` 446 行 /
`docs/05-runtime.md` 1,319 行 の時点。

## ラン構成

| tag | CLI | model | 固有引数 | 渡し方 | 開始 | 終了 | EXIT | 出力 | 読了証明 |
|---|---|---|---|---|---|---|---|---|---|
| sol1 | codex exec | `gpt-5.6-sol` | `model_reasoning_effort=ultra` | パス渡し・repo 自律読込 | 21:53:55 | 22:23:47 | 0 | 22,543 B / 333 行 | 一致 (24688/446/1319 + 最終 2 行 verbatim) |
| terra1 | codex exec | `gpt-5.6-terra` | `model_reasoning_effort=ultra` | パス渡し・repo 自律読込 | 21:54:15 | 22:11:54 | 0 | 14,706 B / 149 行 | 一致 |
| terra2 | codex exec | `gpt-5.6-terra` | `model_reasoning_effort=ultra` | パス渡し・repo 自律読込 | 21:54:35 | 22:11:15 | 0 | 13,141 B / 147 行 | 一致 |
| glm1 | opencode run | `zai-coding-plan/glm-5.2` | `--variant low` | 文書埋め込み (`target.md` 2,180 行) | 21:55:25 | 22:00:00 | 0 | 6,993 B / 50 行 | 行数一致・最終 2 行は内容行のみ (2 行目が code fence のため部分一致) |

- 全ラン `-s read-only` / `--ephemeral` / 専用作業 dir。glm は `XDG_DATA_HOME` を分離。
- stagger: codex 20 秒、glm 50 秒。watchdog 4,500 秒 — 発火なし。
- 事前プローブ: 4 系統すべて極小プロンプトで `7` を返すことを確認済み。

## 材料の完全性

glm 用 `target.md` は抜粋の合成物であるため、**引用行 1,050 行すべてを出典ファイルと機械照合**した
(`verified=1050 mismatches=0`)。各抜粋に出典パスと行範囲を明記し、「切れ目を連続したコードとして
読むな」を本文に書いた。R24 の「スプライスが全系統を同一偽陽性へ誘導する」を踏まえた措置。

codex 3 系統はパス渡しのため合成物を経由していない。

## 独立性

- 4 ランすべて他系統のプロンプト・途中経過・報告を参照していない。
- terra は同一モデル 2 サンプルだが `--ephemeral` の別セッション。
- 判定語・重大度・ID・読了証明の形式は 4 系統で共通。glm のみ出力上限 250 行と対象範囲を縮小
  (巨大 repo のパス渡しで凍結する既知の性質による)。

## 判定の分布

| tag | 判定 | 指摘数 |
|---|---|---|
| sol1 | 不合格 | 5 |
| terra1 | 不合格 | 6 |
| terra2 | 条件付き合格 | 5 |
| glm1 | 条件付き合格 | 3 |

裁定は `tasks/r25-audit/adjudication.md`。
