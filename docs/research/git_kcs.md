以下では、**Gitの仕組みをかなり忠実に参考にしながら、KCSを「全ローカルファイルを失わず、AIと人間が探索できる知識アーカイブ」として再定義**します。

KCSの作成意図は、AIを契機としてローカルの知識空間を再定義することです。PDF / PowerPoint / Word / 画像のような検索に向かないファイル空間を、Markdownを主とした統一テキスト表現へ変換し、GoogleがWeb文書にもたらした共通の検索体験をローカルファイル空間にも実現する。さらに、開発者がGitで享受してきた履歴付き知識アーカイブの恩恵を、すべてのユーザーに広げることを副目的とします。

結論から言うと、KCSは単なる検索ツールではなく、次のように定義するのが最も強いです。

> **KCSは、GitのContent-Addressed StorageとSnapshot管理をローカルファイル全体に拡張し、全ファイルをMarkdown化・索引化・履歴保存して、人間とAI Agentが現在と過去の知識を探索できるローカルファーストの知識アーカイブである。**

---

# 1. KCSの再定義

これまでのKCSは、

```text
ローカルファイルを検索・ナビゲーションするシステム
```

でした。

今回の方針では、さらに踏み込みます。

```text
ローカルファイルを失わない
過去状態も探索できる
AI Agentが履歴込みで知識にアクセスできる
```

つまり、KCSは次の3つの合成です。

```text
Finder / Explorer
+
Git
+
AI Agent Knowledge Index
```

ただし、Gitと同じものではありません。

Gitは、

```text
ソースコード中心の履歴管理
```

KCSは、

```text
ローカルファイル全体の知識アーカイブ
```

です。

---

# 2. Gitから取り入れるべき核心

Gitの本質は、実は「差分保存」ではありません。
本質は以下です。

```text
1. Content-addressed object store
2. Tree snapshot
3. Commit DAG
4. References
5. Index / staging
6. Ignore
7. Garbage collection
```

KCSではこれらを以下のように再解釈します。

| Git        | KCS                                          |
| ---------- | -------------------------------------------- |
| blob       | raw file object / normalized markdown object |
| tree       | folder snapshot                              |
| commit     | KCS snapshot                                 |
| branch     | snapshot lineage                             |
| tag        | named archive point                          |
| index      | pending indexing state                       |
| .gitignore | .kcsignore                                   |
| gc         | unreferenced object cleanup                  |
| checkout   | snapshot materialization / view              |
| blame      | evidence provenance                          |

---

# 3. KCSの基本構造

Git風にすると、`.kcs` はこうなります。

```text
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
```

ここで重要なのは、**原文ファイルをcontent-addressed objectとして保存する**ことです。

---

# 4. Gitのblobに相当するもの

## Git

Gitではファイル内容は blob として保存されます。

```text
blob = ファイル内容
blob_id = hash(content)
```

## KCS

KCSでは最低2種類のblobを持ちます。

```text
raw object
normalized markdown object
```

例：

```text
objects/raw/ab/cd/<sha256>
objects/normalized/ef/12/<sha256>.md
```

### Raw Object

原文ファイルそのもの。

```text
report.pdf
image.png
slide.pptx
README.md
```

すべてcontent hashで保存します。

### Normalized Object

Markdown化された結果。

```text
report.pdf.md
image.png.md
slide.pptx.md
README.md
```

これもhashで保存します。

---

# 5. 同じファイルは一度だけ保存する

ここがGit由来の重要な容量対策です。

同じ内容なら、パスが違っても保存は1回。

```text
docs/report.pdf       → sha256:abc
backup/report.pdf     → sha256:abc
old/report-copy.pdf   → sha256:abc
```

保存は1回。

コミット側では、

```text
path → object_hash
```

だけを持ちます。

---

# 6. KCSのtree

Gitのtreeは、

```text
ディレクトリ構造
```

を表します。

KCSでも同様に、ある時点のフォルダ構造を保存します。

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

これにより、

```text
ある時点でどのパスにどのファイルが存在したか
```

を再現できます。

---

# 7. KCS commit

Gitのcommitは、

```text
tree + parent + metadata
```

です。

KCSでも同じです。

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

重要なのは、KCS commitは原文を直接持つのではなく、

```text
treeへのポインタ
```

