# KCS 統合要件ドラフト

> 正本は `docs/research/` 配下の研究ノートである。このファイルは研究ノートを実装向けに統合した要件ドラフトであり、矛盾がある場合は `docs/research/` 側を優先して同期する。

> **KCSは、すべてのローカルファイルを content-addressed object として保存し、Markdown 化して、現在と過去の知識を人間と AI Agent が探索できるようにする Git inspired なローカル知識アーカイブである。KCS core はオフラインで既存 snapshot / artifact を探索・復元でき、Prepare / Markdownize（OCRを含む） / マルチモーダル Embedding / optional Summary・Classification・Rerank はユーザー選択の Adapter に委譲する。**

> **KCS is a Git-inspired, local-first knowledge archive that stores every file as a content-addressed object, normalizes it into Markdown, and makes both current and historical knowledge navigable by humans and AI Agents. The KCS core remains offline-capable for existing snapshots and artifacts, while Prepare, Markdownize (including OCR), multimodal Embedding, and optional Summary / Classification / Rerank work are delegated to user-selected adapters.**

---

## 1. KCS の再定義

KCS の作成意図は、AI を契機として **ローカルの知識空間そのものを再定義すること** である。長年、PDF / PowerPoint / Word / 画像のような検索に向かないファイル形式がローカルファイル空間のデフォルトだった。一方で Web では、Google が文書空間に共通の検索体験を与え、ブラウザ上で同じ指標・同じフォーマット・同じ操作感で情報へアクセスできるようにした。

KCS はこれをローカルファイル空間で実現する。原本ファイルを保存しつつ、Markdown を主とする統一テキスト表現へ正規化し、全文検索・意味検索・履歴検索・出典追跡を同じ体験として扱えるようにする。副目的として、開発者が Git で享受してきた **履歴付き知識アーカイブ** の恩恵を、開発者以外のユーザーにも広げる。

これまでの KCS は次のものでした。

```text
ローカルファイルを検索・ナビゲーションするシステム
```

今回の方針ではさらに踏み込みます。

```text
ローカルファイルを失わない
過去状態も探索できる
AI Agent が履歴込みで知識にアクセスできる
```

つまり、KCS は次の 3 つの合成です。

```text
Finder / Explorer
+
Git
+
AI Agent Knowledge Index
```

ただし Git と同じものではありません。

```text
Git: ソースコード中心の履歴管理
KCS: ローカルファイル全体の知識アーカイブ
```

---

## 2. プロダクト基本: オフラインで動作可能であること

KCS は **core が完全オフラインで動作する** ことを基本要件とする。ネットワーク接続は前提としない。

ここでいうオフライン保証の対象は、KCS 本体の object store / snapshot / restore / search / index 管理である。Prepare、Markdownize（OCRを含む）、マルチモーダル Embedding、optional Summary / Classification / Rerank などの処理は Adapter に委譲し、ユーザーが LLM などのオンライン API、ローカル LLM などのオフライン API、決定論的ライブラリ実装を自由に選べるようにする。

### オフライン動作が必須となる機能

```text
KCS object store
Snapshot / Restore / GC / Pack
履歴完全削除 / 法務・秘匿向け purge
既存 BM25 / Vector / Graph index の保持・参照
既存の normalized object / chunk / embedding object を使った検索
Adapter 実行の状態管理と再開
```

Adapter がオフライン実装を提供する場合、以下もオフラインで動作できる。

```text
Prepare 処理 (raw object → prepared object / prepared unit)
Markdownize 処理 (PDF / docx / pptx / xlsx / 画像 / 音声 → Markdown。OCR を含む)
マルチモーダル Embedding 生成
optional Summary / Classification / Rerank
BM25 / Vector / Graph 検索
```

これらは Adapter が提供する能力であり、KCS core のオフライン保証対象ではない。KCS core が保証するのは、実行時 Adapter が利用できない状態でも、すでに生成済みの snapshot / normalized object / chunk / embedding object / index を使って探索・復元できることである。

Adapter の実行設定、コマンドパス、URL、認証情報は共有対象ではない。各デバイスの `~/.config/kcs/` や OS keychain などに保存し、`.kcs/` は Adapter を管理しない。`.kcs/` に残すのは、生成済み artifact の provenance と互換性判定に必要な profile hash などの非実行情報に限る。

### Adapter 設計への含意

