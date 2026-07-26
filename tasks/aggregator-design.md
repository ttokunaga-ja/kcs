# レプリケーション型 aggregator 設計 (2026-07-25)

ユーザー裁定により、横断検索の実行モデルを **scatter-gather (fan-out + merge)** から
**replication (device-level read replica)** へ変更する。

- 変更前: [05-runtime.md §1.8](../docs/05-runtime.md) 「各 `.kio` は独立した index (sqlite.db) を持つため、
  横断検索は次の実行モデルで行う」= scope ごとに独立クエリ → RRF マージ
- 変更後: 各 `.kio` の index 内容を device-level の 1 DB へ複製し、**1 クエリで採点・選択する**

正本は変わらない。**truth = 各フォルダ直下の `.kio`**、aggregator は再構築可能な cache のまま
([03-data-model.md §4](../docs/03-data-model.md))。

## 1. 変更の動機

動機は 2 つ。性能は**副次的**である (実測は §7 — Stage 1 では変わらず、Stage 3 で縮む)。

1. **採点の正しさが構造的に保証される。** 428 個の独立コーパスがある限り BM25 は比較不能で、
   RRF の text 項と vector 項を同一スケールで足せない (I17)。コーパスが 1 つなら問題自体が消える。
   `global-text.sqlite` (I17 の修正) はこの解を text にだけ先行適用したもので、本設計はその一般化。
2. **権限を device 横断で扱える。** 現在、承認は `.kio/approvals.jsonl` + `scope.json` に閉じており、
   「どの scope が何を承認しているか」を一覧する手段が無い。428 scope では実用上の問題になる。

## 2. 保存先と名前

```
$XDG_CACHE_HOME/kio/aggregator.sqlite
```

cache root であり data root ではない。全内容が各 `.kio` から再構築可能で、消しても
再生成されるだけである ([03-data-model.md §4](../docs/03-data-model.md) の不変条件 2 を満たす)。
I17 で導入した `global-text.sqlite` は本 DB へ吸収する (後方互換不要)。

## 3. 何を複製するか — 「解決済みの集合」を持つ

**生テーブルを複製しない。** `chunks` / `chunk_config_generations` / `tree_entries` /
`kio_eligible_identity` / `first_seen_commit` を全部複製して aggregator 側で eligibility 述語を
組み直すと、**liveness 判定ロジックが 2 箇所に増える**。R1-R24 の監査で塞いだ穴の多くはこの型の
乖離だった。

代わりに、**refresh 時に scope 側の既存コードで live chunk 集合を解決し、その答えだけを持つ**。
aggregator は「この scope の index_generation G における生きた chunk はこれ」という射影であり、
liveness の再実装を含まない。

**列は読み手が現れた段階で足す。** 読み手のいない列は「どのコードも参照しない 3,851 行分のデータ」に
なるだけで、spec が実装より先行する原因にもなる。下表の Stage 列がその境界である。

| 表 | Stage | 供給元 | 内容 |
|---|---|---|---|
| `agg_scopes` | **1** | 各 `.kio` | `scope_id` PK, `index_generation`, `refreshed_at` |
| `agg_scopes` (追加列) | 3 | registry + `.kio` | `kio_path`, `root_path`, `kio_format_version`, `embedding_profile_hash`, `head_commit`, `chunking_config_hash` — 安全性再確認 (§4.2 手順 3) と候補 materialize に要る |
| `agg_chunks` | **1** | 解決済み live 集合 | `scope_id`, `chunk_id`, `text`, `heading_path` |
| `agg_chunks` (追加列) | 3 | 同上 | `raw_hash`, `tool_profile_hash`, `gen`, `raw_path`, `section_id`, `byte_start`, `byte_end` — 候補を replica から materialize するときに要る |
| `agg_fts` | **1** | `agg_chunks` の external content | **全 scope 単一の FTS5** (trigram) — `bm25()` がコーパス全体で計算される |
| `agg_embeddings` | **1** | `chunk_vec` (live 集合分) | `chunk_rowid`, `scope_id`, `vector`, `dimensions` |
| `agg_approvals` | 2 | `.kio/approvals.jsonl` + `scope.json` | `scope_id`, `tool_id`, `tool_profile_hash`, `kind`, `granted_at` — **投影のみ** |

### 更新方式 — write-through (2026-07-25 確定)

**正本を書いた処理が、同じ処理の中で replica にも書く。** 読み手が「変わったかどうか」を検知するのではない。

