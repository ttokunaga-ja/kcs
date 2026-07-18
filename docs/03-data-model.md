# 03 Data Model

統合元: 旧 `research/git_kcs.md` (CAS / DAG) + 旧 `research/kcs.md` (.kcs layout) + 旧 `research/hash.md` (identity) + 旧 `research/read_only.md` (write boundary)。いずれも正本ではなく、2026-07-18 に docs から撤去 (経緯は git 履歴で参照可)。

---

# 1. 概念モデル — CAS + Snapshot DAG

KCS は Git inspired な content-addressed store と snapshot DAG を、ローカルファイル全体に拡張したアーカイブ。

```
Object 種別:
  raw          原本ファイルバイト列
  prepared     Markdownize 前の中間表現 (page image, sheet etc.)
  image        文書内 embedded image (Markdownize 時に抽出。type は予約済み、実装は Step 2
               [09-mvp-scope.md §3.1](09-mvp-scope.md))
  manifest     normalized instance manifest の確定版 (canonical JCS bytes — §2.1。tree v2/v3 の
               normalize.manifest_hash が指す)
  toollock     tool-lock.json の確定版 (canonical JCS bytes — §5.2。commit の tool_lock_hash が指す)
  normalized_unit  unit 単位の Markdown (read-only artifact, content hash 不採用)。
                   normalized の正本 (§2.1)
  chunk        normalized から見出し単位で切り出し
  embedding    chunk のベクトル表現
  tree         path → object_hash のスナップショット
  commit       tree + parents + metadata
```

raw / prepared / image / chunk / embedding / manifest / toollock / tree / commit は **CAS object** として `objects/<type>/ab/cd/<digest64>` に保存。hash の算出は object 種別ごとに §8.1 で規定する: raw / prepared / image は**バイト列そのものの content hash**、manifest / toollock / tree / commit は **canonical JSON 保存バイト列の content hash** (manifest は §2.1、toollock は §5.2 の JCS bytes)、chunk / embedding は **identity タプルから導出する identity hash**。normalized_unit は **path-named** で `objects/normalized_units/ab/cd/<raw64>.<tool64>.g<gen>/` 配下に保存する (content hash 不採用、§5。詳細は §2.1)。ファイル全文の normalized Markdown は unit を決定論的に結合した **view (再生成可能な cache)** であり、正本ではない。

# 2. .kcs 物理レイアウト

```
.kcs/
  HEAD
  config.toml         folder-scope の設定 (ignore, chunking, search, budget)
  scope.json          scope_id (init 時採番の ULID、以後不変・export/import でも保持) と
                      このフォルダ自身・子 .kcs リンク (旧称 folder.json は廃止)
  tool-lock.json      Adapter capability 記録 (cmd/url/auth は含めない)
  manifest.json       working/index state (永続的真実は tree/commit object)
  objects/
    raw/ab/cd/<raw64>
    prepared/ab/cd/<prepared64>
    images/ab/cd/<image64>          # 文書内 embedded image (type 予約済み、実装 Step 2。
                                    # media_type は unit metadata に記録)
    normalized_units/ab/cd/<raw64>.<tool64>.g<gen>/
      manifest.json                    # 順序付き unit 一覧 + unit status (正本, §2.1)
      <unit_ref>.json                  # unit object (unit_ref = base16(sha256(unit_key))[0:16])
    normalized/ab/cd/<raw64>.<tool64>.g<gen>.md   # 全文 view (cache, 再生成可能)
    manifests/ab/cd/<manifest64>    # manifest の immutable 確定版 (canonical JCS bytes、§2.1。
                                    # tree v2 の normalize.manifest_hash が指す — §8)
    toollocks/ab/cd/<toollock64>    # tool-lock の immutable 確定版 (canonical JCS bytes、§5.2。
                                    # commit の tool_lock_hash が指す)
    chunks/ab/cd/<chunk64>
    embeddings/ab/cd/<embedding64>
    trees/ab/cd/<tree64>
    commits/ab/cd/<commit64>
  refs/
    heads/main
    tags-v1/tag-<digest64>          # canonical: digest64 = sha256(NFC + Unicode lowercase の論理 tag 名)
    tags/<logical-name>             # legacy Unix raw-name refs (read-only compatibility)
  tombstones/ab/cd/<raw64>      purge の tombstone lifecycle 記録 (raw_hash ごとの append-only events[] —
                                purged / retired。active 判定 = 末尾 event。05-runtime.md §3.5。CAS object ではない)
  purge/epoch         purge の ABA barrier (単調カウンタ — 05-runtime.md §3.5。欠落 = 読取 fail-closed)
  tasks.jsonl         batch タスクストア (04-pipeline.md §5.1。append-only の運用データ、SQLite 非採用)
  chunks.jsonl        chunk association ledger (**truth** — chunk object が持たない世代 association の正本。
                      作成行 = {chunk_id, chunking_config_hash, created_at, first_seen_commit, path}。
                      path = chunk 生成時点の path (SQLite chunks.raw_path の rebuild 入力)。
                      **publication event 行** = {event:"publication", chunk_id, chunking_config_hash,
                      introduction_commit} — 初回以外の追加 introduction (incomparable な別枝での公開、
                      association の後発公開) を auto snapshot 時に append する。publication relation
                      (04 §4.1 cache) の rebuild 正本はこの ledger (digest は照合のみ)。append-only、
                      SQLite rebuild の入力 — 04-pipeline.md §4.1/§4.6、本書 §8)
  index/
    sqlite.db         FTS5 + sqlite-vec (query acceleration layer; 真実は objects/)
  logs/
    access.jsonl
  packs/              v2+ (delta compression, MVP 対象外)
```

`<raw64>` / `<tool64>` / `<digest64>` 等は、対応する論理 hash
`sha256:<64 lowercase hex>` から `sha256:` を除いた **64 文字の小文字 hex digest** である。
物理ファイル名とディレクトリ名にはこの digest-only 表現を使い、`:` を含めない。JSON、SQLite、
refs、CLI 出力、Evidence URI 等で扱う論理 hash は従来どおり `sha256:<64 lowercase hex>` のままであり、
object identity と hash 算出規約は変わらない。

**旧物理パスとの互換性と移行**:

- 新しく物理 object、normalized instance/view、tombstone を作成する場合は上記の digest-only 名を使う
- 旧 Unix store にある `sha256:<64hex>` を leaf または basename 要素に含む物理パスは、検証付きの
  compatibility fallback として読み取る。CAS object は要求された論理 hash と内容/identity hash を、
  normalized は manifest の `(raw_hash, tool_profile_hash, gen)` を、tombstone はレコード内の
  `raw_hash` を照合してから受け入れる