LLM などのオンライン API、ローカル LLM などのオフライン API、決定論的ライブラリ、ローカルコマンドは **差し替え可能な Adapter** として位置付ける。KCS は特定の Prepare / Markdownize / Embedding / Summary / Classification / Rerank 実装を中核に含めず、Adapter 契約と実行記録を管理する。OCR は単独 Adapter として Markdownize と並列に置かず、画像・スキャン PDF などを Markdown 化する Markdownize Adapter の内部能力として扱う。

Adapter は提供主体ではなく、実行形態と決定性で分類する。

```text
online_api:
  ネットワーク越しに呼び出す API。例: hosted LLM / hosted embedding / hosted OCR API

offline_api:
  同一端末またはローカルネットワーク内で呼び出す API。例: local LLM server / local embedding server

deterministic_library:
  決定論的なライブラリやローカル処理。例: PDF text extraction / parser / rule-based normalizer
```

MVP で必要な Adapter は以下である。

```text
1. Prepare Adapter
2. Markdownize Adapter
3. Embedding Adapter
4. Summary Adapter optional
5. Classification Adapter optional
6. Rerank Adapter optional
```

廃止する Adapter:

```text
Image Embedding Adapter
Text Embedding Adapter
```

Adapter は共通の KCS API を通じて KCS core と接続する。オンライン API、オフライン API、決定論的ライブラリのいずれを使う場合も、KCS core は同じ API 境界で task、input hash、output hash、profile hash、ネットワーク送信許可、実行状態を管理する。

```text
KCS core:  offline-capable
Adapter:   user-selected
Optional:  online_api adapter (explicit network opt-in)
```

`--online` 等の明示オプトインなしにネットワーク越しの API へファイル内容を送信しない。Adapter はオンライン API を使えるが、KCS core はオンライン API が停止しても既存 snapshot と既存 artifact を探索・復元できなければならない。

### `tool_profile_hash` による再現性

Prepare / Markdownize / Embedding / Summary / Classification / Rerank のバージョン・量子化・パラメータは、実行設定そのものではなく、`tool-lock.json` と `tool_profile_hash` に非実行の profile 情報として記録する。

ただし、Markdownize（OCR / 画像認識を含む）、Embedding、Summary、Classification、Rerank など非決定的な処理を挟む場合、KCS の再現性は「同じ入力から必ず同じ出力を再生成できる」ことではなく、**一度生成された artifact を原本 hash と tool profile に紐付けて固定し、同じ原本 hash では既存 artifact を尊重する**ことを意味する。

```text
raw_hash unchanged
  → existing normalized object を使う
  → Adapter 前処理を自動再実行しない

raw_hash changed
  → new normalized object generation candidate

explicit re-normalize requested
  → same raw_hash でも新しい normalized artifact を生成可能
```

原本ファイルが正であり、Normalized Markdown は原本から生成された派生 artifact である。明示的な再 Markdown 化を行わない限り、原本 hash が変わらないファイルに対して Agent 前処理を再実行しない。

### MVP の実行範囲

MVP は **単一端末限定** とする。同期、共有版、Web 上の修正提案、複数端末間の競合解決は MVP 外である。

ただし、MVP は検索体験を削った薄いデモではない。初期ユーザーは CLI に慣れた開発者を想定しつつ、将来の一般ユーザー向け UX を損なわない設計にする。横断検索、履歴検索、出典追跡、復元、安全な削除境界など、KCS の基本体験に直結する機能は時間をかけてでも実装する。

そのうえで、MVP でもプロダクトの中核思想を検証できるよう、次は最小要件に含める。

```text
content-addressed object store
snapshot DAG
Normalized Markdown artifact
Evidence Pointer
全文検索 / hybrid search の土台
履歴込み検索
restore
resume / retry / repair
purge
```

MVP は短期デモではなく、KCS の基本機能を実装する最初の完成形として扱う。実装順序は段階化してよいが、MVP の受入範囲から横断検索、履歴検索、出典追跡、復元、purge、安全な再実行を外さない。

### 理由

```text
ローカルファイルアーカイブの本質は所有とプライバシー
ネットワーク依存は機密文書 / 規制下文書の運用と相容れない
オフライン環境 (現場 / 機内 / 法務隔離) でも知識にアクセスできる必要がある
オンライン API への依存はサービス停止時に knowledge access を失う
```

---

## 3. Git から取り入れるべき核心

Git の本質は「差分保存」ではなく次の 7 つです。

```text
1. Content-addressed object store
2. Tree snapshot
3. Commit DAG
4. References
5. Index / staging
6. Ignore
7. Garbage collection
```

