# 09 MVP Scope

統合元: `north-star-scenarios.md` + `design-homework.md` + `consolidation-plan.md` の Phase plan + `01-positioning.md` から MVP/Phase 部分の抜粋。

> 本書は **実装着手前に確定する論点** を一所に集める。Step 1 着手前に §1-§4 を確定、Step 3 着手前に §5 の (2)(3) を確定する。

---

# 1. MVP に含める / 捨てる

## 1.1 MVP に含める (Phase 1〜3)

```
- content-addressed raw object 保存
- Normalized Markdown (incremental Markdownize 含む)
- chunk
- Embedding
- FTS (FTS5 外部 content + trigram tokenizer)
- Hybrid search (paging / MMR / cursor)
- Evidence Pointer
- snapshot DAG (commit / tree)
- restore (--to 必須)
- time-travel search (--at / --all-history / --include-deleted)
- 初回スキャン preview + 明示承認
- budget guardrail (cost ceiling / kill switch)
```

## 1.2 MVP で捨てる (v2 以降に倒す)

```
- 完全な Knowledge Graph (node/edge 自動生成)
- 複雑な Agent navigation (neighbors, beam search)
- GUI
- クラウド共有・修正提案・workspace 概念
- pack/delta 圧縮
- 高度な分類器の自動移動 (auto_organize は提案表示のみ)
- 多デバイス同期 (synchronization は v2+)
```

これらは **MVP の旗印にしない** だけで、設計検討は続けてよい。Phase 4-5 ラベルを付けて archive。

---

# 2. Phase Plan

```
Phase 1: Evidence 基盤   raw / normalized / chunk / Evidence Pointer
Phase 2: 検索            FTS5 / sqlite-vec / hybrid (paging / MMR)
Phase 3: 履歴            tree / commit / restore / --at
Phase 4: 自動化          auto snapshot / Downloads watch / inbox / classification 提案
Phase 5: Agent           agent API / navigation / neighbors / node / edge
```

各 Phase は前 Phase に依存。Phase 1 が動かないうちに Phase 4-5 は深掘りしない。**今書いた Phase 5 設計はほぼ確実に書き直しになる前提**。

---

# 3. 実装 Step とコード規模上限

```
Step 1 (1-2ヶ月): kcs-core + kcs-cli で init / status / commit / log のみ
                  → CAS と snapshot DAG の正しさを早期検証
Step 2 (2-3ヶ月): kcs-pipeline + kcs-adapter (大手 LLM API デフォルト)
Step 3 (2-3ヶ月): kcs-index + kcs-search (hybrid + Evidence Pointer)
Step 4 (1ヶ月):   restore + --at + time-travel
```

**コア規模上限 (ripgrep 以下)**:

```
テスト除いて   11,000 - 16,000 LOC (Rust)
テスト含めて   20,000 - 30,000 LOC
```

これを超えるなら設計肥大化の兆候。7 クレートを一度に書こうとしないこと。Step 1 を書く前に Phase 4-5 の細部を詰めると空中楼閣化する。

---

# 4. 北極星シナリオ (Phase 3 完成時の Done 条件)

実装中の機能追加判断は「**3 シナリオのどれに resp するか**」で評価する。該当しないなら Phase 4-5 へ送る。

## M3-1: 「3ヶ月前に書いた結論の根拠 PDF を 5 秒以内に出す」

```
状況:  PDF のファイル名は覚えていない。本文の数値や用語の一部だけ覚えている。
操作:  kcs search "X の根拠 数値Y" → kcs open <evidence>
検証:  hybrid search / Evidence Pointer 表示 / 原本回帰
完了:  - p95 < 5 秒 (1万 chunk indexed)
       - Evidence Pointer に commit + raw_hash + chunk_hash + heading_path + span
       - kcs open は OS 規定アプリで原本を開く
```

## M3-2: 「リネーム済みファイルの過去版を含めて検索」

```
状況:  資料をリネームした。過去名で書いた他メモから「あの資料」を探したい。
操作:  kcs search "認証仕様" --all-history → kcs view <evidence-at-commit-X>
検証:  --all-history / raw_hash 同一性 (リネームで死なない) / 過去版閲覧
完了:  - リネーム前後で同じ raw_hash の chunk が両方ヒット
       - 結果に path_at_commit と現在 path を併記
       - 過去版 Markdown は再生成せず当該 commit の object をそのまま返す
```

## M3-3: 「削除したはずの資料から特定の数字を再発見」

```
状況:  半年前に削除した資料の中の数字をもう一度見たい。
操作:  kcs search "API リミット 1000" --include-deleted → kcs restore <ev> --to ./recovered/
検証:  CAS 永続性 / --include-deleted / restore の working tree 非破壊
完了:  - 削除済みファイルの chunk が結果に出る
       - kcs restore は --to <dir> を必須 (working tree 直接書き戻し禁止)
       - purge 済み (commit_type=purged) は除外、tombstone を返す
```

## 4.1 計測項目

```
Latency       p50 / p95 / p99       目標: M3-1 p95 < 5秒, M3-2/3 p95 < 7秒
Recall        Recall@10 / @20       目標: 各シナリオで Recall@10 >= 0.8
Evidence      必須フィールド充足率   目標: 100%
Working tree  上書き 0 件            CI で常時検出。違反はリリースブロッカー
```

## 4.2 シナリオ凍結規律

Step 1 着手後は **シナリオの追加・差し替えしない**。Phase 1-3 完了までシナリオを動かさない。例外: 物理的に実装不可能と判明した場合のみ本書で撤回 + 代替採用。

---

# 5. 設計上の宿題 (実装で必ずぶつかる 4 論点)

## 5.1 Markdown 非決定性の運用 — first-instance-wins