- canonical path と legacy path の両方が存在する場合は両方を検証する。いずれかが期待値と一致しない、
  または同一 identity に対して内容が競合する場合は store corruption として fail closed する
- 要求内容と完全一致する検証済み legacy 表現はその場で再利用し、通常の read/index を契機に
  canonical path へ copy、rename、rewrite しない。normalized の同一 gen を更新する既存の partial retry
  だけは、選択済みの legacy layout 内で instance/view を置き換えられるが、canonical への eager migration
  は行わない。したがって事前の一括移行は不要であり、既存 store は段階的に利用し続けられる

tag の新規物理 leaf は上記の固定 ASCII hash 形式を使う。論理 tag 名は OS 非依存の portable
leaf 規則 (Windows 予約名、`<>:"/\\|?*`、control、末尾 dot/space を禁止) を満たす必要があり、
NFC 正規化 + Unicode lowercase が同じ名前は case-insensitive collision として同一 slot を占める。
`HEAD` の case variant は論理 tag 名として予約する。canonical ref は legacy namespace と分離した
`refs/tags-v1/tag-<digest64>` に置くため、`tag-<digest64>` に見える旧 raw tag も別の canonical ref と
誤認せず、その論理名のまま読める。旧 Unix store の `refs/tags/<name>` は bounded・hash 検証付き
fallback で読み、canonical と legacy
が併存するときは全表現が同じ commit を指す場合だけ受理する。履歴 tree 内の `path` は論理名なので、
Windows で物理 leaf にできない既存 Unix 名も read/inspect は可能とし、restore 等の物理化直前に
対象 OS の規則を別途検証する。

**format_version**: 旧称 `VERSION 0.1.0` (旧 research/kcs.md) は `kcs_format_version` に統一。semver は [10-operations.md §12.5](10-operations.md) 参照。**保存場所 = `.kcs/scope.json` の `kcs_format_version` フィールド** (init 時に記録し migration でのみ更新。読めない・欠落した store は旧版とみなし read-only + migration 誘導 — 互換判定の入力)。

## 2.1 normalized instance と全文 view

**normalized の正本は unit object 群** ([04-pipeline.md §2](04-pipeline.md))。1 つの
`(raw_hash, tool_profile_hash, gen)` の組を **normalized instance** と呼び、
`objects/normalized_units/ab/cd/<raw64>.<tool64>.g<gen>/` ディレクトリ全体で表現する。

manifest schema:

```json
{
  "raw_hash": "sha256:abc...",
  "tool_profile_hash": "sha256:tool1...",
  "gen": 0,
  "parent_gen": null,
  "parent_instance": null,
  "run_id": "run_01H...",
  "units": [
    {
      "order": 0,
      "unit_key": "page:1",
      "unit_ref": "3f2a9c0d1b4e5f60",
      "unit_type": "page",
      "status": "done",
      "prepared_hash": "sha256:...",
      "error_kind": null
    },
    {
      "order": 56,
      "unit_key": "page:57",
      "unit_ref": "9c1b7788aa02c3d4",
      "unit_type": "page",
      "status": "failed",
      "prepared_hash": "sha256:...",
      "error_kind": "invalid_input"
    }
  ],
  "generated_at": "2026-04-25T12:00:00Z"
}
```