KCS では以下のように再解釈します。

| Git        | KCS                                          |
| ---------- | -------------------------------------------- |
| blob       | raw file object / normalized markdown object |
| tree       | folder snapshot                              |
| commit     | KCS commit / snapshot                        |
| branch     | snapshot lineage                             |
| tag        | named archive point                          |
| index      | pending indexing state                       |
| .gitignore | .kcsignore                                   |
| gc         | unreferenced object cleanup                  |
| checkout   | snapshot materialization / view              |
| blame      | evidence provenance                          |

`index` / pending task / retry state は、KCS の正本ではない。これらは処理効率と再開性のための運用状態であり、失われても raw object / normalized object / tree / commit object から再検出・再生成できることを優先する。KCS が失ってはならないのは原本ファイル由来の raw object と、その raw object に紐づく履歴・証拠・snapshot である。

---

## 4. KCS の基本構造

KCS の `.kcs` は、知識スコープのルートに1つだけ置くものではない。基本的には `.DS_Store` のように各フォルダに隠しディレクトリとして生成され、子フォルダや孫フォルダにもそれぞれ `.kcs` が存在する。

各 `.kcs` は、自分が配置されたフォルダ直下のファイルと子フォルダリンクを管理する。子フォルダの中身は、その子フォルダ自身の `.kcs` が管理する。

ファイル名は `scope.json` を正とする。過去の研究メモに出てくる `folder.json` は同じ概念の旧称であり、実装・契約ドキュメントでは採用しない。

`kcs init` は実行フォルダの `.kcs` を作成する。子フォルダの `.kcs` は、`kcs index` や探索処理が ignore されていない対象を発見した時点で必要に応じて生成する。つまり、各フォルダに `.kcs` が存在する設計を前提にしつつ、空フォルダや未到達フォルダへ先回りして大量生成する必要はない。

Git 風の内部構造としては、各フォルダの `.kcs` はこうなります。

```text
folder/
  .kcs/
    HEAD
    config.toml
    scope.json
    index
    objects/
      raw/
      normalized/
      chunks/
      embeddings/
      nodes/
      trees/
      commits/
    refs/
      heads/
      tags/
    logs/
    cache/
    tmp/
  child-folder/
    .kcs/
```

ここで重要なのは、**原文ファイルを content-addressed object として保存する**ことです。

---

## 5. Git の blob に相当するもの

### Git

Git ではファイル内容は blob として保存されます。

```text
blob = ファイル内容
blob_id = hash(content)
```

### KCS

KCS では最低 2 種類の blob を持ちます。

```text
raw object
normalized markdown object
```

例:

```text
objects/raw/ab/cd/<sha256>
objects/normalized/ef/12/<sha256>.md
```

#### Raw Object

原文ファイルそのもの。

```text
report.pdf
image.png
slide.pptx
README.md
```

すべて content hash で保存します。

#### Normalized Object

Markdown 化された結果。

```text
report.pdf.md
image.png.md
slide.pptx.md
README.md
```

これも hash で保存します。

---

## 6. 同じファイルは同一 `.kcs` 内で一度だけ保存する

Git 由来の重要な容量対策。ただし、KCS は `.kcs` を各フォルダに分散配置するため、dedup の保証範囲は同一 `.kcs/objects` 内に限定する。

同じ `.kcs` 内で同じ内容なら保存は 1 回。

```text
report.pdf            → sha256:abc
report-copy.pdf       → sha256:abc
report-final.pdf      → sha256:abc
```

同じ `.kcs/objects/raw/` 内では保存は 1 回。コミット側では次のみを持ちます。

```text
path → object_hash
```

別フォルダの別 `.kcs` に同一内容のファイルがある場合は、物理的な重複保存を許容する。これは、フォルダローカルな所有権、`.kcs` 単位の export / purge / restore / partial sync を壊さないためである。

```text
dedup scope = one .kcs object store
cross-.kcs dedup = not guaranteed
```

---

## 7. KCS の tree

Git の tree は **ディレクトリ構造** を表します。KCS でも同様に、ある時点のフォルダ構造を保存します。

```json
{
  "tree_id": "tree_abc",
  "entries": [
    {
      "path": "docs/report.pdf",
      "type": "file",
      "raw_hash": "sha256:abc",
      "normalized_hash": "sha256:def"
    },
    {
      "path": "notes/idea.md",
      "type": "file",
      "raw_hash": "sha256:ghi",
      "normalized_hash": "sha256:jkl"
    }
  ]
}
```

