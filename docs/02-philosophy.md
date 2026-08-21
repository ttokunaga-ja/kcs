# 02 Philosophy

> **NOTE**: プロダクト位置づけ・ターゲット・MVP スコープ・競合分析は [01-positioning.md](01-positioning.md) を正本とする。本書は **理念の根拠** (なぜ Evidence Pointer か、なぜ Markdown 正規化か、なぜ消えない履歴か) のみを語る。

# 0. Kio は何か (一行で)

```
英: Evidence-grounded local knowledge archive
日: 原文根拠付きローカル知識アーカイブ
```

> **ローカルファイルを、過去も含めて、AI と人間が根拠付きで探索できる知識アーカイブにする。**

Kio は次のいずれでもない: 「全部入りの Git for knowledge」「個人 AI 検索ツール」「OS 級プロダクト」「Knowledge Graph プラットフォーム」。詳細は [01-positioning.md](01-positioning.md)。

# 0.1 Kio の作成意図

長年、ローカルのファイル空間では PDF、PowerPoint、Word、画像、スキャン資料のような、検索・引用・再利用に向かない形式がデフォルトになってきました。一方で Web では、Google が文書空間に検索体験を与え、ブラウザを通じて同じ指標・同じフォーマット・同じ操作感で知識へアクセスできるようにしました。

Kio は、その体験をローカルファイル空間にも持ち込む試みです。ただし「全部を一新する」のではなく、**既存ワークフロー (Obsidian vault, Documents, Downloads, Git リポジトリ群) を置き換えず横断する外部アーカイブ層** として始めます。原本ファイルを失わずに保持しつつ、Markdown を主とした統一テキスト表現へ正規化し、人間と AI Agent が同じ知識空間を検索・比較・引用・復元できるようにします。

Kio の最初のターゲットは **大量の PDF・Markdown・コード・画像を扱う開発者・研究者・技術者** です。一般ユーザー向けの GUI プロダクトではありません ([01-positioning.md §2](01-positioning.md))。Git の思想を借りますが、「Git を一般ユーザーに翻訳する」プロダクトではなく、**content-addressing / snapshot / restore / provenance を Evidence Pointer という形に再構成した知識アーカイブ** です。

---

# Git・競合VCSの思想と、Kioの位置づけ

## 1. Gitが本来解こうとしている問題

Gitは、もともと**ソースコード開発のための分散バージョン管理システム**です。公式にも、Gitは小規模から大規模プロジェクトまで高速・効率的に扱う分散VCSと説明されています。GitHub上のGitリポジトリ説明でも、Gitは高速・スケーラブルな分散リビジョン管理システムであり、高水準操作から内部操作まで扱える豊富なコマンド群を持つとされています。([Git][1])

Gitの中心思想は次です。

```text
Gitが重視するもの:
- 分散開発
- ローカルでの完全な履歴保持
- ブランチによる作業分離
- マージによる統合
- コミット単位の履歴管理
- 開発者が明示的に履歴を操作する自由
```

これはソフトウェア開発では非常に強力です。

しかし、Kioが扱おうとしている対象は、純粋なソースコードではありません。

```text
Kioが扱うもの:
- PDF
- PowerPoint
- Word
- 画像
- 講義資料
- 抽出Markdown
- RAG用チャンク
- 出典情報
- 時点情報
- バージョン情報
```

つまり、KioはGitのような「コードの履歴管理」ではなく、**知識の構造・出典・時点・版・文脈を管理する基盤**を目指しています。

---

# 2. Gitの構造的・思想的な問題点

## 2.1 一般ユーザーには概念が重い

Gitには、次のような概念があります。

```text
branch
merge
rebase
commit
checkout
HEAD
detached HEAD
index
staging area
stash
remote
origin/main
conflict
```

開発者には必要ですが、一般ユーザー向けの知識管理・資料管理では重すぎます。

特にKioでは、ユーザーに求めたい体験は次です。

```text
ユーザーに見せたい体験 (MVP):
- 資料を入れる
- 自動で検索可能になる
- 過去の版と根拠 (Evidence Pointer) を辿れる
```

ここにGit用語をそのまま持ち込むと、一般ユーザーには理解しにくくなります。

現在の CLI は `snapshot` と `restore` を公開し、履歴 object を `commit` と呼ぶ。作成入口は
`kio snapshot create` だけで、旧 `kio commit` alias は受理しない。

---

## 2.2 Gitの競合は「作業停止」として現れる

Gitでは、競合が起きると多くの場合、ユーザーが手動で解決しなければ作業が進みません。