unit object schema (`<unit_ref>.json`):

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
  "metadata": {
    "page": 12,
    "bbox_annotations": []
  },
  "reused_from": null,
  "generated_at": "2026-04-25T12:00:00Z"
}
```

`reused_from` は unit_mapping ([04-pipeline.md §2.2](04-pipeline.md)) による再利用の provenance:
`{ "raw_hash": "sha256:old...", "gen": 0, "unit_key": "page:11" }`。再利用時は unit object 本体を
新 instance へ **複製** する (per-.kcs 重複容認、§9)。
`metadata` は optional (旧 object は `{}` と読む) で、page/bbox/confidence と Step 4 の bounded
`bbox_annotations` を保持する。検索用 annotation block は同じ unit の `markdown` にも決定論的に
materialize されるため、chunk span と Evidence 解決元がずれない。

不変条件:

- unit object は read-only artifact。書き換え・削除しない (purge を除く)
- manifest の `units[].status` の遷移は `failed → done` の一方向のみ (部分失敗の再開、§6)。
  done unit の差し替えは新 gen 作成のみ (`kcs reindex --force`、または prepared_hash 変化起因の
  自動 gen+1 — 下記 gen 段落の例外)
- **manifest の各確定版は immutable object として保存する**: manifest の finalize (初回確定と、partial retry で
  `failed → done` を反映した各確定) のたびに、canonical JCS bytes を `objects/manifests/ab/cd/<manifest64>` へ
  content-addressed で書く (post-write verify 対象)。path-named `manifest.json` は**最新版の作業コピー**であり、
  過去版の解決は manifest object のみが担う。tree entry の `normalize.manifest_hash` (§8) は常に対応する
  manifest object を指すため、same-gen partial retry で作業コピーが更新された後も、過去 commit 時点の
  unit 完成状態を正確に列挙・検証できる (fsck の照合 = [10-operations.md §7.5.1](10-operations.md))

**gen (generation)**: 同一 `(raw_hash, tool_profile_hash)` に対する instance の世代番号 (0 起点の整数)。
通常は `g0` のみ存在する。`gen = 現最大 + 1` の新 instance を作れるのは `kcs reindex --force` と、
**prepare profile / renderer 変更による `prepared_hash` 変化が駆動する再 Markdownize** (§6 — first-instance-wins の
第二の合法経路。オンライン課金を伴うため 04 §4.6 と同型の確認プロンプト + budget guardrail の対象) だけであり、
既存 instance は保全する ([07-adapter-spec.md §9](07-adapter-spec.md))。identity はあくまで
`(raw_hash, tool_profile_hash)` であり、gen は同一 identity 配下の instance の区別にのみ使う。
**normalized_hash の代替ではない** (§5: Markdown の content hash は計算・保存・比較しない)。
新規参照 (新規 commit の tree entry / 新規 chunk) は常に最新 gen を使う。

**全文 view**: `objects/normalized/ab/cd/<raw64>.<tool64>.g<gen>.md` は
unit を決定論的に結合した **再生成可能な cache** であり、正本ではない。組み立て規則:

1. manifest.units を `order` 昇順に走査する
2. `status = done` の unit は、その `markdown` から末尾の連続する改行を除去した文字列を採用する
3. `status = failed` の unit は、固定文字列 `<!-- KCS-MISSING-UNIT <unit_key> <error_kind> -->` を採用する
4. 採用した文字列を `"\n\n"` で結合し、末尾に `"\n"` を 1 つ付す — これが view 本文
5. §10 のヘッダコメントを本文の前に付す。chunk の byte offset は **unit-local** (当該 unit の
   `markdown` 本文 UTF-8 bytes 先頭を 0 とする byte span、§8.1) であり、全文 view 上の位置・ヘッダ・結合順は
   chunk identity に影響しない

view の破損・喪失・直接編集は `kcs repair` による再生成で解消する。up_to_date 判定 (§6) に
view の存在は使わない。

# 3. スコープ境界 (重要)

各 `.kcs` が管理するのは **その `.kcs` が配置されたフォルダ直下のファイルのみ** である。この規則は次の 3 点で一意に定まる:

1. 管理対象は scope フォルダ **直下** のファイルに限る。サブフォルダ配下のファイルは、そのサブフォルダに `.kcs` が存在するか否かに関わらず、親 `.kcs` の管理対象に **ならない** (再帰包含は行わない)。
2. サブフォルダは常に独立スコープの候補である。対象ファイルを含むサブフォルダには `kcs index` が子 `.kcs` を生成する ([06-cli-spec.md §1](06-cli-spec.md), [10-operations.md §4](10-operations.md))。ignore されたサブツリーには子 `.kcs` を生成しない。**VCS リポジトリ root (`.git` 等の VCS 管理ディレクトリを持つフォルダ) とその配下にも既定では子 `.kcs` を生成しない** (skip + status 表示。`[scope] index_vcs_repos = true` で opt-in) — リポジトリの履歴は VCS 自身が持ち、`.kcs` の自動生成はリポジトリを汚す ([01-positioning.md §8](01-positioning.md) の方針の機械化)。**本既定の導入以前に生成済みの既存子 `.kcs` は grandfathered** — 引き続き有効な scope として index・検索の対象に残る (skip が適用されるのは新規生成の判断のみ)。
3. したがって tree entry の `path`、Evidence Pointer の `path_at_commit`、task の `input_path` は **パス区切り (`/`) を含まないファイル名** である。`/` を含む path を持つ tree / pointer は schema violation (`KCS-E-STORE-PATH-001`) として拒否する。

ファイルの位置は `scope_path` (正本 `.kcs` の絶対パス) + ファイル名で一意に表現される。「フォルダ木を横断してファイルを探す」体験は、個々の `.kcs` の再帰包含ではなく scope_registry を使った横断検索 ([05-runtime.md §1.8](05-runtime.md)) が担う。

```
親 .kcs と子 .kcs 間で同一ファイルが二重 object 保存されることは発生しない。
別 .kcs 間の同一内容ファイルは、ユーザーが意図的に複数フォルダへ配置した場合に限り
物理的重複保存を許容する (per-.kcs dedup, cross-.kcs dedup なし)。
```

# 4. 二層構造 — truth vs cache

```
truth = folder-local .kcs           raw object / normalized / chunks / commits / refs
cache = scope_registry / aggregator 検索の探索対象一覧 / stale 検出 / UI 統合
```

`scope_registry` 保存先: `~/.local/share/kcs/scope-registry.sqlite`。

不変条件:

```
1. scope_registry のみで .kcs の状態を変える実装は禁止
2. scope_registry 喪失は再構築可能 (各 .kcs を rescan)
3. .kcs 喪失は復旧不能 (検証とバックアップの運用は 10-operations.md §7.5)
4. 検索結果メタには「正本の .kcs パス」を必ず含める
5. raw object の所有権・dedup は scope_registry でグローバル化しない
```

## 4.1 永続ストア一覧 (technology × truth/cache)

各永続ストアの実装技術と喪失時の扱いの正本表 (2026-07-14 実装準拠で確定)。個別 schema の正本は右端の参照先に置く。

| ストア | 技術 | 区分 | 喪失時 | schema 正本 |
|---|---|---|---|---|
| `.kcs/objects/` (raw / prepared / images / normalized_units / manifests / toollocks / chunks / embeddings / trees / commits) | file (CAS) | **truth** | 復旧不能 (検証: [10-operations.md §7.5](10-operations.md)) | §8 / §2.1 |
| `.kcs/HEAD` / `refs/` | file (atomic rename) | **truth** | 復旧不能 | §2 |
| `.kcs/tombstones/` + erase receipt | file | **truth** (purge 証跡) | 復旧不能 | [05-runtime.md §3.5](05-runtime.md) |
| `.kcs/scope.json` / `config.toml` / `tool-lock.json` | JSON / TOML (schema 検証: [10-operations.md §12.3](10-operations.md)) | **truth** | 復旧不能 | 各 spec |
| `.kcs/logs/access.jsonl` | JSONL (append-only) | **truth** (access_events の正本) | 復旧不能 | §2 |
| `.kcs/purge/epoch` | 単調カウンタ (text) | **truth** (purge の ABA barrier) | 欠落 = 読取 fail-closed。次の locked mutation が journal の target_epoch から単調性を回復して再作成 | [05-runtime.md §3.5](05-runtime.md) |
| `.kcs/manifest.json` | JSON (schema 検証) | working-state cache (永続的真実は tree/commit object) | rescan で再構築 | §8 files |
| `.kcs/tasks.jsonl` | JSONL (append-only) | 運用データ | 喪失許容 ([04-pipeline.md §5.7](04-pipeline.md)) | [04-pipeline.md §5.1](04-pipeline.md) |
| `.kcs/chunks.jsonl` | JSONL (append-only) | **truth** (chunk の世代 association / created_at / first_seen_commit / 生成時点 path — chunk object には含めない §8) | 復旧不能 (SQLite rebuild の入力) | §8 / [04-pipeline.md §4.1](04-pipeline.md) |
| `.kcs/index/sqlite.db` | **SQLite** (chunks / chunk_config_generations / chunk_publications / chunk_fts / embeddings / chunk_vec / tree_entries / index_metadata の 8 表) | cache | `kcs repair --rebuild-db` | [04-pipeline.md §4](04-pipeline.md) |
| `~/.local/share/kcs/scope-registry.sqlite` | **SQLite** (`scopes` 1 表) | cache | 各 `.kcs` の rescan | [10-operations.md §3](10-operations.md) |
| `~/.local/share/kcs/cost-ledger.sqlite` | **SQLite** (`cost_ledger` / `batch_requests` の 2 表、WAL) | 運用データ (課金台帳 + **in-flight Batch intent の正本** — [04-pipeline.md §5.8](04-pipeline.md)。tasks.jsonl と異なり喪失許容ではない) | 確定課金は再構築不可 (Adapter 報告値の記録であり再導出元がない)。in-flight は provider job 一覧の intent_token 全走査で回収 | [04-pipeline.md §5.4](04-pipeline.md) (SQL 正本) |

**SQLite を使うのはこの表の 3 ファイル (計 11 テーブル)**。うち index/sqlite.db と scope-registry.sqlite は正本から再構築可能な検索キャッシュ、**cost-ledger.sqlite だけは再構築不可の運用台帳** (cache ではない — schema 変更は rebuild でなく in-place migration 側、[10-operations.md §7.5.3](10-operations.md))。コンテンツの truth は引き続きファイル (CAS objects/ ほか) が正本であり、tasks.jsonl は喪失許容の JSONL のまま。旧 spec が SQLite テーブルとして定義していた `files` / `normalization_runs` / `prepared_units` は採用しない (§8、[04-pipeline.md §4.7](04-pipeline.md))。課金 + in-flight intent の記録は 2026-07-18 に JSONL 3 ファイル構成から cost-ledger.sqlite へ確定した ([04-pipeline.md §5.4](04-pipeline.md) — 2 相プロトコルが UNIQUE・単一 Tx・ON CONFLICT 冪等の保証を正本要件とするため)。

# 5. Identity — hash と semantic_fingerprint の分離

```
raw_hash             原文バイト列の同一性 (1 バイト違えば別 object)
tool_profile_hash    Adapter capability の identity (§5.1)
tool_lock_hash       tool-lock.json 全体を畳み込んだ識別子 (§5.2)
semantic_fingerprint 意味的・視覚的・構造的な近さ (page fingerprint, embedding 等)
```

ルール:

- 同一性判定 (up_to_date / dedup) には hash を使う
- 類似性判定 (重複候補提示, page reuse, 分類) には semantic_fingerprint を使う
- 命名で区別 (`*_hash` vs `*_fingerprint`)
- **Markdown content hash (normalized_hash 等) は採用しない**。Markdown は LLM ベース非決定的なため。Markdown 識別は `(raw_hash, tool_profile_hash)` のみ

## 5.1 tool_profile_hash 計算規約

artifact identity は `(raw_hash, tool_profile_hash)` 単独に依存するため、計算規約をプロダクト契約として固定する。

**ハッシュ対象フィールド (capability hash)** — 決定性に影響する情報のみ。`cmd`/`args`/`url`/認証情報は **絶対に含めない**:

```
adapter_kind          "markdownize" | "embedding" | "ocr" | ...
adapter_role          "text" | "image" | "multimodal"
model_or_tool_family  "gemini-2.5-pro" | "gpt-4o" | "tesseract" の正規化名
model_version_pin     ベンダー側 immutable tag (latest 等の可変 alias は禁止)
prompt_template_id    KCS が管理する prompt 識別子
prompt_template_hash  prompt 本文を canonical 化した sha256
sampling              {temperature, top_p, top_k, max_tokens, seed}
output_schema         期待する Markdown / JSON schema id とバージョン
render_params         prepare 専用: {renderer_name, renderer_version, dpi, color_space, output_format}
                      (バイト列決定性に影響する全レンダリング設定 — [04-pipeline.md §2.1](04-pipeline.md))