を持つことです。

---

# 8. KCSの価値は「復元」だけではない

Git的に原文を保存すると、もちろん過去復元できます。

しかしKCSの本当の価値はそこだけではありません。

KCSが可能にするのは、

```text
過去の知識も検索できる
削除済みファイルも探索できる
AI Agentが時間軸を指定して検索できる
現在と過去の差分を知識単位で見られる
```

です。

つまり、

```text
Time-travel knowledge navigation
```

が可能になります。

---

# 9. Normalized Markdownも履歴保存する

原文だけではAI Agentは検索しづらいです。

KCSでは各raw objectに対して、Markdown化結果も保存します。

```text
raw_hash + markdown_tool_profile_hash
→ normalized_hash
```

例：

```json
{
  "raw_hash": "sha256:abc",
  "tool_profile_hash": "sha256:tool1",
  "normalized_hash": "sha256:def",
  "normalized_object": "objects/normalized/de/f0/def.md"
}
```

これにより、

```text
この原文をこのMarkdown化ツールで処理した結果
```

を固定できます。

---

# 10. EmbeddingもGit風に管理する

Embeddingはraw fileではなく、chunkに対して生成されます。

```text
chunk_hash + embedding_profile_hash
→ embedding_object
```

保存先：

```text
objects/embeddings/ab/cd/<hash>
```

重要なのは、Embeddingをcommitに直接埋め込まないことです。

commitは、

```text
どのembedding objectを使ったか
```

を参照するだけ。

Embedding object は正本ではなく、chunk と embedding profile から再構築可能な派生 artifact として扱う。欠損・破損・profile 不一致がある場合は再生成するか、全文検索へ fallback する。

---

# 11. Chunkもオブジェクト化する

Normalized Markdownから見出し単位でchunkを作る。

```text
normalized_hash + heading/span
→ chunk_hash
```

chunk object：

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

# 12. Knowledge Nodeも履歴化する

KCSでは、知識ノードは検索やアクセス履歴から育つので、これも履歴化できます。

```json
{
  "node_id": "node_001",
  "label": "API認証仕様",
  "evidence_chunks": ["chunk_a", "chunk_b"],
  "created_at_commit": "kcs_123",
  "status": "stable"
}
```

あるcommit時点で、どの知識ノードが存在したかを保持する。

---

# 13. KCS indexとGit indexの違い

Gitのindexはstaging areaです。

KCSにも似たものを作れます。

```text
.kcs/index
```

ただし意味は違います。

KCS indexは、

```text
現在のファイル状態
Markdown化状態
Embedding状態
検索インデックス状態
```

を持つ作業領域です。

つまり、

```text
working tree → normalized → chunks → index
```

の進捗管理です。

---

# 14. KCS status

Gitと同じように状態を出せます。

```bash
kcs status
```

出力：

```text
KCS status

Scope: /Users/takumi/Documents

New files:
  docs/new.pdf

Modified files:
  notes/idea.md

Deleted files:
  old/spec.pdf

Pending Markdownization:
  docs/new.pdf

Pending Embedding:
  42 chunks

Ready to snapshot:
  17 files changed
```

---

# 15. KCS snapshot

Gitのcommitに相当するコマンドは、`commit` よりも `snapshot` の方が良いです。

理由は、Gitと完全互換ではないからです。

```bash
kcs snapshot create -m "before refactor"
```

これで、

```text
raw objects
normalized objects
chunks
embedding references
tree
commit
```

が固定されます。

---

# 16. なぜ `commit` ではなく `snapshot` か

`commit` はGit互換の期待が強すぎます。

KCSはローカルファイルアーカイブなので、

```text
snapshot
archive
checkpoint
```

の方が適切です。

ただし、Git風UXを重視するならaliasとして、

```bash
kcs commit
```

を許可しても良いです。

推奨：

```text
公式名: snapshot
alias: commit
```

実装上は単一の履歴 object とし、`snapshot` と `commit` を別 object type として分けない。ユーザー向けの正規名は `snapshot`、CLI 自動化や Git に慣れた開発者向けの互換 alias が `commit` である。

---

# 17. KCS checkout

過去状態を復元したい場合は、慎重に設計します。

危険なのは、現在の実ファイルを上書きすることです。

なのでデフォルトでは、