```text
Git的な競合:
- merge conflict が発生
- ファイル内に conflict marker が入る
- ユーザーが手動修正
- git add
- merge / rebase 続行
```

これは開発者向けには妥当ですが、一般向け知識管理では厳しいです。

Kio の現在の CLI に同期・merge・競合解決 surface はない。未実装機能の名称は
[09-mvp-scope.md](09-mvp-scope.md) の非承認 roadmap だけに置く。

---

## 2.3 Gitはコード向けであり、PDF/PPTX/画像には合いにくい

Gitはテキストコードの差分には強いですが、Kioが扱う原本ファイルは多くが非コードです。

```text
Kioの原本:
- PDF
- PPTX
- DOCX
- 画像
- スキャン資料
- HTML
```

これらはGitのように自動マージする対象ではありません。

そのためKioでは、原本ファイルに対してGit的なmergeをしません。

```text
Kioの原本ファイル方針:
- 原本ファイルは自動マージしない
- 変更が来たら新しい版として保存する
- 後から登録された版を最新とする
- 過去版は保持する
- 戻す場合も新しい版として記録する
```

つまり、Kioでは原本ファイルを「編集可能なテキスト差分」ではなく、**時点ごとの証拠オブジェクト**として扱います。

---

## 2.4 Gitは履歴改変が強力すぎる

Gitでは、`rebase`、`reset`、`amend`、`force push` などによって履歴を書き換えられます。

これは開発者には便利ですが、Kioでは危険です。

Kioで重要なのは、次のような監査可能性です。

```text
Kioで必要な監査性:
- どの原本ファイルがいつ追加されたか
- どの版が最新だったか
- どの抽出Markdownがどの原本版から生成されたか
- どの tool_profile による Markdown 化が有効だったか
```

そのためKioでは、Gitのような履歴改変を避けます。

```text
Kioの履歴方針:
- 原本ファイルはimmutable
- 抽出Markdownもimmutable
- 修正パッチは禁止
- リバートも新しい版として記録
- 削除は原則archive
- 法務・秘匿・誤取り込みでは明示的な purge で**本文を全履歴から物理削除**可能 (commit / tree の構造 metadata — path 文字列と raw_hash — は残る。§6.1)
- イベントログを残す
```

Kioでは「きれいな履歴」よりも、**消えない履歴・検証可能な履歴・出典を追える履歴**を重視します。

## 「忘れない」と purge の両立

Kio の中核主張は「原則として忘れない」ことです。一方で、法務・秘匿・誤取り込みの場合に履歴ごと削除する `purge` も提供します。これらは矛盾しません。**purge は「忘れる」のではなく「消した事実を記録して忘れる」操作**として位置づけます。

purge の例外性は次のように担保します:

```text
1. purge は通常削除 (archive) と明確に区別する。
   - archive: 履歴上は残し「現在は使っていない」状態にする。デフォルト操作。
   - purge: 履歴から物理的に消す。例外操作。

2. purge を発動できるのは次の正当事由がある場合に限る:
   - 法令上の削除義務 (個人情報・GDPR の forget 権 等)
   - 機密漏洩への対応 (誤って取り込んだ秘匿文書)
   - 著作権・契約上の保持禁止
   - 誤取り込みの是正 (取り込むべきでなかった対象 — 秘匿文書に限らない)

3. purge を実行すると、対象内容は消えるが「purge した事実」は残る:
   - commit_type = "purged" の新 commit が記録される
   - 誰が、いつ、どの正当事由で実行したかを保存
   - これにより監査可能性は維持される (= 透明な忘却)

4. purge は破壊的操作として、CLI で明示確認を必須とし (対話の確認プロンプトまたは非対話の `--yes` — [05-runtime.md §3.1](05-runtime.md))、
   `--reason <legal|privacy|misingest|copyright|other>` を必須引数とする (閉 enum — [08-evidence-pointer-spec.md](08-evidence-pointer-spec.md) §4.1 の purged_reason と同一)。
```

つまり Kio は「忘れない」を理念としつつ、「忘れる必要があるときは、忘れたことを忘れない」かたちで purge を内包します。詳細手順は [05-runtime.md](05-runtime.md) §3 (Purge) と [06-cli-spec.md](06-cli-spec.md) §6 を正本とする。

---

# 3. 競合製品・新しいVCSから学べること

## 3.1 Jujutsu: 競合を後から解決できる状態として扱う

Jujutsuは、Gitのように競合で操作を止めるのではなく、競合状態をコミットに記録し、後から解決できる設計を持っています。([JJ VCS Docs][2])

