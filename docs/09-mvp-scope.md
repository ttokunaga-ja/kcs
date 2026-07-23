# 09 MVP Scope

統合元: 旧 `north-star-scenarios.md` + 旧 `design-homework.md` + 旧 `consolidation-plan.md` の Phase plan + `01-positioning.md` から MVP/Phase 部分の抜粋 (research 検討メモは 2026-07-18 に撤去 — git 履歴で参照可)。

> 本書は **実装着手前に確定する論点** を一所に集める。Step 1 着手前に §1-§4 を確定する。§5 の各宿題の確定期日と現在の status は **§5.5 の表が正本** (本行に期日を再掲しない — 転記の陳腐化が gate を誤発動させるため)。

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
- kcs index 完了時の auto snapshot (定期 auto snapshot / watch は Phase 4。[05-runtime.md §8](05-runtime.md))
- restore (--to 必須)
- time-travel search (--at / --all-history / --include-deleted)
- ベースライン index (deterministic 抽出 + FTS。API キーなしで init→index→search→open が成立 — [01-positioning.md §3](01-positioning.md))
- 初回スキャン preview + 明示承認
- budget guardrail (cost ceiling / kill switch)
- purge 最小形 (tombstone + commit_type=purged + 検索除外 + ログスクラブ。M3-3 の完了条件)
- kcs evidence verify <pointer> (単発。--batch は含まない)
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
- Adapter の OS サンドボックス強制・第三者 Adapter の配布/署名 (07-adapter-spec.md §7.1)
- GC の実装一式 (kcs gc / tiered retention / CoW 並行 GC / power-loss sweep)
- purge の完全な履歴書き換え (tree/commit 再結線・filename 秘匿ケース。05-runtime.md §3.5)
- export / import (.kcsz bundle)
- kcs evidence verify --batch / kcs evidence retarget の実装
- agent API の外部公開・発見導線 (外部 Agent は MVP では kcs search --json 等の CLI 契約を使う)
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

各 Phase は前 Phase に依存。Phase 1 が動かないうちに Phase 4-5 は深掘りしない。**今書いた Phase 5 設計はほぼ確実に書き直しになる前提**。MVP における Agent 導線は CLI + `--json` のみ ([06-cli-spec.md §9](06-cli-spec.md))。MCP server 等の Agent 統合導線は Phase 5 論点として登録済み (設計は Phase 5 着手時)。

---

# 3. 実装 Step とコード規模上限

```
Step 1 (1-2ヶ月): kcs-core + kcs-cli で init / status / snapshot / log / diff / inspect / tag
                  → CAS と snapshot DAG の正しさを早期検証
Step 2 (2-3ヶ月): kcs-pipeline + kcs-adapter
                  → 同梱 deterministic Adapter でベースライン抽出 (normalized まで。**検索の成立は
                    Step 3 の chunk/FTS/search 実装と合わせて** — §3 の割当が正)
                  → 推奨構成は大手 LLM API による AI 強化 (opt-in)
                  → 注: tree schema v2/v3 (2026-07-18 — 03 §8) により Step 1-2 実装の tree hashing は
                    v2/v3 対応 (manifest_hash / chunking_config_hash / chunk_set_hash) の rework が必要
                    (あわせて manifest object 保存 (03 §2.1)・chunk_publications / index_metadata 表・
                    config association の introduction_commit 列 (04 §4.1) も同期間の実装対象)
Step 3 (2-3ヶ月): kcs-index + kcs-search (hybrid + Evidence Pointer)
Step 4 (1.5-2ヶ月): restore + --at + time-travel
                    + purge 最小形 (tombstone) + evidence verify (単発)
```

**コア規模上限 (ripgrep 以下)**:

```
テスト除いて   11,000 - 16,000 LOC (Rust)
テスト含めて   20,000 - 30,000 LOC
```