これにより「ある時点でどのパスにどのファイルが存在したか」を再現できます。

---

## 8. KCS commit

Git の commit は `tree + parent + metadata`。KCS でも同じです。

```json
{
  "commit_id": "kcs_01H...",
  "tree": "tree_abc",
  "parents": ["kcs_01G..."],
  "created_at": "2026-04-29T12:00:00Z",
  "message": "snapshot after indexing docs",
  "stats": {
    "files_added": 12,
    "files_modified": 3,
    "files_deleted": 1,
    "raw_objects_added": 5,
    "normalized_objects_added": 5,
    "chunks_added": 240
  }
}
```

KCS commit は原文を直接持つのではなく **tree へのポインタ** を持ちます。

---

## 9. KCS の価値は「復元」だけではない

Git 的に原文を保存すれば過去復元はできます。しかし KCS の本当の価値はそこだけではありません。

```text
過去の知識も検索できる
削除済みファイルも探索できる
AI Agent が時間軸を指定して検索できる
現在と過去の差分を知識単位で見られる
```

つまり次が可能になります。

```text
Time-travel knowledge navigation
```

---

## 10. Normalized Markdown も履歴保存する

原文だけでは AI Agent は検索しづらい。KCS では各 raw object に対して Markdown 化結果も保存します。

```text
raw_hash + markdown_tool_profile_hash
→ normalized_hash
```

例:

```json
{
  "raw_hash": "sha256:abc",
  "tool_profile_hash": "sha256:tool1",
  "normalized_hash": "sha256:def",
  "normalized_object": "objects/normalized/de/f0/def.md"
}
```

これにより「この原文をこの Markdownize Adapter / tool profile で処理した結果」を固定できる。Markdown 化処理の実体は KCS core ではなく Adapter が担う。OCR はこの Markdownize Adapter の内部能力として扱う。KCS は Adapter の実装種別に依存せず、生成済み normalized object を原本 hash と tool profile に紐付けて保持する。

Normalized Markdown は、原本ファイルから生成された **読み取り専用の派生 artifact** である。ユーザーや AI Agent は normalized object を直接編集しない。追記・補足・誤抽出の指摘は annotation / note / extraction issue として別 object に保存する。

原本が Markdown ファイルである場合は、その Markdown ファイル自体を原本として編集する。PDF / 画像 / Office 文書などから生成された Normalized Markdown を編集対象にしたい場合は、原本を Markdown に移行し、その Markdown を新しい正本として扱う。

OCR や layout detection の誤りは Normalized Markdown の手編集では直さない。MVP では最低限、誤抽出箇所を `extraction issue` として記録し、再 Markdown 化または原本更新の候補として扱う。未反映の extraction issue は通常検索・RAG の根拠本文には混ぜず、レビューや修復のための補助情報として扱う。

---

## 11. Embedding も Git 風に管理する

Embedding は Text / Image で Adapter を分けない。Gemini 等のマルチモーダル Embedding を前提に、単一の Embedding Adapter が Markdown chunk、Image Object、検索クエリを同一のベクトル空間へ写像する。

```text
target_hash + embedding_profile_hash
→ embedding_object
```

入力対象:

```text
markdown_chunk
image_object
query
text
image
```

保存先:

```text
objects/embeddings/ab/cd/<hash>
```

Embedding は commit に直接埋め込まず、commit からは「どの embedding object を使ったか」を参照するだけにする。Embedding 生成の実体は単一の Embedding Adapter が担う。KCS core は embedding object と `embedding_profile_hash`、`dimensions`、`distance`、`modality` の対応、互換性、検索時の fallback を管理する。

Embedding object は正本ではなく、`target_hash + embedding_profile_hash` から再構築可能な派生 artifact として扱う。欠損・破損・profile 不一致がある場合、KCS は再生成タスクを作るか、全文検索へ fallback する。秘匿・法務・誤取り込みの purge では、embedding も本文情報を含み得る派生物として削除対象に含める。

画像説明文を経由した二段階 Embedding や、Image 専用 Embedding Adapter は採用しない。インデックスは物理的には `chunk_vec` / `image_vec` のように分けてもよいが、概念上は同じ Embedding Adapter、同じ `profile_hash`、同じ vector space で扱う。

推奨する概念テーブル:

