# WS1a 契約テスト仕様書: Step 1 (kio-core + kio-cli)

> 本書は **実装より先にテストを固定する** ためのケース仕様。Rust 実装コードは含まない。
> Step 1 実装者 (別エージェント) はこの仕様を「動かしてはならない契約」として消化する。
> 正本 spec は `docs/` の README + 01〜10。**本書は spec を写経・補間せず、各テストに根拠 § を必ず付す**。
> spec に記述がない挙動は勝手に契約化せず、末尾 §C「未定義事項」に切り出す。
>
> 改訂 r2 (2026-07-02): クロスレビュー反映。テストベクタは再計算一致につき不変。根拠 § の
> 過剰契約 8 件を修正、カバレッジ 9 件を追加、未定義リストから spec 導出可能な 4 件を契約へ昇格。

対象コマンド (Step 1): `init` / `status` / `snapshot` (alias `commit`) / `log` / `diff` / `inspect` / `tag`
(正本: `docs/09-mvp-scope.md §3.1` — CAS raw object store + snapshot DAG / 上記 7 コマンド = Step 1)

---

## 0. テスト ID 体系と優先度

| 接頭辞 | 対象契約 | 主な根拠 |
| --- | --- | --- |
| `CT-HASH-*` | hash 算出規約 (raw/tree/commit/fan-out/JCS/object_type/self-hash 排除) | `03 §8.1` |
| `CT-TREE-*` | tree entries ソート・重複禁止・直下のみ path・gen 欠落=0・flat スケール | `03 §3, §8, §8.1, §8.2` |
| `CT-COMMIT-*` | commit_type enum・first parent・no-op・HEAD/refs・timestamp | `03 §8, §8.1` / `05 §2, §8` / `06 §12` |
| `CT-GC-*` | `gc_policy × commit_type` / `protected` schema 遵守 (GC は実行しない) | `05 §2.1, §2.2, §2.6` |
| `CT-SCOPE-*` | スコープ境界 (直下のみ・子 .kio 独立) | `03 §3` |
| `CT-CLI-*` | 各コマンドの exit code / `--json` 完全 hash / error code 形式 / schema validation | `06 §1, §4, §7, §8, §11` |
| `CT-LOCK-*` | 書き込み系コマンドの `.kio/.lock` 排他 | `05 §5, §6` |
| `CT-STATE-*` | files 状態分類のうち Step 1 で判定可能なもの | `03 §6, §8` |
| `CT-OBS-*` | 観測ログ `events.jsonl` / `errors.jsonl` (Step 1 割当) | `06 §13` / `05 §7` / `09 §3.1` |

**優先度**

- **P0** = Step 1 完了条件。全て緑でなければ Step 1 を「完了」と呼べない。
- **P1** = 推奨。契約の周辺・堅牢性。落ちても致命ではないが実装欠陥の強い兆候。
- **P2** = あれば良い。Step 3 以降の前倒し検証や参考ベクタ。

P0 総数は §D 末尾に集計。

---

## A. 具体的テストベクタ (最重要)

以下は `python3` (3.14) で実計算した固定ベクタ。**再現手順**: 各入力バイト列 / JSON を
`sha256` および `JCS(...)→sha256` に通す。JCS 近似は
`json.dumps(obj, separators=(',',':'), ensure_ascii=False, sort_keys=True).encode('utf-8')`。

> **RFC 8785 との差異について (重要)**: 本書のベクタが使うキーはすべて ASCII、数値はすべて整数である。
> この条件下では上記 Python 近似は RFC 8785 JCS と **バイト一致** する (キーの UTF-16 コード単位ソート =
> ASCII 範囲では Unicode コードポイントソートと同一、整数の直列化も一致、文字列は最小エスケープで一致)。
> **差異が顕在化するのは (a) 非 ASCII のキー名、(b) 浮動小数点の数値** の場合のみで、Step 1 の
> tree/commit object schema (`03 §8`) はどちらも含まない。実装が本ベクタと不一致になった場合、
> まず「実装の JCS が RFC 8785 準拠か」を疑うこと (Python 近似の綻びではない)。
> 非 ASCII は **値** (`message` に日本語、`heading_path` に日本語) には現れうるが、値は UTF-8 リテラルで
> 直列化され (エスケープしない) 両者一致する — CT-HASH-009 で確認。

### A.1 raw content hash ベクタ (`03 §8.1` raw = バイト列の content hash)