```
Step 別の目安 (テスト除く):

  Step 1   2,500 -  4,000 LOC   CAS / DAG / init / status / snapshot / log / diff
  Step 2   3,500 -  5,000 LOC   pipeline / adapter / budget / resume / retry
  Step 3   3,500 -  5,000 LOC   FTS / vector / hybrid / Evidence Pointer
  Step 4   1,500 -  2,500 LOC   restore / time-travel / purge 最小形 / verify
  合計    11,000 - 16,000 LOC   (総期間 7-10 ヶ月。Step 別最大の単純合計 16,500 は
                                 総額上限 16,000 に切られる — 全 Step 同時に上限へ達する配分は取らない)
```

これを超えるなら設計肥大化の兆候。§3.1 で Phase 4+ に割り当てた機能を Step 1-4 に前倒しした場合も同じ兆候として扱う。テスト除き 16,000 LOC を超えたら削減先を検討する: multi-scope search の設定項目縮小 ([05-runtime.md §1.8](05-runtime.md))、`kcs repair --verify-objects` の自動定期実行の Phase 4+ 送り、export/import 予約行の据え置き等。総額上限 11,000-16,000 LOC 自体は動かさない。7 クレートを一度に書こうとしないこと。Step 1 を書く前に Phase 4-5 の細部を詰めると空中楼閣化する。

## 3.1 機能 × Step 割当表

05/06/08 の契約機能がどの Step / Phase で実装されるかの **正本は本表**。各契約 spec の記述は「契約の内容」を定め、本表は「実装時期」を定める。本表にない機能を実装したくなったら、まず本表への追加 (と北極星シナリオとの対応確認) を行う。