```bash
kcs checkout <snapshot>
```

で直接上書きしない。

推奨は、

```bash
kcs restore <snapshot> --to ./restore-dir
```

です。

例：

```bash
kcs restore kcs_123 --to ~/Recovered/kcs_123
```

これで安全に過去ファイルを復元できます。

---

# 18. KCS time-travel search

KCS最大の価値です。

```bash
kcs search "認証仕様"
```

デフォルトは最新。

```bash
kcs search "認証仕様" --at kcs_123
```

特定snapshot時点で検索。

```bash
kcs search "認証仕様" --all-history
```

削除済み・旧版を含めて検索。

```bash
kcs search "認証仕様" --since 2026-04-01
```

期間指定。

---

# 19. Gitのbranchに相当するもの

KCSでもbranchは使えますが、意味はやや違います。

```text
Git branch = 開発系列
KCS branch = 知識空間の系列
```

用途：

```text
通常利用: main
実験的Markdown化: experimental
別Embeddingモデル: bge
法務用厳密保存: legal-archive
```

ただし、MVPではbranchは後回しで良いです。

---

# 20. Tag

これは早めに入れても価値があります。

```bash
kcs tag thesis-submission
kcs tag before-cleanup
kcs tag contract-review-v1
```

タグは特定snapshotに名前をつける。

---

# 21. KCS ignore

Gitの `.gitignore` と同じ思想ですが、KCSでは「デフォルト全管理、明示除外」です。

```text
.kcsignore
```

例：

```text
node_modules/
target/
*.tmp
*.cache
```

動画もデフォルト管理するなら、除外はユーザーが明示。

```text
*.mp4
*.mov
```

デフォルト全管理は維持する。実装は便利な `.kcsignore` テンプレートを提供してよいが、ユーザーの明示なしに検索範囲や保存範囲を現在フォルダだけへ狭めない。

---

# 22. 大容量ファイルの扱い

あなたの思想では、デフォルト管理です。

ただし警告は必要です。

```text
Large file detected: video.mp4 (8.2GB)
KCS will archive it by default.
Add pattern to .kcsignore to exclude.
```

設定：

```toml
[storage]
archive_all_files = true
large_file_warning = "1GB"
```

---

# 23. 容量対策

容量を犠牲にするとしても、無駄は減らすべきです。

Gitから学べる容量対策：

```text
content-addressing
deduplication
pack files
compression
garbage collection
delta compression
```

KCSでも採用します。

## v0

```text
sha256 object store
zstd compression
dedup
```

## v1

```text
pack files
```

## v2

```text
delta compression for text/markdown
```

---

# 24. Pack file構想

Gitは小さいobjectが大量にあると効率が悪いためpackします。

KCSでも同じ。

```text
objects/raw/...
objects/normalized/...
```

が増えたら、

```text
packs/raw-0001.kcspack
packs/normalized-0001.kcspack
```

へまとめる。

MVPでは不要ですが、将来必要です。

---

# 25. KCS GC

Gitと同じく、到達不能objectを削除できます。

ただし、KCSではデフォルトでは削除しない方が思想に合います。

通常の削除は、最新のtree / manifestから対象pathを消すだけです。過去のcommit / snapshotから復元可能な履歴は維持します。

```bash
kcs gc --dry-run
kcs gc --prune-unreachable
```

デフォルト：

```text
削除しない
```

ユーザー明示時のみ。

ただし、削除・秘匿・法務要件に対してGCだけでは足りません。GCは「到達不能object」を消す機能であり、過去snapshotやtagから到達できる限り、対象ファイルは残ります。

そのためKCSは、Gitの履歴書き換えに相当する **purge** を持ちます。

```bash
kcs purge docs/secret.pdf --all-history --reason "legal erasure request"
kcs purge --raw-hash sha256:abc... --all-history
```

GUIでも、ファイル詳細・検索結果・履歴画面から **このファイルの履歴を完全削除** を実行できるようにします。

purgeは次を行います。

```text
対象path / raw_hashを参照する全tree / commit / manifestを書き換える
対象raw objectを到達不能にする
対象由来のnormalized / prepared unit / chunk / embedding / node / edge / evidenceを到達不能にする
index / pack / cacheを無効化または再構築する
到達不能化されたobjectをGCで物理削除する
```

