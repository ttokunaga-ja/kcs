# 04 Pipeline

統合元: 旧 `research/diff.md` (units / 差分判定) + 旧 `research/db.md` (SQLite schema / 検索バックエンド) + 旧 `research/batch.md` (タスク実行 / retry / budget)。いずれも正本ではなく、2026-07-18 に docs から撤去 (経緯は git 履歴で参照可)。

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

## 1.1 ingest / スキャンの安全規則

working tree の読み取りは次の規則に従う (出典: 旧 `research/folder-history-sqlite-design.md` §20 の監査済み規範の KCS 適応 — 2026-07-18 撤去、git 履歴で参照可):

- **単一 open**: raw_hash の計算と保存する bytes は**同一の open・同一のストリーム**から得る。hash 用と
  保存用に 2 回 open すると、その間の書き換えで「hash A の名前に内容 B」が保存され得る (CAS の破壊)
- **安定確認**: 読み取りの前後で stat (size, mtime) が同一であることを確認し、変化していたら当該
  ファイルはこの実行では取り込まず次回へ回す (書込途中の中間状態を切らない)
- **racy 規則** (stat ショートカットを実装する場合の必須規則): 「stat が前回と同じなら再 hash を省略する」
  最適化は、ファイルの mtime が前回判定時刻と**同一秒以降**の場合は適用してはならない (mtime の秒粒度
  では同一秒内の上書きが「stat 同一・内容相違」になる — Git index と同じ罠)。mtime が現在時刻より
  未来の実体は恒久 racy になるため、内容 hash の一致確認をもって確定してよい

# 2. Prepared Units と差分判定

ファイル全体ではなく **unit 単位** で Markdownize する。これにより差分更新と decoded 単位の局所一貫性を両立する。