```sql
CREATE TABLE embeddings (
  id TEXT PRIMARY KEY,
  target_type TEXT NOT NULL, -- chunk | image | node | query_cache
  target_id TEXT NOT NULL,
  modality TEXT NOT NULL,    -- text | image | multimodal
  vector BLOB NOT NULL,
  dimensions INTEGER NOT NULL,
  distance TEXT NOT NULL,
  profile_hash TEXT NOT NULL
);
```

`tool-lock.json` では、旧来の `embedding_text` / `embedding_image` を使わず、単一の `embedding` profile を記録する。

```json
{
  "embedding": {
    "tool_id": "embed_multimodal",
    "kind": "command",
    "cmd_hash": "sha256:...",
    "args_hash": "sha256:...",
    "config_hash": "sha256:...",
    "mode": "batch",
    "dimensions": 1536,
    "distance": "cosine",
    "modality": "multimodal",
    "profile_hash": "sha256:..."
  }
}
```

`.kcs/config.toml` でも Embedding tool は単一指定にする。

```toml
[tools]
embedding = "gemini_multimodal_embedding"
```

> KCSでは、Embedding処理をText/Imageで分離せず、Gemini等のマルチモーダルEmbeddingを前提とした単一のEmbedding Adapterに統合する。Embedding Adapterは、Markdown chunk、Image Object、検索クエリを同一のベクトル空間へ写像し、KCSはそのprofile_hash・dimensions・distance・modalityを記録する。画像説明文を経由した二段階Embeddingや、Image専用Embedding Adapterは採用しない。

---

## 12. Chunk もオブジェクト化する

Normalized Markdown から見出し単位で chunk を作る。

```text
normalized_hash + heading/span
→ chunk_hash
```

chunk object:

```json
{
  "chunk_hash": "sha256:chunk",
  "normalized_hash": "sha256:def",
  "heading_path": ["認証仕様", "API Token"],
  "char_start": 1200,
  "char_end": 1500,
  "text_hash": "sha256:text"
}
```

---

## 13. Knowledge Node も履歴化する

KCS では知識ノードは検索やアクセス履歴から育つので、これも履歴化できます。

```json
{
  "node_id": "node_001",
  "label": "API認証仕様",
  "evidence_chunks": ["chunk_a", "chunk_b"],
  "created_at_commit": "kcs_123",
  "status": "stable"
}
```

ある commit 時点でどの知識ノードが存在したかを保持します。

---

## 14. KCS index と Git index の違い

Git の index は staging area。KCS にも似たものを作りますが意味は違います。

```text
.kcs/index
```

KCS index は次の作業領域です。

```text
現在のファイル状態
Markdown化状態
Embedding状態
検索インデックス状態
```

つまり次の進捗管理です。

```text
working tree → normalized → chunks → index
```

---

## 15. KCS status

Git と同様に状態を出します。

```bash
kcs status
```

出力:

```text
KCS status

Scope: /Users/takumi/Documents

New files:
  docs/new.pdf

Modified files:
  notes/idea.md

Deleted files:
  old/spec.pdf

Pending Markdownize:
  docs/new.pdf

Pending Embedding:
  42 chunks

Ready to snapshot:
  17 files changed
```

---

## 16. KCS commit / snapshot

KCS では `commit` と `snapshot` を内部的に別 object として分けない。どちらも `tree + parent + metadata` を持つ同一の履歴 object とし、`message`、`actor`、`reason`、`protected` などのメタデータによって、手動保存・自動保存・import・repair・重要保存点を区別する。

ユーザー向けの公式語彙は `snapshot` とし、CLI では開発者向け alias として `commit` を許可する。実装上の object type は単一であり、`commit` と `snapshot` の二重管理を作らない。

```bash
kcs commit -m "before refactor"
kcs snapshot create -m "before refactor"
```

これで次が固定されます。

```text
raw objects
normalized objects
chunks
embedding references
tree
commit object
```

---

## 17. CLI と GUI の語彙

CLI は Git に慣れたユーザーと自動化を重視し、Git 風のコマンドを維持する。

```bash
kcs commit -m "before cleanup"
kcs checkout <commit>
kcs status
kcs log
kcs diff
```

GUI では Git 用語をそのまま見せず、一般ユーザーが理解しやすい表現に言い換える。

```text
commit / snapshot  → 版を保存 / スナップショットを作成
checkout           → 表示する版を切り替える / 復元する
branch             → 修正提案 / 変更案
merge              → 反映
log                → 変更履歴
```

---

## 18. KCS checkout

過去状態の復元は慎重に設計します。現在の実ファイルを上書きするのは危険なので、デフォルトでは直接上書きしません。