保持する監査情報は、内容や秘匿pathを復元できない最小限のtombstoneに限ります。

```text
purge_id
actor
executed_at
reason
object_count_removed
redacted_target_label
```

つまりKCSの通常方針は「消さない」ですが、明示的な法務・秘匿・誤取り込み対応では、特定ファイルの全履歴を完全削除できます。

---

# 26. `.kcs` の新しい構造

この思想なら `.kcs` はこうなります。

```text
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
```

---

# 27. KCS object model

Git風に整理するとこうです。

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

# 28. KCS snapshotは何を保証するか

KCS snapshotは以下を保証します。

```text
その時点で存在したファイルの一覧
各ファイルの原文内容
各ファイルのMarkdown化結果
各chunk
検索用index metadata
知識ノード
Evidence Pointer
```

つまり、過去時点を再検索可能にする。

---

# 29. 検索体験の変化

この設計にすると、KCSは強い検索体験を提供できます。

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

# 30. KCSの価値の再定義

最も強い定義はこれです。

> **KCSは、ローカルファイルシステムをcontent-addressedな知識アーカイブへ変換し、現在・過去・削除済みのファイルを含む知識空間を、人間とAI Agentが共通の操作で探索できるようにするシステムである。**

---

# 31. Gitとの比較

| 項目         | Git      | KCS                        |
| ---------- | -------- | -------------------------- |
| 対象         | リポジトリ    | ローカルフォルダ全体                 |
| 主対象        | テキスト/コード | 全ファイル                      |
| 正規化        | なし       | Markdown化                  |
| AI検索       | なし       | あり                         |
| 原文保存       | blob     | raw object                 |
| Markdown保存 | なし       | normalized object          |
| 検索         | grep程度   | BM25 + Vector + Navigation |
| 履歴         | commit   | snapshot                   |
| 復元         | checkout | restore                    |
| 知識ノード      | なし       | あり                         |

---

# 32. 捨てるべきもの

この方針でも、捨てるものがあります。

## 捨てる

```text
Git本体との完全互換
Gitフォーク
差分だけ保存という説明
DBだけの軽量index思想
```

---

# 33. 残すべきもの

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

# 34. KCSがGitより優先する価値

Gitは容量効率と開発履歴を重視します。

KCSは、

```text
知識を失わないこと
AIが探索できること
原文へ戻れること
```

を重視します。

つまり、

> **KCSは容量効率より知識保存性を優先する。**

これを明言した方がいいです。

---

# 35. 最終方針

```text
Default:
  全ファイルを管理
  原文をcontent-addressed storeへ保存
  Markdown化結果も保存
  最新も過去も検索可能
  デフォルト検索は全 indexed scope を対象にする

Optional:
  .kcsignoreで除外
  gcで削除
  purgeで特定ファイルの全履歴を完全削除
  large file warning
```

---

# 36. 最終一文

READMEや設計書の最初に置くべき一文です。

> **KCS is a Git-inspired, local-first knowledge archive that stores every file as a content-addressed object, normalizes it into Markdown, and makes both current and historical knowledge navigable by humans and AI Agents.**

日本語：

> **KCSは、すべてのローカルファイルをcontent-addressed objectとして保存し、Markdown化して、現在と過去の知識を人間とAI Agentが探索できるようにするGit inspiredなローカル知識アーカイブである。**

これが現在の方針に最も合っています。

検索スコープは、現在の最終方針として次のように定義します。

# KCS検索スコープの最終方針

## 基本原則

> **検索のデフォルトは、KCSが認識しているすべてのフォルダ・ファイルを対象にする。現在フォルダのみ、または現在フォルダとその配下のみを対象にしたい場合は、明示的にscopeを指定する。**

初回の indexed scope は、ユーザーが `.kcsignore` や設定で明示的に除外していないすべての対象範囲とする。

つまり、KCSはローカルファイル空間全体の統一検索体験をデフォルトにします。これは、GoogleがWeb文書空間に対して提供した横断検索体験を、ローカルのファイル空間に持ち込むためです。

---

# 1. デフォルト検索範囲

例：

```text
A/
  .kcs/
  a.md
  B/
    .kcs/
    b.md
    D/
      .kcs/
      d.md
  C/
    .kcs/
    c.md
```

`A/` で検索：

```bash
cd A
kcs search "認証"
```

