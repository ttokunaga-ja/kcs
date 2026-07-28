# R24 実装監査の裁定 (2026-07-25)

対象: H1 (embedding Batch レーン) + H2 (`repair` の確認プロンプト)。

**R24 は H1 のみ有効。H2 は監査材料の欠陥により無効となり、R24b として取り直した。**

---

## 1. ラウンド構成と受理ゲート

### R24 (H1 + H2、target.md 1,732 行)

| tag | model | EXIT | 出力 | 読了行数 | 最終2行 | 判定 | 受理 |
|---|---|---|---|---|---|---|---|
| sol | gpt-5.6-sol (ultra) | 0 | 11,123 B | 1732 ✓ | ✓ | 不合格 | ✓ |
| terra1 | gpt-5.6-terra (ultra) | 0 | 8,921 B | 1732 ✓ | ✓ | 不合格 | ✓ |
| terra2 | gpt-5.6-terra (ultra) | 0 | 8,149 B | 1732 ✓ | ✓ | 不合格 | ✓ |
| son1 | claude-sonnet-5 (high) | 0 | 14,906 B | 1732 ✓ | ✓ | 不合格 | ✓ |
| son2 | claude-sonnet-5 (high) | 0 | 15,213 B | 1732 ✓ | ✓ | 不合格 | ✓ |
| glm | zai-coding-plan/glm-5.2 (low) | 0 | 10,270 B | 1732 ✓ | **✗ (1 行ずれ)** | 条件付き合格 | △ |
| kimi | kimi-openai/kimi-k3 (max) | — | 0 B | — | — | — | **✗ 凍結** |

- **glm**: 最終 2 行を「(行1731) ``` / (行1732) 空行」と報告。実際は「`}` / ```」。
  1 行ずれ = 品質 NG として記録するが、read ログ上は全 4 チャンクを読了しており、
  指摘内容は他系統と整合したため**内容は採用**した。
- **kimi**: 起動 1 分後に `opencode.db-wal` が 601,552 B で停止し、25 分間不成長。
  §6 の凍結判定に該当。単独降格はせず打ち切り (6 系統で収束済みのため限界効用が低い)。

### R24b (H2 のみ、target.md 677 行・スプライス 0)

| tag | model | EXIT | 出力 | 読了行数 | 最終2行 | 判定 | 受理 |
|---|---|---|---|---|---|---|---|
| sol | gpt-5.6-sol (ultra) | 0 | 8,991 B | 677 ✓ | ✓ | 不合格 | ✓ |
| son | claude-sonnet-5 (high) | 0 | 11,946 B | 677 ✓ | ✓ | — | ✓ |
| terra | gpt-5.6-terra (ultra) | 0 | 6,665 B | 677 ✓ | ✓ | 不合格 | ✓ |

---

## 2. 監査材料の欠陥 (**このラウンドの最大の学び**)

R24 の `target.md` に**転記スプライスが 2 箇所**あった。機械検出は
「target.md の連続する 2 行が、出典ファイルでも連続しているか」の全行照合による。

| 位置 | 内容 | 影響 |
|---|---|---|
| L1160-1161 | `estimate_embedding_cost` の signature が重複し、間に `// (本体)` プレースホルダ | **軽微** — 直後に実体があり意味は読める |
| **L1293-1300** | **`RepairOperation::RebuildDb` の arm 冒頭に `prune_orphans` 本体を直結し、間の約 30 行 (レーン解決・lock・verify pass・`mode == VerifyObjectsPruneOrphans` ガード) が落ちた** | **致命的** — §7 (H2) の被覆が無効 |