```bash
kcs checkout <snapshot>     # デフォルトでは実ファイルを上書きしない
```

推奨は次です。

```bash
kcs restore <snapshot> --to ./restore-dir
```

例:

```bash
kcs restore kcs_123 --to ~/Recovered/kcs_123
```

これで安全に過去ファイルを復元できます。

---

## 19. KCS time-travel search

KCS 最大の価値です。

```bash
kcs search "認証仕様"
```

デフォルトは最新。

```bash
kcs search "認証仕様" --at kcs_123
```

特定 snapshot 時点で検索。

```bash
kcs search "認証仕様" --all-history
```

削除済み・旧版を含めて検索。

```bash
kcs search "認証仕様" --since 2026-04-01
```

期間指定。

### 検索スコープ

デフォルト検索は **KCS が認識しているすべてのフォルダ・ファイル** を対象にする。ここでいう「すべて」は、KCS に登録済みまたは検出済みの indexed scope 全体であり、検索結果には実際に検索した scope を必ず含める。

初回登録時の indexed scope は、ユーザーが `.kcsignore` や設定で明示的に除外していないすべての対象範囲とする。デフォルト全体検索は、明示 ignore されていないローカル知識空間を横断するための既定動作である。

ただし、初回スキャンでは対象範囲 preview、除外提案、明示承認を必須とする。これはデフォルト全管理を弱めるものではなく、KCS が単なる検索インデックスではなく原本複製を伴う content-addressed archive であることを、ユーザーが理解したうえで開始するためである。

初回スキャン前に表示する情報:

```text
対象 root / scope
推定ファイル数
推定容量
大容量ファイル
hidden / system / build / cache 系候補
現在有効な ignore
network transmission policy
```

除外候補は提案に留め、ユーザーの明示なしに自動除外しない。未承認 scope に対する `kcs index` は preview と確認を要求し、非対話環境では承認情報または `--yes` / `--approve` がない限り失敗させる。

```bash
kcs search "認証仕様"
```

意味:

```text
all indexed scopes / all tracked folders and files
```

現在フォルダだけ、または現在フォルダとその配下だけを検索したい場合は、明示的に scope を絞る。

```bash
kcs search "認証仕様" --scope .
kcs search "認証仕様" --scope . --descendants
kcs search "認証仕様" --scope ./Research
kcs search "認証仕様" --scope ./Research --descendants
kcs search "認証仕様" --all-scopes
```

`--scope .` は現在フォルダのみ、`--scope . --descendants` は現在フォルダとその配下 scope、`--scope <path>` は指定フォルダのみ、`--scope <path> --descendants` は指定フォルダとその配下 scope、`--all-scopes` はデフォルトと同じく全 indexed scope を対象にする。

AI Agent API でも同じルールを適用する。レスポンスには、実際に検索した scope、ユーザー指定によって除外した scope、権限や設定により検索できなかった scope を含める。

---

## 20. Git の branch に相当するもの

KCS でも branch は使えますが意味はやや違います。

```text
Git branch = 開発系列
KCS branch = 知識空間の系列
```

用途:

```text
通常利用:                main
実験的Markdown化:        experimental
別Embeddingモデル:       bge
法務用厳密保存:          legal-archive
```

MVP では branch は後回しで良い。

---

## 21. Tag

早めに入れる価値があります。

```bash
kcs tag thesis-submission
kcs tag before-cleanup
kcs tag contract-review-v1
```

タグは特定 snapshot に名前を付けます。

---

## 22. KCS ignore

Git の `.gitignore` と同じ思想ですが、KCS では **デフォルト全管理、明示除外** です。

```text
.kcsignore
```

例:

```text
node_modules/
target/
*.tmp
*.cache
```

動画もデフォルト管理。除外はユーザーが明示します。

```text
*.mp4
*.mov
```

KCS はデフォルト全管理を維持し、除外は `.kcsignore` または設定で明示する。実装は便利な ignore テンプレートを提供してよいが、ユーザーの明示なしに検索範囲や保存範囲を現在フォルダだけへ狭めない。

容量効率よりも、知識を失わず、あとから検索・履歴探索・復元できる利便性を優先する。したがって、動画・巨大PDF・画像・Officeファイルも、ユーザーが明示的に除外しない限り管理対象に含める。

ただし、UI / CLI では、KCS が検索インデックスだけでなく原本ファイルを content-addressed archive に保存すること、初回 index で追加ディスク容量を使うこと、同一 `.kcs` 内 dedup 後の保存見込み、別 `.kcs` 間で重複保存される可能性を明示する。