検索対象：

```text
A/.kcs
A/B/.kcs
A/B/D/.kcs
A/C/.kcs
Documents/.kcs
Work/.kcs
Downloads/.kcs
...
```

つまり、**KCSが認識している全 indexed scope**。

---

`A/B/` で検索：

```bash
cd A/B
kcs search "認証"
```

検索対象：

```text
A/.kcs
A/B/.kcs
A/B/D/.kcs
A/C/.kcs
Documents/.kcs
Work/.kcs
Downloads/.kcs
...
```

つまり、どのフォルダから実行しても、デフォルトは全体検索です。

---

# 2. スコープモデル

```text
default scope = all indexed scopes
restricted scope = explicitly selected folder scope
```

より形式的には：

```text
SearchScope(default)
= all registered / discovered KCS scopes
```

現在フォルダだけに制限する場合：

```text
SearchScope(--scope .)
= current folder scope only
```

現在フォルダと配下だけに制限する場合：

```text
SearchScope(--scope . --descendants)
= current folder scope + descendant scopes
```

---

# 3. `.kcs` の役割

各 `.kcs` は自分のフォルダ直下の情報だけを持つ。

```text
folder/.kcs
  = folder直下のファイル
  + 子フォルダ.kcsへのリンク
```

ただし、検索実行時のデフォルトは現在フォルダに閉じません。scope registry または探索済みの `.kcs` 一覧から全 indexed scope を検索し、ユーザーが指定した場合だけ対象を絞ります。

---

# 4. 検索時の探索

デフォルト検索：

```text
all indexed scopes
```

制限検索：

```text
--scope <path>              指定フォルダのみ
--scope <path> --descendants 指定フォルダと配下
--scope .                  現在フォルダのみ
--scope . --descendants     現在フォルダと配下
```

---

# 5. コマンド仕様

## デフォルト: 全体検索

```bash
kcs search "query"
```

意味：

```text
all indexed scopes
```

---

## 現在フォルダだけ

必要なら：

```bash
kcs search "query" --scope .
```

対象：

```text
current folder scope only
```

---

## 現在フォルダと配下

必要なら：

```bash
kcs search "query" --scope . --descendants
```

---

## 任意フォルダだけ

必要なら：

```bash
kcs search "query" --scope ./Research
```

---

## 任意フォルダと配下

必要なら：

```bash
kcs search "query" --scope ./Research --descendants
```

---

## 全体検索を明示

デフォルトと同じだが、スクリプトやAgentでは明示してもよい。

```bash
kcs search "query" --all-scopes
```

---

# 6. AI Agentにも同じルール

AI Agentが検索する場合も、デフォルトは全 indexed scope です。

```json
{
  "query": "認証仕様",
  "scope": "default"
}
```

解釈：

```text
all indexed scopes
```

レスポンスには検索範囲を明示します。

```json
{
  "scope": {
    "mode": "all_scopes",
    "included": [
      "/A/.kcs",
      "/A/B/.kcs",
      "/A/B/D/.kcs",
      "/A/C/.kcs"
    ],
    "excluded": []
  }
}
```

---

# 7. `.kcs/scope.json` のポリシー

ファイル名は `scope.json` を正とする。過去メモでの `folder.json` は同じ概念の旧称であり、実装では使わない。

各 `.kcs` にはこう書けます。

```json
{
  "folder_id": "kcs_folder_01H...",
  "path": ".",
  "parent": {
    "path": "../",
    "access_by_default": false
  },
  "children": [
    {
      "path": "B/",
      "kcs_path": "B/.kcs",
      "access_by_default": true
    }
  ],
  "policy": {
    "search_self": true,
    "participates_in_global_search": true,
    "allow_restricted_scope_search": true
  }
}
```

---

# 8. この設計の価値

この方針はかなり良いです。

理由：

* Finder / Explorer の感覚に近い
* ローカルファイル空間全体をGoogle検索のように扱える
* 現在フォルダや配下だけへの絞り込みもできる
* フォルダを公開単位にしやすい
* AI Agentの探索範囲をレスポンスで明示できる

---

# 9. 最終要件文

設計書にはこう書くのがよいです。

