# 04 Pipeline

統合元: `research/diff.md` (units / 差分判定) + `research/db.md` (SQLite schema / 検索バックエンド) + `research/batch.md` (タスク実行 / retry / budget)。いずれも正本ではない (経緯参照用)。

---

# 1. パイプライン全体

```
working tree
   │ ingest
   ▼
raw object        (CAS, raw_hash 単位)
   │ prepare (Adapter, 任意)
   ▼
prepared object   (page image, sheet 等の中間表現)
   │ markdownize (Adapter, full または incremental)
   ▼
normalized        (read-only artifact, content hash 不採用)
   │ chunking
   ▼
chunk             (CAS, chunk_hash 単位)
   │ embedding (Adapter)
   ▼
embedding         (CAS)
   │ indexing
   ▼
SQLite (FTS5 + sqlite-vec, query acceleration)
```

各ステージは [バッチタスク (§5)](#5-バッチ実行-batch--retry--budget) として記録される。`task state` は喪失を許容する運用データで、失われても object store と tool profile から未完了作業を再検出できる。

# 2. Prepared Units と差分判定

ファイル全体ではなく **unit 単位** で Markdownize する。これにより差分更新と decoded 単位の局所一貫性を両立する。

```
ファイル種別   | unit
PDF           | page
PPTX          | slide
DOCX          | heading section / page (page hash がデバイス間で安定しないので heading 優先)
XLSX          | sheet
画像          | image
Markdown      | heading section
code          | file / symbol
```

物理配置は [03-data-model.md §2 / §2.1](03-data-model.md) を正とする:

```text
.kcs/objects/prepared/ab/cd/<prepared64>           # unit 単位の中間表現 (CAS)
.kcs/objects/normalized_units/ab/cd/<raw64>.<tool64>.g<gen>/
  manifest.json                                   # 順序付き unit 一覧 + unit status
  <unit_ref>.json                                 # unit object (unit_ref = base16(sha256(unit_key))[0:16])
```

`<prepared64>` / `<raw64>` / `<tool64>` は論理 hash から `sha256:` を除いた 64 文字の小文字 hex。
JSON 内の `prepared_hash` / `raw_hash` / `tool_profile_hash` は `sha256:<64hex>` のまま保持する。
旧 Unix store の prefixed physical basename は [03-data-model.md §2](03-data-model.md) の
検証付き compatibility fallback で読み取り、新規作成時は digest-only basename を使う。

(prepared unit 専用ディレクトリは設けない。prepared object は最初から unit 粒度の CAS object であり、
`(raw_hash, unit_key, prepared_hash, fingerprint, order)` の台帳は SQLite cache (§4.7) に持つ。
raw object + 決定論的 prepare から再構築可能。)

unit object (schema は [03-data-model.md §2.1](03-data-model.md) と同一。unit の同定は instance 内で `unit_key` / `unit_ref`):

```json
{
  "unit_key": "page:12",
  "unit_type": "page",
  "raw_hash": "sha256:abc...",
  "prepared_hash": "sha256:...",
  "tool_profile_hash": "sha256:tool1...",
  "gen": 0,
  "mode": "full",
  "markdown": "## 3.2 認証仕様\n...",
  "reused_from": null,
  "generated_at": "2026-04-25T12:00:00Z"
}
```

normalized 全文 (`report.pdf.md`) は **生成物 (view)** で、unit を決定論的に結合して組み立てる
(組み立て規則は [03-data-model.md §2.1](03-data-model.md))。正本は unit object 群 (normalized instance)。

**unit_key の正準生成規則** (2026-07-03 確定、step2a §C-3):

```text
unit_key = "<unit_kind>:<selector>"
page / slide : 1-based の 10 進数、先頭ゼロ無し (page:1, page:12, slide:3)
sheet        : シート名 (NFC 正規化のみ。空白・大小文字は保持)。同名重複は 2 つ目以降に
               "#2", "#3" を付す (sheet:Sheet1, sheet:Sheet1#2 — 出現順)
doc          : text-native ファイル (Markdown / コード / plain text) は単一 unit "doc:1"。
               heading 単位の分割は chunk (Step 3) の責務であり unit では行わない
```

unit_key は `unit_ref` 算出 ([03-data-model.md §2.1](03-data-model.md)) と Evidence Pointer の入力に
なる determinism-critical な識別子であり、上記以外の形式を Adapter が発行した場合は受け入れ検査
(§3.2 V5) で reject する。

## 2.1 page fingerprint と再利用判定

差分判定は **raw 側 + tool_profile_hash** で完結し、Markdown content hash は使わない (Adapter の非決定性ゆえ)。

unit が「変わったか」の判定:

```
prepared_hash が変わった
  または
raw_hash が変わり、unit に対応する page_fingerprint が変わった
  または
tool_profile_hash が変わった
```

これらが変わらなければ **既存 Markdown unit をそのまま再利用** (= LLM 再呼び出し不要)。

page fingerprint は `(perceptual hash, text hash, visual hash)` の三つ組。一致時は再 Markdownize 不要を契約として明記する。

**MVP (Step 2) の具体アルゴリズム** (2026-07-03 確定、step2a §C-1):

```text
text hash       = sha256(unit のテキスト層バイト列)。テキスト層が無い unit は空バイト列の sha256
perceptual hash = MVP では prepared unit バイト列の sha256 で代替 (= 完全一致のみ)
visual hash     = MVP では perceptual hash と同値 (フィールドは将来分離のため保持)
一致判定        = 三つ組の全要素一致
```

perceptual 近似 (pHash 等) の導入は Phase 4+。完全一致方式の偽陰性 (レンダリング揺れによる不一致) は
「当該 unit を full 再処理する」側に倒れるだけで、誤った再利用は構造的に起きない。

**prepared のバイト列決定性** (2026-07-03 確定、step2a §C-2): prepared のレンダリングパラメータ
(renderer 名 / version / DPI / 色空間 / 出力フォーマット) は prepare Adapter の tool_profile
([07-adapter-spec.md §5.1](07-adapter-spec.md)) に含め、**同一入力ページ × 同一 profile のレンダリングは
バイト安定であること**を prepare Adapter の採用要件とする (バイト不安定な renderer は perceptual
fingerprint 導入 (Phase 4+) まで採用しない)。プラットフォーム間のバイト差は許容する
(cross-.kcs dedup を保証しない [03-data-model.md §9](03-data-model.md) と整合)。同一
(raw_hash, prepare tool_profile_hash) の再 prepare は first-instance-wins (§5.5) に従い既存 prepared を再利用する。

## 2.2 unit_mapping — 旧新 unit の対応付け

ページ挿入/削除で位置ベースの unit_key (`page:12` 等) はずれるため、キーの単純比較では
先頭挿入 1 枚で全 unit が「変更」になってしまう。KCS は Markdownize の前に、fingerprint
ベースで旧 unit と新 unit を対応付ける (**unit_mapping**)。

入力: 旧 instance の manifest (order 順) と、新 raw の prepared unit 列 (order 順)。
各 unit は page fingerprint (§2.1) を持つ。

アルゴリズム (決定論的):

```text
1. exact 対応 (unchanged):
   旧 unit 列と新 unit 列の fingerprint 完全一致を等価関係として、
   order を保存する最長共通部分列 (LCS) を取り 1:1 対応させる。
   同一 fingerprint の unit が複数あっても LCS の順序保存で一意に決まる。
   → (old_unit_key, new_unit_key, confidence=1.0, reason="fingerprint_exact")

2. 区間対応 (changed):
   exact 対応をアンカーとして旧新の unit 列を区間に分割し、各区間内で
   未対応の旧 unit と新 unit を order 順に 1:1 対応させる (min(m, n) 組)。
   → (old_unit_key, new_unit_key, confidence=0.5, reason="order_aligned")

3. 残余:
   区間内で対応が付かなかった新 unit → added
   区間内で対応が付かなかった旧 unit → removed
```

帰結:

```text
unchanged        reason="fingerprint_exact" の新 unit。KCS が旧 unit の markdown を
                 新 unit_key で再利用する (LLM 呼び出しなし)。unit object は新 instance へ
                 複製し、reused_from に旧 (raw_hash, gen, unit_key) を記録する
changed_unit_keys reason="order_aligned" の新 unit_key
added_unit_keys   残余の新 unit_key
removed_unit_keys 残余の旧 unit_key
```

**変化率** (§3.1 発動条件 4 の定義):

```text
変化率 = (|changed_unit_keys| + |added_unit_keys| + |removed_unit_keys|) / max(|新 unit 集合|, 1)
```

unit_mapping は毎回決定論的に再計算できるため永続台帳は持たない。記録は
`normalization_runs.changed_unit_keys` (cache) と unit object の `reused_from` (provenance) に残す。

将来拡張 (MVP 外): 区間対応の代わりに perceptual / visual hash の距離による近傍マッチングを
使う場合は、距離関数・閾値を tool_profile とは独立の設定として本節に追記する。

## 2.3 Diff 種別

```
Raw Diff       原文の差分 (raw_hash / page_fingerprint 変化)
Unit Diff      unit 単位の追加・削除・変更
Semantic Diff  chunk 単位の意味的差分 (Phase 4+ で使用、optional)
```

# 3. Markdownize

raw / prepared → normalized。非 text-native は文書処理 API 系 Adapter (Mistral OCR、第一候補) または生成 LLM 系 Adapter (Gemini / Claude / GPT)。Adapter contract は [07-adapter-spec.md §5.2](07-adapter-spec.md) を参照。

## 3.1 Incremental Markdownize (要件)

ファイル更新時、Adapter に **新 raw + 旧 raw + 旧 Markdown + 変更ヒント** をセットで渡し、軽微な変更なら Adapter が部分更新を返す。

**発動条件 (AND 5 つ)**:

```
1. 同一 file_id に対する既存 done normalization_run がある
2. raw_hash のみ変化 (tool_profile_hash は不変)
3. Adapter が capabilities = ["incremental_update"] を宣言
4. unit_mapping (§2.2) による変化率 < threshold (default 0.30)
5. 直前 N 回 (default 5) 連続 incremental の場合は full を強制 (style drift 防止)
```

いずれかが満たされなければ自動 fallback to full。

**Adapter 入力契約**:

```json
{
  "mode": "incremental",
  "new_raw":  { "path": "...", "raw_hash": "sha256:..." },
  "previous": {
    "raw":               { "path": "...", "raw_hash": "sha256:..." },
    "normalized_units":  [...],
    "tool_profile_hash": "sha256:..."
  },
  "hints": {
    "changed_unit_keys":  ["page:12", "page:13"],
    "added_unit_keys":    ["page:57"],
    "removed_unit_keys":  [],
    "page_fingerprints":  {...}
  },
  "tool_profile_hash":   "sha256:...",
  "spec_version":        1
}
```

`hints` の changed / added / removed は unit_mapping (§2.2) の帰結をそのまま渡す。
`fingerprint_exact` で対応が付いた unit (unchanged) は KCS が unit_key を付け替えて再利用済み
であり、Adapter には渡さない。

**Adapter 出力契約**:

```json
{
  "mode_used":           "incremental" | "full",
  "updated_units":       [...],
  "unchanged_unit_keys": [...],
  "added_units":         [...],
  "removed_unit_keys":   [...],
  "fallback_to_full":    false,
  "reason":              null | "..."
}
```

Adapter 側に「軽微とは言えない」拒否権あり (`fallback_to_full=true`)。

**identity 不変性**: incremental/full で出力が異なっても identity は `(raw_hash, tool_profile_hash)` のまま。`tool_profile_hash` 計算入力に incremental flag は含めない。

## 3.2 incremental 出力の受け入れ検査 (KCS 側 validation)

KCS は Adapter の incremental 出力を **persist する前に** 次を検証する。新 unit 全集合 `N` は
unit_mapping (§2.2) の帰結 (`unchanged 候補 ∪ changed ∪ added`)。

```text
V1 被覆・排他: keys(updated_units) ∪ keys(added_units) ∪ unchanged_unit_keys = N
              かつ 3 集合は互いに素 (unit の返し忘れ / 二重出力の検出)
V2 removed:   removed_unit_keys が hints.removed_unit_keys と完全一致
V3 越権禁止:  keys(updated_units) ⊆ hints.changed_unit_keys
              (hints に無い unit の書き換え = unchanged unit の再出力違反の検出)
V4 added:     keys(added_units) = hints.added_unit_keys と完全一致
V5 形式:      各 updated / added unit の markdown が非空文字列で、
              unit_key / unit_type が prepared unit 側と整合
V6 mode:      mode_used = "full" の場合は full 出力契約として検証
              (全 unit が揃っていること。V1〜V5 は適用しない)
```

違反時の挙動:

```text
error_code:      KCS-E-ADAPTER-CONTRACT-001
当該応答は unit 1 つも persist しない (全体 reject)
同一入力で full モードへ自動 fallback (fallback_reason = "contract_violation")
full 出力でも V6 に違反する場合は run を failed (invalid_input 系, retry しない)
```

内容 (意味) の検証は行わない。Markdown content hash を持たないため ([03-data-model.md §5](03-data-model.md))、
受け入れ検査は構造検証のみを保証範囲とする。

# 4. SQLite Schema (Query Acceleration Layer)

`.kcs/index/sqlite.db`。**真実は objects/、SQLite は再構築可能** (`kcs repair --rebuild-db`)。

## 4.1 chunks

```sql
CREATE TABLE chunks (
  chunk_id TEXT PRIMARY KEY,
  raw_hash TEXT NOT NULL,
  tool_profile_hash TEXT NOT NULL,
  gen INTEGER NOT NULL DEFAULT 0,
  unit_key TEXT NOT NULL,
  chunking_config_hash TEXT NOT NULL,  -- chunk 世代 (03-data-model.md §5.3)。identity には含めない
  raw_path TEXT NOT NULL,              -- chunk 生成時点の path (表示用)。現在 path は tree_entries join で得る
  heading_path TEXT,
  section_id TEXT,
  char_start INTEGER,
  char_end INTEGER,
  text_hash TEXT NOT NULL,
  text TEXT NOT NULL,
  first_seen_commit TEXT,              -- この chunk を含む最初の commit (commit_hash)。commit 作成時に付与
  created_at TEXT NOT NULL
);
CREATE INDEX idx_chunks_ident ON chunks(raw_hash, tool_profile_hash, gen);
```

`chunk_id` (PRIMARY KEY) の値は chunk object の `chunk_hash` と同一文字列とする (算出式は [03-data-model.md §8.1](03-data-model.md))。`gen` / `unit_key` は chunk が由来する normalized instance の世代と unit ([03-data-model.md §2.1](03-data-model.md)。`char_start` / `char_end` は unit-local)。chunk が属する Markdown 全体の content hash (normalized_hash) は持たない。

**chunk 境界の正準規則** (2026-07-03 確定、step3a §C-1 の決定性論点解消。chunk_hash の入力である heading_path / section_id / span を実装非依存にする):

```text
1. 入力は normalized instance の unit 列 (03 §2.1 の順序)。chunk は unit 境界を跨がない
2. heading 検出は ATX 形式 (行頭 1-6 個の # + 空白) のみ。setext 見出しは heading と見なさない。
   コードフェンス内の # は heading と見なさない
3. heading_path = chunk 先頭位置で有効な ATX 見出しテキストのスタック (階層は # の個数。
   レベル飛びはそのまま積む)。unit 先頭から見出し未出現の間は heading_path = []
4. section_id = heading_path の各要素を slug 化し "/" で結合。slug 規則: NFC 正規化 →
   ASCII 英字は小文字化 → 空白列を "-" に → 英数字・ハイフン・アンダースコア・日本語文字
   (ひらがな/カタカナ/漢字) 以外を除去 → 連続 "-" を 1 つに → 先頭末尾の "-" を除去。
   同一 unit 内の重複 slug は 2 つ目以降に "#2", "#3" を付す (出現順)
5. 分割: 見出し区間が max_chars (03 §11 [chunking]) を超える場合、段落境界 (空行) で
   貪欲に max_chars 以下へ分割する。単一段落が max_chars を超える場合のみ文字位置で
   機械分割する。分割片は同一 heading_path / section_id を共有し、unit-local の
   char_start / char_end で区別する (chunk identity は span を含むため衝突しない)
```

**chunks 行は append-only**。ファイルの更新・リネーム・削除では既存 chunk 行を削除・変更しない。これが time-travel 検索 (`--at` / `--all-history` / `--include-deleted`、[05-runtime.md §1.6](05-runtime.md)) の実体である。chunk 行を削除する経路は `kcs purge` のみ (対象 raw_hash の chunk 行・FTS エントリ・embeddings を物理削除、[05-runtime.md §3.5](05-runtime.md))。raw / chunk object は GC の削除対象外である ([05-runtime.md §2.6](05-runtime.md))。既存行への UPDATE は `first_seen_commit` の付与のみ許可する。

## 4.2 chunk_fts (FTS5 外部 content)

MVP から **外部 content モード** を採用 (整合性保証のため):

```sql
CREATE VIRTUAL TABLE chunk_fts USING fts5(
  chunk_id UNINDEXED,
  text,
  heading_path,
  content='chunks',
  content_rowid='rowid'
);
```

trigger で chunks との同期を自動保守:

```sql
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunk_fts(rowid, chunk_id, text, heading_path)
    VALUES (new.rowid, new.chunk_id, new.text, new.heading_path);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunk_fts(chunk_fts, rowid, chunk_id, text, heading_path)
    VALUES('delete', old.rowid, old.chunk_id, old.text, old.heading_path);
END;
CREATE TRIGGER chunks_au AFTER UPDATE OF text, heading_path ON chunks BEGIN
  INSERT INTO chunk_fts(chunk_fts, rowid, chunk_id, text, heading_path)
    VALUES('delete', old.rowid, old.chunk_id, old.text, old.heading_path);
  INSERT INTO chunk_fts(rowid, chunk_id, text, heading_path)
    VALUES (new.rowid, new.chunk_id, new.text, new.heading_path);
END;
```

`chunks_au` を `UPDATE OF text, heading_path` に限定するのは、`first_seen_commit` の付与 (§4.1 で唯一許可された UPDATE) で FTS が再書き込みされるのを防ぐため。

**Tokenizer**: デフォルト `trigram` (CJK 対応)。英文中心の場合のみ `unicode61 remove_diacritics 2` を選択可。`.kcs/config.toml [search.fts]` で切替。

## 4.3 embeddings (sqlite-vec + metadata)

```sql
CREATE TABLE embeddings (
  id TEXT PRIMARY KEY,
  target_type TEXT NOT NULL,    -- chunk | image | node | query_cache
  target_id TEXT NOT NULL,
  modality TEXT NOT NULL,       -- "multimodal" のみ (非 multimodal は KCS-E-EMBED-MODALITY-001 で採用不可、07 §5.3)
  vector BLOB NOT NULL,
  dimensions INTEGER NOT NULL,
  distance TEXT NOT NULL,
  profile_hash TEXT NOT NULL
);

CREATE VIRTUAL TABLE chunk_vec USING vec0(
  chunk_id TEXT PRIMARY KEY,
  embedding FLOAT[<dim>]
);
```

`embeddings` テーブル (メタデータ + vector BLOB) と `chunk_vec` (vec0 virtual table) は、いずれも `objects/` から再構築可能な加速層であり、真実は `objects/` にある (§4 冒頭)。両テーブル間では **`embeddings` テーブルを正** とし、`chunk_vec` は `embeddings` からの導出物として扱う。不整合を検出した場合および `kcs repair --rebuild-db` では、`objects/` → `embeddings` → `chunk_vec` の順に再構築する。

KCS は Text/Image を分けず **単一マルチモーダル Embedding Adapter** のみを許可する (非 multimodal profile は `KCS-E-EMBED-MODALITY-001` で採用拒否、[03-data-model.md §7](03-data-model.md))。

## 4.4 その他のテーブルの正本

```text
normalization_runs / files / chunks / tree / commit   03-data-model.md §8
tasks                                                 本書 §5.1
tree_entries                                          本書 §4.5 (commit tree の射影 cache)
prepared_units                                        本書 §4.7 (cache)
evidence_pointers                                     テーブル非採用 (pointer は self-contained)。
                                                      schema の正本は 08-evidence-pointer-spec.md §2
access_events                                         正本は logs/access.jsonl (03-data-model.md §2)。
                                                      SQLite 集計 cache の採否は Step 3 で判断
```

nodes / edges は Phase 5 のため MVP の schema には含めない。

## 4.5 tree_entries (commit tree 射影)

time-travel 検索の liveness 判定用に、tree object ([03-data-model.md §8](03-data-model.md)) を SQLite へ射影する:

```sql
CREATE TABLE tree_entries (
  commit_hash TEXT NOT NULL,
  path TEXT NOT NULL,
  raw_hash TEXT NOT NULL,
  tool_profile_hash TEXT,
  gen INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (commit_hash, path)
);
CREATE INDEX idx_tree_entries_ident ON tree_entries(commit_hash, raw_hash, tool_profile_hash, gen);
```

規範:

- tree_entries は tree object の射影 cache。真実は `objects/trees/`。`gen` は tree entry の `normalize.gen` ([03-data-model.md §8](03-data-model.md)) の射影で、tree entry に `gen` 欠落時は 0 と読む
- **常駐必須は HEAD commit 分のみ**。commit 作成時に新 HEAD 分を挿入する。旧 HEAD 分は cache として残してよい
- `--at <commit>` 検索時、当該 commit 分が無ければ tree object を展開して挿入する。tree は immutable なので展開結果は常に同一
- `kcs repair --rebuild-db` は HEAD 分のみ再構築する (他 commit 分は次回 `--at` 時に再展開)。旧 HEAD 分の掃除は GC (実行系は Phase 4+、[05-runtime.md §2](05-runtime.md)) が担う。GC が tree_entries 行を消しても raw / chunk object は削除しない ([05-runtime.md §2.6](05-runtime.md))

## 4.6 chunk 世代と chunking 設定変更

`[chunking]` 設定 ([03-data-model.md §11](03-data-model.md)) の変更は raw_hash / tool_profile_hash に現れないため、独立した世代判定を行う:

- chunk / embedding 段の最新判定は `(raw_hash, tool_profile_hash, gen, chunking_config_hash)` の一致で行う ([03-data-model.md §5.3](03-data-model.md))。03 §6 の up_to_date 判定 (Markdownize 段) は変更しない
- 検索対象は常に **現行 chunking_config_hash の chunk のみ** ([05-runtime.md §1.6](05-runtime.md))
- 設定変更を検出したら、次回 `kcs index` で全 normalized instance (履歴分含む) の再 chunk + 再 embedding task を積む。再 chunk はローカル処理で LLM 不要。embedding のみ再課金 (§5.4 budget guardrail の対象)
- 開始前に再生成対象 chunk 数と embedding 概算コストを提示し確認する (`--yes` で省略)
- 旧世代 chunk 行は **削除しない**。Evidence Pointer の chunk_hash 解決 ([08-evidence-pointer-spec.md §6](08-evidence-pointer-spec.md)) 用に残置する (検索には出ない)
- 再生成未完了の instance はその間検索から漏れる (index 未完了と同じ扱い。`kcs status` に表示)

## 4.7 prepared_units (台帳, cache)

```sql
CREATE TABLE prepared_units (
  raw_hash TEXT NOT NULL,
  unit_key TEXT NOT NULL,
  prepared_hash TEXT NOT NULL,
  unit_type TEXT NOT NULL,
  fingerprint TEXT NOT NULL,    -- JSON: { text_hash, perceptual_hash, visual_hash }
  order_index INTEGER NOT NULL,
  PRIMARY KEY (raw_hash, unit_key)
);
```

この表は cache。raw object (CAS) + 決定論的 prepare から再構築可能 (§5.7)。

# 5. バッチ実行 (Batch / Retry / Budget)

すべての非同期処理 (Prepare / Markdownize / Embedding / Summary / Classification / Rerank / index / node 生成) は **task** として記録する。

初回大量投入では、deterministic なタスク (Prepare / ベースライン抽出 / FTS index) を online Adapter タスク (Markdownize / Embedding) より優先してスケジュールし、**ベースライン index を先に完了させる**。これにより budget pause ([§5.4](#54-cost-guardrail--kill-switch)) が起きても検索の成立自体は阻害されない。

## 5.1 タスクモデル

```json
{
  "task_id": "task_01H...",
  "type": "markdownize",
  "mode": "full",                       // or "incremental"
  "input_path": "report.pdf",
  "input_hash": "sha256:abc...",
  "previous_raw_hash": "sha256:old...", // incremental 時
  "parent_run_id": "run_01H...",        // incremental 時
  "changed_unit_keys": ["page:12"],     // incremental 時
  "output_ref": ".kcs/objects/normalized_units/ab/cd/<raw64>.<tool64>.g0/",
  "unit_keys": null,
  "status": "pending",
  "attempts": 0,
  "next_retry_at": null,
  "deadline": "2026-05-02T23:59:59Z",
  "heartbeat_at": null,
  "fallback_reason": null,
  "created_at": "2026-04-25T12:00:00Z"
}
```

`unit_keys` は unit スコープの再投入 (partial の retry) 時のみ非 null で、対象 unit_key の配列。
null は全 unit 対象。

## 5.2 状態遷移

```text
pending → running → done                     全 unit done
pending → running → partial                  1 unit 以上 done かつ 1 unit 以上 failed
pending → running → failed → pending         全 unit 失敗、または run 前提の失敗 (prepare 失敗等)。retryable
partial → done                               失敗 unit の再投入がすべて成功
running が heartbeat_at + 5min を超えたら stale。別 worker が pull 可能
```

**partial の規範** (markdownize task):

- 状態表現の正本は normalized instance の manifest (`units[].status`,
  [03-data-model.md §2.1](03-data-model.md))。task / normalization_runs はその cache
- done unit は保全する (first-instance-wins)。chunking / embedding / index は done unit 由来のみ実行し、
  failed unit 由来の chunk は index に載せない (= 検索対象は成功 unit のみ)
- `kcs status` は partial のファイルについて失敗 unit_key と error_kind を表示する (silent 欠落の禁止)
- retry は **失敗 unit のみ** を対象とする:
  - Adapter が `incremental_update` を持つ場合: `mode=incremental`、
    `hints.changed_unit_keys = 失敗 unit のキー`、`previous = 同一 instance の done unit 群` で再投入
  - 持たない場合: `mode=full` で再実行するが、既に done の unit は first-instance-wins で既存を保持し、
    失敗していた unit の出力のみ採用する
- manifest の unit status 遷移は `failed → done` の一方向のみ。error_kind が permanent
  (invalid_input 等, §5.3) の unit は再投入せず、partial のまま `kcs status` に表示し続ける

`task` テーブルが消えても問題ない設計 (object store と tool profile から再検出可能)。ただし `attempts` 履歴は失われる (リトライ予算がリセットされる) 点を許容。

## 5.3 エラー種別と Retry Budget

```
network_error      retryable             max_attempts=5,  exp(base=2s, cap=60s), jitter=full
                                         KCS-E-BATCH-NET-001
rate_limit         retryable later       max_attempts=∞,  honor "Retry-After" header
                                         KCS-E-BATCH-RATE-001
auth_error         user action required  max_attempts=0
                                         KCS-E-BATCH-AUTH-001
quota_exceeded     retryable             max_attempts=3,  fixed(1h)
                                         KCS-E-BATCH-QUOTA-001
invalid_input      failed permanent      max_attempts=0
                                         KCS-E-BATCH-INPUT-001
contract_violation failed permanent      max_attempts=0 (full fallback を 1 回自動投入)
                                         KCS-E-ADAPTER-CONTRACT-001
budget_exceeded    paused                KCS-E-BATCH-BUDGET-001
```

エラーコード namespace は [10-operations.md §12.1](10-operations.md)。

## 5.4 Cost Guardrail / Kill Switch

将来 LLM コスト低下を前提とするが、移行期の暴走防止のため **MVP から budget guardrail を入れる**。

```toml
# ~/.config/kcs/config.toml — device cap (正。デバイス上の全 .kcs の合算に適用)
[budget]
monthly_usd_cap = 50.0
warn_at_percent = 80
hard_stop = true
[budget.per_adapter]
markdown = 30.0
embedding = 15.0
summary = 5.0

# .kcs/config.toml — folder cap (任意。この .kcs のタスクのみに適用する追加制限)
[budget]
monthly_usd_cap = 10.0
```

- cap は二層で判定する。**device cap** (`~/.config/kcs/config.toml`、デバイス上の全 `.kcs` の当月合算に適用、既定 $50) が正であり、**folder cap** (`.kcs/config.toml`、その `.kcs` の当月消費のみに適用) は任意の追加制限。folder cap 未設定なら device cap のみが効く
- 判定式: scope S の新規タスクを起動できるのは `ledger(S, 当月) < folder_cap(S)` **かつ** `ledger(device, 当月) < device_cap` のとき (= effective cap は両者の残余の min)。`per_adapter` の下限も同様に両層で判定する
- 累積コストは Adapter 報告値 (input/output token × 単価) を `~/.local/share/kcs/cost-ledger.sqlite` (デバイスグローバル 1 個) に記録し、各記録に `scope_id` を付与する。folder cap の判定はこの ledger の scope 別集計で行う (`.kcs` 内に ledger は置かない。cache/truth 規約上、課金台帳はデバイスローカルの運用データであり `.kcs` の truth ではない)
- いずれかの cap 超過時、走行中タスクは完了させ、新規タスクは `paused` 状態へ。`kcs status` は超過した cap の種別 (`device` | `folder`) と scope を表示する
- `kcs batch resume --override-budget` で明示的に再開可能 (当月の device cap / folder cap の両方を無視して再開する)。override は markdownize / embedding **両 Adapter の budget 判定に対称に**効く。override 無しの `kcs batch resume` は budget 超過 pause タスクを markdownize / embedding いずれも据え置き (sticky)、他要因の pause のみ再開する
- ローカル LLM 利用時は単価 0 として記録 (= cap に効かない)

**resume / retry / reindex が駆動する enrichment**: `kcs batch resume` / `kcs batch retry` は online markdownize タスクに加え、**embedding enrichment パスも駆動する** (embedding タスクは現行世代の live chunk 集合から DB 駆動で再検出される。opt-in は Adapter 単位 = embedding は自身の承認行を見る、[07-adapter-spec.md §3](07-adapter-spec.md))。同様に `kcs reindex --force` / `kcs repair --rebuild-db` は rebuild 後に enrichment を実行し、新世代 chunk の embedding を追随させる (§4.6)。offline なら embedding タスクを enqueue のみとし `index_status` ([05-runtime.md §1.7](05-runtime.md)) に pending として可視化する。retry の失敗タスクは backoff / retry 予算 (§5.3) を尊重し、`next_retry_at` 未来または非 retryable の embedding タスクを持つ chunk は enrichment 対象から除外する

## 5.5 冪等性

`(input_hash, tool_profile_hash) → output_ref` 一致なら done として短絡 (キャッシュヒット)。これは **first-instance-wins** ([03-data-model.md §6](03-data-model.md), [09-mvp-scope.md §設計宿題](09-mvp-scope.md))。LLM API の二重課金を防ぐため、Adapter 層に idempotency_key を要求する。

**embedding の content ベース再利用**: embedding タスクは上記の短絡に加え、対象 chunk の
`(text_hash, embedding profile_hash, dimensions, distance, modality)` に一致する既存 embedding が
同一 `.kcs` 内にあれば、Adapter を呼ばず既存 vector を再利用する。`text_hash` は chunk 抽出範囲のみの
hash ([03-data-model.md §8](03-data-model.md)) であり、normalized_hash (不採用) ではない。
これにより incremental Markdownize 後、unchanged unit 由来で本文が変わらない chunk は
embedding を再生成しない。budget 判定と cost ledger 記帳は **実際に Adapter へ送信した (再利用でない)
chunk の文字数のみ**を対象とし、再利用 chunk (API 非呼出) は課金しない。バッチ内で再利用と実送信が
混在し実送信側が失敗した場合も、再利用で既に `chunk_vec` を確定した chunk は done を保持する
(送信失敗が再利用済み chunk に波及しない)。

## 5.6 CLI exit code (batch 系)

横断規約 ([10-operations.md §12.2](10-operations.md)) に従う:

```
0  全タスク success または all up_to_date
1  汎用 failure
2  invalid usage / config 不正
3  一部タスク failed (retryable 残あり)
4  全タスク failed permanent
5  auth_error がある
6  budget_exceeded により paused
7  user 中断 (SIGINT/SIGTERM)
```

## 5.7 Resume と Repair

- `kcs batch resume`: 中断状態 (running stale, pending) を再開
- `kcs repair --rebuild-db`: SQLite を objects/ から再構築する。復元範囲は次の通り:

  復元されるもの (objects/ が正本):

  ```text
  normalization_runs の done / partial / missing_output 相当の状態
      (normalized_units/ の manifest と unit object から)
  最新 gen (instance ディレクトリ名の g<gen> から)
  manifest 記載の run_id / parent_gen (provenance)
  prepared_units 台帳 (raw object + 決定論的 prepare の再実行から)
  chunks / embeddings / FTS index (normalized instance からの再導出)
  ```

  喪失を許容するもの (task と同様の運用データ):

  ```text
  failed run の記録 (error / fallback_reason / attempts)
  parent_run_id チェーン (manifest の parent_gen で世代関係のみ復元可能)
  incremental の連続回数カウンタ (発動条件 5 の根拠)
  ```

  安全側規定: incremental の連続回数が復元不能な場合、次回 Markdownize は **full を強制** する
  (style drift 防止側に倒す)。failed の喪失は pending への退行として扱い、次回 `kcs index` の
  再スキャンで再検出・再投入される。

# 6. 検索バックエンド方針

```
text  : FTS5 (外部 content + trigram tokenizer)         デフォルト
vector: sqlite-vec                                      デフォルト
hybrid: RRF + MMR (詳細は 05-runtime.md §1)
```

将来候補 (Phase 4+):

```
Tantivy           large-scale BM25
LanceDB / Qdrant  large-scale vector
```

MVP では single SQLite に集約。`.kcs` 単位の export/restore/portability を優先。