---

## 23. 大容量ファイルの扱い

デフォルトは管理対象。ただし警告と容量見積もりは必須。

```text
Large file detected: video.mp4 (8.2GB)
KCS will archive it by default.
Add pattern to .kcsignore to exclude.
```

設定:

```toml
[storage]
archive_all_files = true
large_file_warning = "1GB"
```

ディスク枯渇が予測される場合でも、KCS が勝手に対象範囲を狭めてはならない。必要容量、空き容量、除外候補を表示し、続行・除外・延期・中断をユーザーに選ばせる。

---

## 24. 容量対策

容量を犠牲にするとしても無駄は減らす。Git から学べる対策は次です。

```text
content-addressing
deduplication
pack files
compression
garbage collection
delta compression
```

KCS でも段階的に採用します。

### v0

```text
sha256 object store
zstd compression
dedup
```

### v1

```text
pack files
```

### v2

```text
delta compression for text/markdown
```

---

## 25. Pack file 構想

Git は小さい object が大量にあると効率が悪いため pack します。KCS でも同じ。

```text
objects/raw/...
objects/normalized/...
```

が増えたら次へまとめる。

```text
packs/raw-0001.kcspack
packs/normalized-0001.kcspack
```

MVP では不要だが将来必要。

---

## 26. KCS GC

Git と同じく到達不能 object を削除可能。ただし KCS ではデフォルトでは削除しない方が思想に合います。

通常の削除は、最新の tree / manifest から対象 path を消す操作であり、過去の commit / snapshot から復元可能な履歴は維持する。これは KCS の根幹であり、通常の `delete` や `archive` で過去版を破壊してはならない。

```bash
kcs gc --dry-run
kcs gc --prune-unreachable
```

デフォルト:

```text
削除しない
```

ユーザー明示時のみ削除。

`gc --prune-unreachable` が削除できるのは、どの commit / snapshot / tag / protected object からも到達不能な object のみである。過去 commit から到達可能な raw / normalized / chunk / embedding / tree / commit object は、最新ファイルから消えていても GC 対象外とする。

### 履歴完全削除 / 法務・秘匿向け purge

GC だけでは、削除・秘匿・法務要件には足りない。特定ファイルを「過去の履歴からも完全に消す」必要がある場合、KCS は Git の履歴書き換えに相当する **明示的な purge 機能** を持つ。

```bash
kcs purge docs/secret.pdf --all-history --reason "legal erasure request"
kcs purge --raw-hash sha256:abc... --all-history
```

GUI では、検索結果・履歴ビュー・ファイル詳細画面から **このファイルの履歴を完全削除** を実行できるようにする。この操作は通常削除や archive とは別物であり、確認 UI と影響範囲の preview を必須にする。

`purge` の保証範囲は KCS 管理下の object store、snapshot DAG、index、pack、cache、tombstone である。OS backup、Time Machine、クラウド同期の過去版、外部 export、ユーザーが手動コピーしたファイル、KCS 外のログまでは KCS 単体では保証しない。UI 文言では「KCS 管理下の履歴から完全削除」という意味で扱う。

purge は次を行う。

```text
対象 path / raw_hash を参照する全 tree / commit / manifest を書き換える
対象 raw object を到達不能にする
対象 raw object 由来の normalized / prepared unit / chunk / embedding / node / edge / evidence を到達不能にする
対象を含む index / pack / cache を無効化または再構築する
到達不能化された object を GC で物理削除する
```

保持する監査情報は、内容・本文・秘匿 path を再構成できない最小限の tombstone に限る。

```text
purge_id
actor
executed_at
reason
object_count_removed
redacted_target_label
```

purge は破壊的操作なので、デフォルトの知識保存性とは分けて扱う。KCS の通常思想は「消さない」だが、ユーザーが明示した法務・秘匿・誤取り込みの要件では、履歴を含めて完全削除できなければならない。

---

## 27. `.kcs` の新しい構造

この思想なら、各フォルダに生成される `.kcs` はこうなります。

```text
folder/
  .kcs/
    VERSION
    HEAD
    config.toml
    scope.json
    manifest.json
    tool-lock.json

    objects/
      raw/
      normalized/
      chunks/
      embeddings/
      nodes/
      edges/
      trees/
      commits/

    refs/
      heads/
        main
      tags/

    index/
      sqlite.db
      bm25/
      vector/

    logs/
      access.jsonl
      events.jsonl

    packs/
    cache/
    tmp/
  child-folder/
    .kcs/
```