| # | 入力 | `raw_hash` | fan-out `ab/cd` |
| --- | --- | --- | --- |
| RAW-1 (空) | `b""` (0 バイト) | `sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `e3` / `b0` |
| RAW-2 (日本語) | UTF-8 `認証仕様\n` (hex `e8aa8de8a8bce4bb95e6a7980a`) | `sha256:bbe1da2edd1819b58ce32163144923f850fc7f2c7b4fe130635c6b54a8e7ac59` | `bb` / `e1` |

### A.2 tree object JCS→sha256 ベクタ (`03 §8, §8.1`)

再現用の entry 素材 (すべて実 sha256):

- `notes.md`   の raw = `b"# Notes\n"`        → `sha256:365d0b84ae63c2afc293dedd2b00bdf0dc8d6ef70c9297d90f9e5682ab0d72ee`
- `report.pdf` の raw = `b"%PDF-1.4 dummy\n"` → `sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a`
- `tool_profile_hash` プレースホルダ = `sha256(b"KIO-TEST-TOOL-PROFILE-1")` = `sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0`
  (Step 1 に Markdownize は無い。ここでは「entry に normalize ブロックが載る場合」の hash 安定性を検証する目的の固定値。§C-2 参照)

入力オブジェクト (entries は path UTF-8 バイト昇順にソート済み: `notes.md` 0x6e < `report.pdf` 0x72):

```json
{
  "object_type": "tree",
  "entries": [
    { "path": "notes.md",   "type": "file", "raw_hash": "sha256:365d...72ee",
      "normalize": { "tool_profile_hash": "sha256:e067...c8f0", "gen": 0 } },
    { "path": "report.pdf", "type": "file", "raw_hash": "sha256:74bc...ca8a",
      "normalize": { "tool_profile_hash": "sha256:e067...c8f0", "gen": 0 } }
  ]
}
```

**canonical バイト列 (JCS, キーは再帰ソート)**:

```text
{"entries":[{"normalize":{"gen":0,"tool_profile_hash":"sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0"},"path":"notes.md","raw_hash":"sha256:365d0b84ae63c2afc293dedd2b00bdf0dc8d6ef70c9297d90f9e5682ab0d72ee","type":"file"},{"normalize":{"gen":0,"tool_profile_hash":"sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0"},"path":"report.pdf","raw_hash":"sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a","type":"file"}],"object_type":"tree"}
```

- `tree_hash` = **`sha256:eca8de0abaf2a27a1ea57feff4f44385bcfb3485274e73ddfa7c47144f383e1e`**
- fan-out `ab/cd` = `ec` / `a8` → `objects/trees/ec/a8/<leaf>`

### A.2b 空 tree (entries 0 件) ベクタ (`03 §8, §8.1` から導出)

`03 §8` の schema (`entries` は配列) と `03 §8.1` の直列化規則から、entry 0 件の tree は
`entries: []` として一意に表現できる:

```text
canonical: {"entries":[],"object_type":"tree"}
tree_hash = sha256:849dc4fa25bc1a7b09b74dba30c0bb85224fb8f659c3b2b177b7189b0327a967
fan-out   = 84 / 9d
```

### A.3 commit object JCS→sha256 ベクタ (`03 §8, §8.1`, parents 1 件)

- parent commit プレースホルダ = `sha256(b"KIO-TEST-PARENT-COMMIT-1")` = `sha256:30fa71e5c11a90a28c8c0895382e8f45df431047fcc699afed45ee316cfbf65a`
- `tool_lock_hash` ダミー = `sha256(b"KIO-TEST-TOOL-LOCK-1")` = `sha256:8a32a740871b1dd9db1bda186dce07e8e6c60d2cd316f21683ea2bd857c16ffb`
- `tree` = A.2 の `tree_hash`

入力オブジェクト:

```json
{
  "object_type": "commit",
  "tree": "sha256:eca8...3e1e",
  "parents": ["sha256:30fa...f65a"],
  "created_at": "2026-04-29T12:00:00Z",
  "message": "snapshot after indexing docs",
  "tool_lock_hash": "sha256:8a32...6ffb",
  "stats": { "files_added": 12, "files_modified": 3, "files_deleted": 1 },
  "commit_type": "manual"
}
```

**canonical バイト列 (JCS)**:

```text
{"commit_type":"manual","created_at":"2026-04-29T12:00:00Z","message":"snapshot after indexing docs","object_type":"commit","parents":["sha256:30fa71e5c11a90a28c8c0895382e8f45df431047fcc699afed45ee316cfbf65a"],"stats":{"files_added":12,"files_deleted":1,"files_modified":3},"tool_lock_hash":"sha256:8a32a740871b1dd9db1bda186dce07e8e6c60d2cd316f21683ea2bd857c16ffb","tree":"sha256:eca8de0abaf2a27a1ea57feff4f44385bcfb3485274e73ddfa7c47144f383e1e"}
```

- `commit_hash` = **`sha256:6b9884a55265cb9dab75ecc79e1e90de145aeae91e3bb5b43538e58fe848eac6`**
- fan-out `ab/cd` = `6b` / `98` → `objects/commits/6b/98/<leaf>`

### A.3b root commit (parents 0 件) ベクタ (`03 §8.1` から導出)

`03 §8.1`「commit の `parents` は commit_hash の配列」より、parents はフィールドとして常在する配列であり、
直前 HEAD が存在しない root commit は **`parents: []`** と表現する (フィールド省略は「配列」定義と矛盾)。

入力: A.3 と同じ tree / tool_lock_hash、`parents: []`、`message: "initial snapshot"`、
`stats: { "files_added": 2, "files_modified": 0, "files_deleted": 0 }`。

```text
canonical: {"commit_type":"manual","created_at":"2026-04-29T12:00:00Z","message":"initial snapshot","object_type":"commit","parents":[],"stats":{"files_added":2,"files_deleted":0,"files_modified":0},"tool_lock_hash":"sha256:8a32a740871b1dd9db1bda186dce07e8e6c60d2cd316f21683ea2bd857c16ffb","tree":"sha256:eca8de0abaf2a27a1ea57feff4f44385bcfb3485274e73ddfa7c47144f383e1e"}
commit_hash = sha256:c0cc8b407ba5e9a8e1769b3919b1c804a1853ad3ab34c9674eb56f81f59e6059
fan-out     = c0 / cc
```

### A.4 fan-out パス導出ベクタ (`03 §2, §8.1`)

```text
入力  commit_hash = "sha256:6b9884a55265cb9dab75ecc79e1e90de145aeae91e3bb5b43538e58fe848eac6"
手順  1. "sha256:" プレフィックスを除いた digest = 6b9884a5...eac6
      2. ab = digest[0:2] = "6b"
      3. cd = digest[2:4] = "98"
出力  格納パス = objects/commits/6b/98/<hash 表記>
```

同規則を tree (`ec/a8`)・raw (RAW-1: `e3/b0`, RAW-2: `bb/e1`) に適用。
leaf ファイル名は `03 §2` のレイアウト定義 (`objects/raw/ab/cd/<raw_hash>` 等) と `03 §8.1` の
hash 表記規則 (`"sha256:" + base16(...)`) の合成により **hash 表記そのもの (= `sha256:` prefix 込み)**。
prefix を除くのは `ab`/`cd` の導出のみ、と spec は明示的に区別している。

### A.5 (P2 参考) chunk identity hash ベクタ (`03 §8.1` chunk。実装は Step 3)

入力 (null/未設定は入力に含めない規則。ここでは section_id あり):

```text
canonical: {"char_end":1500,"char_start":1200,"gen":0,"heading_path":["認証仕様","API Token"],"raw_hash":"sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a","section_id":"auth/api-token","spec_version":1,"tool_profile_hash":"sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0","unit_key":"page:12"}
chunk_hash = sha256:8fefa4825444efb1a120df709f45764a9ac074a9a2c0002ee4307baa7bbfe15a
```

このベクタは非 ASCII の **値** (`heading_path` 日本語) を含み、UTF-8 リテラル直列化で RFC 8785 と一致する
ことの確認材料になる (CT-HASH-009 の根拠データ)。Step 1 では計算しない。

---

## B. テストケース

各ケース: **ID / 優先度 / Given-When-Then / 正本根拠**。

### CT-HASH-* — hash 算出規約 (`03 §8.1`。動機: `08 §6` Evidence Pointer 永続性契約)

**CT-HASH-001** — P0 — raw hash: 空バイト列
- Given: 0 バイトのファイル。
- When: raw object として CAS へ保存する。
- Then: `raw_hash = sha256:e3b0c442...b855` (A.1 RAW-1)。格納先 `objects/raw/e3/b0/<hash 表記>`。
- 根拠: `03 §8.1` (raw = バイト列 content hash / fan-out 規則)。

**CT-HASH-002** — P0 — raw hash: UTF-8 日本語テキスト
- Given: 内容 `認証仕様\n` (UTF-8, 13 バイト) のファイル。
- When: raw object 保存。
- Then: `raw_hash = sha256:bbe1da2e...ac59` (A.1 RAW-2)。fan-out `bb/e1`。
- 根拠: `03 §8.1`。BOM 付与・改行変換など一切せず生バイト列を hash すること。

**CT-HASH-003** — P0 — tree JCS→sha256 (entries 2 件、ソート済み、object_type 込み)
- Given: A.2 の 2 entry。
- When: tree object を JCS 直列化して保存し、保存バイト列を sha256 する。
- Then: canonical バイト列が A.2 と一致し、`tree_hash = sha256:eca8de0a...3e1e`。
- 根拠: `03 §8.1` (tree = 保存バイト列 sha256 / `object_type` 必須 / entries ソート)。
- 補足: Step 1 の raw-only entry の `normalize` ブロックの正しい形は未定義 (§C-2)。本ベクタは
  「normalize ブロックが載る場合」の直列化安定性を固定する。

**CT-HASH-004** — P0 — commit JCS→sha256 (parents 1 件、tool_lock_hash ダミー、timestamp UTC Z)
- Given: A.3 の入力。
- When: commit object を JCS 直列化して保存し sha256。
- Then: canonical バイト列が A.3 と一致し、`commit_hash = sha256:6b9884a5...eac6`。
- 根拠: `03 §8.1` (commit = 保存バイト列 sha256 / parents = commit_hash 配列 / timestamp UTC Z)。

**CT-HASH-005** — P0 — fan-out ab/cd 導出と leaf 名
- Given: A.4 の commit_hash。
- When: 格納パスを導出する。
- Then: `ab=6b`, `cd=98`。leaf ファイル名は hash 表記そのもの (`sha256:` prefix 込み)。
  完全パス = `objects/commits/6b/98/sha256:6b9884a5...eac6`。tree/raw も同規則 (A.4)。
- 根拠: `03 §2` (レイアウト `objects/raw/ab/cd/<raw_hash>`) / `03 §8.1` (hash 表記 = `sha256:`+hex、
  prefix 除去は `ab`/`cd` 導出のみと明示)。
- 補足: `:` を含むファイル名は Windows NTFS で不可。移植時は spec 側の対応が必要になるが、
  これは契約の穴ではなく将来の移植課題 (現行 spec は上記で一意)。

**CT-HASH-006** — P0 — hash 表記の正準形
- Given: 任意の object hash。
- When: 文字列表現を得る。
- Then: `"sha256:" + base16(小文字 hex)`。大文字 hex・prefix 欠落・別アルゴリズム名は不正。
- 根拠: `03 §8.1` (共通規則)。

**CT-HASH-007** — P0 — object 本体は自身の hash を含めない (round-trip)
- Given: 保存済み tree / commit object。
- When: 保存バイト列を再読込して再 sha256 する。
- Then: 保存キー (= hash) と一致する。object 本体に `tree_id` / `commit_id` / 自己 hash フィールドが**無い** (旧フィールドは廃止)。検証は再ハッシュのみで足りる。
- 根拠: `03 §8.1` (「object 本体は自身の hash を含めない」「検証は再ハッシュのみ」)。

**CT-HASH-008** — P0 — JCS 入力キー順非依存
- Given: 同一内容だが JSON 構築時のキー順・entry 内フィールド順が異なる 2 つの tree in-memory 表現。
- When: それぞれ JCS 直列化して hash。
- Then: 同一 `tree_hash`。JCS は canonical 化時にキー順を再決定するため記載順は hash に影響しない。
- 根拠: `03 §8` (「JCS ではキー順は canonical 化時に自動決定」)。

**CT-HASH-009** — P1 — 非 ASCII 値の UTF-8 リテラル直列化 (RFC 8785 差異の確認)
- Given: `message` に日本語を含む commit (例 `"認証仕様の更新"`)。
- When: JCS 直列化。
- Then: 日本語は UTF-8 リテラルバイトで出力 (`\uXXXX` エスケープしない)、ASCII 化をしない。制御文字 (U+0000–001F) と `"` `\` のみエスケープ。RFC 8785 とバイト一致。
- 根拠: `03 §8.1` (「RFC 8785 JCS canonical form の JSON バイト列として保存」) / RFC 8785 §4.2。
- 補足: A.5 の chunk ベクタ (`heading_path` 日本語) が同性質の参照データ。