> KCSでは、検索のデフォルトスコープを「KCSが認識しているすべてのフォルダ・ファイル」とする。初回の indexed scope は、ユーザーが明示的に ignore していないすべての対象範囲である。各 `.kcs` は自フォルダ直下のファイルおよび子フォルダへのリンクのみを保持するが、検索時には全 indexed scope を対象にする。現在フォルダのみ、現在フォルダと配下、任意フォルダのみ、任意フォルダと配下を対象にしたい場合は、明示的なscope指定で検索範囲を制限する。

---

# 最終定義

```text
Default search = all indexed scopes
Restricted search = explicit scope option
```

`kcs init` は現在フォルダの `.kcs` を作成する。子フォルダの `.kcs` は、`kcs index` や探索処理が ignore されていない対象を発見した時点で必要に応じて生成する。各フォルダに `.kcs` を置く前提は維持しつつ、空フォルダや未到達フォルダへ先回りして全生成する必要はない。

この仕様で進めるのが良いです。


理解しました。ここは設計の根幹なので、認識を修正します。

あなたの想定する `.kcs` は、**知識スコープのルートに1つ置く方式ではなく、各フォルダに配置されるフォルダローカルな管理単位**です。
かなり **macOS の `.DS_Store` 的** な発想に近いです。

---

# 修正後の `.kcs` の考え方

## 基本定義

> **`.kcs` は、基本的にすべてのフォルダに隠しディレクトリとして生成され、自分が配置されているフォルダ直下のファイル・フォルダに関するMarkdown化結果・インデックス・メタ情報だけを保持する。**

つまり、`.kcs` はそのフォルダの管理ファイルです。知識スコープのルートに1つだけ置くものではなく、子フォルダや孫フォルダにもそれぞれ存在します。

```text
Documents/
  .kcs/
  report.pdf
  memo.md
  Research/
    .kcs/
    paper.pdf
  Work/
    .kcs/
    spec.docx
```

このとき、

```text
Documents/.kcs
```

が直接管理するのは、

```text
Documents/report.pdf
Documents/memo.md
Documents/Research/
Documents/Work/
```

までです。

`Research/paper.pdf` のMarkdown化結果は、

```text
Documents/Research/.kcs
```

が持ちます。

---

# Gitとの違い

Gitはこうです。

```text
repo/
  .git/
  src/
  docs/
```

`.git` が repo 全体を管理します。

KCSはこうです。

```text
root/
  .kcs/
  folderA/
    .kcs/
  folderB/
    .kcs/
```

各フォルダが自分の `.kcs` を持ちます。

つまり、

```text
Git = centralized repository metadata
KCS = distributed folder metadata
```

です。

---

# `.DS_Store` との近さ

macOS の `.DS_Store` は、各フォルダに置かれ、そのフォルダの表示状態などを保存します。

KCSの `.kcs` は、それをAI時代向けに拡張したものです。

```text
.DS_Store = フォルダ表示メタデータ
.kcs      = フォルダ知識メタデータ
```

---

# この方式の強み

## 1. スコープ制御が自然

各 `.kcs` は自分のフォルダしか管理しません。

したがって、検索時に scope を明示すれば、

```text
現在フォルダだけ
現在フォルダと配下だけ
任意フォルダだけ
```

へ自然に制限できます。デフォルト検索は全 indexed scope ですが、個々の `.kcs` が持つ情報はフォルダローカルです。

---

## 2. アクセス制御がしやすい

たとえば、

```text
Documents/
  Work/
    .kcs/
  Private/
    .kcs/
```

で、`Work/.kcs` 自体は `Private/.kcs` の中身を直接管理しない。

つまり、兄弟フォルダの情報は個々の `.kcs` に混ざらない。全体検索で `Private/.kcs` も対象にするかどうかは、scope registry、ignore、権限、明示的なscope指定で制御します。

---

## 3. フォルダ単位で公開しやすい

```text
Research/
  .kcs/
  paper.pdf
  notes.md
```

このフォルダを共有すれば、そのフォルダのKCS情報だけも一緒に共有できます。

`.kcs` 単位で公開可能、という思想と相性が良いです。

---

## 4. 部分同期しやすい

クラウド化した場合も、

```text
特定フォルダ + その .kcs
```

だけ同期すればよいです。

Google Drive / Dropbox / iCloud 的なフォルダ共有と相性が良いです。

---

# この方式で必要な設計