```
ファイル種別   | unit (正準 unit_key は §2 後半の 4 kind のみ — 本表はその適用)
PDF           | page
PPTX          | slide
DOCX          | page (prepare の変換 PDF 経由 — [07-adapter-spec.md §5.2](07-adapter-spec.md)。
               heading 単位の分割は chunk (Step 3) の責務であり unit では行わない)
XLSX          | sheet
画像          | doc:1 (単一 unit — 画像 1 ファイル = 1 unit)
Markdown      | doc:1 (heading 分割は chunk の責務)
code          | doc:1 (symbol 分割は chunk の責務)
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
`(raw_hash, unit_key, prepared_hash, fingerprint, order)` の台帳は永続化しない論理台帳 (§4.7) —
raw object + 決定論的 prepare からいつでも再導出できる。)

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
sheet        : シート名 (NFC 正規化のみ。空白・大小文字は保持)。**元名に含まれる `#` は `##` へ
               escape** してから、同名重複の 2 つ目以降に "#2", "#3" を付す (可逆・決定的 —
               sheet:Sheet1, sheet:Sheet1#2 — 出現順。実名 "A#2" は sheet:A##2 となり
               "A" の 2 枚目 sheet:A#2 と衝突しない)
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
   同スコアの LCS 対応が複数ありうる (旧 [A,A] × 新 [A]、旧 [A] × 新 [A,A] の双方向) ため、
   **tie-break = 対応ペア列を (旧 index 列, 新 index 列) の辞書順で最小になるものを選ぶ**
   (完全順序 — 旧 index 昇順だけでは新側の重複を順序付けられない)。
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
1. 同一ファイル (= scope 内の同一 path binding。file_id は廃止済み — [03-data-model.md §8](03-data-model.md))
   に対する既存 done normalization_run がある。rename を跨いだ同一性は追跡しない (rename + 編集は full)
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
              unit_key / unit_type が prepared unit 側と整合。加えて Normalized Markdown v1
              ([07-adapter-spec.md §5.2.1](07-adapter-spec.md) が正本) の機械検証可能な規約 —
              UTF-8 (BOM 禁止)・NFC・LF のみ・trailing space 禁止・ATX 見出し・``` fence・
              生 HTML / autolink 禁止 — への適合を検査し、違反 unit を含む応答は reject する
V6 mode:      mode_used = "full" の場合は full 出力契約として検証
              (全 unit が揃っていること。V1〜V4 は適用しないが、**V5 の形式検査は
              full 出力の全 unit にも適用する**)
```

違反時の挙動:

```text
error_code:      KCS-E-ADAPTER-CONTRACT-001
当該応答は unit 1 つも persist しない (全体 reject)
run は failed (retryable — 同一 mode で 1 回のみ再試行 (§5.2 表)。再違反は failed permanent)。
full への自動 fallback は行わない
(fallback は incremental capability 非互換の場合のみ — 正本 [07-adapter-spec.md §8.1](07-adapter-spec.md))
Batch 経由の場合の課金記帳・旧 intent の終端・再投入手順は §5.8 相 3 の reject 終端が正本
(「1 回のみ」も同所の durable 判定に従う)。非 Batch (sync online) 実行も縮退 2 相の
batch_requests 行 (§5.4) を使うため、「1 回のみ」の判定は同じ durable な
contract_violation_count で行う (§5.8 — プロセス内カウントは持たない)
full mode 応答の V5/V6 違反も同様に全体 reject + failed (invalid_input 系は retry しない)
```

内容 (意味) の検証は行わない。Markdown content hash を持たないため ([03-data-model.md §5](03-data-model.md))、
受け入れ検査は構造検証のみを保証範囲とする。

# 4. SQLite Schema (Query Acceleration Layer)

`.kcs/index/sqlite.db`。**真実は objects/、SQLite は再構築可能** (`kcs repair --rebuild-db`)。

## 4.1 chunks

```sql
CREATE TABLE chunks (
  chunk_id TEXT NOT NULL PRIMARY KEY,    -- rowid 表の TEXT PRIMARY KEY は NOT NULL を含意しないため明示
  raw_hash TEXT NOT NULL,
  tool_profile_hash TEXT NOT NULL,
  gen INTEGER NOT NULL,                -- chunk は常に normalized instance 由来のため DEFAULT を持たない
  unit_key TEXT NOT NULL,
  raw_path TEXT NOT NULL,              -- chunk 生成時点の path (表示用)。現在 path は tree_entries join で得る。
                                       -- rebuild 入力 = chunks.jsonl の path (03 §2)
  heading_path TEXT NOT NULL,          -- 見出し未出現は空 ([] 相当)。NULL は許可しない (境界規則 3)
  section_id TEXT,
  byte_start INTEGER NOT NULL,           -- chunk identity (03 §8.1) の必須入力
  byte_end INTEGER NOT NULL,
  text_hash TEXT NOT NULL,
  text TEXT NOT NULL,
  first_seen_commit TEXT,              -- 最初の publication commit (便宜列。時点条件の正本は chunk_publications)
  created_at TEXT NOT NULL
);
CREATE INDEX idx_chunks_ident ON chunks(raw_hash, tool_profile_hash, gen);

CREATE TABLE chunk_publications (      -- publication relation (cache — rebuild 正本は chunks.jsonl の
                                       -- publication event 行 (03 §2)。event 行を欠く旧 store は
                                       -- 親先行 topological walk で再導出: §7 rebuild)
  chunk_id            TEXT NOT NULL,
  introduction_commit TEXT NOT NULL,   -- この chunk が (再) 導入された commit。単一の first_seen_commit では
                                       -- incomparable な複数導入 (merge の side 枝等) を表現できないため多対多
  PRIMARY KEY (chunk_id, introduction_commit)
);                                     -- 時点条件の判定はこの relation を参照 (05 §1.6)

CREATE TABLE index_metadata (          -- 単一行。05 §1.5 index_generation の保存先
  id               INTEGER PRIMARY KEY CHECK (id = 1),
  index_generation TEXT NOT NULL,      -- ULID (rebuild / purge / enrichment finalize / FTS 内容変化 /
                                       --  tombstone lifecycle 更新で更新 — 05 §1.5)
  last_lifecycle_epoch INTEGER NOT NULL DEFAULT 0
                                       -- lifecycle epoch (.kcs/tombstones/lifecycle-epoch — 単調カウンタ、
                                       --  event append ごとに +1) のうち回転へ反映済みの値。
                                       --  counter > この値 = 回転未了 → 書き込み系冒頭の回復で補完。
                                       --  時刻比較は使わない (同一 ms・時計逆行で補完を見逃す)。
                                       --  rebuild 完了 Tx で現 counter 値に初期化する (05 §3.5)
);

CREATE TABLE chunk_config_generations (
  association_rowid INTEGER PRIMARY KEY AUTOINCREMENT,
  chunk_id TEXT NOT NULL,
  chunking_config_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  introduction_commit TEXT NOT NULL,   -- この association が公開された snapshot commit。時点指定検索は
                                       -- association の introduction にも ancestor-or-equal を要求 (05 §1.6)
  UNIQUE(chunk_id, chunking_config_hash, introduction_commit)
                                       -- 3 列 UNIQUE: incomparable な別枝の複数 introduction を行として
                                       -- 保持する (2 列 UNIQUE では第二枝の insert が矛盾する)
);
```

`chunk_id` (PRIMARY KEY) の値は chunk object の `chunk_hash` と同一文字列とする (算出式は [03-data-model.md §8.1](03-data-model.md))。`gen` / `unit_key` は chunk が由来する normalized instance の世代と unit ([03-data-model.md §2.1](03-data-model.md)。`byte_start` / `byte_end` は unit-local)。chunk が属する Markdown 全体の content hash (normalized_hash) は持たない。

**chunk 境界の正準規則** (2026-07-03 確定、step3a §C-1 の決定性論点解消。chunk_hash の入力である heading_path / section_id / span を実装非依存にする):

```text
1. 入力は normalized instance の unit 列 (03 §2.1 の順序)。chunk は unit 境界を跨がない
2. heading 検出は ATX 形式 (行頭 1-6 個の # + 空白) のみ。setext 見出しは heading と見なさない。
   コードフェンス内の # は heading と見なさない
3. heading_path = chunk 先頭位置で有効な ATX 見出しテキストのスタック (階層は # の個数。
   レベル飛びはそのまま積む)。unit 先頭から見出し未出現の間は heading_path = []
4. section_id = heading_path の各要素を slug 化し "/" で結合。slug 規則: NFC 正規化 →
   ASCII 英字は小文字化 → 空白列を "-" に → 英数字・ハイフン・アンダースコア・日本語文字
   (Unicode script property が Hiragana / Katakana / Han の文字 + 長音記号 ー U+30FC・々 U+3005 に
   固定 — 集合の変更は chunking_config_hash の変更として扱う) 以外を除去 → 連続 "-" を 1 つに → 先頭末尾の "-" を除去。
   同一 unit 内の重複 slug は 2 つ目以降に "#2", "#3" を付す (出現順)
5. 分割: 見出し区間が max_chars (03 §11 [chunking]) を超える場合、段落境界 (空行) で
   貪欲に max_chars 以下へ分割する。単一段落が max_chars を超える場合のみ文字位置で
   機械分割する。max_chars と「文字位置」の計数単位 = **Unicode scalar value** (code point) であり、
   機械分割は scalar 境界でのみ行う (UTF-8 byte の途中で切らない。grapheme cluster は考慮しない —
   Unicode 版依存を避け、実装非依存の決定性を優先)。分割片は同一 heading_path / section_id を共有し、
   unit-local の byte_start / byte_end で区別する (chunk identity は span を含むため衝突しない)
```

**chunks 行は append-only**。ファイルの更新・リネーム・削除では既存 chunk 行を削除・変更しない。これが time-travel 検索 (`--at` / `--all-history` / `--include-deleted`、[05-runtime.md §1.6](05-runtime.md)) の実体である。chunk 行を削除する経路は `kcs purge` のみ (対象 raw_hash の chunk 行・FTS エントリ・embeddings を物理削除、[05-runtime.md §3.5](05-runtime.md))。raw / chunk object は GC の削除対象外である ([05-runtime.md §2.6](05-runtime.md))。既存行への UPDATE は `first_seen_commit` の付与のみ許可する。

同じ chunk identity が複数の chunking config で同じ境界を生む場合、`chunks` の 1 行を複製・上書きせず
`chunk_config_generations` に association を追記する。検索の「現行 `chunking_config_hash`」filter は
この relation と join し、cursor は page 1 の最大 `association_rowid` も固定する。append-only
`chunks.jsonl` は同じ chunk_id の別 config association record を保持でき、SQLite rebuild はそこから
この relation を再構築する。

## 4.2 chunk_fts (FTS5 外部 content)

MVP から **外部 content モード** を採用 (整合性保証のため):

```sql
CREATE VIRTUAL TABLE chunk_fts USING fts5(
  text,
  heading_path,
  content='chunks',
  content_rowid='rowid',
  tokenize='trigram'          -- 既定。設定で 'unicode61 remove_diacritics 2' へ切替可
);                            -- (切替時は許可値 enum から DDL を生成する。プレースホルダの
                              --  literal 実行は parse error — 掲載 DDL は常に実行可能形とする)
```

`chunk_id` 列は FTS 側に **持たない** (2026-07-14 実装準拠へ更新 — 旧 spec の `chunk_id UNINDEXED` 列は
廃止)。外部 content モードでは hit の rowid で `chunks` と join でき、chunk_id と metadata は
`chunks` 側から取得する。

trigger で chunks との同期を自動保守:

```sql
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunk_fts(rowid, text, heading_path)
    VALUES (new.rowid, new.text, new.heading_path);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunk_fts(chunk_fts, rowid, text, heading_path)
    VALUES('delete', old.rowid, old.text, old.heading_path);
END;
CREATE TRIGGER chunks_au AFTER UPDATE OF text, heading_path ON chunks BEGIN
  INSERT INTO chunk_fts(chunk_fts, rowid, text, heading_path)
    VALUES('delete', old.rowid, old.text, old.heading_path);
  INSERT INTO chunk_fts(rowid, text, heading_path)
    VALUES (new.rowid, new.text, new.heading_path);
END;
```

`chunks_au` を `UPDATE OF text, heading_path` に限定するのは、`first_seen_commit` の付与 (§4.1 で唯一許可された UPDATE) で FTS が再書き込みされるのを防ぐため。

**Tokenizer**: デフォルト `trigram` (CJK 対応)。英文中心の場合のみ `unicode61 remove_diacritics 2` を選択可。`.kcs/config.toml [search.fts]` で切替 (tokenizer は上記のとおり CREATE 文に固定で埋まるため、切替は FTS の再構築を伴う)。

## 4.3 embeddings (sqlite-vec + metadata)

本節が `embeddings` / `chunk_vec` の **schema 正本** である ([07-adapter-spec.md §5.3](07-adapter-spec.md) は profile — モデル / 次元 / 距離 / modality — の正本)。

```sql
CREATE TABLE embeddings (
  id TEXT NOT NULL PRIMARY KEY,
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
  embedding float[768] distance_metric=cosine
);
```

`chunk_vec` の次元は採用 profile の **768 (MRL 切り詰め) / cosine に固定** する ([07-adapter-spec.md §5.3](07-adapter-spec.md))。保存 vector と query vector はいずれも L2 正規化済みのため、cosine distance の順位は厳密に一致する。

`embeddings` テーブル (メタデータ + vector BLOB) と `chunk_vec` (vec0 virtual table) は、いずれも `objects/` から再構築可能な加速層であり、真実は `objects/` にある (§4 冒頭)。両テーブル間では **`embeddings` テーブルを正** とし、`chunk_vec` は `embeddings` からの導出物として扱う。不整合を検出した場合および `kcs repair --rebuild-db` では、`objects/` → `embeddings` → `chunk_vec` の順に再構築する。`chunk_vec` の導出は **`chunks.text_hash` と `embeddings.target_id` の結合**で行い、同一 `text_hash` を持つ複数 chunk には同じ embedding を複数の `chunk_vec` 行へ展開する (content ベース再利用 §5.5 の裏面)。**結合は現行 tool-lock の embedding profile に限定する** — `(profile_hash, dimensions, distance, modality)` が現行 lock と一致する embedding 行のみ。複数 profile の embedding が正規に並存し得るため、無条件結合は chunk ごとに複数候補を生み `chunk_vec` の PRIMARY KEY と衝突する (rebuild 停止)。chunk ごとに候補が **0 件または 1 件**であることを検証する (0 件 = 未 enrichment — chunk_vec 行を作らず pending として text-only で検索を継続する ([05-runtime.md §1](05-runtime.md)。offline / budget pause 中の rebuild で正常に生じる)。2 件以上のみ corruption として rebuild 停止)。

KCS は Text/Image を分けず **単一マルチモーダル Embedding Adapter** のみを許可する (非 multimodal profile は `KCS-E-EMBED-MODALITY-001` で採用拒否、[03-data-model.md §7](03-data-model.md))。

## 4.4 その他のテーブル / ストアの正本

sqlite.db に存在するのは §4.1〜§4.5 の 8 表 (chunks / chunk_config_generations / chunk_publications /
chunk_fts / embeddings / chunk_vec / tree_entries / index_metadata) のみ (ストア全体の一覧は [03-data-model.md §4.1](03-data-model.md))。

```text
chunks / tree / commit object                         03-data-model.md §8
embeddings / chunk_vec                                本書 §4.3 (profile の正本は 07 §5.3)
tree_entries                                          本書 §4.5 (commit tree の射影 cache)
files / normalization_runs                            SQLite テーブル非採用。正本は .kcs/manifest.json /
                                                      normalized instance manifest (03-data-model.md §8)
tasks                                                 SQLite テーブル非採用。.kcs/tasks.jsonl
                                                      (レコード形式は本書 §5.1)
prepared_units                                        SQLite テーブル非採用。決定論的に再導出する
                                                      論理台帳 (本書 §4.7)
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
  manifest_hash TEXT,                  -- tree schema v2 (03 §8) の射影。v1 tree は NULL (legacy)
  PRIMARY KEY (commit_hash, path)
);
CREATE INDEX idx_tree_entries_ident ON tree_entries(commit_hash, raw_hash, tool_profile_hash, gen);
```

規範:

- tree_entries は tree object の射影 cache。真実は `objects/trees/`。`gen` は tree entry の `normalize.gen` ([03-data-model.md §8](03-data-model.md)) の射影で、tree entry に `gen` 欠落時は 0 と読む。`manifest_hash` は v2 tree entry の射影 (時点条件は `chunk_publications` の introduction の ancestry — [05-runtime.md §1.6](05-runtime.md)。`first_seen_commit` は便宜列)
- **常駐必須は HEAD commit 分のみ**。commit 作成時に新 HEAD 分を挿入する。旧 HEAD 分は cache として残してよい
- `--at <commit>` 検索時、当該 commit 分が無ければ tree object を展開して挿入する。tree は immutable なので展開結果は常に同一
- `kcs repair --rebuild-db` は HEAD 分のみ再構築する (他 commit 分は次回 `--at` 時に再展開)。旧 HEAD 分の掃除は GC (実行系は Phase 4+、[05-runtime.md §2](05-runtime.md)) が担う。GC が tree_entries 行を消しても raw / chunk object は削除しない ([05-runtime.md §2.6](05-runtime.md))

## 4.6 chunk 世代と chunking 設定変更

`[chunking]` 設定 ([03-data-model.md §11](03-data-model.md)) の変更は raw_hash / tool_profile_hash に現れないため、独立した世代判定を行う:

- chunk / embedding 段の最新判定は `(raw_hash, tool_profile_hash, gen, chunking_config_hash)` の一致で行う ([03-data-model.md §5.3](03-data-model.md))。03 §6 の up_to_date 判定 (Markdownize 段) は変更しない
- デフォルト (HEAD) 検索の対象は **現行 chunking_config_hash の chunk のみ**。時点指定 (`--at` / history 系) は **対象 tree の `chunking_config_hash`** の association で絞る — tree v2 が時点 config を保存する意味はここにある (v1 tree は config 未記録のため現行値で代替し、結果に注記する。[05-runtime.md §1.6](05-runtime.md))
- 設定変更を検出したら、次回 `kcs index` で全 normalized instance (履歴分含む) の再 chunk + 再 embedding task を積む。再 chunk はローカル処理で LLM 不要。embedding のみ再課金 (§5.4 budget guardrail の対象)
- 開始前に再生成対象 chunk 数と embedding 概算コストを提示し確認する (`--yes` で省略)
- 旧世代 chunk 行は **削除しない**。Evidence Pointer の chunk_hash 解決 ([08-evidence-pointer-spec.md §6](08-evidence-pointer-spec.md)) 用に残置する (デフォルト検索には出ない。時点指定は対象 tree の config で対象になる — [05-runtime.md §1.6](05-runtime.md))
- 再生成未完了の instance はその間検索から漏れる (index 未完了と同じ扱い。`kcs status` に表示)

## 4.7 prepared_units (論理台帳 — SQLite テーブル非採用)

prepare 結果の台帳は **SQLite に永続化しない** (2026-07-14 実装準拠へ更新 — 旧 `CREATE TABLE
prepared_units` は未実装のまま廃止)。prepare は決定論的 (§2) であり、raw object (CAS) からいつでも
同一結果を再導出できるため、台帳はパイプライン実行時の in-memory 構造 (kcs-pipeline の
`PreparedUnit` 列) として持てば足りる。incremental Markdownize の unit fingerprint 比較 (§3) も、
previous instance の manifest / unit object と、新 raw の再 prepare 結果の突き合わせで行う。

レコードの論理形 (再導出結果の形状契約):

```text
(raw_hash, unit_key)    識別子 (一意)
prepared_hash
unit_type
fingerprint             JSON: { text_hash, perceptual_hash, visual_hash }
order_index             unit の出現順 (03-data-model.md §2.1 の順序)
```

将来 prepare の再実行コストが問題になった場合のみ、この論理形のまま SQLite cache 化してよい
(その場合も喪失許容・再構築可能な cache として扱う — §5.7、[10-operations.md §7.5.3](10-operations.md))。

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
pending → paused → pending                   保留。hold_reason = budget (§5.4) | auth |
                                             tier_b_approval (10-operations.md §1.1)。解除条件 =
                                             理由の解消 (budget は §5.4 の再開規則、tier_b は明示承認)。
                                             rate_limit は paused ではなく pending + next_retry_at で
                                             表現する (§5.3 — 呼出後に判明し Retry-After が解除条件)。
                                             paused は Adapter 未呼出のため AdapterRun には現れない
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
    (§3.1 の発動条件 4 (変化率 < threshold) は失敗 unit 集合に対して評価し、超過時は full で再投入)
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
contract_violation retryable             max_attempts=1 (同一 mode で 1 回のみ再投入 — 出力揺れ対策。
                                         再違反は failed permanent = Adapter バグ。full への自動
                                         fallback はしない: 正本 07 §8.1、capability 非互換のみ §8.4)
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
markdownize = 30.0
embedding = 15.0
summary = 5.0

# .kcs/config.toml — folder cap (任意。この .kcs のタスクのみに適用する追加制限)
[budget]
monthly_usd_cap = 10.0
```

- cap は二層で判定する。**device cap** (`~/.config/kcs/config.toml`、デバイス上の全 `.kcs` の当月合算に適用、既定 $50) が正であり、**folder cap** (`.kcs/config.toml`、その `.kcs` の当月消費のみに適用) は任意の追加制限。folder cap 未設定なら device cap のみが効く
- 判定式: scope S の新規タスクを起動できるのは `ledger(S, 当月) + candidate < folder_cap(S)` **かつ** `ledger(device, 当月) + candidate < device_cap` のとき (= effective cap は両者の残余の min。candidate = 起動しようとするタスク自身の予約額)。**candidate = 0 のタスク (単価 0 のローカル LLM — 下記) は cap 判定の対象外として起動できる** (cap は外部支出の上限であり、超過状態でも無償タスクは封鎖しない)。`per_adapter` の下限は **device 層専用** (folder cap は total のみ — folder 側 `[budget.per_adapter]` は定義しない) で、**第三条件として同様に判定する**: `ledger(device, adapter_kind, 当月) + candidate < per_adapter_cap(adapter_kind)` (設定キー名 = adapter_kind と同一 enum: markdownize / embedding / summary。**enum 外の未知キーは schema error** — [10-operations.md §12.3](10-operations.md))。`ledger(...)` は cost_ledger の当月合算 (estimated 行も usd 非 NULL のため数値として効く — §5.8) + 未終端 batch_requests (state 0/1) の `estimated_usd` 合算 (= 予約)。**判定と相 1 の reservation 作成は同一の `BEGIN IMMEDIATE` Tx で行う** (check-then-act の並行超過を防ぐ — cap 超過なら相 1 を作らない)。**sync online 呼出は縮退 2 相に従う**: reservation は cost_ledger ではなく **batch_requests 行**で行う — 相 1 = 行作成 + `estimated_usd` 予約を cap 判定と同一 Tx で (intent_token = attempt token。§5.8 と同じ状態機械の縮約 — upload / job 相は無い)。呼出後、終端 (成功・billable reject・contract reject) の**確定記帳と state=2/3 を同一 Tx** で行い、**cost_ledger へは終端の確定行のみ**を追記する (cost_ledger は追記台帳のため予約 → 確定の書換えはできない — 予約の実体は batch_requests 側が持つ)。複数 external call を行うタスクは request を直列化し、request ごとに新しい相 1 (submission_seq = MAX+1) → 終端を完了してから次の request を開始する (request 単位の冪等記帳 — 並行 request は作らない。課金済み call の盲目再試行を禁止)。**provider request id は応答受信直後・終端 Tx より前に行の `batch_job_id` へ耐久記録する** (下記 DDL — sync 行の照会キー)。**crash 回収** (書き込み系コマンド冒頭 — §5.8 の回復と同時): 残った state 0/1 の `request_kind='sync'` 行は、`batch_job_id` (provider request id) が記録済みで照会可能なら結果を確定し、未記録・照会不能なら unknown として estimated を確定記帳し state=3 で terminal 化する (過大計上を許容 — 未記帳の過少計上より安全側)。sync 行は §5.8 の job / upload 照合・可視化猶予・回復期限の対象外 (job / upload 相が無い) だが、abandon (同じ intent_token / 4 組指定) は適用できる。**sync 行は provider 側に残骸 (upload / job) を作らないため、全ての終端 Tx (成功・reject・unknown 精算・abandon) で同一 Tx 内に `intent_token` を NULL 化する** — 「NULL 化は残骸掃除の完了時のみ」(§5.8) は batch 行の規則であり、sync では終端 = 掃除完了である (これが無いと「旧 token の消し込み完了後にのみ再投入可」の順序規範と衝突し、同一タスクキーの再投入が恒久停止する)。複数 request の途中 (前 request 終端済み・次 request 未開始) で crash した場合は、終端済み行 (token NULL) への通常の相 1 (新 token・MAX+1) で次の request から再開する。**crash 回収が確定するのは記帳と state のみ** — 照会で得た出力は persist しない (出力が必要なら新しい相 1 で再実行する。出力を persist する経路は相 3 と同じく persist 直前の tombstone 再検査に従う — [05-runtime.md §3.5](05-runtime.md))
- 累積コストは Adapter 報告値 (input/output token × 単価) を `~/.local/share/kcs/cost-ledger.sqlite` (デバイスグローバル 1 個。WAL + busy_timeout — [05-runtime.md §6](05-runtime.md)) に記録する。folder cap の判定はこの ledger の scope 別集計で行う (`.kcs` 内に ledger は置かない。cache/truth 規約上、課金台帳はデバイスローカルの運用データであり `.kcs` の truth ではないが、**再構築不可のため cache でもない** — [03-data-model.md §4.1](03-data-model.md)、schema 変更は in-place migration 側 [10-operations.md §7.5.3](10-operations.md))
- store は 2 表で構成し、**以下の DDL を SQL 正本とする** (旧 3 JSONL + lock 構成は 2026-07-18 に廃止 — §5.8 の 2 相プロトコルは UNIQUE 制約・単一 Tx・ON CONFLICT 冪等という SQLite の保証を前提に監査された機構であり、append-only JSONL では等価の保証を構成できない。[10-operations.md §12.7](10-operations.md) リネーム表):

```sql
CREATE TABLE cost_ledger (               -- 確定・推定課金の追記台帳 (行の UPDATE / DELETE 禁止)
    scope_id          TEXT NOT NULL,
    adapter_kind      TEXT NOT NULL,     -- 'markdownize' | 'embedding' | ...
    input_hash        TEXT NOT NULL,     -- §5.5 のタスク同一性キーと同じ組
    tool_profile_hash TEXT NOT NULL,
    submission_seq    INTEGER NOT NULL,  -- 投入の通算連番。**新しい外部投入の開始 (相 1) ごとに
                                         --  MAX+1 を採番** — 同一 attempt の回復中は不変 (§5.8)
    batch_job_id      TEXT NOT NULL,     -- 値規則: 実 job id。job id 不明の記帳 (期限超・abandon) は
                                         --  当該 intent_token (§5.8 の記帳済み判別の突合キー)。
                                         --  sync 呼出 (Batch 非対応 provider) は provider request id、
                                         --  無ければ当該 attempt の intent_token
    usd               REAL NOT NULL      -- estimated=1 の行は保守的な推定額 (NULL 禁止 — SUM が
        CHECK (usd >= 0 AND               --  負値も禁止 (cap の相殺・過少計上を防ぐ)
               typeof(usd) IN ('integer', 'real')),
                                         --  NULL を無視すると budget 判定が過少 = 安全側の逆になる。
                                         --  typeof 検査: REAL affinity は TEXT 混入を通し SUM が 0.0
                                         --  扱いにする = cap 過少計上のため型も強制する
    estimated         INTEGER NOT NULL DEFAULT 0 CHECK (estimated IN (0, 1)),
    outcome           TEXT NOT NULL      -- DEFAULT を持たない — INSERT での明示を必須にする
        CHECK (outcome IN ('succeeded', 'contract_violation', 'expired', 'abandoned',
                           'submit_rejected', 'purged', 'unknown_settled')),
                                         -- 終端確定行の到達理由 (§5.8 の対応表と同一 Tx で必須記載。
                                         --  DEFAULT 'succeeded' を許すと省略記帳が成功に化け、
                                         --  ON CONFLICT 冪等の下で訂正不能になる)。
                                         --  reset (--reset-violations) 後も違反履歴が台帳に恒久に残る
    month             TEXT NOT NULL      -- 'YYYY-MM' (確定月配賦 — cap 集計キー。書式と月範囲も強制 —
        CHECK (month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'
               AND substr(month, 6, 2) BETWEEN '01' AND '12'),
                                         --  不正書式・00/13〜99 月は当月合算から漏れ cap を過少判定する)
    recorded_at       INTEGER NOT NULL,  -- UTC ミリ秒
    UNIQUE (scope_id, adapter_kind, input_hash, tool_profile_hash, submission_seq)
);
-- 記帳は必ず INSERT ... ON CONFLICT DO NOTHING (再試行・クラッシュ再実行で二重計上しない)。
-- UNIQUE キーが冪等性の実体のため、submission_seq を進めずに別内容を記帳してはならない (§5.8)

CREATE TABLE batch_requests (            -- in-flight Batch intent の正本 (§5.8 の状態機械)
    scope_id          TEXT NOT NULL,
    adapter_kind      TEXT NOT NULL,
    input_hash        TEXT NOT NULL,
    tool_profile_hash TEXT NOT NULL,
    state             INTEGER NOT NULL DEFAULT 0
        CHECK (state IN (0, 1, 2, 3)),   -- 0=投入前/中 1=job 作成済み 2=完了 3=terminal error
    request_kind      TEXT NOT NULL DEFAULT 'batch'
        CHECK (request_kind IN ('batch', 'sync')),
                                         -- 縮退 2 相 (sync online) 行の判別 (§5.4)。回復の適用規則を
                                         --  分岐する — sync 行は job/upload 照合・猶予・期限の対象外
    intent_token      TEXT,              -- UUIDv7 (相 1 で発行)。NULL 化は残骸掃除の完了時のみ (§5.8)
    upload_id         TEXT,              -- 相 2a 成功直後に記録
    batch_job_id      TEXT,              -- 相 2b 成功後・または回復の found 自己記述化で記録。
                                         --  sync 行では provider request id (応答受信直後に記録 — §5.4)
    provider_scope_id TEXT,              -- 相 2a の upload 直前に記録 (§5.8 手順 2 — 非 NULL は
                                         --  「相 2a 着手」の印)。相 1 の再発行で NULL へ戻る (手順 1)
    job_create_started_at INTEGER,       -- UTC ミリ秒。可視化猶予・回復期限の起点 (§5.8)
    submission_seq    INTEGER NOT NULL DEFAULT 0,
                                         -- 行 (再) 作成時は cost_ledger 同キーの MAX(submission_seq)
                                         --  から継承する (通算連番の高水位の正本は ledger — 0 から
                                         --  数え直すと既存記帳と UNIQUE 衝突する)
    attempts          INTEGER NOT NULL DEFAULT 0,
    contract_violation_count INTEGER NOT NULL DEFAULT 0,
                                         -- reject 終端 Tx (§5.8 相 3) で increment。相 1 の NULL 戻しの
                                         --  対象外 — 「同一 mode で 1 回のみ」の durable 判定源
    estimated_usd     REAL NOT NULL      -- budget 予約額 (§5.4 判定式)。相 1 作成時に保守見積を必須設定
        CHECK (estimated_usd >= 0 AND    --  (NULL/負を許すと SUM が予約を取りこぼし cap を過少判定。
               typeof(estimated_usd) IN ('integer', 'real')),
                                         --   typeof 検査は cost_ledger.usd と同じ理由)
    error             TEXT,              -- 'submit_rejected' | 'expired' | 'abandoned' | ...
                                         --  拒否課金 provider (07 §5.7 条件 6) の submit_rejected は
                                         --  terminal 化と同一 Tx で estimated 記帳 (Adapter 返却の
                                         --  billable_units / estimated_usd、無ければ行の estimated_usd
                                         --  — ledger 0 行のままの terminal 化を許さない)
    completed_at      INTEGER,           -- state を 2/3 へ確定する全ての UPDATE で同時に書く。
                                         --  未終端は NULL (status の滞留検知に使う)
    created_at        INTEGER NOT NULL,
    PRIMARY KEY (scope_id, adapter_kind, input_hash, tool_profile_hash)
) WITHOUT ROWID;
```
- いずれかの cap 超過時、走行中タスクは完了させ、新規タスクは `paused` 状態へ。`kcs status` は超過した cap の種別 (`device` | `folder`) と scope を表示する
- `kcs batch resume --override-budget` で明示的に再開可能 (当月の device cap / folder cap の両方を無視して再開する)。override は markdownize / embedding **両 Adapter の budget 判定に対称に**効く。override 無しの `kcs batch resume` は budget 超過 pause タスクを markdownize / embedding いずれも据え置き (sticky)、他要因の pause のみ再開する
- ローカル LLM 利用時は単価 0 として記録 (= cap に効かない)

**resume / retry / reindex が駆動する enrichment**: `kcs batch resume` / `kcs batch retry` は online markdownize タスクに加え、**embedding enrichment パスも駆動する** (embedding タスクは現行世代の live chunk 集合から DB 駆動で再検出される。opt-in は Adapter 単位 = embedding は自身の承認行を見る、[07-adapter-spec.md §3](07-adapter-spec.md))。同様に `kcs reindex --force` / `kcs repair --rebuild-db` は rebuild 後に enrichment を実行し、新世代 chunk の embedding を追随させる (§4.6)。offline なら embedding タスクを enqueue のみとし `index_status` ([05-runtime.md §1.7](05-runtime.md)) に pending として可視化する。retry の失敗タスクは backoff / retry 予算 (§5.3) を尊重し、`next_retry_at` 未来または非 retryable の embedding タスクを持つ chunk は enrichment 対象から除外する。**`kcs batch resume` / `retry` / `kcs reindex --force` がオンライン成果 (normalized / chunk) を finalize したときも、`kcs index` 完了時と同じ auto snapshot ([05-runtime.md §8.1](05-runtime.md)) を作成する** — derived 成果の変化は tree entry の `normalize.manifest_hash` / tree の `chunking_config_hash` / tree の `chunk_set_hash` (公開 chunk 集合 — chunk のみの後着でも変わる) を変えるため (tree schema v2/v3 — [03-data-model.md §8](03-data-model.md))、tree_hash が変わり通常の no-op 規則のまま commit が生まれる。これが無いと完成した成果が次回 `kcs index` まで検索に現れない (chunk の検索対象化は auto snapshot 後 — [05-runtime.md §1.6](05-runtime.md))

## 5.5 冪等性

`(input_hash, tool_profile_hash) → output_ref` 一致なら done として短絡 (キャッシュヒット)。これは **first-instance-wins** ([03-data-model.md §6](03-data-model.md), [09-mvp-scope.md §設計宿題](09-mvp-scope.md))。LLM API の二重課金防止は二段構え: sync 呼出は provider が idempotency key を提供する場合にそれを要求し、**Batch 投入 (job 作成に idempotency key の無い provider が現実) は §5.8 の 2 相プロトコルを正本とする**。

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
3  retryable な失敗が残っている (部分成功を含む — [06-cli-spec.md §7](06-cli-spec.md))
4  全タスク failed permanent
5  auth_error がある
6  budget_exceeded により paused
7  user 中断 (SIGINT/SIGTERM)
```

## 5.7 Resume と Repair

- `kcs batch resume`: 中断状態 (running stale, pending) を再開
- `kcs repair --rebuild-db`: SQLite を objects/ から再構築する (SQLite に存在するのは §4.1〜§4.5 の 8 表のみ。再構築完了時は index_metadata へ新 index_generation ULID を採番し、**同じ完了 Tx で `last_lifecycle_epoch` を現在の lifecycle-epoch counter 値に初期化する** (DEFAULT 0 のままでは全 lifecycle record が回転未了と誤検出され、全走査と不要回転が走る — [05-runtime.md §3.5](05-runtime.md)) — [05-runtime.md §1.5](05-runtime.md)。**publication / association introduction の再導出は chunks.jsonl を正本とする**: 作成行の first_seen_commit + publication event 行 (03 §2 — truth) を読み取って復元し、tree の chunk_set_hash は照合のみに使う。event 行を欠く旧 store は fallback として全 commit を親先行 topological order で走査し、chunk / config association ごとに「既採用 introduction のいずれの子孫でもない commit」のみを introduction として追加する (結果は ancestor-minimal 集合で walk 順序に依存しない)。**backfill は行わない** (pre-release — 既存 dev store は rebuild-db が ledger / fallback から再導出する)。生存する creation 行 / chunk object を持たない、**または introduction commit が不在・ref から到達不能**な publication event 行は無視する (dangling — [05-runtime.md §8.1](05-runtime.md) の耐久順序で正常に生じ、次回 finalize が冪等に再 append する)。
  以下の normalization_runs / prepared_units は SQLite テーブルではなく、manifest / 再 prepare から
  導出される**状態**を指す — [03-data-model.md §8](03-data-model.md) / §4.7)。復元範囲は次の通り:

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

## 5.8 Online Batch 投入の 2 相プロトコル (課金・クラッシュ安全)

Batch 型 online Adapter ([07-adapter-spec.md §5.7](07-adapter-spec.md)) は「upload → job 作成 →
collect」の各段の間にクラッシュ窓があり、provider 側に課金・機密の実体 (upload・job) が残る。
§5.5 の done 短絡はローカル出力の重複を防ぐだけで、**provider 側に作成済みの job を KCS が知らない
状態 (無記録の in-flight)** は防げない。二重課金防止は次の 2 相プロトコルを正本とする (設計出典:
旧 `research/folder-history-sqlite-design.md` §9 の多エンジン監査 r8〜r20 で固めた機構の KCS 適応 —
2026-07-18 撤去、git 履歴で参照可。原則 = **外部に副作用を起こす前に意図を耐久記録する**。課金の
記録喪失は有界だが、無記録の in-flight job は無制限に残る)。

**記録の正本**: `cost-ledger.sqlite` の `batch_requests` 行 (DDL は §5.4 が SQL 正本)。tasks.jsonl は
喪失許容 (§5.7) のため、in-flight Batch の回復は batch_requests だけで可能でなければならない。各段の
記録は同 DB の単一 Tx で行う。cost-ledger.sqlite ごと喪失した場合の最終回収線は、provider job 一覧の
metadata から intent_token 規約に一致する job を全走査することである (帰属は metadata の (scope_id, adapter_kind, input_hash, tool_profile_hash) と出力 JSONL の custom_id が担う — 新規 UUIDv7 の token 単独では帰属できない)。tasks.jsonl の task 記述子 (mode / unit_keys / output_ref) は喪失しうるが、**確定先と対象 unit は決定論的に再導出できる**: 出力の取り込み先はタスクキー (input_hash = raw、tool_profile_hash) と gen 規則から、対象 unit は provider 出力 JSONL の custom_id (= unit_key) から復元し (**失敗 unit は出力に現れない — 期待 unit 集合は prepared units (raw から決定論的に再導出) との差集合で判定する**)、mode が不明な場合は full として扱う (§5.7 の安全側規定と同型)。

手順 (1 job 単位):

1. **相 1 — intent 記録**: batch_requests 行を INSERT / UPDATE する (state=0、intent_token = **新規
   UUIDv7** — 時刻成分を回復期限の起点に使う、estimated_usd = 予約額)。再投入 (retry /
   `kcs reindex --force`) で相 1 を再発行する場合、**同じ UPDATE で upload_id / batch_job_id /
   job_create_started_at / provider_scope_id / error / completed_at を NULL へ戻す** (残存させると
   下記の照合・猶予起点が旧 attempt の値で誤判定する)。**submission_seq はこの相 1 で必ず
   MAX + 1 へ採番する** (基準 = cost_ledger 同キーの MAX と自行現値の大きい方。同一 attempt の
   回復・再開では変えない。採番を怠ると、次の実課金記帳が旧 attempt の seq と UNIQUE 衝突して
   ON CONFLICT DO NOTHING に黙って吸収される — 行再作成時も同じ規則)
2. **相 2a — upload**: upload の**直前に `provider_scope_id` を行へ記録する** (これから呼び出す
   client instance から取得。相 2b まで遅らせると upload 後のクラッシュで残骸の存在する scope を
   再特定できない)。入力・中間ファイル (JSONL 等) の filename に intent_token を埋め込んで upload し、
   **成功直後に upload_id を行へ記録**する (job 作成が失敗しても残骸の handle を失わない)
3. **相 2b — job 作成**: 呼出の**直前**に `job_create_started_at = now` を**単独の小 Tx**で行へ記録する
   (`provider_scope_id` は相 2a で記録済み — **job 作成は同一 client instance で行い、記録後に設定を
   再読みしない。現 instance の scope が記録値と一致しない場合は呼び出さず、旧 upload を掃除して
   相 2a からやり直す** — [07-adapter-spec.md §5.7](07-adapter-spec.md))。job metadata に
   **intent_token と (scope_id, adapter_kind, input_hash, tool_profile_hash)** を埋め込んで作成 →
   成功後に batch_job_id と state=1 を記録する
4. **相 3 — collect**: 出力の取得・persist 後、確定課金の cost_ledger 記帳と state=2 + completed_at を
   **同一 Tx** で行い、upload を削除する (**404 = 削除成功**として扱う。削除失敗・クラッシュは次回回復が
   再試行し、**全削除の完了をもって intent_token を NULL 化**する)。
   **persist 直前に対象 raw の tombstone を再検査する** — purge 済みなら出力を破棄し、下記の reject 終端と
   同形 (error='purged') で閉じる (削除済み派生物を再 persist しない — [05-runtime.md §3.5](05-runtime.md))。
   **出力が受け入れ検査 (§3.2) で reject された場合 (contract_violation) も persist しない**: 同一 Tx で
   確定課金 (provider 報告値) の記帳 + `state=3`・`error='contract_violation'`・completed_at + upload 掃除を
   行い、attempts を耐久更新する。§3.2 の「同一 mode で 1 回のみ再試行」は**この終端 Tx の完了後に**、
   新 intent_token・新 submission_seq の相 1 として開始する (旧 attempt を state=1 のまま放置して
   再 collect ループに入らない・記帳を落とさない)。再投入の mode は原則同一 — tasks.jsonl 喪失で
   mode が復元不能な場合は full で 1 回 (§5.7 の安全側規定と同型)。**「1 回のみ」の判定は durable**:
   reject 終端 Tx で `contract_violation_count` を increment する (相 1 の NULL 戻しの対象外)。
   再投入できるのは count == 1 のときだけで、count >= 2 は failed permanent
   (tasks.jsonl 喪失後もこの判定は batch_requests から回復できる。error 列は最新状態の表示であり
   判定源にしない — 相 1 が NULL へ戻すため)。count は**タスクキー単位の通算**であり mode 別に
   数えない (mode 切替後の違反も加算)。検証済み Adapter 更新後の脱出路として
   `kcs batch retry --reset-violations <selector>` (確認プロンプト必須) が count を 0 に戻す。
   **selector は abandon と同形** (intent_token または 4 組タスクキー — 曖昧な指定は拒否して
   token を要求。**terminal な sync 行は intent_token が NULL 化済みのため 4 組キーで指定する**)。**reset が変えるのは count のみ** — attempts・submission_seq・cost_ledger は
   不変で、reset 後の再投入は旧 attempt の残骸掃除完了後に新 intent_token・新 submission_seq の
   相 1 として開始する (順序規範と同型)。違反の監査履歴は cost-ledger の記帳行に残る
   (**各終端確定行の `outcome` 列** — §5.4 DDL。reset は台帳を書き換えない)。provider が job の **expired** を報告した場合も
   reject 終端と同形: estimated を確定記帳 + state=3 (error='expired') + 掃除。expired 起因の
   再投入は通常の retry 予算に従い、contract_violation_count は増やさない

**記帳の冪等性**: cost_ledger への記帳は `INSERT ... ON CONFLICT DO NOTHING` (§5.4 の UNIQUE が実体)。
記帳前の「記帳済み判別」は同一タスクキー × **batch_job_id IN (発見 job id, 当該 intent_token)** の
既存行で行う (token キーで estimated 記帳 → 後日 job id で確定、の順で同一 job が 2 行にならない)。
job id 不明の記帳 (期限超・abandon) は **submission_seq を +1 へ行 UPDATE し、その新値で token キー・
usd = 行の estimated_usd (保守推定額 — NULL 禁止) の estimated 行を記帳する** (seq 現値のまま記帳すると、次の正規 close が同じ seq を計算して
UNIQUE 衝突し、実課金が DO NOTHING に黙って吸収される)。この +1 は「同一 attempt の回復中は seq 不変」
と矛盾しない — 期限超の +1 は直後の載せ直し (= 新 attempt の開始) の採番を兼ね、abandon の +1 は最終
attempt の終端採番である (どちらも当該 attempt の「回復の再試行」ではない)。**estimated 行は当該 attempt の最終記録であり、
後日 job が確認できても書き換え・確定し直しはしない** (UPDATE 禁止と整合。二重計上は記帳済み判別が
防ぎ、実額との差は既知の有界誤差として受容する)。

**outcome の対応 (各終端 Tx の INSERT で明示必須 — 省略は実装エラー、§5.4 DDL は DEFAULT を持たない)**:
正常完了 = `succeeded` / §3.2 reject 終端 = `contract_violation` / expired 終端 = `expired` /
abandon = `abandoned` / 拒否課金 provider の submit 拒否 = `submit_rejected` / purge 起因の
terminal 化 (error='purged') = `purged` / 回復期限超過・照会不能の estimated 確定 = `unknown_settled`。

**記帳値の事前検証**: Adapter 報告値 (usd / unit 数) は INSERT 前に有限・非負の数値であることを
検証し、違反は §3.2 の contract violation と同経路で reject 終端する (KCS-E-ADAPTER-CONTRACT-001)。
**このとき確定記帳には provider 報告値を使わない** — 行の `estimated_usd` を `estimated=1`・
`outcome='contract_violation'` で記帳して同一 Tx で terminal 化する (不正値は CHECK を通らず
Tx を閉じられないため — 報告値が有効な場合のみ provider 値で記帳する)。
DDL の CHECK は最終防衛線であり、**CHECK 違反で Tx が失敗した場合は実装エラー
`KCS-E-STORE-CONSTRAINT-001` (permanent — `ON CONFLICT DO NOTHING` には吸収されず、同じ値での
再試行はループするだけのため再試行しない)** ([10-operations.md §12.1](10-operations.md) STORE domain)。

**回復** (書き込み系 batch コマンド — `kcs index` / `kcs batch resume` / `kcs batch retry` /
`kcs batch abandon` — の冒頭。**これらと `kcs reindex` は `.kcs/.lock` を取得する書き込み系であり
([05-runtime.md §6](05-runtime.md))、相 1〜2b の遷移・token の発行も lock 保持下で行う** — 並行する
resume/retry が同一行へ別 token を書くと、先行 job が無記録 in-flight になる。未終端の行 (state 0/1) と
intent_token 非 NULL の終端行 (= 残骸掃除未完) を三値で照合する。**`request_kind='sync'` の行は
job / upload 照合の対象外** — §5.4 の crash 回収で終端化する。以下は batch 行の規則。回復の照会・
出力取得・upload 掃除は既存 request に対する受信・掃除であり**新規送信に当たらない — network
opt-in / `--online` なしで実行できる** ([07-adapter-spec.md §3](07-adapter-spec.md))):

- **found** (job 取得/一覧で intent_token 一致): 追跡を続行し相 3 へ。batch_job_id 未記録なら発見値を
  行へ書く (自己記述化 — 以後この行は token 照合の対象から外れる)
- **confirmed-absent**: 「不在」と断定できるのは、**記録済み provider_scope_id と同一 scope での
  全ページ走査済み一覧**に無く、かつ**可視化猶予 (既定 10 分)** を経過したときのみ (部分応答・別 scope の
  空応答は不在の証明にならない)。**相 2b 未着手 (job_create_started_at IS NULL) の行は job 一覧照合の
  対象にしない** — job 不存在は記録から確定している。ただし **provider_scope_id 非 NULL (= 相 2a 着手)
  の行は、記録済み scope の `list_uploads` を token で照合し、発見した upload の削除 (404 含む) または
  採用 (再利用) を完了してから**、token 時刻起点の猶予経過で再投入してよい (upload 一覧にも可視化猶予を
  適用。怠ると upload_id 記録前クラッシュの残骸が、新 token への置換で恒久に発見不能になる)
- **unknown** (照会失敗・scope 不一致・部分応答): 何も変更せず保持し、次回再試行する。**回復期限**
  (max(intent_token 時刻, job_create_started_at) + 既定 48h、config で変更可) を超えたら「作成されたが
  確認不能」として **estimated 記帳** (上記の seq+1 行 UPDATE + token キー + usd = 推定額) を冪等に行ってから再投入する
  (記録喪失より過大計上を許容 — budget 判定は安全側に倒れる)
- **恒久 unknown** (資格情報喪失等) の行は `kcs status` に **stalled** として表示し (表示には
  intent_token を含める)、`kcs batch abandon` ([06-cli-spec.md §1](06-cli-spec.md) — **指定子は
  intent_token または (scope, adapter, input_hash, tool_profile_hash) の 4 組タスクキー** — 3 組では
  同一 input の別 profile 行と曖昧になる。曖昧な指定は拒否して token を要求する。tasks.jsonl の task_id
  は喪失許容の識別子であり、正本 batch_requests 行を指す手段にならない) を脱出路とする: ユーザー確認で estimated
  記帳 + state=3 (error='abandoned') + completed_at。**intent_token は残骸掃除の完了まで NULL 化しない**
  (intent_token 埋込 filename が upload 残骸の唯一の発見キーであるため、先に消すと掃除が残骸を発見
  できず provider TTL まで機密が残留する。掃除の完了 (404 含む) が NULL 化の条件。恒久に掃除できない
  場合は既知の残余として表示し続ける)

**残骸掃除**: terminal な task の upload (upload_id 記録分 + intent_token 埋込 filename の一覧照合分) を
削除する。abandon 済み task は照合・記帳を行わず掃除のみ行う。

**順序規範**: 明示 retry / `kcs reindex --force` が terminal task を再投入する場合、**旧 intent_token の
照合・記帳・消し込みを完了してから**、retry 予算のリセットと新しい相 1 を行う (逆順だと旧 attempt の
発見・記帳が新 attempt の予算・記録を汚す)。

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