当初の設計は逆向きで、検索時に `index_generation` を比較して差分 scope を射影し直していた。
この向きが成立するのは**索引を変えうる全経路が漏れなく回転させる**場合だけで、実装を数えると
**回転する経路は 2 つ、回転しない in-place 書き込みは 4 つ**だった (I20 / I21)。しかも回転は
**コマンドの上端**にあり、`run_batch` は回収 (回転あり) の後で同期レーンの enrichment (回転なし) を
走らせるので、回転を足しても後段を取りこぼす。write-through は**呼び出しグラフの下端**に置ける
— `persist_group_vector` は両レーンが共有する唯一の書き込み点、`rebuild_sqlite_index` の rename は
再構築 3 コマンドが共有する唯一の入れ替え点。

| 書き手 | 方式 | 理由 |
|---|---|---|
| 索引の再構築 (`index` / `reindex` / `repair rebuild-db`) | 全置換 | temp DB + rename で rowid が総入れ替え、生き残る chunk 集合も任意に変わる |
| `reindex --at <commit>` | 全置換 | snapshot の投影であって増分ではない |
| purge | 全置換 | chunk・association・vector・orphan embedding の 4 層を消す。正確さがミリ秒より重い |
| 埋め込み (両レーン) | 差分 | 触った chunk を書き手が知っている。本文は変わらない |
| 内容アドレス再利用の link | 差分 | 同上 (API 呼び出し無しの dedup ヒット) |

差分はパス全体で溜めて**末尾で 1 回**流す。dogfood fixture に 2,321 group あり、group ごとに
別 DB の transaction を張るのは、パスが既に知っている集合を記録するのに高すぎる。

全置換は upsert ではなく **delete-then-insert**。scope が持たなくなった chunk を落とさないと、その語の
document frequency を永久に膨らませ続け、他の全 chunk の IDF を静かに下げるため。

**差分は replica にまだ無い scope には何も書かない。** 差分は変化分しか運ばないので scope を新規に
作れず、それでスタンプだけ押すと**一度も複製されていない本文について「最新」と検索に告げる**。
押さずに残せば次の検索が全射影する — それが正しい縮退。

**スタンプは最後に書く。** generation スタンプがこの投影の commit marker で、その手前で落ちた更新は
スタンプが古いまま残り、次の検索が再射影する。これが DB を跨ぐ atomic commit 無しで replica を
正しく保てる理由。SQLite の master journal による複数 DB の atomic commit は rollback-journal
モードでしか働かず (attach 側を WAL にすると master journal が作られない — 実測で確認)、
WAL を捨てる代償に見合わない。

**秘匿判定は複製しない。** `link_chunk_vecs_to_content_vector` / `link_chunk_vec` は
「何件 link したか」ではなく「**どの chunk_id を link したか**」を返す。R20-10 の secrets hold と
width 不一致の判定はこの 1 箇所にあり、replica が `held` を自前で再評価する形にすると、
両者が乖離した日に hold 中の chunk が vector 検索へ露出する (§5 不変条件 8)。
replica は結果に従い、規則を複製しない。

## 4. 検索の実行モデル

### 4.1 aggregator が答える条件

既定検索 — すなわち次を**すべて**満たすとき:

- 時間選択子が無い (`--at` / `--all-history` / `--since` / `--include-deleted` のいずれも指定なし)
- cursor が凍結済み commit を再生しているのではない (page 1、または aggregator 世代が一致する page N)

満たさないものは **fan-out 経路へ委譲する**。fan-out は削除せず、reference 実装かつ
fallback として残す ([03-data-model.md §4](../docs/03-data-model.md) 不変条件 2 —
aggregator を失っても検索が成立しなければならない)。

### 4.2 手順

1. **refresh (修復経路)**: registry の全 scope について `index_generation` を比較し、差分のある scope
   だけ射影し直す。**通常はここで何も起きない** — write-through 済みなので差分はゼロ。残してあるのは
   write-through が届かなかった場合 (replica の削除、cache root ごとの消失、書き込み失敗、
   write-through 導入前に索引された scope) を検索が自力で埋めるためで、**replica が cache である
   (不変条件 2) ことを成立させているのはこの経路**。到達不能な scope は `agg_scopes` から落とし、
   `excluded_scopes` に理由を積む
2. **1 クエリで採点**:
   - text 項 = `agg_fts` に対する 1 回の MATCH + `bm25()` — **コーパス全体の N・df・avgdl**
   - vector 項 = `agg_embeddings` 全体に対する cosine — 従来どおり全体順位
   - RRF は **2 つの global rank** を足す。per-scope rank は登場しない