| 機能 | 正本 | 実装 |
| --- | --- | --- |
| CAS raw object store + snapshot DAG (tree / commit) | [03-data-model.md](03-data-model.md) | Step 1 |
| `init` / `status` / `snapshot` (`commit` alias) / `log` / `diff` / `inspect` / `tag` | [06-cli-spec.md §1](06-cli-spec.md) | Step 1 |
| `gc_policy` × `commit_type` 対応の schema 遵守 (GC 実行はしない) | [05-runtime.md §2.2](05-runtime.md) | Step 1 |
| JSON Schema validation (Step 1 は scope / manifest / config。以後各 Step で対象 schema を追加) | [06-cli-spec.md §11](06-cli-spec.md) | Step 1〜 |
| 観測ログ `events.jsonl` / `errors.jsonl` | [06-cli-spec.md §13](06-cli-spec.md) | Step 1 |
| 初回スキャン preview + 明示承認 / `.kcsignore` | [06-cli-spec.md §2](06-cli-spec.md) / [10-operations.md §1](10-operations.md) | Step 2 |
| preview のコスト概算・budget 超過警告 | [06-cli-spec.md §2](06-cli-spec.md) / [10-operations.md §1](10-operations.md) | Step 2 |
| Prepare / Markdownize (full + incremental) / Adapter 実行 | [07-adapter-spec.md](07-adapter-spec.md) / [04-pipeline.md §3](04-pipeline.md) | Step 2 |
| 同梱 deterministic Adapter によるベースライン抽出 (normalized まで — 検索成立は Step 3 の index/search と合わせて) | [07-adapter-spec.md §2.1](07-adapter-spec.md) | Step 2 |
| Mistral OCR 系標準 Markdownize Adapter + embedded image 抽出・image object 保存 | [07-adapter-spec.md §5.2](07-adapter-spec.md) / [03-data-model.md §2](03-data-model.md) | Step 2 |
| batch / retry / resume / budget guardrail | [04-pipeline.md §5](04-pipeline.md) | Step 2 |
| `kcs index` 完了時の auto snapshot (no-op 条件・HEAD 更新 — §1.1 の MVP 項目) | [05-runtime.md §8](05-runtime.md) | Step 2 |
| `kcs adapter revoke` (network 承認の取り消し — opt-in 系と同時) | [07-adapter-spec.md §3](07-adapter-spec.md) / [06-cli-spec.md §1](06-cli-spec.md) | Step 2 |
| `kcs repair --registry-prune` (恒久到達不能 registry 行の確認付き退役) | [10-operations.md §3](10-operations.md) | Step 3 |
| 構造化 task/artifact descriptor (Adapter 境界の内部 API) | [06-cli-spec.md §9](06-cli-spec.md) | Step 2 |
| secrets Tier A/B 除外 + quarantine + `--yes` 制約 + `approval_method` 記録 | [10-operations.md §1.1](10-operations.md) / [06-cli-spec.md §2](06-cli-spec.md) | Step 2 |
| chunk / Embedding / FTS5 / sqlite-vec | [04-pipeline.md §4](04-pipeline.md) | Step 3 |
| hybrid search (RRF / MMR / paging / cursor) | [05-runtime.md §1](05-runtime.md) | Step 3 |
| Evidence Pointer 発行・解決 / `kcs open` / `kcs view` | [08-evidence-pointer-spec.md §2-3](08-evidence-pointer-spec.md) | Step 3 |
| `kcs search --json` (外部 Agent 向け最小契約) + `index_status` | [05-runtime.md §1.7](05-runtime.md) | Step 3 |
| `kcs reindex` (gen+1 の再 Markdownize / 再 index) | [07-adapter-spec.md §9](07-adapter-spec.md) / [09-mvp-scope.md §5.1](09-mvp-scope.md) | Step 3 |
| 観測ログ `metrics.jsonl` / `access.jsonl` (M3 の latency 計測に必要) | [06-cli-spec.md §13](06-cli-spec.md) / [05-runtime.md §7](05-runtime.md) | Step 3 |
| `restore --to` / `--at` / `--all-history` / `--include-deleted` | [05-runtime.md §4](05-runtime.md) | Step 4 |
| purge 最小形 (tombstone + `commit_type=purged` + 検索除外 + `--erase-tombstone` + ログスクラブ [10-operations.md §7](10-operations.md)) | [05-runtime.md §3](05-runtime.md) / [08-evidence-pointer-spec.md §4.1](08-evidence-pointer-spec.md) | Step 4 |
| `kcs repair --rebuild-db` (SQLite index 再構築 — 破損時の復旧経路) | [10-operations.md §7.5.3](10-operations.md) | Step 3 |
| `kcs repair --verify-objects` (CAS object 整合性検証) / `--prune-orphans` (orphan prepared/image 削除 — 法務 purge の完結手段) | [10-operations.md §7.5](10-operations.md) | Step 4 |
| `kcs evidence verify <pointer>` (単発) | [08-evidence-pointer-spec.md §4.3](08-evidence-pointer-spec.md) | Step 4 |
| purge の完全な履歴書き換え (tree/commit 再結線・filename 秘匿ケース) | [05-runtime.md §3.5](05-runtime.md) / [08-evidence-pointer-spec.md §4.2](08-evidence-pointer-spec.md) | v2+ / Phase 4+ |
| `kcs gc` (on-demand / shallow / prune-unreachable) | [05-runtime.md §2.2-2.3](05-runtime.md) | Phase 4+ |
| tiered retention GC (auto snapshot と同時に導入) | [05-runtime.md §2.4](05-runtime.md) | Phase 4+ |
| CoW 並行 GC / power-loss sweep | [05-runtime.md §2.5](05-runtime.md) | Phase 4+ |
| 定期 auto snapshot / on_idle GC (OS スケジューラ委譲、常駐なし) | [05-runtime.md §8](05-runtime.md) / [05-runtime.md §2.3](05-runtime.md) | Phase 4+ |
| export / import (`.kcsz`) | [06-cli-spec.md §10](06-cli-spec.md) | Phase 4+ |
| `kcs evidence verify --batch` | [08-evidence-pointer-spec.md §4.3](08-evidence-pointer-spec.md) | Phase 4+ |
| `kcs evidence retarget` | [08-evidence-pointer-spec.md §5](08-evidence-pointer-spec.md) | Phase 4+ |
| `kcs move` (scope 内移動の明示追跡。現状は lock 対象として予約のみ、full spec は未定) | [05-runtime.md §6](05-runtime.md) | Phase 4+ (予約) |
| agent API の外部公開・発見導線 / navigation | [06-cli-spec.md §9](06-cli-spec.md) | Phase 5 |
| GUI 用語翻訳マッピング | [06-cli-spec.md §14](06-cli-spec.md) | Phase 4+ |