結果として **5/6 系統が「`--yes` の判定が誤った enum variant 配下にある」を指摘**したが、
実ソース ([main.rs:1330-1333](../crates/kio-cli/src/main.rs#L1330)) では `skip_prompt` は
正しく `VerifyObjects` 分岐の内側にある。**全数が偽陽性**であり、
モデル側の誤読ではなく**こちらが壊れた材料を渡した**ことによる。

R24b (正しい全文・スプライス 0) では**この指摘は 1 件も出ず**、代わりに実在の欠陥が出た。
材料の健全性が結論を支配することの実証例である。

> **恒久対策**: 監査材料を組んだら、投入前に必ず「連続 2 行の出典連続性」を全行照合する。
> 本ラウンドで使ったスクリプトは §6 に残す。

---

## 3. H1 の裁定 (名寄せ後)

| # | 争点 | 一致 | 裁定 | 状態 |
|---|---|---|---|---|
| **F1** | 宣言済み単価がレーンを無視し Batch が sync 単価で記帳される | **3/6** (sol-1, terra1-001, terra2-003) | **fatal 認容** | **修正済み** |
| **F2** | 予約見積りが実送信の contextualized text を含まない | **3/6** (sol-2, terra1-002, terra2-004) | **fatal 認容** | **修正済み** |
| **F3** | collect が全単射を検査せず、部分結果でも Succeeded 確定 | **4/6** (sol-4, terra1-003, terra2-002, glm-4) | **fatal 認容** | **修正済み** |
| **F4** | 失敗 job が無制限に再投入される (KNOWN GAP) | **6/6 全会一致** | **fatal 認容** | **修正済み** |
| F5 | batch client 不可時に OCR と embedding が別レーンになる | 2/6 (terra1-006, terra2-005) | **認容** (ユーザー裁定「両方バッチか両方即時」に直接違反) | 未 |
| F6 | 512 固定分割が inline 20MB 上限を保証しない | 1/6 (terra1-007) | 認容 (major) | 未 |
| F7 | 飛行中行の profile と現在 profile の一致を未確認 | 2/6 (sol-5, terra1-004) | 認容 (major) | 未 |
| F8 | 未知の provider state を永久に in-flight 扱い | 1/6 (terra2-007) | 認容 (major) | 未 |
| F9 | `list_jobs` の 5,000 件打ち切りで回復走査が取りこぼす | 1/6 (sol-8) | 要調査 | 未 |
| F10 | `active_embedding_send_lane` の doc コメントが陳腐化 | 3/6 (glm-5, son1-5, son2-6) | 認容 (minor) | 未 |
| — | `estimate_embedding_cost` 二重定義でコンパイル不能 | 3/6 (glm-1, son1-4, terra1-011) | **却下** — 材料の転記欠陥 (§2)。実ソースは定義 1 個 | — |
| — | `repair --yes` が誤った variant 配下 | 5/6 | **却下** — 材料の転記欠陥 (§2)。R24b で再検査 | — |

### 修正の要点

**F1** — `embedding_usd_per_token` が `tools.toml` の宣言単価を**レーン判定より前に return** していた。
`[pricing]` のキーは `pages`/`tokens_in`/`tokens_out` の閉じた enum でレーンの次元を持たないため、
宣言値は**標準 (sync) 単価**と解釈し Batch は係数 0.5 で導出する形に変更した。
**この欠陥は本セッションで `~/.config/kio/tools.toml` を作成した時点で発火していた** —
Phase 2 をそのまま実行していれば、Batch ジョブが実額の 2 倍で記帳され、
budget cap が守る金額が倍速で消費されていた。

**F2** — 見積りは `representative.text`、送信は `contextualized_embedding_input(context, text)`。
`usage: None` で確定記帳は見積りのままなので、context 分が**恒久的に過少記帳**されていた。
inputs を予約より前に構築し、実際に送る文字列から見積もる形に変更 (batch / sync 両経路)。

**F3** — 07 §5.3 (1) の全単射契約が collect 側に無かった。512 件投入に 511 件が返ると、
残り 1 件はベクタ未書き込みのまま行が Completed になり `intent_token` も NULL 化され、
**恒久的な索引の穴**になっていた。設計 A では task キー自体がメンバ digest なので、
**回収できた結果から digest を再計算して行の `input_hash` と突き合わせる**ことで
スキーマ変更なしに全単射を検査できる。不一致なら Succeeded ではなく Terminal + contract violation。

**F4** — `phase1_intent` の `ON CONFLICT` は `batch_job_id` を NULL に戻す一方
**`attempts` は SET 対象外＝保存される**。この既存カウンタを上限 3 で見るだけで、
スキーマ変更なしに再投入を有界化できた。

---

## 4. H2 の裁定 (R24b、正しい材料)

| # | 争点 | 一致 | 裁定 | 状態 |
|---|---|---|---|---|
| **H2-1** | blocked preview 後も確認なしで破壊的本実行へ進む | 1/3 (sol-2) | **fatal 認容** | **修正済み** |
| **H2-2** | `--yes` 単独を clap の `requires` が拒否できない | **3/3** (sol-5, son-5, terra-004) | **認容** | **修正済み** |
| **H2-4** | **preview が本実行を拘束しない** (確認した集合と消す集合が別) | **3/3** (sol-1, son-1, terra-001) — うち **2 件が fatal** | **fatal 認容 — 本ラウンド H2 の最重要指摘** | **未** |
| **H2-3** | 削除対象を**列挙せず件数だけ**で確認している | **3/3** (sol-3, son-2, terra-003) | **認容 — 06 §1 の「先に列挙して見せてから問う」に違反** | 未 |
| H2-5 | blocked 時の JSON に `error_code` が無い | **3/3** (sol-6, son-3, terra-005) | 認容 (major) | 未 |
| H2-6 | `registry-prune` が確認後に未表示の行を追加削除しうる | 2/3 (son-1, terra-002 [fatal]) | 認容 (H2-4 と同根) | 未 |
| H2-7 | reachability 読取り失敗を無視し参照中を orphan 扱い | 1/3 (sol-4) | 要調査 (fatal 候補) | 未 |
| H2-8 | 契約テストが主要な確認経路を網羅していない | 3/3 | 認容 | 未 |

**H2-1** — `if preview.status != "blocked" { confirm() }` の後、`prune_orphans(false)` を
**無条件に呼んでいた**。preview と本実行の間に blocker (purge journal・実行中タスク) が
解消すると、**確認を一度も経ずに削除**が走る。blocked なら本実行に進まず preview を返す形に変更。

**H2-2** — clap の `requires` は `ArgAction::SetTrue` 同士では効かない (既定値 `false` でも
「存在する」と見なされる)。`--yes` 単独が受理され黙って無効化されていた。明示検証に置換。

---

## 5. 未修正分の扱い

F5〜F10 / H2-3〜H2-8 は**認容したが本セッションでは未修正**。

### 最優先 — `repair --prune-orphans` を使う前に直すべき (H2-3 / H2-4 / H2-6 は同根)

**preview が本実行を拘束していない。** 現状は `prune_orphans(repo, true)` で数え、
確認を取り、`prune_orphans(repo, false)` で**もう一度スキャンして消す**。
2 回のスキャンの間に対象が増えれば、**ユーザーが承諾していない対象まで削除される**。
`registry-prune` も同型 (terra-002 が fatal 判定)。

正しい形は「preview が返した**対象リストそのもの**を本実行へ渡し、その集合だけを消す」。
これで H2-4 (拘束) と H2-3 (列挙) が同時に解ける — 列挙するにはリストが要るからである。
`PruneOrphansReport` / `RegistryPruneReport` が件数しか持たないので、
対象リストを持たせる改修が前提になる。

> **Phase 2 はブロックしない**: 索引化の経路 (`index` / `batch resume`) は
> `repair --prune-orphans` を呼ばない。ただし **`repair` を破壊的に使うのは
> この修正が入るまで避ける**こと。

### 次点 — Phase 2 の前に片付ける価値がある

- **F5 (レーン分裂)**: ユーザー裁定「片方がバッチなどはなく、両方バッチか両方即時」への直接違反。
  Gemini の batch client だけが解決できない構成で OCR=Batch / embedding=Sync になる。
  現実には両方とも `tools.toml` の `env:` 参照で解決するため**同時に落ちる**公算が高く、
  Phase 2 の実害は小さい。ただし裁定の明文違反なので直す。
- **F6 (512 固定分割)**: inline 20MB 上限をメンバ数だけで守っている。
  dogfood の chunk 長 (max 6,000 字) では実測 3MB 程度で余裕があるが、上限は**サイズで**掛けるべき。

残りは実運用の踏み方が限定的なため backlog へ送る。

---

## 6. 修正の検証

- **全テスト 1,312 passed / 0 failed** (着手時 1,309 → 新規 3: 全単射・再投入上限・宣言単価のレーン分割)
- **F1 は実機で 2:1 を確認**。同一の宣言 `tokens_in = 0.0000002` に対し
  `index --approve --online` = `$0.00000185` (batch) / `--realtime` = `$0.00000370` (sync)。
  修正前はどちらも `$0.00000370` になっていた。
- **QB11 が構造回帰を検出した**: `--yes` の検証を `run_repair` の冒頭に直接置いたところ、
  `lock_store()` が「関数の先頭 1,500 文字」の窓から押し出されて落ちた。
  検証を `reject_inert_repair_yes` へ切り出して解消。**契約テストが fix の形を正した例**。

### 自分の fix が開けかけた穴 (記録)

F4 の再投入上限を最初 **`attempts`** で実装したが、**`attempts` を戻すコマンドが存在しない**。
上限に達したメンバ集合は恒久的に再投入不能な行き止まりになる。
`kio batch reset-violations` (CL62-CL68) という既存の脱出路を持つ
**`contract_violation_count`** に付け替えた。

> 「fix が開ける穴」の定番脈 ([[project_kio_audit_process]]) が**自分の fix にも出た**。
> 上限・ゲートを足すときは「**この上限を戻す経路は存在するか**」を必ず対にして確認する。

---

## 7. 監査材料の連続性チェック (恒久化)

```python
# target.md の連続 2 行が出典でも連続しているかを全行照合する。
# 出力が 0 でなければスプライスがある。
idx = {}                       # 行文字列 -> [(file, lineno)]
for path, lines in sources.items():
    for i, line in enumerate(lines):
        idx.setdefault(line, []).append((path, i))
prev = None
for n, line in enumerate(target):
    if not line.strip() or len(line.strip()) < 12:   # 短行は偶然一致するので除外
        prev = None; continue
    cands = idx.get(line)
    if not cands:
        prev = None; continue
    if prev and not any((p, i + 1) in set(cands) for (p, i) in prev):
        print(f"splice at line {n+1}: {line[:70]}")
    prev = cands
```