**CT-HASH-010** — P1 — object_type による種別分離
- Given: `object_type` を除けば同一構造になりうる 2 object。
- When: それぞれ hash。
- Then: `object_type` 値 (`"tree"` vs `"commit"`) の差で hash が異なる。`object_type` 欠落 object は保存前に拒否 (種別誤認防止)。
- 根拠: `03 §8.1` (「種別誤認防止のため `object_type` を必須で含める」)。

**CT-HASH-011** — P2 — chunk identity hash ベクタ (Step 3 前倒し確認)
- Given: A.5 の入力。
- When: JCS→sha256。
- Then: `chunk_hash = sha256:8fefa482...e15a`。`text_hash` は hash 入力に含めない。null/未設定フィールド (例 section_id 無し strategy) は入力から省く。
- 根拠: `03 §8.1` (chunk identity hash / `text_hash` 非包含 / null 省略)。**Step 1 範囲外**。

### CT-TREE-* — tree 契約 (`03 §3, §8, §8.1, §8.2`)

**CT-TREE-001** — P0 — entries は path UTF-8 バイト昇順に一意ソート
- Given: 追加順が `report.pdf`, `notes.md` の 2 entry (未ソート)。
- When: tree object を組み立てて直列化。
- Then: 保存 entries は `notes.md`, `report.pdf` の順 (A.2)。挿入順・辞書ロケール順に依存しない。
- 根拠: `03 §8.1` (「entries は `path` の UTF-8 バイト列昇順で一意にソート」)。

**CT-TREE-002** — P0 — 重複 path 禁止
- Given: 同一 `path` を 2 回持つ entry 集合。
- When: tree 構築。
- Then: schema violation として拒否 (成功保存しない)。
- 根拠: `03 §8.1` (「同一 `path` の重複 entry は禁止」)。

**CT-TREE-003** — P0 — path 区切り (`/`) を含む path は `KIO-E-STORE-PATH-001` で拒否
- Given: entry `path = "sub/report.pdf"`。
- When: tree 構築 / 保存。
- Then: `error_code = KIO-E-STORE-PATH-001`、書き込みしない、exit 2 (schema validation 失敗)。
- 根拠: `03 §3` (「`/` を含む path を持つ tree/pointer は schema violation `KIO-E-STORE-PATH-001`」) / `06 §8` (error code 定義) / `06 §7` (exit 2)。

**CT-TREE-004** — P0 — `normalize.gen` 欠落は gen 0 と読む (forward compatible)
- Given: `normalize` ブロックに `gen` を含まない過去形式の tree entry を読む。
- When: entry を解釈する。
- Then: `gen = 0` として扱う。読み替えは解釈時のみで、既存 object の hash は不変。
- 根拠: `03 §8` (「フィールド欠落は `gen = 0` と読む (forward compatible)」)。

**CT-TREE-005** — P1 — flat entries (サブツリー object を作らない)
- Given: 直下 3 ファイルの scope。
- When: tree 生成。
- Then: 単一 tree object に 3 entry を flat 配列で保持。ディレクトリ単位のサブツリー object は生成しない。
- 根拠: `03 §8.2` (「tree は entries を単一の flat 配列で持つ」)。

**CT-TREE-006** — P2 — 直下ファイル数 soft limit 超過警告 (Step 2 送り)
- Given: 直下ファイル数が 10,000 (soft limit) を超える scope。
- When: `kio index` を実行。
- Then: 警告を表示するが処理は継続する (エラーにしない)。
- 根拠: `03 §8.2` (「超過時 `kio index` は警告を表示し…処理自体は継続する」)。
- 補足: 警告の契機は spec 上 **`kio index`** であり、`kio index` は Step 2 割当 (`09 §3.1`)。
  したがって Step 1 では検証不能 → P2 (Step 2 で昇格)。snapshot 経路への警告適用は spec に無い
  (過剰契約になるため課さない)。

**CT-TREE-007** — P1 — tree の `object_type` 必須
- Given: `object_type` を欠く tree byte列。
- When: 保存 / inspect による解釈。
- Then: 拒否 (CT-HASH-010 と同一根拠を tree で確認)。
- 根拠: `03 §8.1`。

**CT-TREE-008** — P1 — 空 tree (entries 0 件) の canonical 表現
- Given: 直下対象ファイルが 0 の scope で tree を生成する。
- When: tree object を直列化。
- Then: canonical バイト列 `{"entries":[],"object_type":"tree"}`、
  `tree_hash = sha256:849dc4fa...a967` (A.2b)。毎回同一 (決定論)。
- 根拠: `03 §8` (`entries` は配列 — 0 件は `[]` で一意) / `03 §8.1` (直列化規則)。