## `.kcs` はそのフォルダ内だけを管理する

明確なルール：

```text
folder/.kcs は folder 直下のファイルと子フォルダへのリンクのみ管理する
child/.kcs は child 直下のファイルと子フォルダへのリンクのみ管理する
grandchild/.kcs は grandchild 直下のファイルと子フォルダへのリンクのみ管理する
```

子フォルダの中身は管理しない。

---

# 具体例

```text
A/
  .kcs/
  a.md
  B/
    .kcs/
    b.pdf
  C/
    .kcs/
    c.docx
```

## `A/.kcs` が持つもの

```text
a.md のMarkdown化結果
B/ への child link
C/ への child link
```

## `B/.kcs` が持つもの

```text
b.pdf のMarkdown化結果
親 A/ への parent link
```

## `C/.kcs` が持つもの

```text
c.docx のMarkdown化結果
親 A/ への parent link
```

---

# 検索時の動作

## デフォルト検索

KCSが認識している全 indexed scope。

```bash
cd A/B
kcs search "認証"
```

検索対象：

```text
A/.kcs
A/B/.kcs
A/C/.kcs
その他の登録済み .kcs
```

つまり、実行位置に関係なくデフォルトは全体検索。

---

## 現在フォルダだけにする場合

明示的に指定。

```bash
kcs search "認証" --scope .
```

検索対象：

```text
A/B/.kcs
```

---

## 現在フォルダと子フォルダを含める場合

明示的に指定。

```bash
kcs search "認証" --scope . --descendants
```

この場合、`B/.kcs` から子 `.kcs` を辿る。

---

## 任意フォルダだけを検索する場合

明示的に指定。

```bash
kcs search "認証" --scope ../C
```

---

## 任意フォルダと配下を検索する場合

```bash
kcs search "認証" --scope ../C --descendants
```

---

## 全体検索を明示する場合

```bash
kcs search "認証" --all-scopes
```

---

# 親・子パスの保存

あなたの言う通り、各 `.kcs` は親と子のパスだけを持つ。

```json
{
  "folder_id": "sha256:...",
  "path": "/Users/takumi/Documents/A/B",
  "parent": "../",
  "children": [
    {
      "name": "subfolder",
      "path": "subfolder/",
      "kcs_path": "subfolder/.kcs"
    }
  ]
}
```

ただし、兄弟のパスは各 `.kcs` が直接持たなくてもよい。全体検索は、個々の `.kcs` が兄弟を知ることではなく、scope registry または探索済み `.kcs` 一覧を検索実行側が束ねることで実現する。

```text
各 .kcs は親と子だけ知る
検索実行側は全 indexed scope を束ねる
```

これが安全です。

---

# `.kcs` 内部構造

各フォルダの `.kcs` は軽量であるべきです。

```text
folder/
  .kcs/
    VERSION
    scope.json
    manifest.json
    normalized/
    index/
      sqlite.db
    objects/
    logs/
```

---

# `scope.json`

```json
{
  "kcs_format": "0.1.0",
  "folder_id": "kcs_folder_01H...",
  "folder_path": ".",
  "parent": {
    "path": "../",
    "kcs_path": "../.kcs",
    "relation": "parent_link"
  },
  "children": [
    {
      "name": "Research",
      "path": "Research/",
      "kcs_path": "Research/.kcs",
      "relation": "child_link"
    }
  ],
  "policy": {
    "participates_in_global_search": true,
    "allow_restricted_scope_search": true
  }
}
```

---

# `manifest.json`

直下のファイルのみ。

```json
{
  "files": [
    {
      "path": "memo.md",
      "kind": "text_native",
      "raw_hash": "sha256:...",
      "normalized_hash": "sha256:...",
      "status": "indexed"
    },
    {
      "path": "report.pdf",
      "kind": "non_text_native",
      "raw_hash": "sha256:...",
      "normalized_hash": "sha256:...",
      "status": "indexed"
    }
  ],
  "folders": [
    {
      "path": "Research/",
      "kcs_path": "Research/.kcs"
    }
  ]
}
```

---

# `normalized/`

そのフォルダ直下のファイルだけ。

```text
A/.kcs/normalized/
  a.md
  report.pdf.md
```

`B/b.pdf` は `B/.kcs/normalized/` に保存します。

---