3. **安全性の再確認 (結果件数に比例)**: 上位候補を出した scope についてのみ live `.kio` を開き、
   (a) `kio_format_version` 互換、(b) purge journal 非活性、(c) `index_generation` が射影時と同一 —
   を確認する。落ちた scope の候補は捨て、`excluded_scopes` に理由を記録し、次順位から補充する
4. diversify (MMR / group_by_raw_hash) を統合後の候補列へ適用 — 現行 §1.4 のまま

**手順 3 が設計の要点である。** 安全性判定を replica に委ねると staleness がそのまま
「死んだ Evidence Pointer を返す」に化ける。かといって全 428 scope を毎回開けば fan-out に戻る。
**結果を出した scope だけ検証する**ので、コストは `O(結果ページの distinct scope 数)` ≈ 1〜10 であり、
scope 総数に依存しない。

## 5. 不変条件 (03 §4 の拡張)

既存の 5 条は `scope_registry` と同じく aggregator にも適用する。加えて:

```
6. aggregator は安全性判定の最終権限を持たない。
   purge journal / kio_format_version / index_generation は、
   結果を返す scope について live .kio で再確認する。
7. aggregator は候補の「選択と採点」を担い、liveness 判定を再実装しない。
   refresh 時に scope 側で解決済みの集合だけを持つ。
8. 権限の書き込みは常に .kio へ行う。aggregator は投影のみで、
   承認の可否を aggregator の行で判定してはならない。
```

## 6. 権限管理

`agg_approvals` は**読み取り専用の投影**である。用途は横断的な可視化と一括操作の入口。

- `kio approvals list --all-scopes` — device 横断で承認状態を一覧
- 一括承認 / 一括取消は各 `.kio` へ write-through してから当該 scope を refresh

送信 gate の判定は従来どおり `.kio` を読む (不変条件 8)。aggregator が古くても
「未承認なのに送信される」は起こらない。

## 7. 段階

| Stage | 状態 | 内容 |
|---|---|---|
| 1 | **完了 (2026-07-25)** | `aggregator` モジュール (`global_text` を拡張・改名)、4 表。**両レーンの rank を単一コーパス上の global rank へ統一**。`regrade_vector_rank_globally` は fallback 専用へ降格。fan-out は候補選択と fallback として存置 |
| 2 | 未着手 | `agg_approvals` の追加 (表ごと未作成 — 書き手が現れるまで置かない) と横断コマンド |
| 3 | 未着手 | **replica が候補選択も担う**。安全性再確認 (§4.2 手順 3) の独立実装、per-scope `candidate_depth` 打ち切りの解消、時間選択子の replica 対応 (commit DAG の投影) |

### Stage 1 で「安全性再確認」を独立実装しなかった理由

Stage 1 では候補を出すのが per-scope 経路のままなので、手順 3 の (a)(b)(c) は**その過程ですでに
満たされている** — `Repository::open_for_search` の版検査が (a)、`ReadBarrierCheckpoint` が (b)、
`INDEX_REBUILDING` 判定が (c) に対応する。ここで別実装を足すと同じ判定が 2 箇所になり、
不変条件 7 が避けようとしている乖離をこちら側で作ることになる。

**Stage 3 で replica が候補を返し始めた瞬間に必須**になる。それまでは実装しない。

### Stage 1 の実測

| | 値 |
|---|---|
| replica | 428 scope / 3,851 chunk / 3,851 vector / 24.6 MB (うち vector 11.8 MB) |
| 初回射影 | 2.3 秒 |
| 差分ゼロ検索 | 1.19 秒 |
| scatter-gather fallback | 1.20 秒 |
| hybrid rank1 | 7 → **8** / 32 |
| hybrid top5 | 22 → **24** / 32 |

**性能は変わらない。** 1.2 秒はほぼ全部 428 個の `.kio` を開くコストで、Stage 3 まで縮まない。
順位の改善は「vector 順位が*候補プール*の順位から*コーパス全体*の順位になった」効果である。

## 8. spec 側の変更点

| 文書 | 変更 |
|---|---|
| [05-runtime.md §1.8](../docs/05-runtime.md) | 実行モデルを replication へ。**「text backend の rank は per-scope のまま融合する」を撤回**し、両項 global rank に統一。fan-out を fallback として明記 |
| [03-data-model.md §4](../docs/03-data-model.md) | aggregator を「将来の」から実在の cache へ。不変条件 6-8 を追加。§4.1 の SQLite ファイル一覧を 3 → 4 へ |
| [01-positioning.md](../docs/01-positioning.md) / [10-operations.md](../docs/10-operations.md) / [README.md](../docs/README.md) | 二層構造の説明から「将来の」を外し、役割を更新 |