**CT-TREE-009** — P1 — 生成される tree entry のフィールドと raw_hash 形式
- Given: snapshot が生成した tree の各 entry。
- When: entry を検査。
- Then: `path` / `type` / `raw_hash` を持ち、`raw_hash` は `^sha256:[0-9a-f]{64}$` に一致する。
- 根拠: `03 §8` (tree entry schema) / `03 §8.1` (hash 表記 = `sha256:` + 小文字 hex)。
- 補足: `type` の値域 (`"file"` 以外の有無) は未定義 (§C-11)。本テストは `type` の存在のみ assert。

### CT-COMMIT-* — commit 契約 (`03 §8, §8.1` / `05 §2, §8` / `06 §12`)

**CT-COMMIT-001** — P0 — commit_type 7 値 enum を受理
- Given: `commit_type ∈ {manual, auto, imported, migrated, repaired, merged, purged}`。
- When: commit 生成 / 保存 (Step 1 で実際に発行するのは manual/auto。他 5 値は schema 受理のみ確認)。
- Then: 全 7 値が CHECK 制約を通過する。
- 根拠: `05 §2.1` (CHECK 制約 7 値) / `03 §8` (enum)。

**CT-COMMIT-002** — P0 — 不正 commit_type を拒否
- Given: `commit_type = "snapshot"` 等、enum 外の値。
- When: commit 保存。
- Then: 拒否 (SQLite CHECK 制約 / schema validation)、書き込みしない。exit 2。
- 根拠: `05 §2.1` (「SQLite CHECK 制約で固定」) / `03 §8` (「値域は永久に変更しない契約」)。

**CT-COMMIT-003** — P0 — parents 先頭 = first parent (直前 HEAD)
- Given: HEAD = commit C1。C1 から派生する新 commit C2 を作る。
- When: C2 を生成。
- Then: `C2.parents[0] == C1 の commit_hash`。parents は commit_hash の配列。
- 根拠: `03 §8.1` (「parents の第一要素は直前 HEAD (first parent)」)。

**CT-COMMIT-004** — P0 — root commit の parents は `[]`
- Given: 空の履歴 (HEAD 無し) で最初の commit を作る。
- When: root commit を生成。
- Then: `parents` フィールドは存在し値は `[]`。A.3b の入力なら
  `commit_hash = sha256:c0cc8b40...6059`。
- 根拠: `03 §8.1` (「commit の `parents` は commit_hash の配列」— 配列として常在。直前 HEAD が
  無い場合の要素は 0 件。フィールド省略は配列定義と矛盾するため不可)。

**CT-COMMIT-005** — P0 — no-op: tree 不変なら auto snapshot は新 commit を作らない
- Given: HEAD commit の tree_hash = T。working tree が不変 (再計算しても tree_hash = T)。
- When: `kio index` 成功完了相当の auto snapshot 契機 (Step 1 では snapshot 経路で tree 再計算) が走る。
- Then: 新 commit を作らない (no-op)。tree も CAS なので新規 object を生成しない。HEAD 不変。
- 根拠: `05 §8.1` (「tree_hash が現在の HEAD の tree と一致する場合は commit を作らない (no-op)」) / `03 §8.2`。

**CT-COMMIT-006** — P1 — manual `kio snapshot`/`commit` の unchanged tree 時挙動
- Given: HEAD tree 不変。
- When: 明示 `kio snapshot` / `kio commit -m ...`。
- Then: **未定義 (§C-3)**。§8.1 の no-op は auto snapshot にのみ明記。テストは実装決定 (no-op か empty commit 生成か) を固定し、その決定を assert する。
- 根拠: `05 §8.1` (no-op は auto に限定した記述) / `06 §1`。