注: 定期 auto snapshot / on_idle GC は 09 §2 の Phase plan (Phase 4: 自動化) に従い Phase 4+ とした。05 §8 見出しの「Phase 4 範囲」と整合する。これを Phase 3 に前倒しする場合は、当該行と tiered retention 行を Step 4 に移し、Step 4 の期間・LOC 見積り (1.5-2 ヶ月 / 1,500-2,500 LOC) を再拡大する。

## 3.2 Step 1 着手ゲート

Step N の着手条件は「§5.5 で期日が『Step N 着手前』の行がすべて decided」という機械的チェックとする。**期日 cell に未完注記 (「〜を除き充足」等の but 書き) が残る行は decided 扱いしない** — #5 は M3-1 の増補完了時に件数と query set digest (凍結済み `eval/golden-queries.jsonl` の raw UTF-8 bytes の sha256 — `sha256:<lowercase-hex>` 表記) を当該行へ追記して注記を除去する (= 再凍結の機械記録。それまで Step 3 の着手条件を満たさない)。主観判定 (「だいたい固まった」) は用いない。

Step 1 開始日: **2026-07-16**。本日 (2026-07-02) 時点の Step 1 ブロッカーは #1 / #4 で、いずれも decided 済み (§5.5) のため、上記日付までに残る作業は本改訂のドキュメント反映のみ。開始日を過ぎても着手しない場合、その理由を本節に追記する (理由なき延期の可視化)。

---

# 4. 北極星シナリオ (Phase 3 完成時の Done 条件)

実装中の機能追加判断は「**3 シナリオのどれに resp するか**」で評価する。該当しないなら Phase 4-5 へ送る。

## M3-1: 「3ヶ月前に書いた結論の根拠 PDF を 5 秒以内に出す」

```
状況:  PDF のファイル名は覚えていない。本文の数値や用語の一部だけ覚えている。
操作:  kcs search "X の根拠 数値Y" → kcs open <evidence>
検証:  hybrid search / Evidence Pointer 表示 / 原本回帰
完了:  - p95 < 5 秒 (20 scopes / 合計 10 万 chunk indexed、横断検索デフォルトで計測)
       - Evidence Pointer に commit + raw_hash + chunk_hash + heading_path + span
       - kcs open は OS 規定アプリで原本を開く (working tree 優先、無ければ CAS から
         read-only 一時展開。06-cli-spec.md §1.1)
       - ベースライン優位: 既存手段で失敗しやすいクエリ集合 Q_hard (スキャン PDF の
         画像内テキスト / 語彙一致しない言い換え / 図表・画像の内容参照、20 問以上) で、
         Spotlight (mdfind) と ripgrep-all をベースラインに Recall@10 を比較し、
         KCS >= 0.8 かつ各ベースラインを 0.3 以上上回る
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
       - purge 済み (canonical final event = purged — 08 §3.1 手順 5。commit_type=purged はその監査痕跡) は検索結果から除外される (purged chunk 行は物理削除済み — search 経由では到達しない)。tombstone 応答は既存 Evidence Pointer (過去回答の保存分) を restore / verify / open に与えた場合の挙動 (08 §4)
```

## 4.1 計測項目

```
Latency       p50 / p95 / p99       目標: M3-1 p95 < 5秒, M3-2/3 p95 < 7秒
                                    (前提: 20 scopes / 合計 10 万 chunk。05-runtime.md §1.8)
Recall        Recall@10 / @20       目標: 各シナリオで Recall@10 >= 0.8
Baseline      Q_hard での対 Spotlight/rga 優位   目標: M3-1 完了条件のとおり (KCS >= 0.8, 差 >= 0.3)
Evidence      必須フィールド充足率   目標: 100%
Working tree  上書き 0 件            CI で常時検出。違反はリリースブロッカー

初回体験 (基準データセット D1: PDF 1,000 本 / 5GB 相当)
TTFV (baseline)   kcs init → ベースライン index 完了 → 初回 kcs search 成功
                                       目標: 30 分以内 / LLM コスト $0
TTFV (enriched)   online 承認 → 最初の 100 ファイルが AI 強化済みで検索可能
                                       目標: 承認から 15 分以内
Cost 予実比       preview 概算 vs 実績  目標: 乖離 ±30% 以内 (D1 全量 AI 強化時)
試算根拠          Markdownize 単価      Mistral OCR 4 Batch $2 / 1,000 pages 前提
                                       (研究メモ: 旧 research/markdown.md — git 履歴。単価改定時は本表を更新)
```