```text
Jujutsuから学ぶこと:
- 競合を即時解決必須の失敗状態にしない
- 競合状態をデータとして保存する
- ユーザーは後から解決できる
```

---

## 3.2 Pijul: patchを一級概念にし、競合を通常状態として扱う

Pijulは、patch theoryに基づくVCSであり、公式サイトでも競合を「mergeの失敗」ではなく標準ケースとして扱うと説明しています。([Pijul][3])

Kioへの示唆は、**変更そのものを意味のある単位として扱うべき**という点です。

Gitではファイルツリーのスナップショットが中心ですが、Kioでは次のような意味的変更が重要です。

```text
Kioで重要な変更:
- 注釈を追加した
- タグを追加した
- 資料リンクを作った
- 原本ファイルの新しい版が登録された
- 抽出Markdownが生成された
- tool_profile が更新され再Markdownizeされた
```

ただし Kio の正本アーキテクチャは CAS + snapshot DAG (tree/commit) である ([03-data-model.md](03-data-model.md) §1)。Pijul から学ぶのは「意味的変更を追跡可能な単位として残す」姿勢であり、Kio ではこれを snapshot DAG の commit_type と observability ログ ([10-operations.md](10-operations.md)) で実現する。イベントログを正本にはしない。

---

## 3.3 Sapling: Git互換を保ちつつ、使いやすさと大規模性を改善する

MetaのSaplingは、Git互換性を持ちながら、ユーザーフレンドリーさとスケーラビリティを重視したソース管理システムです。MetaはSaplingを「user-friendly and scalable」と位置づけ、大規模リポジトリにも対応する設計を説明しています。([Engineering at Meta][4])

Saplingは、stacked commitsやレビューしやすいワークフローを重視しています。公式ドキュメントでも、commit stackを編集しやすくする仕組みが説明されています。([Sapling][5])

Kioへの示唆は次です。

```text
Saplingから学ぶこと:
- 内部は高度でも、UIは使いやすくする
- 大規模データに耐える必要がある
- 変更を小さく分け、レビューしやすくする
- ユーザーがミスから復元しやすい設計にする
```

Kioではこれを、次のように置き換えます。

```text
Kioでの方針:
- 内部構造 (CAS / DAG) の複雑さを CLI の少数コマンドに隠す
- ユーザーがミスから復元しやすくする (snapshot / restore)
- 大量資料でも検索・復元可能にする
```

---

# 4. Kioが成し遂げようとしていること

Kio、つまり Knowledge Coordinate System が目指しているのは、単なるMarkdown管理でも、単なるクラウド同期でも、単なるRAG用前処理でもありません。

Kioが成し遂げようとしているのは、**知識を「座標を持つもの」として管理すること**です。

---

## 4.1 従来のRAGの問題

通常のRAGでは、文書をチャンク化し、ベクトル検索や全文検索で近いものを探します。

```text
通常のRAG:
文書
  ↓
Markdown化 / テキスト化
  ↓
チャンク化
  ↓
Embedding
  ↓
検索
  ↓
回答生成
```

しかし、この方法では次の問題が起きます。

```text
通常RAGの問題:
- 古い資料と新しい資料が混ざる
- 同じ概念の年度差分を区別できない
- 出典ページは出せても、版や時点が曖昧
- 誰が追加した情報か分からない
- 原本由来かユーザー注釈か曖昧
- 抽出ミスと原本内容が混ざる
- 修正や再抽出の履歴が追えない
- 競合した知識をどう扱うかが曖昧
```

特に講義資料QAや研究室ナレッジでは、単に「似ている文書」を探すだけでは不十分です。

必要なのは、

```text
この知識は
どの原本の
どの版の
どのページから
いつ抽出され
どの抽出版が使われ
どの文脈で有効で
誰の注釈なのか
```

を扱えることです。

---

## 4.2 Kioの目的

Kioの目的は、知識を次のような多次元座標で扱うことです。

```text
K = (S, R, T, V, P, C)

S: Semantic
   意味的な近さ・埋め込み表現

R: Relation
   概念・資料・ページ・注釈・タグ間の関係

T: Time
   時点・年度・有効期間

V: Version
   原本ファイル版・抽出版・変更履歴

P: Provenance
   出典・原本・抽出方法・作成者・信頼度

C: Context
   授業・研究テーマ・ユーザー・チーム・検索目的
```

つまりKioは、文書を単なるテキストではなく、**意味・関係・時間・版・出典・文脈を持つ知識オブジェクト**として扱います。

---

# 5. KioがGitから取り入れるもの・捨てるもの

## 5.1 取り入れるもの