dimensions / distance / modality   embedding 専用
runtime_kind          "cloud" | "local" (capability レベル)
spec_version          この計算規約自体のバージョン
```

実装バイナリのバージョン (`adapter_binary_version`, OS, ハードウェア) は **`binary_hash` として別保存**し、`tool_profile_hash` には含めない。これにより Adapter のマイナー bug fix で全 re-index が走らない。

**算出式** (RFC 8785 JCS 準拠):

```
tool_profile_hash = "sha256:" + base16(sha256(JCS(canonicalize(profile_fields))))
```

null フィールドは hash 入力に含めない (省略と null を識別しない)。

**prompt_template_hash**:

```
1. trim trailing whitespace per line
   (行末の ASCII 空白 U+0020 と TAB U+0009 のみ除去。全角空白・\f・\v は除去しない。
    行区切りは CRLF / LF / 単独 CR のいずれも行区切りとして扱う)
2. normalize line endings to \n (CRLF → \n、単独 CR → \n)
3. NFC 正規化
4. 末尾の空行を削除
5. sha256, "sha256:" プレフィックス
```

手順 1-2 の対象文字集合と単独 CR の扱いは 2026-07-03 に確定 (契約テスト設計 step2a §C-4 の決定性論点解消)。

`spec_version` の bump は breaking change 扱い (migration plan 必須)。

## 5.2 tool_lock_hash 計算規約

commit object 等で参照される `tool_lock_hash` は `tool-lock.json` 全体の identity:

```
tool_lock_hash = "sha256:" + base16(sha256(JCS({
  spec_version: <int>,
  prepare:        { tool_id, profile_hash },
  markdown:       { tool_id, profile_hash },
  embedding:      { tool_id, profile_hash, dimensions, distance, modality },
  summary:        { tool_id, profile_hash },         # optional
  classification: { tool_id, profile_hash },         # optional
  rerank:         { tool_id, profile_hash }          # optional
})))
```

**preimage の保存**: tool-lock の materialize ([07-adapter-spec.md §6](07-adapter-spec.md)) 時に、この
canonical JCS bytes を `objects/toollocks/ab/cd/<hash64>` へ content-addressed で保存する (immutable) —
commit の `tool_lock_hash` から当時の lock 内容 (model pin・Adapter 定義) を復元・検証できる
(manifest object と同族。fsck の再 hash 対象 — [10-operations.md §7.5.1](10-operations.md))。
作業コピー `tool-lock.json` は最新版であり、過去版の解決は toollock object のみが担う。

`cmd`/`args`/`url`/`config_hash`/capabilities は入力に含めない。embedding のみ次元・距離・modality を含めるのは、横断検索互換性 (§7) の決定根拠になるため。optional adapter は未設定なら省略 (null と識別しない)。

## 5.3 chunking_config_hash 計算規約

chunk 境界は Adapter ではなく core 側の chunking 設定 (`.kcs/config.toml [chunking]`、§11) で決まるため、`tool_profile_hash` には畳み込まれない。chunk / embedding の世代判定用に独立の hash を持つ:

```text
chunking_config_hash = "sha256:" + base16(sha256(JCS({
  spec_version: <int>,
  strategy: "heading",
  max_chars: 6000
})))
```

- 対象は `[chunking]` 配下の **chunk 境界に影響する全キー**。キーを追加したら `spec_version` を bump する
- デフォルト値も明示的に畳み込む (キー省略と明示指定を識別しない)
- これは同一性 hash であり、identity には使わない。chunk identity は §8.1 のとおり `(raw_hash, tool_profile_hash, gen, unit_key, heading_path, section_id, byte_start, byte_end)` のまま。`chunking_config_hash` は chunk の**世代**を表すメタデータに留める

# 6. Up_to_date 判定

ファイルが Markdown 化済みかの判定は、最新 normalized instance の manifest と unit object の存在 (§2.1) のみで決定する。Markdown content hash 一致は **判定条件に含めない** (§5)。

```python
current_raw_hash = hash(file)
inst = latest_instance(current_raw_hash, current_tool_profile_hash)
       # objects/normalized_units/ 配下の最大 gen の manifest (§2.1)