```
問題: 同じ (raw_hash, tool_profile_hash) から複数回生成した結果が LLM 非決定性により異なりうる。
採用: 最初に確定したインスタンスを永続化、以後は再生成しない (first-instance wins)。
実装:
  - normalization_run のキャッシュヒット判定で短絡
  - kcs reindex --force のみ上書き許可
  - 上書き時は parent_run_id でチェーンを残す
正本: 03-data-model.md §6, 04-pipeline.md §5.5
Status: decided (Step 1 着手前確定)
```

## 5.2 remarkdownize の CLI セマンティクス

```
問題: 別 LLM で再変換すると tool_profile_hash が変わり chunk が別物。
      既存 Evidence Pointer は古い chunk_hash を指し続ける (これは設計として正しい)。
未決: 「最新 Markdown へ pointer を切り替える」操作 (cherry-pick 相当)。

設計案:
  kcs evidence retarget <pointer> [--latest|--at <commit>]
  - 同一 raw_hash 配下で最新の Markdownize 結果を取得
  - heading_path / span を semantic_fingerprint で対応付け
  - 対応が見つかれば新 chunk_hash 返却。曖昧なら候補リスト
  - 元 pointer は不変。新 pointer (retargeted_from を保持) を返す

未決事項:
  - --latest のデフォルト挙動 (auto retarget か proposal か)
  - 対応なし時のエラーコード
  - AI Agent からの API 形

正本: 06-cli-spec.md / 05-runtime.md
Status: draft (Step 3 着手前確定)
```

## 5.3 Dead Evidence Pointer のセマンティクス

```
問題: 「Evidence Pointer の不変性」と「法務 purge」の緊張領域。purge 後の pointer 挙動が未定義。

設計案:
  1. raw_hash が tombstone → tombstone レスポンス
     { "status": "purged", "purged_at", "purged_reason", "commit", "raw_hash" }
  2. raw_hash が完全削除 → KCS-E-PURGE-NOT-FOUND-001

  検出 API:
  kcs evidence verify <pointer> [--strict]
    → status = alive | tombstoned | not_found

未決事項:
  - tombstone がデフォルトか、完全削除がデフォルトか (法務要件次第)
  - bulk verify API のスループット要件
  - tombstone 自体を purge する操作 (二重 purge) の有無

正本: 05-runtime.md §3.3 / 08-evidence-pointer-spec.md
Status: draft (Step 3 着手前確定)
```

## 5.4 Incremental Markdownize のプロンプト規約

```
問題: 「旧 raw + 旧 Markdown + 新 raw を Adapter に渡して差分更新」の挙動を Adapter 任せにすると揺れる。

設計 (schema は確定済み, [04-pipeline.md §3.1](04-pipeline.md)):
  入力 schema / 出力 schema は KCS が固定。
  Adapter 側プロンプト規約:
  - "unchanged" と判断した unit は出力に含めない (旧 unit を再利用)
  - 変更 unit は完全に書き直す (部分編集ではなく)
  - heading 構造の変更は KCS には影響しない (chunk side で対応)
  - Adapter が「軽微とは言えない」と判断したら fallback_to_full=true

未決事項:
  - spec_version の bump 規約
  - fallback_to_full の閾値 hint の Adapter / KCS 衝突時の優先順位
  - ストリーミング応答の有無 (大型 PDF の TTFB)

正本: 07-adapter-spec.md (新規) / 暫定 04-pipeline.md §3.1
Status: schema decided / プロンプト規約 draft (Step 1 着手前 = Step 2 で実装するため確定要)
```

## 5.5 進行状況テーブル

| # | 項目 | Status | 期日 (Step) |
| --- | --- | --- | --- |
| 1 | Markdown 非決定性 = first-instance-wins | decided | Step 1 着手前 |
| 2 | remarkdownize CLI セマンティクス | draft | Step 3 着手前 |
| 3 | Dead Evidence Pointer | draft | Step 3 着手前 |
| 4 | Incremental Markdownize プロンプト規約 | partial | Step 1 着手前 |

未確定 (draft) のままステップに到達した項目は **そのステップを着手しない**。設計を先に進める方が、実装中の手戻りより安価。

---

# 6. ドキュメント統合ゲート

実装着手前にドキュメントを **10-12 本に圧縮** する (統合済み)。

## 6.1 現在の構造 (確定)

```
docs/
  README.md
  01-positioning.md            ★core / 競合 / 差別化
  02-philosophy.md             理念
  03-data-model.md             ★契約: CAS / identity / 書き込み境界
  04-pipeline.md               ★契約: パイプライン / SQLite / batch
  05-runtime.md                ★契約: 検索 / commit / GC / purge / restore
  06-cli-spec.md               CLI / exit code / error / agent API
  07-adapter-spec.md           Adapter / incremental プロンプト規約
  08-evidence-pointer-spec.md  Evidence Pointer / Dead Pointer / retarget
  09-mvp-scope.md              本書
  10-operations.md             横断規約 (semver / 観測 / リネーム表)
  11-requirements.md           既存要件ドラフト
  research/                 設計検討メモ (正本ではない)
```

## 6.2 凍結ゲート

```
Step 1 着手後はドキュメントを凍結する。
凍結を破る条件:
  1. Step 1-4 で実装が物理的に不可能と判明した設計
  2. 外部 Agent との互換性を破壊する変更
  3. データ破壊リスクのある誤り
それ以外の「綺麗にする」「より良い表現にする」は Step 4 完了後に回す。
```

設計判断の経緯は git history で追える。本プロジェクトでは ADR フォルダを採用しない (Phase 1 着手前の小規模プロジェクトでは spec 一本化の方が運用コストが低い)。