KioはGitの思想を完全に否定するわけではありません。

むしろ、次の良さは取り入れます。

```text
Gitから取り入れるもの:
- 履歴を残す
- 差分を見られる
- 以前の版に戻せる
- 誰が何を変えたか追跡できる
- 変更をレビューできる
- 最新版と過去版を区別できる
```

これらはKioにも必要です。

---

## 5.2 捨てるもの

一方で、Gitの表面概念は捨てます。

```text
Kioで捨てるGit的要素:
- Branchをユーザーに見せる
- Mergeを手動でさせる
- Rebaseをさせる
- Conflict markerを出す
- HEADやindexを意識させる
- force push的な履歴改変
- 原本ファイルの自動マージ
```

理由は、Kioの対象がソースコード開発ではなく、**PDF・画像・ノートを含む知識アーカイブ**だからです。原本バイナリに merge/rebase の概念は成立しない。ターゲットユーザーは [01-positioning.md](01-positioning.md) §2 (開発者・研究者・技術者) を正本とする。

---

# 6. Kioの具体的な設計方針

## 6.1 原本ファイルは証拠として扱う

Kioでは、PDFやPPTXなどの原本ファイルを編集可能なテキストではなく、証拠として扱います。

```text
原本ファイル:
- 変更ごとに新しい版として保存
- 自動マージしない
- 後から来た版を最新にする
- 過去版は保持する
- 戻す場合も新しい版として記録
```

これにより、原本性が守られます。

ただし、法務・秘匿・誤取り込みなどで「過去の履歴からも消す」必要がある場合は例外です。この場合は通常の削除やGCではなく、`purge` を明示的に実行し、**消す事実の記録 (tombstone) を先に耐久化したうえで**、対象ファイルに由来する raw / prepared / image / normalized / chunk / embedding / index の本文を全履歴にわたり物理削除します (共有され得る prepared / image / embedding は他文書からの live 参照が 0 の場合のみ — marker は既定 tombstone、`--erase-tombstone` は non-public receipt — 用途は [08-evidence-pointer-spec.md §4.2](08-evidence-pointer-spec.md) の列挙) (順序と対象の正本は [05-runtime.md](05-runtime.md) §3.5 — 記録が先でないと、クラッシュ時に「消えたのに痕跡が無い」状態になります) (commit / tree object 自体の履歴 DAG は書き換えません。詳細は [05-runtime.md](05-runtime.md) §3.5)。MVP では CLI (`kio purge <path|--raw-hash <h>> --reason <...>`、[06-cli-spec.md](06-cli-spec.md) §6) で提供する。

---

## 6.2 抽出Markdownは編集しない

Kioでは、原本ファイルから抽出されたMarkdownを編集対象にしません。

```text
抽出Markdown:
- 原本由来の証拠表現
- 読み取り専用
- immutable
- 修正パッチ禁止
- 原本版ごとに生成
- tool_profile が変われば別 artifact として保存
```

これは、RAG回答の根拠が「本当に原本に基づくものか」を守るためです。

抽出ミスがある場合は、本文修正ではなく、

```text
- tool_profile の更新 (Adapter / prompt / モデルの改訂) による再 Markdownize
  → identity (raw_hash, tool_profile_hash) が変わり、別 artifact として保存される
- 同一 tool_profile での明示的な再実行 (kio reindex --regenerate)
```

で扱います。

---

# 7. KioがGitや既存VCSより先に進めたい部分

KioはGitの代替VCSを作りたいわけではありません。

Kioが目指すのは、**知識管理に特化した、RAG時代の版管理・出典管理**です。

Gitが主に扱うのは、

```text
ファイルの変更履歴
```

です。

Kioが扱いたいのは、

```text
知識の成立条件
```

です。

具体的には、次の違いがあります。

| 観点     | Git       | Kio                       |
| ------ | --------- | ------------------------- |
| 主対象    | ソースコード    | 知識・資料・注釈・抽出結果             |
| 正本     | リポジトリ履歴   | folder-local `.kio` (raw object + 派生 artifact + snapshot DAG) |
| 競合     | 手動解決      | 現行範囲外 |
| Branch | 明示的に使う    | 現行CLI surface には含めない |
| 履歴     | 改変可能      | 監査性重視、原則append-only       |
| バイナリ資料 | 苦手        | 版追加で扱う                    |
| RAG連携  | 想定外       | 中核機能                      |
| 出典管理   | ファイル単位中心  | ページ・抽出版・時点・文脈まで扱う         |
| 時点指定   | Git履歴で間接的 | 知識座標として明示                 |
| ユーザー層  | 開発者       | 開発者・研究者・技術者 |