---

## 28. KCS object model

Git 風に整理するとこうです。

```text
raw_blob         原文ファイル
normalized_blob  Markdown化結果
chunk_blob       チャンク
embedding_blob   ベクトル
node_object      知識ノード
edge_object      関係
tree_object      パス構造
commit_object    snapshot
```

---

## 29. KCS commit / snapshot は何を保証するか

KCS commit / snapshot は以下を保証します。

```text
その時点で存在したファイルの一覧
各ファイルの原文内容
各ファイルのMarkdown化結果
各chunk
検索用index metadata
知識ノード
Evidence Pointer
tool_profile_hash (再現性のため)
```

つまり過去時点を再検索可能にする。

---

## 30. 検索体験の変化

この設計で KCS は強い検索体験を提供できます。

```bash
kcs search "卒論テーマ"
```

最新検索。

```bash
kcs search "卒論テーマ" --all-history
```

過去も含める。

```bash
kcs search "卒論テーマ" --deleted
```

削除済みも含める。

```bash
kcs restore "昔の研究計画書"
```

検索から復元。

---

## 31. KCS の価値の再定義

最も強い定義はこれです。

> **KCSは、ローカルファイルシステムを content-addressed な知識アーカイブへ変換し、現在・過去・削除済みのファイルを含む知識空間を、人間と AI Agent が共通の操作で探索できるようにするシステムである。KCS core はオフラインで既存 snapshot / artifact を探索・復元できる。**

---

## 32. Git との比較

| 項目         | Git      | KCS                        |
| ---------- | -------- | -------------------------- |
| 対象         | リポジトリ    | ローカルフォルダ全体                 |
| 主対象        | テキスト/コード | 全ファイル                      |
| 正規化        | なし       | Markdown 化                 |
| AI 検索      | なし       | あり (Adapter 経由)              |
| 原文保存       | blob     | raw object                 |
| Markdown 保存 | なし       | normalized object         |
| 検索         | grep 程度  | BM25 + Vector + Navigation |
| 履歴         | commit   | commit / snapshot          |
| 復元         | checkout | restore                    |
| 知識ノード      | なし       | あり                         |
| ネットワーク要件   | push/pull で必要 | 不要(オプション)             |

---

## 33. 捨てるべきもの

```text
Git本体との完全互換
Gitフォーク
差分だけ保存という説明
DBだけの軽量index思想
オンライン API 前提の設計
```

---

## 34. 残すべきもの

```text
Git風content-addressing
snapshot DAG
refs/tags
ignore
gc
restore
blame/provenance
```

---

## 35. KCS が Git より優先する価値

Git は容量効率と開発履歴を重視する。KCS は次を重視する。

```text
知識を失わないこと
AIが探索できること
原文へ戻れること
KCS core がオフラインで自立すること
```

つまり次を明言する。

> **KCSは容量効率より知識保存性を優先する。**
> **KCSはネットワーク利便性よりオフライン自立性を優先する。**

---

## 36. 最終方針

```text
Default:
  全ファイルを管理
  原文を content-addressed store へ保存
  Markdown 化結果も保存
  最新も過去も検索可能
  デフォルト検索は全 indexed scope を対象にする
  KCS core はオフラインで動作

Optional:
  .kcsignore で除外
  gc で削除
  purge で特定ファイルの全履歴を完全削除
  large file warning
  user-selected adapter
  online_api adapter (explicit network opt-in)
```

---

## 37. 最終一文

README や設計書の最初に置くべき一文。

> **KCS is a Git-inspired, local-first knowledge archive that stores every file as a content-addressed object, normalizes it into Markdown, and makes both current and historical knowledge navigable by humans and AI Agents. The KCS core remains offline-capable for existing snapshots and artifacts, while Prepare, Markdownize (including OCR), multimodal Embedding, and optional Summary / Classification / Rerank work are delegated to user-selected adapters.**

> **KCSは、すべてのローカルファイルを content-addressed object として保存し、Markdown 化して、現在と過去の知識を人間と AI Agent が探索できるようにする Git inspired なローカル知識アーカイブである。KCS core はオフラインで既存 snapshot / artifact を探索・復元でき、Prepare / Markdownize（OCRを含む） / マルチモーダル Embedding / optional Summary・Classification・Rerank はユーザー選択の Adapter に委譲する。**