if inst is None:
    pending
elif all(u.status == "failed" for u in inst.units):
    failed           # 全滅 — retryable (04-pipeline.md §5.2 の failed → pending と同じ扱い)
elif any(u.status == "done" and not unit_object_exists(u) for u in inst.units):
    missing_output   # done 宣言 unit の object 欠落 — failed unit と併存しても partial で隠さない
                     # (回復対象 = 欠落 done ∪ failed の和集合。欠落を先に判定しないと
                     #  permanent failed の陰で欠落が恒久に再投入されない)
elif any(u.status == "failed" for u in inst.units):
    partial          # 成功 unit は検索対象。失敗 unit のみ再投入 (04-pipeline.md §5.2)
else:
    up_to_date
# prepare profile の変更は 04 §2.1 の prepared_hash 変化として再投入を駆動する — 本判定は instance の
# 存在のみを見るが、§2.1 の差分判定が上流で新 run を積むため up_to_date に留まらない
```

判定の正本は manifest + unit object の存在である (`normalization_runs` は SQLite テーブルとしては
持たない — §8。run 状態は manifest から導出し、復元セマンティクスは [04-pipeline.md §5.7](04-pipeline.md))。
全文 view の存在は判定に使わない。

ファイル状態分類:

```
new            初めて見つかった原文
up_to_date     最新 Markdown あり (unit 段の判定 — chunk 生成の完了は含まない。chunk が期待集合
               (当該 (raw, profile, gen, config) の決定論的 re-chunk 結果) に達していない間は
               index_status (05-runtime.md §1.7) が partial として可視化する)
modified       path 同じだが raw_hash が変わった
tool_changed   raw_hash 同じだが tool_profile_hash が変わった
partial        一部 unit の Markdownize が失敗 (成功 unit は検索対象、欠損は kcs status に表示)
missing_output manifest は done を記録しているが unit object ファイルが見当たらない
failed         前回 Markdown 化失敗
pending        実行待ち
```

`corrupted` (Markdown content hash 不一致) は採用しない。Markdown は read-only artifact として content hash を持たないため。

# 7. Embedding 互換性ルール

複数 `.kcs` 横断 vector 検索の条件:

```
dimensions / distance / modality / embedding profile_hash がすべて一致
```

不一致なら BM25 のみ横断検索、または再 index 要求。

**modality は `"multimodal"` に固定する (2026-07-03 確定)**。text と image 等を別ベクトル空間に埋め込む
構成 (`modality="text"` 等の非 multimodal profile) は**採用不可**であり、tool-lock への materialize /
adapter 登録の時点で `KCS-E-EMBED-MODALITY-001` (exit 2、[06-cli-spec.md §8](06-cli-spec.md)) として
拒否する。採用 profile は [07-adapter-spec.md §5.3](07-adapter-spec.md) の単一マルチモーダル profile のみ。

# 8. 主要テーブル / object スキーマ

## files (working state) — 実体は manifest.json (SQLite テーブル非採用)

working state の実体は `.kcs/manifest.json` の `files` 配列であり、**SQLite に `files` テーブルは
作らない** (§4.1。2026-07-14 実装準拠へ更新 — 旧 `CREATE TABLE files` 定義は未実装のまま廃止)。
schema は `kcs-core/schemas/manifest.schema.json` (JSON Schema、[10-operations.md §12.3](10-operations.md))
で検証する:

```json
{
  "schema_version": 1,
  "updated_at": "2026-07-14T00:00:00Z",
  "files": [
    { "path": "report.pdf", "raw_hash": "sha256:ab...", "status": "modified" }
  ]
}
```

- `path` は自フォルダ直下のファイル名のみ (`/` を含まない — §3 スコープ境界)
- `status` は `new | modified | deleted | unchanged` の固定 enum
- ファイル削除を検出しても entry は **削除しない**。`status = "deleted"` に更新し、最後に観測した
  raw_hash を保持する。同一 path が再作成されたら status を戻す
- manifest は working-state cache であり (§2 レイアウト注記のとおり永続的真実は tree/commit object)、
  cursor-stable `--include-deleted` の truth は page-1 snapshot の first-parent trees から導出する
  ([05-runtime.md §1.6](05-runtime.md)); manifest/files の後発変更は paging 集合を変えない

旧テーブル定義にあった `file_id / size_bytes / mtime / kind / first_seen_at / last_seen_at` は
持たない。必要になった場合は manifest.json の `schema_version` bump で追加する。

## normalization_runs — 実体は normalized instance manifest (SQLite テーブル非採用)

normalization run の正本は normalized instance の `manifest.json` (§2.1) であり、**SQLite に
`normalization_runs` テーブルは作らない** (§4.1。2026-07-14 実装準拠へ更新)。run 状態は独立永続化
せず、manifest + unit object の存在から導出する (§6、[04-pipeline.md §5.7](04-pipeline.md))。

run レコード (パイプライン内部表現。manifest へは provenance として `run_id` / `parent_gen` を記録):

```text
run_id                                 manifest.run_id として永続化 (provenance)
raw_hash / tool_profile_hash / gen     instance identity (= instance ディレクトリ名 §2.1)
mode                                   full | incremental
status                                 pending | running | done | partial | failed
                                       (manifest の unit status から導出)
changed_unit_keys                      incremental の対象 unit ([04-pipeline.md §5.1](04-pipeline.md) task にも記録)
output_ref                             normalized instance ディレクトリ
fallback_reason                        capability_missing | threshold_exceeded | ...
                                       (task 側の運用データ、喪失許容)