---

# 8. Kioの本質的な価値

Kioが成し遂げようとしていることを一文で言うなら、次です。

```text
Kioは、文書を単なるファイルやMarkdownではなく、意味・関係・時間・版・出典・文脈を持つ「知識座標」として管理し、RAGや人間の検索・編集・共有において、どの知識をどの根拠で使っているかを明確にする仕組みである。
```

もう少し実装寄りに言うと、Kioは次を実現します。

```text
Kioが実現すること (MVP):
1. 原本ファイルの版管理
2. Markdown 化 artifact の immutable 管理
3. 出典 (Evidence Pointer)・原本版・抽出条件 (tool_profile) の追跡
4. 時点指定検索 (--at)
5. 版差分の比較

```

---

# 9. Kioの研究・プロダクト上の主張

Kioの主張は、以下のように置けます。

## 主張1：RAGには「検索精度」だけでなく「知識の座標」が必要

従来のRAGは、意味的に近いチャンクを探すことに偏っています。

しかし実際には、

```text
似ているが古い資料
同じ言葉だが年度が違う定義
出典はあるが抽出版が古い情報
ユーザー注釈と原本情報の混在
```

が問題になります。

Kioは、これを `S, R, T, V, P, C` の座標で管理します。

---

## 主張2：Gitの履歴管理は有用だが、そのまま知識管理には使えない

Gitの履歴・差分・復元の思想は有用です。

しかし、

```text
Branch
Merge
Rebase
Conflict
Commit
HEAD
```

をそのまま Kio の CLI surface に持ち込むべきではありません。現在の CLI は
snapshot、restore、Evidence という必要な操作だけを公開します。

---

## 主張3：抽出Markdownは編集用ノートではなく、証拠表現である

原本由来のMarkdownを編集可能にすると、RAGの出典整合性が崩れます。

そのためKioでは、

```text
抽出Markdown = 原本を検索・引用するための証拠表現
```

として扱います。

ユーザー編集を抽出 Markdown に混ぜず、誤抽出は tool profile を更新した再 Markdownize
または明示的 reindex で扱います。

---

# 10. 最終的なKioの設計原則

Kioの設計原則は、次のようにまとめられます。

```text
1. 原本ファイルは証拠として版管理する
2. 原本ファイルは自動マージしない
3. 後から来た原本版を最新とする
4. 過去版は保持する
5. リバートも新しい版として記録する
6. 抽出Markdownはimmutableにする
7. 抽出Markdownの修正パッチは禁止する
8. 誤抽出は tool_profile 更新による再 Markdownize または明示的 reindex で扱う
9. folder-local .kio を正本とする
10. すべての重要変更をイベントログとして残す
11. 知識を意味・関係・時間・版・出典・文脈の座標で扱う
12. 法務・秘匿要件では特定ファイルの本文を全履歴から明示的に完全削除できる (構造 metadata — path 文字列と raw_hash — は残る。§2.4)
```

---

# まとめ

Gitは、ソフトウェア開発のための分散バージョン管理として非常に優れています。
しかしKioが扱いたいのは、コードではなく、**原本資料・抽出テキスト・注釈・タグ・出典・時点・文脈を含む知識空間**です。

そのためKioでは、Gitの良さである、

```text
履歴
差分
復元
レビュー
変更追跡
```

を取り込みます。

一方で、Gitの一般ユーザーに不向きな部分である、

```text
Branch
Merge
Rebase
HEAD
Conflict marker
履歴改変
手動競合解決
```

は表に出しません。

Kioが目指すのは、最終的に次の状態です。

```text
ユーザーには、資料を入れるだけで検索・引用・要約できるように見える。
内部では、原本版・Markdown 化 artifact・出典・時点が厳密に管理されている。
AIは、どの知識をどの根拠で使っているかを明示できる。
```

つまりKioは、**Gitのような履歴管理を、RAG時代の知識管理に再設計する試み**です。

[1]: https://git-scm.com/?utm_source=chatgpt.com "Git"
[2]: https://docs.jj-vcs.dev/latest/conflicts/?utm_source=chatgpt.com "Conflicts"
[3]: https://pijul.org/?utm_source=chatgpt.com "Pijul"
[4]: https://engineering.fb.com/2022/11/15/open-source/sapling-source-control-scalable/?utm_source=chatgpt.com "Sapling: Source control that's user-friendly and scalable"
[5]: https://sapling-scm.com/docs/overview/stacks/?utm_source=chatgpt.com "Stacks of commits"