**CT-COMMIT-007** — P0 — HEAD / refs/heads/* / refs/tags/* の値は commit_hash
- Given: commit C を作り HEAD を進める / tag を打つ。
- When: `.kio/HEAD`, `.kio/refs/heads/main`, `.kio/refs/tags/<name>` を読む。
- Then: 各ファイルの値は commit_hash (= `sha256:` + 64 hex) そのものである (symbolic ref 等の
  間接形式ではない)。
- 根拠: `03 §8.1` (「`HEAD` / `refs/heads/*` / `refs/tags/*` の値は commit_hash」— HEAD 含め直値と定義済み)。

**CT-COMMIT-008** — P0 (**Step 2 ゲートへ移動** — 2026-07-03 監査裁定: `kio index` が Step 2 割当のため Step 1 では原理的に検証不能。4 エンジン監査一致) — commit_type=auto は index 成功完了時に生成される
- Given: working tree に変更あり。
- When: `kio index` 成功完了 (Step 1 の取り込み経路)。
- Then: 同一プロセス内で `commit_type=auto` の commit が 1 つ作られる (tree 変化時)。
- 根拠: `05 §8.1` (契機 2) / `09 §1.1` (「kio index 完了時の auto snapshot」)。
- 補足: Step 1 に本格 pipeline は無い。`kio index` 自体が Step 2 割当のため、Step 1 で auto 契機を検証できない場合は本ケースを **P1 に降格 or Step 2 送り** とし、Step 1 は manual snapshot と no-op (CT-COMMIT-005) の検証に集中してよい (§C-4 関連)。

**CT-COMMIT-009** — P1 — snapshot の自動 message 形式
- Given: `-m` を省略した `kio snapshot`。
- When: commit 生成。
- Then: `message` が `"snapshot at <UTC timestamp>"` 形式 (timestamp は UTC ISO8601+Z)。
- 根拠: `06 §1` (「-m 省略時は自動 message (\"snapshot at <UTC timestamp>\")」) / `06 §12`。

**CT-COMMIT-010** — P0 — created_at は UTC ISO8601 + `Z`
- Given: 任意の commit 生成。
- When: `created_at` を読む。
- Then: `2026-04-29T12:00:00Z` 形式。TZ 欠落 (`...12:00:00`) や local (`+09:00`) を **永続化しない**。
- 根拠: `06 §12` (「UTC ISO8601 拡張形式 + suffix `Z` に固定」正/誤例) / `03 §8.1`。
- 補足: 秒精度か μ秒精度 (`.123456Z`) かは両方許容 (§C-10)。

**CT-COMMIT-011** — P1 — refs (heads / tags) 更新は temp + atomic rename (部分書き込みを外部に見せない)
- Given: (a) refs/heads/main を新 commit へ進める。(b) `kio tag` で refs/tags/<name> を作る。
- When: 更新中に別プロセスが同 ref を読む。
- Then: 旧値か新値のいずれか (中間・切れた値を観測しない)。更新は `.kio/.lock` 保持下で temp file 書き込み + atomic rename。heads と tags の両方で確認する。
- 根拠: `05 §6` (「refs (refs/heads/main, refs/tags/*) の更新は `.kio/.lock` 保持下で、temp file 書き込み + atomic rename により行う」)。

**CT-COMMIT-012** — P1 — 生成 commit は `03 §8` schema の全フィールドを持つ
- Given: `kio snapshot` が生成した commit object。
- When: フィールドを検査。
- Then: `object_type` / `tree` / `parents` / `created_at` / `message` / `tool_lock_hash` / `stats` /
  `commit_type` を持つ。`stats` は `files_added` / `files_modified` / `files_deleted` (整数) を持つ。
  `tree` / `tool_lock_hash` / `parents[]` は hash 表記 (`^sha256:[0-9a-f]{64}$`)。
- 根拠: `03 §8` (commit object schema) / `03 §8.1` (hash 表記)。
- 補足: 手書きの不正 object (フィールド欠落) を **読む** 側の validation は spec 未規定のため契約化しない
  (`object_type` 欠落の拒否のみ CT-HASH-010/CT-TREE-007 で明示根拠あり)。

### CT-GC-* — `gc_policy` / `protected` × commit_type schema 遵守 (`05 §2.1, §2.2, §2.6`。GC は実行しない)

**CT-GC-001** — P0 — gc_policy(commit_type) マッピング
- Given: 各 commit_type。
- When: `gc_policy` を引く (Step 1 は schema/純関数のみ。回収は実行しない)。
- Then:
  - `auto → shallow`, `migrated → shallow`, `repaired → shallow`
  - `manual → none`, `imported → none`, `merged → none`, `purged → none`
- 根拠: `05 §2.2` (gc_policy 表)。

**CT-GC-002** — P0 — `full` はどの commit_type にも割り当てない
- Given: 全 commit_type。
- When: gc_policy を引く。
- Then: 戻り値に `full` が現れない (commit object は append-only、削除経路が存在しない)。
- 根拠: `05 §2.2` (「full (commit object の削除) はどの commit_type にも適用しない」) / `05 §2.6`。

**CT-GC-003** — P1 — Step 1 は GC を実行しない
- Given: 任意の履歴。
- When: Step 1 の通常操作 (init/status/snapshot/log/diff/inspect/tag)。
- Then: tree/commit/raw いずれの object も回収・削除されない。shallow 化も起きない (Step 1 に GC 実行系は無い)。`kio gc` は Step 1 対象外コマンド (§D 参照)。
- 根拠: `05 §2.2` 冒頭 (「GC の実装は Phase 4+…MVP では GC を実行せず…schema のみ Step 1 の設計時から契約として遵守」) / `09 §3.1` (`kio gc` = Phase 4+)。

**CT-GC-004** — P1 — protected(commit_type) マッピング
- Given: 各 commit_type。
- When: `protected` フラグを引く。
- Then: `manual / imported / merged / purged → true`、`auto / migrated / repaired → false`。
- 根拠: `05 §2.1` (commit_type 表の protected 列)。

### CT-SCOPE-* — スコープ境界 (`03 §3`)

**CT-SCOPE-001** — P0 — 直下のみ (サブフォルダ配下ファイルは tree に入らない)
- Given: scope 直下に `a.pdf`、サブフォルダ `sub/` 配下に `b.pdf`。
- When: snapshot の tree を生成。
- Then: tree entries は `a.pdf` のみ。`sub/` 配下は (`sub/` に子 `.kio` があってもなくても) 親 tree に含めない。
- 根拠: `03 §3` 規則1 (「管理対象は scope フォルダ直下のファイルに限る。…再帰包含は行わない」)。

**CT-SCOPE-002** — P1 — path_at_commit / input_path も `/` を含まない
- Given: Evidence Pointer / task descriptor (Step 3+) の path フィールド。
- When: 生成する。
- Then: `/` を含む場合 `KIO-E-STORE-PATH-001` (CT-TREE-003 と同一契約)。**Step 1 では tree entry path のみが実対象**、pointer/task は Step 3+ につき参考。
- 根拠: `03 §3` 規則3 / `08 §2` (`path_at_commit` は `/` を含まない)。

### CT-CLI-* — CLI 契約 (`06 §1, §4, §7, §8, §11, §12`)

**CT-CLI-001** — P0 — `kio init` が `.kio` レイアウトを生成
- Given: 未初期化フォルダ。
- When: `kio init`。
- Then: exit 0。`.kio/` 配下に少なくとも `HEAD`, `refs/heads/`, `objects/{raw,trees,commits}/`, `config.toml`, `scope.json` を生成。`scope.json` に ULID の `scope_id` を採番 (以後不変)。現在フォルダのみ作成し子 `.kio` は作らない。
- 根拠: `06 §1` (「`kio init` は現在フォルダの `.kio` のみ作成」) / `03 §2` (レイアウト) / `03 §2` scope.json (「scope_id (init 時採番の ULID、以後不変)」)。

**CT-CLI-002** — P1 — `kio init` を初期化済みフォルダで実行
- Given: 既に `.kio` があるフォルダ。
- When: `kio init`。
- Then: **未定義 (§C-5)**。テストは実装決定 (冪等 no-op / エラー exit 2) を固定し assert。scope_id を再採番しない (既存 scope_id 保全) ことは最低限の不変条件として P1 で確認。
- 根拠: `03 §2` (scope_id 不変) — 二重 init は明記なし。

**CT-CLI-003** — P0 — `kio status` は exit 0 (clean/成功時)
- Given: 初期化済み scope。
- When: `kio status`。
- Then: ファイル状態 (new/modified/deleted; §CT-STATE) を表示し exit 0。全 up_to_date 相当 (Step 1 は pipeline 無しなので「変更なし」) で 0。
- 根拠: `06 §1` (status) / `06 §7` (`0 成功 / 全 up_to_date`)。
- 補足: Step 1 での status の状態語彙は §C-4 (pipeline 由来状態の扱い) 参照。

**CT-CLI-004** — P0 — `kio snapshot` / `kio commit` は同一履歴 object を作る (alias 同値)
- Given: 変更ありの scope。
- When: `kio snapshot create -m "msg"` と、別 fixture で `kio commit -m "msg"`。
- Then: 両者とも commit object を生成し exit 0。`commit` は `snapshot` の alias で内部的に同一 object を作る (同一入力なら同一 commit_hash)。
- 根拠: `06 §1` (「`commit` は…alias。内部的には同じ履歴 object を作る」)。

**CT-CLI-005** — P0 — `kio log` は履歴 commit を列挙して exit 0
- Given: 2 commit の履歴。
- When: `kio log`。
- Then: exit 0。両 commit が出力に含まれる (hash で識別)。
- 根拠: `06 §1` (log) / `06 §7`。
- 補足: **列挙順序・遡行規則 (first-parent / 全 DAG / 新旧順) は 06 に未定義** (§C-9)。順序は
  「決定論的に毎回同一」のみ assert し、具体順は実装確定後に固定する。

**CT-CLI-006** — P0 — `kio diff <a> <b>` は 2 commit の tree 差分を提示して exit 0
- Given: commit A (files: a.pdf) と commit B (files: a.pdf 変更 + b.pdf 追加)。
- When: `kio diff A B`。
- Then: exit 0。変更のあったファイル (a.pdf, b.pdf) が差分として出力に現れ、無変更ファイルは差分と
  して現れない。差分の判定基盤は tree entry の raw_hash 比較。
- 根拠: `06 §1` (diff) / `03 §8` (tree entries が比較対象データであること)。
- 補足: **added/modified/deleted の表示分類・出力書式は 06/03 から導けない** (§C-7)。分類語彙は
  契約化せず、実装確定後に固定。差分ありでの exit code 意味論も未定義 (§C-7)。本テストは正常系 exit 0 のみ。

**CT-CLI-007** — P0 — `kio inspect <hash>` は object を JSON 表示
- Given: 保存済み tree / commit hash。
- When: `kio inspect <hash>`。
- Then: exit 0。当該 object の JSON を表示。`--json` では完全 hash (CT-CLI-009)。
- 根拠: `06 §1` (「inspect <hash> object を JSON で表示」)。

**CT-CLI-008** — P0 — `kio tag <name> [<commit>]` が ref を作る
- Given: commit C。
- When: `kio tag v1 C` (commit 省略時は HEAD 対象と仮定、§C-6)。
- Then: exit 0。`.kio/refs/tags/v1` の値が C の commit_hash (CT-COMMIT-007)。
- 根拠: `06 §1` (tag) / `03 §8.1` (refs/tags/* = commit_hash)。
- 補足: 同名再 tag・tag 削除・commit 省略時の既定は未定義 (§C-6)。

**CT-CLI-009** — P0 — `--json` は完全 hash + 絶対 path + 色なし
- Given: 任意コマンドの `--json`。
- When: 実行。
- Then: 出力の hash は短縮せず完全形 (`sha256:` + 64 hex)、path は絶対、ANSI 色なし。
- 根拠: `06 §4` (「`--json` は色なし + 絶対 path + 完全 hash」) / `03 §8.1` (「`--json` は完全 hash」)。

**CT-CLI-010** — P2 — 人間向け短縮表示は「する場合は先頭 12 hex」
- Given: `--json` なしの log/inspect が hash を短縮表示する実装を選んだ場合。
- When: 実行。
- Then: 短縮形式は先頭 12 hex (`sha256:9f2c1a7b04de…`)。
- 根拠: `03 §8.1` (「人間向け表示は先頭 12 hex への短縮**可**」— 許可であって必須ではない)。
- 補足: 短縮の要否は実装裁量のため契約は「短縮するなら 12 hex 形式」のみ。必須契約は CT-CLI-009 (--json 完全 hash) 側。

**CT-CLI-011** — P0 — error object の形と error_code 形式
- Given: 任意のエラー (例 CT-TREE-003 の path 違反)。
- When: エラーを返す。
- Then: `{ "error_code": "...", "message": "...", "context": {...} }` 形式。`error_code` は `KIO-E-<DOMAIN>-<SUBDOMAIN>-<NNN>` に一致 (DOMAIN は `06 §8` の 12 値のいずれか)。
- 根拠: `06 §4` (error 形式) / `06 §8` (error code namespace / DOMAIN 一覧)。

**CT-CLI-012** — P0 — invalid usage / schema validation 失敗は exit 2 (Step 1 対象 schema 網羅)
- Given: (a) 未知フラグ、(b) schema 違反の `.kio/config.toml`、(c) schema 違反の `.kio/scope.json`、
  (d) schema 違反の `.kio/manifest.json`、(e) enum 外 commit_type、(f) `/` 入り path。
- When: CLI 起動 / 当該操作を実行。
- Then: いずれも exit 2。schema 違反 (b)(c)(d) は `KIO-E-CONFIG-SCHEMA-NNN` を返す。
- 根拠: `06 §7` (`2 invalid usage / config 不正 / schema validation 失敗`) / `06 §11` (「validation 失敗は exit 2 + `KIO-E-CONFIG-SCHEMA-NNN`」/ 対象ファイル一覧) / `09 §3.1` (「JSON Schema validation (Step 1 は scope / manifest / config)」)。

**CT-CLI-013** — P1 — `kio inspect` 存在しない hash
- Given: 未保存の hash。
- When: `kio inspect <hash>`。
- Then: エラー。error_code は STORE domain が妥当だが**具体コード・exit code は未定義 (§C-8)**。テストは実装決定を固定。
- 根拠: `06 §8` (STORE domain) — 具体コード明記なし。

**CT-CLI-014** — P1 — exit code 体系の網羅 (Step 1 到達可能値のみ)
- Given: 各条件。
- When: 実行。
- Then: `0 成功`, `2 invalid usage/schema`, `8 incompatible format version` (CT-CLI-018), `9 confirm 拒否` (Step 1 では purge 系が無いため到達経路は限定。tag 上書き確認等を設ける場合のみ) を確認。`5 auth`, `6 budget` は Step 2+ 機能に紐づき Step 1 では通常到達しない。
- 根拠: `06 §7` (exit code 一覧)。

**CT-CLI-015** — P2 — Step 1 範囲外コマンドの扱い
- Given: `kio search` / `kio index` / `kio purge` / `kio restore` 等 (Step 2+/3+/4)。
- When: Step 1 バイナリで実行。
- Then: **未定義 (§C-14)**。テストは「未実装コマンドが exit 0 で成功を偽装しない」ことのみ確認し、
  具体 exit code は実装決定を固定する。
- 根拠: `06 §1` (正本コマンド一覧) / `09 §3.1` (実装時期の割当) — 未実装期間の CLI 挙動は spec に無い。

**CT-CLI-016** — P1 — `kio init [<path>]` の path 指定
- Given: 存在するフォルダ `<path>` (カレント以外)。
- When: `kio init <path>`。
- Then: exit 0。`<path>/.kio` が作られる (カレントには作らない)。生成内容は CT-CLI-001 と同一契約。
- 根拠: `06 §1` (`kio init [<path>]` 構文)。
- 補足: `<path>` 不存在時の挙動 (作成 or エラー) は未定義 — 実装決定を固定 (§C-5 に併記)。

**CT-CLI-017** — P1 — `kio log --at <commit>` / `--since <dur>` の引数受理
- Given: 有効な commit hash と `7d` 形式の duration。
- When: `kio log --at <commit>` / `kio log --since 7d`。
- Then: exit 0 (受理してエラーにしない)。不正な duration (例 `--since banana`) は exit 2 (invalid usage)。
- 根拠: `06 §1` (`kio log [--at <commit>] [--since <dur>]` 構文) / `05 §1.6` (`--since 7d` の duration 形式) / `06 §7` (exit 2)。
- 補足: log における `--at` / `--since` の絞り込み意味論は未定義 (§C-9 に併記)。受理契約のみ。
- **2026-07-03 監査裁定**: Step 1 は発注書暫定判断 #9 (受理して "not implemented" exit 1) を正とし、本ケースの exit 0/2 契約は **Step 4 (--at 実装時) に移行**する。文書間矛盾は本注記で解消。

**CT-CLI-018** — P1 — 非互換 `kio_format_version` は exit 8
- Given: `kio_format_version` が実装より MAJOR で新しい `.kio`。
- When: 任意のコマンドを実行。
- Then: exit 8 (incompatible format version)。データを書き換えない。
- 根拠: `06 §7` (`8 incompatible profile / format version`) / `03 §2` (`kio_format_version`、semver は 10 §12.5)。

### CT-LOCK-* — 並行性 / `.kio/.lock` (`05 §5, §6`)

**CT-LOCK-001** — P0 — 書き込み系コマンドの同時実行で store が壊れない (排他不変条件)
- Given: 同一 `.kio` に対し 2 つの書き込み系プロセス (例 `kio snapshot` × 2)。
- When: ほぼ同時に起動。
- Then: **高々 1 プロセスのみが critical section を進め**、object store / refs は一貫した状態を保つ (部分 commit・破損 ref・重複 HEAD 前進が起きない)。もう一方は「失敗」または「待機後に成功」のいずれか (§C-1)。最終的に矛盾のない履歴になる。
- 根拠: `05 §5` (「同一 `.kio` に対する多重起動は `.kio/.lock` で防止する」) / `05 §6` (`.kio/.lock` を取得するコマンド一覧に snapshot が含まれる)。
- 注: 書き込み系一覧のうち Step 1 で存在するのは `kio snapshot (= commit)`。`index/gc/purge/repair/move` は Step 2+。`kio tag` は 05 §6 の一覧に無い (§C-12 の隣接論点)。

**CT-LOCK-002** — P1 — lock 競合時の敗者挙動 (fail-fast vs block-wait) と error code
- Given: CT-LOCK-001 と同条件。
- When: 敗者プロセスが lock を取れない。
- Then: **未定義 (§C-1)**。spec は「防止」とのみ記述し、即時失敗か待機か、timeout、専用 error_code (現状 `KIO-E-*-LOCK-*` は未定義) を規定しない。テストは実装決定を固定し、選ばれた挙動を assert (即時失敗なら安定した error_code + exit、待機なら bounded な待機後成功)。
- 根拠: `05 §5, §6` — 敗者挙動の明記なし。

**CT-LOCK-003** — P0 — 読み取り系 (log / inspect) は `.kio/.lock` を取得しない
- Given: 書き込み系 (`kio snapshot`) 実行中。
- When: 同時に `kio log` / `kio inspect` を実行。
- Then: 読み取り系は lock を待たずに実行できる (旧スナップショットを読む)。読み取り系が `.kio/.lock` を取得しない。
- 根拠: `05 §6` (「読み取り系 (search / log / view / inspect / evidence verify / restore) は `.kio/.lock` を取得しない」— Step 1 コマンドでは **log と inspect のみ** がこの明示リストに含まれる)。
- 補足: `status` / `diff` は 05 §6 の読み取り系リストにも書き込み系リストにも**現れない** — lock 分類は未定義 (§C-12)。本テストの対象から除外。

**CT-LOCK-004** — P1 — refs の atomic 更新 (部分 ref 不可視)
- CT-COMMIT-011 と同一 (lock 観点。heads / tags 両方)。

### CT-STATE-* — files 状態分類 (Step 1 で判定可能なもの) (`03 §6, §8`)

**CT-STATE-001** — P0 — `new`: 初めて観測した原文
- Given: scope 直下に未登録ファイル。
- When: `kio status`。
- Then: 当該ファイルの状態が `new` と分類・表示される。
- 根拠: `03 §6` (状態分類 `new 初めて見つかった原文`) / `06 §1` (status はファイル状態を表示)。
- 補足: 分類の**観測結果**のみを契約とする。files 行の生成・更新を `kio status` が行うか
  (スキャンの実行主体・書き込み副作用) は 03 §6/§8 に未定義 (§C-13)。

**CT-STATE-002** — P0 — `modified`: path 同じで raw_hash 変化
- Given: 既登録 `a.pdf` の内容を変更 (raw_hash 変化)。
- When: `kio status`。
- Then: `modified` と分類・表示される。
- 根拠: `03 §6` (`modified path 同じだが raw_hash が変わった`)。

**CT-STATE-003** — P1 — `deleted`: files 行を DELETE せず status 更新 + 最終 raw_hash 保持
- Given: 既登録ファイルを OS 上で削除。
- When: 削除が検出される (検出主体は §C-13)。
- Then: files 行を物理削除せず `status='deleted'` に更新し、最後に観測した raw_hash を保持。
- 根拠: `03 §8` (「ファイル削除を検出しても files 行は DELETE しない。`status = 'deleted'` に更新し、最後に観測した raw_hash を保持」)。

**CT-STATE-004** — P1 — 削除 path の再作成で status 復帰
- Given: `deleted` 状態の path に同名ファイルを再作成。
- When: 再作成が検出される。
- Then: status を非 deleted に戻す (新 raw_hash なら modified 相当)。
- 根拠: `03 §8` (「同一 path が再作成されたら status を戻す」)。

**CT-STATE-005** — P2 (注記) — Step 1 で判定 **できない** 状態
- `up_to_date` / `tool_changed` / `partial` / `missing_output` / `failed` / `pending` は最新 normalized instance (Markdownize, Step 2) と unit object の存在を前提とする (`03 §6`)。Step 1 に pipeline は無いためこれらは判定不能 → **Step 1 のテスト対象外**。これらを Step 1 status が返すなら仕様矛盾 (§C-4)。
- 根拠: `03 §6` (判定は「最新 normalized instance の manifest と unit object の存在のみで決定」) / `09 §3.1` (Markdownize = Step 2)。

### CT-OBS-* — 観測ログ (`06 §13` / `05 §7`。`09 §3.1` で events/errors は Step 1 割当)

**CT-OBS-001** — P0 — commit イベントが `events.jsonl` に記録される
- Given: `kio snapshot` で commit を作る。
- When: `~/.local/share/kio/logs/events.jsonl` を読む。
- Then: commit イベント行が追記されている。行は JSON で必須フィールド
  `ts, level, code, component, message, context` を持つ。`ts` は UTC ISO8601+Z (`06 §12`)。
- 根拠: `06 §13` / `05 §7` (「events.jsonl 重要イベント (commit, gc, purge, schema migration)」/ 必須フィールド) / `09 §3.1` (観測ログ events/errors = Step 1)。

**CT-OBS-002** — P0 — エラーが `errors.jsonl` に error_code 付きで記録される
- Given: error_code を伴う失敗 (例 CT-TREE-003 の `KIO-E-STORE-PATH-001`)。
- When: `~/.local/share/kio/logs/errors.jsonl` を読む。
- Then: 当該エラー行が追記され、必須フィールド `ts, level, code, component, message, context` を持ち、
  `code` が発生した error_code と一致する。
- 根拠: `06 §13` / `05 §7` (「errors.jsonl error_code 付きの全エラー」/ 必須フィールド) / `09 §3.1`。

---

## C. 未定義事項 (spec に無い挙動 — 実装者判断 + 要 spec 追記)

> これらは **憶測で契約化しない**。各テストは「実装が選んだ挙動を固定し決定論性を assert する」に留め、
> 値の正本化は spec 追記後に行う。**#1 と #2 の 2 件が真の要-spec (Step 1 着手前の追記を強く推奨)**。
> #3 以降は実装者判断で固定し、事後に spec へ反映すれば足りる。
>
> (r2 注記: 旧 #1 fan-out leaf 名 / 旧 #2 HEAD 格納形式 / 旧 #3 root parents / 旧 #11 空 tree の 4 件は
> spec から導出可能と再判定し、契約テストへ昇格済み — CT-HASH-005 / CT-COMMIT-007 / CT-COMMIT-004+A.3b / CT-TREE-008+A.2b)

1. **lock 競合時の敗者挙動 + error code (要-spec)** — `05 §5,§6` は「防止」とのみ。即時失敗/待機、
   timeout、専用 error_code (`KIO-E-*-LOCK-*` は未定義) が無い。影響: CT-LOCK-001/002。
2. **Step 1 の raw-only tree entry の `normalize` ブロック (要-spec)** — `03 §8` の tree entry schema は
   `normalize: {tool_profile_hash, gen}` を持つが、Markdownize は Step 2。Step 1 で raw のみ取り込んだ
   ファイルの entry の `normalize` を何で埋めるか (省略可? tool_profile_hash=null? gen だけ?) が未定義。
   A.2 のベクタは「normalize 済み entry」を前提にしており、**Step 1 純 raw tree の正しい entry 形が別途必要**。
   影響: CT-HASH-003 / CT-TREE-001/009 の適用範囲。**Step 1 実装の最初の意思決定点**。
3. **manual snapshot の unchanged-tree 挙動** — `05 §8.1` の no-op は auto snapshot にのみ明記。
   明示 `kio snapshot`/`commit` で tree 不変時、no-op か empty commit 生成か未定義。影響: CT-COMMIT-006。
4. **Step 1 の `kio status` 状態語彙** — `03 §6` の状態機械は normalized instance (Step 2) を前提とし、
   pipeline の無い Step 1 で `up_to_date` 等が何を意味するか未定義。Step 1 は raw_hash+path 由来の
   new/modified/deleted のみ判定可能と解すべきだが spec に「Step 1 の縮退状態」の記述が無い。影響: CT-CLI-003 / CT-STATE-005。
   関連: CT-COMMIT-008 (`kio index` 自体が Step 2 割当なのに auto snapshot 契機は index 完了時、という Step 境界の齟齬)。
5. **`kio init` の冪等性・path 引数の細部** — 初期化済みフォルダへの再 init が no-op かエラーか未定義
   (scope_id 不変のみ既知)。`kio init <path>` の `<path>` 不存在時の挙動も未定義。影響: CT-CLI-002/016。
6. **`kio tag` の詳細** — 同名再 tag (上書き/エラー)、tag 削除、`<commit>` 省略時の既定 (HEAD?) が未定義。影響: CT-CLI-008。
7. **`kio diff` の出力形式と exit code 意味論** — added/modified/deleted の表示分類・出力書式が
   06/03 から導けない。差分ありで非 0 にするか (git `--exit-code` 相当) 常に 0 か、受理する ref 形
   (tag/HEAD/短縮 hash) も未定義。影響: CT-CLI-006。
8. **`kio inspect` の失敗 error/exit code** — 存在しない/不正 hash 時の具体 error_code (STORE?) と exit code が未定義。影響: CT-CLI-013。
9. **`kio log` の列挙順序・遡行規則・絞り込み意味論** — 新旧順 / first-parent か全 DAG か、
   `--at` / `--since` が log で何を絞るかが 06 に無い。影響: CT-CLI-005/017。
10. **created_at の精度** — 秒 (`Z`) か μ秒 (`.NNNNNNZ`) か、KIO が生成時どちらを出すか未定義 (`06 §12` は両方「正」)。影響: CT-COMMIT-010 の生成側再現性。
11. **tree entry `type` の値域** — `03 §8` 例は `"file"` のみ。symlink/その他の扱いが未定義 (直下のみ規則では実質 file のみ)。影響: CT-TREE-009。
12. **`status` / `diff` の lock 分類** — `05 §6` の読み取り系明示リスト (search/log/view/inspect/
    evidence verify/restore) にも書き込み系リストにも `status` / `diff` が現れない。`kio tag` (refs 書き込み)
    が書き込み系リストに無いのも同種の穴。影響: CT-LOCK-003 / CT-COMMIT-011。
13. **files 行の生成・更新主体** — `03 §8` は files テーブルの不変条件 (DELETE しない等) を定めるが、
    どのコマンド (`status`? `index`? snapshot?) がスキャンして行を生成・更新するかは未定義。影響: CT-STATE-001/003/004。
14. **Step 1 バイナリにおける未実装コマンドの挙動** — Step 2+ 割当コマンド (`search`/`index`/`purge` 等)
    を Step 1 バイナリが受けたときの exit code / メッセージが spec に無い。影響: CT-CLI-015。

---

## D. Step 1 範囲外として意図的に除外したもの (根拠付き)

以下は Step 1 の契約テストに **含めない**。理由は `09 §3.1` (機能×Step 割当) と各正本 §。

| 除外項目 | 除外理由 (根拠) |
| --- | --- |
| Prepare / Markdownize (full/incremental) / Adapter 実行 / normalized_unit / 全文 view | `09 §3.1`: Step 2。`03 §2.1`, `07`, `04 §3`。ゆえに §C-4/§C-2 の pipeline 状態も除外 |
| `kio index` の実行系 (preview / 承認 / soft limit 警告含む) | `09 §3.1`: Step 2 (`06 §2`)。CT-TREE-006 / CT-COMMIT-008 は該当部分を P2/条件付きに留めた |
| chunk / embedding / FTS5 / sqlite-vec の生成 | `09 §3.1`: Step 3 (`04 §4`)。CT-HASH-011 (chunk) / A.5 は **P2 参考ベクタのみ** |
| 検索 (text/vector/hybrid/RRF/MMR/cursor/multi-scope) | `09 §3.1`: Step 3 (`05 §1`)。`kio search`・`searched_scopes` 等は対象外 |
| Evidence Pointer 発行・解決 / `kio open` / `kio view` / verify / retarget | `09 §3.1`: Step 3-4 (`08`)。本書では Pointer 永続性は **hash 安定性テストの動機付け** (`08 §6`) としてのみ参照 |
| restore / `--at` / `--all-history` / `--include-deleted` / time-travel | `09 §3.1`: Step 4 (`05 §4`) |
| purge (tombstone / `commit_type=purged` 発行経路 / `--erase-tombstone` / Dead Pointer) | `09 §3.1`: Step 4 (`05 §3`, `08 §4`)。commit_type=purged は CT-COMMIT-001 で **enum 受理のみ** 確認、purge 実行はしない |
| GC の **実行** (shallow 化 / tiered retention / prune / CoW / power-loss sweep / `kio gc`) | `05 §2.2`, `09 §3.1`: Phase 4+。Step 1 は `gc_policy` / `protected` × `commit_type` **schema のみ** 遵守 (CT-GC-*) |
| 初回スキャン preview + 明示承認 / `.kioignore` / secrets Tier A/B / budget guardrail | `09 §3.1`: Step 2 (`06 §2`, `10 §1`) |
| 定期 auto snapshot / Downloads watch / OS スケジューラ委譲 / on_idle | `05 §8.2`, `09 §3.1`: Phase 4+。Step 1 の auto 契機は index 完了時のみ (それも §C-4 の Step 境界注記付き) |
| export / import (`.kioz`) / `kio move` | `09 §3.1`: Phase 4+ (`06 §10`, `05 §6` 予約) |
| agent API 外部公開 / MCP / navigation | `09 §3.1`: Phase 5 (`06 §9`) |
| 観測ログのうち `metrics.jsonl` / `access.jsonl` | `09 §3.1`: Step 3。Step 1 対象は `events.jsonl` / `errors.jsonl` のみ (CT-OBS-001/002 で担保) |
| tool_profile_hash / tool_lock_hash / chunking_config_hash の **算出ロジック** | Adapter capability (Step 2) / chunk (Step 3) 由来。Step 1 では commit の `tool_lock_hash` を**外部入力の不透明値**として扱う (CT-HASH-004 でダミー値を用いる)。算出規約 `03 §5.1/§5.2/§5.3` のテストは WS 別 |

---

## 集計 (報告用)

- **P0 テスト数**: 39
  (CT-HASH 8 / CT-TREE 4 / CT-COMMIT 8 / CT-GC 2 / CT-SCOPE 1 / CT-CLI 10 / CT-LOCK 2 / CT-STATE 2 / CT-OBS 2)
- **spec 未定義事項**: 14 件 (§C)。うち **真の要-spec (Step 1 着手前追記推奨) は 2 件**: §C-1 (lock 敗者挙動 + error code)、§C-2 (raw-only tree entry の normalize ブロック)。残り 12 件は実装者判断で固定 → 事後 spec 反映で足りる。