## 4.2 シナリオ凍結規律

Step 1 着手後は **シナリオの追加・差し替えしない**。Phase 1-3 完了までシナリオを動かさない。例外: 物理的に実装不可能と判明した場合のみ本書で撤回 + 代替採用。**一回限りの例外**: M3-1 の Q_hard を §4.1 の「20 問以上」へ増補する**追加のみ**、**Step 3 着手前**に限り認める (既存問の差し替えは不可 — 増補後に再凍結し、以後この例外は消滅する)。この増補に伴う #5 行の件数・digest 追記は本例外の完遂手続きであり、§6.2 のドキュメント凍結の対象外とする。

## 4.3 Recall 評価規約 (ゴールデンクエリ)

§4.1 の Recall@10 >= 0.8 は次の規約で計測する。

評価コーパス (2 種):

```text
synthetic  リポジトリ同梱の合成コーパス (公開可能な文書 + 生成文書、200-500 ファイル規模)。
           複数 scope (.kcs) 構成で fixture 化し、fixture script が
           「編集 → commit → リネーム → commit → 削除 → commit」の履歴シナリオを
           決定論的に再現する。CI / Done 判定の正本
dogfood    開発者自身の実フォルダ (非公開)。数値は公開せず、3 シナリオの主観成功確認に使う
```

ゴールデンクエリ:

- シナリオ M3-1 / M3-2 / M3-3 ごとに **15 件以上**、`eval/golden-queries.jsonl` としてリポジトリに保持する
- 各行: `{ "scenario": "M3-2", "query": "...", "flags": ["--all-history"], "expected": [{ "scope": "research", "file": "auth-spec.md", "path_at_commit": "auth-spec.md", "section": "api-token" }] }`
- expected は `{ scope, file, section }` の分離形式で書く。**M3-2 (rename / 編集を含む履歴シナリオ) の expected 要素には `path_at_commit` (または対象 commit) を併記し、同一 file の版を一意化する** (rename 前後は別の expected 要素) (section = chunk の `section_id` (slug — [04-pipeline.md §4.1](04-pipeline.md))。heading 原文ではない) (path 区切りを含む文字列にしない。スコープ境界は [03-data-model.md §3](03-data-model.md) の「直下のみ」規則)。raw_hash は取り込み後に確定するため、評価ハーネスが取り込み時に `{ scope, file }` → raw_hash / chunk へ解決する
- M3-2 は `--all-history`、M3-3 は `--include-deleted` で実行する

判定:

```text
Recall@10 = |expected ∩ 上位10件の distinct (raw_hash, section)| / |expected| のクエリ平均
            (--all-history シナリオ (M3-2) は distinct 射影と expected 解決を
             (raw_hash, section, path_at_commit) で行う — リネーム前後の両ヒットを別要素として
             数える。raw_hash はリネームで不変のため、この拡張なしには M3-2 完了条件
             「両方ヒット」が計測不能)
Done 条件 = synthetic で各シナリオ Recall@10 >= 0.8
          + dogfood で 3 シナリオの手動成功確認
```

クエリの追加・差し替えは §4.2 の凍結規律に従う — 認められるのは M3-1 の一回限り増補 (Step 3 着手前) のみで、他のクエリ集合は Step 1 着手後は動かさない (悪化を隠すための削除は禁止)。

---

# 5. 設計上の宿題 (実装で必ずぶつかる論点)

## 5.1 Markdown 非決定性の運用 — first-instance-wins