created_at / finished_at
```

`normalized_path` は持たない。instance は `(raw_hash, tool_profile_hash, gen)` から一意に決まる。
世代の親子関係は manifest の `parent_gen` で表現する (`parent_run_id` チェーンは永続化しない —
喪失許容の運用データ、[04-pipeline.md §5.7](04-pipeline.md))。**incremental で親の raw が異なる場合
(raw 更新をまたぐ通常 incremental) は `parent_instance = {raw_hash, tool_profile_hash, gen}` を必須で
記録する** — `parent_gen` は同一 raw 内の局所番号であり、整数だけでは親 instance を一意に復元できない
(full では null)。**manifest_hash** (tree schema v2 の入力 — §8) は manifest の canonical JCS bytes の
sha256 とする。

## 8.1 Object hash 算出規約

object hash は artifact identity と Evidence Pointer の永続性 (08 §6) を支えるプロダクト契約であり、`tool_profile_hash` (§5.1) と同じ厳密さで固定する。

**共通規則**:

- 論理 hash 表記は `"sha256:" + base16(sha256(...))` (小文字 hex)。JSON、SQLite、refs、CLI、URI ではこの完全表記を使う。
- canonical fan-out パスは `objects/<type>/ab/cd/<digest64>`。`digest64` は論理 hash から `sha256:` を除いた 64 文字の小文字 hex で、`ab` / `cd` はその先頭 2 文字 / 続く 2 文字。normalized basename と tombstone leaf も §2 の digest-only 規則に従う。
- object 本体は**自身の hash を含めない** (Git 同様、保存キーが ID。旧 `tree_id` / `commit_id` /
  chunk object 内の `chunk_hash` フィールドは廃止)。raw / prepared / image は保存 byte の content key、
  tree / commit は canonical JSON の content key、chunk は保存 path の key と §8.1 identity tuple を照合する。
- 人間向け表示は先頭 12 hex への短縮可 (`sha256:9f2c1a7b04de…`)。`--json` は完全 hash ([06-cli-spec.md §4](06-cli-spec.md))。
- hash 算出または論理 identity 規約の変更は `kcs_format_version` の MAJOR bump (migration plan 必須)。§2 の digest-only 物理名は、論理 hash を変えず Windows を含む filesystem で同じ object を表現する portability correction であり、identity の変更ではない。旧物理名は §2 の検証付き fallback で読み取る。

**raw / prepared / image** — content hash:

```text
raw_hash      = "sha256:" + base16(sha256(原本ファイルのバイト列))
prepared_hash = "sha256:" + base16(sha256(prepared object のバイト列))
image_hash    = "sha256:" + base16(sha256(抽出画像のバイト列))
```

**tree / commit** — canonical JSON の content hash:

- object は RFC 8785 JCS canonical form の JSON バイト列として保存する。
- `tree_hash` / `commit_hash` = 保存バイト列の sha256。検証は再ハッシュのみで足りる。
- 種別誤認防止のため object 本体に `"object_type": "tree" | "commit"` を必須で含める (Git の object header 相当)。
- tree の `entries` は `path` の UTF-8 バイト列昇順で一意にソートする。同一 `path` の重複 entry は禁止。
- commit の `parents` は commit_hash の配列。第一要素は直前 HEAD (first parent)。
- timestamp は UTC ISO8601 + `Z` ([06-cli-spec.md §12](06-cli-spec.md))。
- `HEAD` / `refs/heads/*` / canonical `refs/tags-v1/*` / legacy `refs/tags/*` の値は commit_hash。

**manifest** — canonical JSON の content hash (§2.1):

```text
manifest_hash = "sha256:" + base16(sha256(manifest の canonical JCS バイト列))
```

- 保存パスは `objects/manifests/ab/cd/<manifest64>` (immutable — §2.1)。fsck は再ハッシュで検証し、
  tree entry の `normalize.manifest_hash` (§8) がこの object を指す ([10-operations.md §7.5.1](10-operations.md))。

**chunk** — identity hash:

```text
chunk_hash = "sha256:" + base16(sha256(JCS({
  "spec_version": 1,
  "raw_hash": "...",
  "tool_profile_hash": "...",
  "gen": <int>,
  "unit_key": "...",
  "heading_path": ["...", "..."],
  "section_id": "...",
  "byte_start": <int>,
  "byte_end": <int>
})))
```

- `gen` は normalized unit の世代番号、`unit_key` は chunk が属する unit の識別子 (例 `page:12`)。`byte_start` / `byte_end` は **unit-local** の UTF-8 byte span (当該 unit 本文 bytes 先頭を 0 とする 0-based half-open — §8)。
- null / 未設定フィールドは hash 入力に含めない (§5.1 と同じ規則。`section_id` を持たない chunking strategy では省略)。
- chunk object 本体 (`text_hash` 等を含む) は `chunk_hash` をキーに保存されるが、`text_hash` は **hash 入力に含めない**。Markdown は LLM ベース非決定的であり (§5)、chunk の同一性は原文 + tool capability + unit 世代 + 構造的位置 + span のみで決まるため。

**embedding** — identity hash:

```text
embedding_hash = "sha256:" + base16(sha256(JCS({
  "spec_version": 1,
  "target_type": "chunk",
  "target_hash": <text_hash>,
  "profile_hash": <embedding profile_hash>,
  "modality": "...", "dimensions": <int>, "distance": "..."
})))
```

- `target_hash` は対象 chunk の **`text_hash`** (chunk 抽出範囲のみの content hash、§8) であって `chunk_hash` ではない。embedding は Markdown 本文そのものの関数なので、同一本文を持つ複数 chunk (別世代・別ファイルの同一断片) は 1 本の `embeddings` 行を共有する — これが **content ベース再利用** ([04-pipeline.md §4.3 / §5.5](04-pipeline.md)) の identity 基盤である。`chunk_vec` (vec0) は `chunk_hash → embedding` の写像として `embeddings` から導出する。
- embedding object の保存 bytes は **`JCS(identity fields) + LF + base64(vector, float32 little-endian) + LF + lower_hex64(sha256(vector bytes))`** に固定する。fsck ([10-operations.md §7.5.1](10-operations.md)) は identity hash の再計算に加え、vector 長 (= dimensions × 4 bytes)・有限値 (NaN / Inf の拒否)・**vector digest の一致** (有限値への bit flip の検出) を検査する。

## tree / commit object

```json
// tree — objects/trees/3f/9a/<tree64> に JCS 形式で保存 (tree_hash は保存バイト列の sha256)
{
  "object_type": "tree",
  "entries": [
    {
      "path": "report.pdf",
      "type": "file",
      "raw_hash": "sha256:abc...",
      "normalize": { "tool_profile_hash": "sha256:tool1...", "gen": 0,
                     "manifest_hash": "sha256:mani..." }
    }
  ],
  "chunking_config_hash": "sha256:cfg...",
  "chunk_set_hash": "sha256:cs..."
}
// tree schema v2 (2026-07-18 確定 — 実装・store 公開前の schema 確定で MAJOR bump ではない、
// [10-operations.md §12.5](10-operations.md)):
//  - entry.normalize.manifest_hash = 当該 normalized instance manifest の canonical hash
//    (JCS bytes の sha256 — §2.1)。unit の failed → done 遷移で変わるため、**derived 成果の変化が
//    tree_hash を変える** = same-gen partial retry の finalize も通常の auto snapshot を生む
//    ([05-runtime.md §8.1](05-runtime.md))
//  - tree.chunking_config_hash = snapshot 時点の effective chunking config (§5.3)。再 chunk も同様に
//    tree_hash を変える
//  - v1 tree (両フィールド欠落) は legacy として読取可 (欠落 = 旧 semantics)。新規 commit は v2 で書く
//  - manifest_hash は objects/manifests/ の immutable manifest object (§2.1) を指す — same-gen retry で
//    作業コピー manifest.json が更新された後も、過去 commit の manifest bytes はこの object から解決できる
// tree schema v3 (2026-07-18 確定 — 同じく実装・store 公開前の schema 確定で MAJOR bump ではない):
//  - tree.chunk_set_hash = この snapshot で公開済みの chunk 集合の digest。canonical bytes =
//    公開 chunk の chunk_hash 完全表記 ("sha256:<64hex>") を UTF-8 バイト列昇順にソートし LF 連結 +
//    末尾 LF 1 つ、その sha256。「公開済み」= 本 tree の binding (raw_hash, tool_profile_hash, gen) に
//    属し、本 tree の chunking_config_hash の association を持つ chunk object の全量 (snapshot 時点で
//    **store に存在するもの** — 存在ベース。0 件のときの canonical bytes = LF 1 byte)。chunking の途中
//    クラッシュで部分集合が manual snapshot に載ることは許容する — chunk は unit 単位で決定的・個々に
//    完全であり、残りは完了時の finalize commit で introduction を得る (検索の部分性は status が可視化)
//  - これにより chunk のみが後着した finalize でも chunk_set_hash → tree_hash が変わり、no-op 規則の
//    まま publication commit が生まれる ([05-runtime.md §8.1](05-runtime.md) 契機 3) — manifest 反映済み
//    snapshot が先行しても後着 chunk の introduction を刻める
//  - v2 tree (chunk_set_hash 欠落) / v1 tree は legacy として読取可 (欠落 = 旧 semantics)。新規 commit は
//    v3 で書く。検証は tree 保存バイト列の再 hash に含まれる (集合の意味的再計算は fsck 対象外)

// commit — objects/commits/9f/2c/<commit64> に JCS 形式で保存
{
  "object_type": "commit",
  "tree": "sha256:3f9a...",
  "parents": ["sha256:71bd..."],
  "created_at": "2026-04-29T12:00:00Z",
  "message": "snapshot after indexing docs",
  "tool_lock_hash": "sha256:...",
  "stats": { "files_added": 12, "files_modified": 3, "files_deleted": 1 },
  "commit_type": "manual"
}
```

JCS ではキー順は canonical 化時に自動決定されるため、上記の記載順は可読性のためのもの。

tree entry の `normalize` ブロックは **optional**。normalized instance が存在しないファイル (未 Markdownize) の
entry では `normalize` を**省略**する (省略 = 当該ファイルの normalized / chunk は存在しない。`null` は書かない —
§5.1 の「省略と null を識別しない」に従う)。Step 1 (pipeline 未実装) では全 entry が `normalize` 省略形になり、
Step 2 で Markdownize されたファイルから順に `normalize` 付き entry へ移行する。

`normalize` が存在する場合、tree entry の `gen` は commit 時点で参照していた normalized instance の世代 (§2.1)。フィールド欠落は `gen = 0`
と読む (forward compatible)。`kcs reindex --force` 後も過去 commit の tree entry は旧 gen を
指し続けるため、`kcs view --at` ([05-runtime.md §4.2](05-runtime.md)) と Evidence Pointer の
不変性保証 ([08-evidence-pointer-spec.md §6](08-evidence-pointer-spec.md)) は gen 保全により成立する。

`commit_type` は固定 enum (詳細は [05-runtime.md §2](05-runtime.md)):

```
manual | auto | imported | migrated | repaired | merged | purged
```

commit object の schema 検証 (publication 時の loader — [05-runtime.md §2.1](05-runtime.md)。commit は CAS JSON object であり SQLite に commit 表は無い) で固定し、**この値域は永久に変更しない契約** (semver MAJOR でも bump しない)。

## 8.2 tree のスケール前提 (flat entries)

tree は entries を単一の flat 配列で持つ。スコープ境界規則 (§3) により entry 数は scope フォルダ直下のファイル数に一致し、1 tree に階層は存在しないため、Git 式のディレクトリ単位 tree object (サブツリー hash 共有) は導入しない。

サイズ見積り (1 entry ≈ 150-250 bytes):

| 直下ファイル数 | tree object サイズ | 備考 |
| --- | --- | --- |
| 100 | 約 25 KB | 典型的なフォルダ |
| 1,000 | 約 250 KB | 大きめの Downloads 等 |
| 10,000 | 約 2.5 MB | 想定上限 (soft limit) |

規範:

- 1 scope の直下ファイル数の想定上限は 10,000 (soft limit)。超過時 `kcs index` は警告を表示し、サブフォルダへの分割または ignore を提案する (処理自体は継続する)
- snapshot 時に tree_hash が現在の HEAD の tree と一致する場合、auto snapshot は commit を作らない (no-op。**例外 = resurrection finalize と tool_lock_hash の変化** — no-op 判定は tree_hash と commit の tool_lock_hash の両方を比較する。正本 [05-runtime.md §8.1](05-runtime.md))。tree は CAS object なので、内容不変なら新規 object も生成されない (tree_hash は保存バイト列の content hash、§8.1)
- 1 ファイルの変更で tree 全体 (上表のサイズ) が新 object として書かれるのは仕様どおりの挙動である。pack/delta 圧縮 (§2, v2+) の導入判断は、この見積りの実測値で再評価する

## chunk

```json
{
  "spec_version": 1,
  "raw_hash": "sha256:abc",
  "tool_profile_hash": "sha256:tool1",
  "gen": 3,
  "unit_key": "page:12",
  "heading_path": ["認証仕様", "API Token"],
  "section_id": "認証仕様/api-token",
  "byte_start": 1200,
  "byte_end": 1500,
  "text_hash": "sha256:text",
  "text": "chunk の exact normalized text"
}
```

chunk identity は `(raw_hash, tool_profile_hash, gen, unit_key, heading_path, section_id, byte_start, byte_end)` で決まり、chunk_hash の算出式は §8.1 に定める (heading_path と section_id は両方 hash 入力。未設定フィールドは省略。**`byte_start` / `byte_end` は unit-local の UTF-8 byte offset・0-based half-open** — 「文字」単位ではない (旧称 `char_start` / `char_end`。実装・pointer 発行前の 2026-07 改名で、意味と名称を一致させた)。Normalized Markdown は UTF-8/NFC/LF に固定されるため byte offset は決定的 — [07-adapter-spec.md §5.2.1](07-adapter-spec.md))。`text_hash` は **chunk 抽出範囲のみ** の hash (= sha256(当該 byte 範囲の exact bytes)) であり、Markdown 全体の hash ではない。`chunking_config_hash` は chunk の**世代**を表すメタデータであり、identity には含めない (§5.3)。chunk object 本体が `gen` を保持するため、tree を失った shallow commit からでも chunk_hash → chunk object → gen で normalized unit instance まで直接解決できる ([08-evidence-pointer-spec.md §3.1](08-evidence-pointer-spec.md))。

chunk object の永続 JSON は上記の `spec_version` + identity fields + `text_hash` + exact `text` に固定し、
自身の `chunk_hash`、path、`first_seen_commit`、`created_at`、`chunking_config_hash` は含めない。
`chunking_config_hash` は同一 chunk identity に複数値が対応しうる generation association として
**append-only の `chunks.jsonl` (§2 layout / §4.1 — truth) を正本に、SQLite の別 relation (cache) へ**保持する。fsck は object bytes の content hash ではなく
§8.1 の identity hash を再計算して保存 fan-out key と照合し、`text_hash` を object 内の `text` と
対応 normalized unit の exact span の両方に照合する。

# 9. Dedup スコープ

```
dedup scope            = one .kcs object store
cross-.kcs dedup       = not guaranteed
cross-.kcs GC scope    = none (各 .kcs に閉じる)
```

per-`.kcs` の prepared/normalized/embedding 重複と purge の `.kcs` 単位スコープは、将来 LLM コスト低下/ローカル LLM 進展前提で **容認** ([01-positioning.md](01-positioning.md))。

# 10. 書き込み主体マトリクス

```
レイヤー                       | User | KCS  | Agent (提案) | Agent (自動適用)
------------------------------ | ---- | ---- | ------------ | ----------------
原本 (raw)                     | yes  | no*  | propose      | no
原本の移動 (file system mv)     | yes  | yes* | propose      | user 承認後のみ
normalized markdown            | no   | yes  | no           | no
image objects (抽出画像)        | no   | yes  | no           | no
chunks / embeddings            | no   | yes  | no           | no
annotations / tags / notes     | yes  | no   | yes          | yes
nodes / edges (Phase 5)        | yes  | no   | yes          | yes
commits / refs (履歴)           | no   | yes  | no           | yes (auto commit)
extraction issues              | yes  | yes  | yes          | yes
```

`*` 「原本の移動」は `kcs move --accept` 経由でのみ KCS が原本を mv する。原本の **内容** は不変なので write ではなく移動。Agent が `kcs move --accept` を直接呼ぶことは禁止 (`--propose` 経由のみ)。

normalized (unit object および全文 view) は **read-only artifact**。全文 view の生成時に付与する
Markdown ヘッダ template:

```markdown
<!--
KCS GENERATED FILE
Do not edit manually.
Source: report.pdf
Raw-Hash: sha256:...
Tool-Profile-Hash: sha256:...
Generated-At: 2026-04-25T12:00:00Z
-->
```

ハッシュ検証で破損検出はしない (§5: Markdown content hash を持たないため)。unit object が直接編集された場合でも次回 `kcs index` は `(raw_hash, tool_profile_hash)` 一致で「up-to-date」と判定する (= Markdown 内容そのものは正本ではなく、原文 + tool_profile が正本)。全文 view (`objects/normalized/*.md`) は cache のため、直接編集は次回 view 再生成で破棄される。

# 11. 設定ファイル

`~/.config/kcs/tools.toml` (デバイスローカル, 共有 `.kcs` には含まれない):

```toml
[markdown.mistral_ocr_markdownize]
kind = "online_api"
model = "mistral-ocr-latest"        # config では可変 alias 可。tool_profile の pin は解決済み immutable 版 (§5.1)
profile_hash = "sha256:..."
capabilities = ["ocr", "layout_detection", "table_extraction"]
```

現行版の認証付き Markdownize / Embedding adapter は KCS 組込み target のみを実行する。`cmd` / `args` / `url` による任意 target は受理せず、旧設定にこれらのキーがある場合は削除して組込み adapter 宣言へ移行する。Summary / Classification / Rerank など未実装 role の外部 dispatch 契約は [07-adapter-spec.md §7](07-adapter-spec.md) の将来仕様であり、現行 runtime が実行できることを意味しない。

`.kcs/config.toml`:

```toml
[scope]
participates_in_global_search = true
[chunking]
strategy = "heading"
max_chars = 6000
# max_chars の計数単位 = Unicode scalar value (code point)。分割規則は 04-pipeline.md §4.1
# [chunking] の変更は chunking_config_hash (§5.3) の変化として検出され、
# chunk / embedding のみ再生成される (再 Markdownize しない)。規則は 04-pipeline.md §4.6
[markdownize.incremental]
enabled = true
threshold = 0.30
max_consecutive = 5
[budget]                   # folder cap (任意の追加制限)。device cap との判定は 04-pipeline.md §5.4
monthly_usd_cap = 10.0
[gc]
mode = "manual_only"           # MVP デフォルト。GC 実行系の実装は Phase 4+ (05-runtime.md §2.3)
idle_threshold_seconds = 300
```

すべての設定は JSON Schema/TOML Schema で validate ([10-operations.md §12.3](10-operations.md))。

## 11.1 .kcsignore 文法 (2026-07-03 追記)

`.kcsignore` は scope ルート (`.kcs` と同階層) に置く。`kcs index` の探索全体 — 直下ファイルの取り込み判定と、サブフォルダへの子 `.kcs` 自動生成の対象判定 ([06-cli-spec.md §1](06-cli-spec.md)) — に適用する。文法は **gitignore 互換サブセット**:

```text
# で始まる行と空行     無視 (コメント)
glob                  * (パスセグメント内) / ** (セグメント跨ぎ) / ? (1 文字)
末尾 /                ディレクトリのみに一致
!pattern              negation (直前までの除外を解除)
評価順               上から順に評価し、最後に一致した規則が勝つ (後勝ち)
パス基準             scope ルート相対
```

secrets built-in デフォルト除外 (Tier A、[10-operations.md §1.1](10-operations.md)) は `.kcsignore` の**暗黙の先頭**に位置するとみなす。したがって Tier A の解除は明示の `!pattern` でのみ可能で、解除時の確認記録は 10 §1.1 の規約に従う。config (`[scope] ignore`) と `.kcsignore` が両方ある場合は config → `.kcsignore` の順に連結して評価する (後勝ちのため `.kcsignore` が優先)。