```
問題: 同じ (raw_hash, tool_profile_hash) から複数回生成した結果が LLM 非決定性により異なりうる。
採用: 最初に確定したインスタンスを永続化、以後は再生成しない (first-instance wins)。
実装:
  - normalization_run のキャッシュヒット判定で短絡
  - 新 generation (gen+1) の instance 作成は kcs reindex --force、または prepared_hash 変化起因の自動 gen+1 ([03-data-model.md §2.1](03-data-model.md) の例外) のみ許可 (上書き・削除はしない)
  - 新 instance 作成時 (raw 跨ぎ incremental の g0 を含む) は manifest の parent_gen (同一 raw 内) / parent_instance = {raw_hash, tool_profile_hash, gen} (raw 跨ぎ incremental のみ必須 — full では null) でチェーンを残す (parent_run_id は task cache の揮発情報 — 永続 provenance ではない。[03-data-model.md §8](03-data-model.md))
  - 過去 commit / 既存 Evidence Pointer は tree entry の gen により旧 instance を参照し続ける
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
  - heading_path の一致 (exact → fuzzy + span 重なり率 — fuzzy は text alignment 成立領域のみ、08 §5) で対応付け
  - 意味ベースの対応付け (semantic_fingerprint) は MVP から除外 (Phase 4+ の optional 拡張)
  - 対応が見つかれば新 chunk_hash 返却。曖昧なら候補リスト
  - 元 pointer は不変。新 pointer と retargeted_from (response 直下 — pointer 外) を返す

決定済み:
  - CLI 形: kcs evidence retarget <pointer> [--latest|--at <commit>] (正本 08 §5)
  - 対応なし (曖昧) 時のエラーコード: KCS-E-EVIDENCE-RETARGET-AMBIG-001 (正本 08 §5)
  - AI Agent からの API 形: 06-cli-spec.md §4 の --json 契約に従う (正本 08 §5)
  - 元 pointer は不変。新 pointer と retargeted_from (response 直下 — pointer 外) を返す (正本 08 §5)

残未決:
  - --latest のデフォルト挙動 (auto retarget か proposal か)
  - (Phase 4+) chunk レベル semantic_fingerprint の実体
    (embedding 再利用か専用 fingerprint か、embedding profile 非互換時の縮退)

正本: 08-evidence-pointer-spec.md §5
Status: draft (retarget 実装は Phase 4+ のため、期日は Phase 4 着手前)
```

## 5.3 Dead Evidence Pointer のセマンティクス

```
問題: 「Evidence Pointer の不変性」と「法務 purge」の緊張領域。purge 後の pointer 挙動が未定義。

設計案:
  1. raw_hash の canonical final event = `purged` (全 marker 正本化 — 08 §3.1 手順 5) → tombstone レスポンス
     { "status": "tombstoned", "purged_at", "purged_reason", "purged_in_commit", "raw_hash" } (正本 08 §4.1)
  2. raw_hash が完全削除 → KCS-E-PURGE-NOT-FOUND-001

  検出 API:
  kcs evidence verify <pointer> [--strict]
    → status = 6 値 union (正本 08 §4.3 — alive | tombstoned | not_found |
               scope_unreachable | unverifiable | registry_duplicate)

決定済み:
  - デフォルトは tombstone。完全削除 (`--erase-tombstone` — public tombstone なしの NOT-FOUND 化。
    tree/commit 再結線・filename 秘匿の履歴書き換えは含まない — §3.1 のとおり v2+/Phase 4+) は
    法的要件上必要な場合のみ (正本 08 §4.2)
  - tombstone レスポンス schema (正本 08 §4.1)
  - 完全削除時は KCS-E-PURGE-NOT-FOUND-001 (正本 08 §4.2)
  - 検出 API: kcs evidence verify <pointer> [--strict] → 6 値 union (正本 08 §4.3)

残未決:
  - bulk verify (--batch) のスループット要件 (実装自体が Phase 4+)
  (二重 purge は 2026-07-18 に確定済み — 再 purge は lifecycle events[] へ `purged` を追加 append する。
   tombstone 判定は「active = 末尾 event が purged」であり、存在だけでは dead にしない — marker 単独の
   規則。解決は 08 §3.1 手順 5 の canonical final event に正本化してから評価する — 正本 05 §3.5)

正本: 08-evidence-pointer-spec.md §4 / 05-runtime.md §3
Status: コアセマンティクスは decided。残未決 1 件 (bulk verify スループット) は Phase 4 着手前確定
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

決定済み:
  - 入出力 schema (正本 04 §3.1)
  - プロンプト規約 5 項: unchanged unit 非出力 / full unit replacement /
    heading 変更は chunk side 対応 / fallback_to_full 短絡 (正本 07 §8.1)
  - fallback_to_full の閾値 hint 衝突時は KCS 側を優先 (正本 07 §8.1)
  - ストリーミング応答: 許容。staging に保持し全体検査後に一括公開、中断は failed (retryable) — pending 状態は無い (正本 07 §8.3)
  - spec_version 不一致は Adapter が invalid_input として失敗、当該 Adapter は failed permanent (full fallback は incremental capability 非互換のみ — 正本 07 §8.1)
  - spec_version の bump 規約 (正本 10 §12.5)

残未決: なし

正本: 07-adapter-spec.md §8 / 04-pipeline.md §3.1 / 10-operations.md §12.5
Status: decided
```

## 5.5 進行状況テーブル

| # | 項目 | Status | 残未決 | 期日 |
| --- | --- | --- | --- | --- |
| 1 | Markdown 非決定性 = first-instance-wins | decided | なし | Step 1 着手前 (充足済み) |
| 2 | remarkdownize CLI セマンティクス | draft | --latest のデフォルト挙動 | Phase 4 着手前 |
| 3 | Dead Evidence Pointer | decided (コア) | bulk verify スループット | Phase 4 着手前 |
| 4 | Incremental Markdownize プロンプト規約 | decided | なし | Step 1 着手前 (充足済み) |
| 5 | 検索評価ハーネス (合成コーパス + ゴールデンクエリ、§4.3) | decided | なし (2026-07-03 完了: `eval/` に合成コーパス 305 ファイル / 7 scope + 履歴 fixture + ゴールデンクエリ 50 件 (M3-1: 18 / M3-2: 16 / M3-3: 16)。dry-run 検証済み。以後のクエリ追加・差し替えは §4.2 凍結規律。**M3-1 Q_hard 増補は 2026-07-23 完了・再凍結** (§4.2 の一回限り例外の完遂 — 本追記は §6.2 凍結対象外の完遂手続き): 「Step 3 着手前」の期日は失効していたため同日のユーザー裁定で失効後実行。増補 8 問 (hard1 ×4 + hard3 ×4、全問を結果測定前に投入 = 事前コミット) は実データ fixture (raster PDF / PPTX 図表 / 画像) を正解担体とするため合成コーパスに載らず、**別ファイル方式**で再凍結する: 既存 `eval/golden-queries.jsonl` は 50 件のまま不変 (digest sha256:b7183fa3586383883ec522256696268eab8e607c1a032020e09223158a5bf08d)、増補分は `eval/golden-queries-qhard.jsonl` 8 件 (digest sha256:d5c30eccc664e6bd4d96e1068970e225d209d04bde34c50eab300d6245d4e163、専用ランナー `eval/run_qhard.py`)。M3-1 の Done 判定は以後**合算 26 問で Recall@10 >= 0.8 (= 21 問以上)**) | 充足 (2026-07-23 増補完了 — 窓失効後実行の裁定含め本行が機械記録) |
| 6 | Markdownize Adapter 選定 = Mistral OCR 系 ([07 §5.2](07-adapter-spec.md)) | decided | なし (実地検証 2026-07-03 完了: sync/batch 両モードで表 1.0 / 日本語 CER 0.0 / 画像 1/1 / 数式 LaTeX 化。`experiments/ocr-verification`) | Step 2 着手前 (充足済み) |

Step N の着手条件は「期日が『Step N 着手前』の行がすべて decided」の機械的チェック (§3.2)。2026-07-02 の本改訂適用後、Step 1 のブロッカーは 0 件。#2/#3 の残未決は実装が Phase 4+ に割当てられた機能 (§3.1) にのみ関わるため、Step 1-4 をブロックしない。

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
  11-requirements.md           既存要件ドラフト (ARCHIVED — 現行正本ではない。読む順に含めない、README §1)
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
