以下の方針でまとめるのがよいです。

# 同期に関する指針

> NOTE: MVPは単一端末・local-firstを優先する。この文書は将来の同期・共有・Web修正提案を扱う研究ノートであり、MVPの正本はローカルobject store / snapshot / search / restore / purgeである。

## 1. 基本思想

同期では、ユーザーにGitのような複雑な概念を見せない。
ユーザー体験としては、次の状態を目指す。

```text
通常時:
  編集内容は自動で同期される

競合時:
  共有版が優先される

自動反映できない変更:
  Web上の「修正提案」として保存される

原本ファイルの変更:
  上書きではなく、新しい版として保存される
```

内部的にはバージョン管理を行うが、UIではBranch、Merge、Commit、Rebaseなどの用語を出さない。

ユーザーには、

```text
共有版
変更履歴
修正提案
以前の版に戻す
```

のような言葉で説明する。

---

# 2. 同期対象の分類

同期対象は、まず次の4種類に分ける。

```text
1. 原本ファイル
   PDF / PPTX / DOCX / 画像 / HTML など

2. 抽出Markdown
   原本ファイルから生成された検索・引用用テキスト

3. 共有データ
   共有ノート、共有タグ、共有リンク、共有ビュー、資料セット設定など

4. 個人データ
   個人メモ、個人注釈、個人タグ、個人ビュー、閲覧履歴など
```

それぞれ同期ルールを分ける。

---

# 3. 原本ファイルの同期指針

原本ファイルは、**変更ごとに新しい版として保存する**。

```text
原本ファイル v1
  ↓ 変更検知
原本ファイル v2
  ↓ 変更検知
原本ファイル v3
```

重要なルールは次の通り。

```text
- 同一ハッシュなら新しい版を作らない
- 内容が変わっていれば新しい版として保存する
- 原本ファイルは自動マージしない
- 後から登録された版を最新として扱う
- 過去版は削除せず保持する
- 戻す場合は、過去版の内容を使った新しい版を作る
```

つまり、原本ファイルは「上書き」ではなく「版追加」で扱う。

---

## 3.1 後から来た版を最新にする

基本ルールは、

```text
最後に登録された原本ファイル版を最新とする
```

でよい。

例：

```text
10:00 A端末が lecture.pdf を更新 → v2
10:05 B端末が lecture.pdf を更新 → v3

latest = v3
```

ただし、v2もv3も保持する。

---

## 3.2 古いファイルが後から来た場合

後から来たファイルが実際には古い内容であっても、原則として新しい版として登録する。

```text
10:00 最新の lecture.pdf → v2
10:10 古い lecture.pdf が別端末から同期 → v3

latest = v3
```

この場合も、履歴からv2へ戻せるようにする。

より安全にするなら、古い可能性がある場合に警告を出す。

```text
このファイルは以前の版を元にしている可能性があります。
新しい版として保存します。
```

ただし、一般ユーザー向けには最初から過度に警告しすぎない方がよい。

---

## 3.3 原本ファイルのリバート

過去版に戻す場合も、過去版を直接 current に戻すのではなく、新しい版として保存する。

```text
v1
v2
v3
v4: v2 の内容に戻す版
```

ユーザーには、

```text
以前の版に戻しました
```

と表示すればよい。

内部的には、`v4` が最新になる。

---

# 4. 抽出Markdownの同期指針

抽出Markdownは、原本ファイルから生成された **証拠表現** として扱う。

```text
原本ファイル
  ↓
抽出Markdown
  ↓
検索・引用・RAG
```

抽出Markdownについては、次のルールを徹底する。

```text
- 編集不可
- 修正パッチ不可
- 変更が必要な場合は再抽出する
- 原本ファイルの版ごとに別の抽出Markdownを生成する
- 抽出Markdownも immutable artifact として保存する
```

例：

```text
原本ファイル v1
  └─ 抽出Markdown e1

原本ファイル v2
  └─ 抽出Markdown e2

原本ファイル v3
  └─ 抽出Markdown e3
```

原本ファイルが最新になった場合は、その版に対応する抽出Markdownを生成する。

---

## 4.1 再抽出の扱い

同じ原本版に対して再抽出する場合も、既存の抽出Markdownを上書きしない。

```text
原本 v3
  ├─ extract e3a: prompt v1
  ├─ extract e3b: prompt v2
  └─ active: e3b
```

検索・RAGでは、原則として `active` の抽出Markdownだけを使う。

---

## 4.2 誤抽出の扱い

誤抽出があっても、抽出Markdown本文は修正しない。

```text
悪い:
  抽出Markdownの本文を直接修正する

良い:
  抽出Issueとして記録する
  再抽出提案を作る
  新しい抽出Markdownを生成する
```

誤抽出への対応は、

```text
抽出Issue
再抽出提案
active抽出版の切り替え
```

で行う。

---

# 5. 共有データの同期指針

共有データは、オンライン上の **共有版** を正本とする。

```text
同期時の正本:
  Web上の共有版
```

ローカル変更は、共有版に安全に反映できる場合だけ適用する。

```text
ローカル変更
  ↓
共有版との差分確認
  ↓
自動マージ可能 → 共有版へ反映
  ↓
自動マージ不可 → 修正提案として保存
```

---

## 5.1 通常の同期

ローカル変更の基準版と、現在の共有版が同じなら、そのまま反映する。

```text
base_version == current_shared_version
  ↓
共有版へ反映
```

例：

```text
共有版: v10
ローカル編集開始時: v10
同期時の共有版: v10

結果:
  そのまま共有版 v11 として反映
```

---

## 5.2 共有版が先に進んでいた場合

ローカル編集後に、他端末や他ユーザーが共有版を更新していた場合は、自動マージを試す。

```text
base_version != current_shared_version
  ↓
自動マージを試す
```

自動マージできる場合は、共有版へ反映する。

```text
別ブロックの編集
別ノートの編集
タグの追加同士
注釈の追加同士
コメント追加
```

自動マージできない場合は、共有版を優先し、ローカル変更はWeb上の修正提案にする。

---

# 6. 個人データの同期指針

個人データは、できるだけ共有データと分離する。

```text
個人メモ
個人注釈
個人タグ
個人ビュー
閲覧履歴
お気に入り
```

これらは基本的に他人の編集と競合しにくい。

個人データは、同一ユーザーの複数端末間で同期する。

```text
Macの個人メモ
  ↓
Web
  ↓
Windows / iPhone
```

個人データの競合も基本は自動解決する。
自動解決できない場合は、共有版ではなく **個人用の修正提案** として保存する。

---

# 7. 競合解決の指針

競合解決では、ユーザーに複雑な操作を求めない。

基本ルールは次の通り。

```text
1. 自動マージを試す
2. 自動マージできるものは共有版へ反映する
3. 自動マージできないものは共有版を優先する
4. 反映できなかった変更はWeb上の修正提案にする
```

このとき、ローカル変更を端末内だけに退避しない。

```text
悪い:
  ローカル端末だけに退避

良い:
  Web上の修正提案として保存
```

---

## 7.1 自動マージしてよい変更

以下は自動マージしやすい。

```text
- 別ノートの編集
- 別ブロックの編集
- 新しい注釈の追加
- コメント追加
- タグ追加
- リンク追加
- 個人ビュー変更
- お気に入り
- 閲覧履歴
```

例：

```text
共有版:
  タグA

ローカル変更:
  タグBを追加

同期結果:
  タグA + タグB
```

---

## 7.2 修正提案にする変更

以下は自動反映せず、修正提案に回す。

```text
- 同じ本文範囲への競合編集
- 同じタイトルへの競合編集
- 削除操作
- 共有タグ体系の変更
- 共有リンク構造の大量変更
- 共有ビューの変更
- 権限変更
- 共有範囲変更
- active抽出版の切り替え
- AIによる大規模整理
- 複数資料にまたがるメタデータ更新
```

特に削除・権限変更・active抽出版切り替えは、安全性を優先して修正提案化する。

---

# 8. 修正提案の指針

修正提案は、GitのBranchやPull Requestに近い役割を持つが、ユーザーにはそのような言葉を見せない。

```text
使う言葉:
  修正提案
  変更案
  反映
  却下
  共有版

避ける言葉:
  Branch
  Merge
  Pull Request
  Commit
  Rebase
```

---

## 8.1 修正提案が作られる条件

修正提案は次の場合に作る。

```text
- 同期時に自動マージできなかった
- 削除や権限変更など危険な操作をした
- AIが大規模な整理を提案した
- active抽出版の切り替えが必要
- 誤抽出に対する再抽出が必要
```

---

## 8.2 修正提案の状態

修正提案には状態を持たせる。

```text
open        未対応
applied     反映済み
rejected    却下
superseded  新しい提案に置き換え
withdrawn   取り下げ
```

---

## 8.3 修正提案に含める情報

修正提案には少なくとも次を含める。

```text
proposal_id
workspace_id
target_type
target_id
base_version_id
current_shared_version_id
author_id
device_id
reason
changes
status
created_at
updated_at
```

例：

```json
{
  "proposal_id": "proposal_001",
  "target_type": "note",
  "target_id": "note_123",
  "base_version_id": "v118",
  "current_shared_version_id": "v120",
  "author_id": "user_001",
  "device_id": "macbook",
  "reason": "sync_conflict",
  "status": "open",
  "changes": [
    {
      "op": "replace",
      "path": "/blocks/b12/text",
      "before": "BM25は語彙一致に強い検索手法である。",
      "after": "BM25は語彙一致に強く、短い質問文にも比較的安定する検索手法である。"
    }
  ]
}
```

---

# 9. 検索・RAGとの関係

検索やRAGでは、未反映の修正提案を通常は使わない。

```text
通常検索:
  共有版 + active抽出Markdown

RAG:
  共有版 + active抽出Markdown

未反映の修正提案:
  デフォルトでは検索対象外
```

理由は、未反映の提案をRAGに使うと、共有版に存在しない内容を根拠に回答してしまうため。

ただし、提案レビュー画面では提案内検索を許可してよい。

```text
レビュー用検索:
  修正提案も対象にできる
```

---

# 10. オフライン同期の指針

オフライン中は、変更をローカルにキューとして保存する。

```text
オフライン編集
  ↓
local pending changes
  ↓
オンライン復帰
  ↓
共有版との差分確認
  ↓
自動反映 / 自動マージ / 修正提案化
```

オンライン復帰時にサーバーへ送れる状態になったら、順番に同期する。

```text
1. 現在の共有版を取得
2. ローカル変更の基準版を確認
3. 自動マージ判定
4. 反映または修正提案化
5. ローカルキューを更新
```

完全に通信できない間だけ、ローカルに保持する。
通信可能になったら、競合した変更もWeb上の修正提案として送信する。

---

# 11. 同期順序の指針

同期順序は次を推奨する。

```text
1. 認証・権限確認
2. 共有版の最新状態を取得
3. 原本ファイル変更を検出
4. 原本ファイル変更を版として登録
5. 抽出Markdown生成ジョブを登録
6. 共有データのローカル変更を同期
7. 個人データのローカル変更を同期
8. 自動マージできない変更を修正提案化
9. 表示用Snapshotと検索インデックスを更新
```

原本ファイルは自動マージしないため、先に版として確定させる。
その後、その版に対応する抽出Markdown生成や検索インデックス更新を行う。

---

# 12. 検索インデックス更新の指針

検索インデックスは、正本データではなく派生データとして扱う。

```text
正本:
  原本ファイル版
  抽出Markdown
  共有データ
  個人データ
  修正提案

派生:
  検索インデックス
  ベクトルDB
  RAG用チャンク
  表示用Snapshot
```

そのため、同期時には必要に応じて再構築できるようにする。

```text
原本ファイル v3 登録
  ↓
抽出Markdown e3 生成
  ↓
チャンク生成
  ↓
検索インデックス更新
```

未反映の修正提案は、通常検索インデックスには入れない。

---

# 13. 削除の同期指針

削除は危険なので、できるだけ物理削除ではなくアーカイブとして扱う。

```text
delete ではなく archive
```

推奨ルールは次の通り。

```text
個人データの削除:
  自動反映してよい

共有データの削除:
  修正提案にする

原本ファイルの削除:
  archived にする
  必要なら管理者確認

抽出Markdownの削除:
  基本的に削除しない
  原本版に紐づくartifactとして保持
```

ただし、法務・秘匿・誤取り込みでは、archiveだけでは不十分な場合がある。この場合は、通常削除ではなく **履歴完全削除 / purge** として扱う。

```text
purge:
  特定pathまたはraw_hashを全履歴から削除する
  対象由来のnormalized / chunk / embedding / evidence / indexも削除する
  GUIでも「このファイルの履歴を完全削除」として実行できる
  監査ログは内容を復元できない最小限のtombstoneに限る
```

purgeは共有・同期環境では特に危険なので、権限確認、影響範囲preview、明示確認を必須にする。同期先にも「対象履歴を消す」操作として伝播し、単なる最新状態の削除と混同しない。

---

# 14. 権限と同期

同期時には、必ず権限を確認する。

```text
- 共有版へ反映できる権限があるか
- 修正提案を作れる権限があるか
- 原本ファイルを更新できる権限があるか
- active抽出版を切り替えられる権限があるか
- 削除/アーカイブできる権限があるか
```

権限がない変更は、失敗扱いにするのではなく、可能であれば修正提案にする。

```text
権限がないため反映できませんでした。
修正提案として保存しました。
```

ただし、機密性の高いワークスペースでは、提案作成自体を禁止してもよい。

---

# 15. ユーザー向け通知

同期で重要な通知は、最小限にする。

通常同期成功時は、過度に通知しない。

```text
保存しました
同期しました
```

程度でよい。

競合時は、次のように表示する。

```text
最新版と重なる編集があったため、自動反映はしませんでした。
この編集は修正提案として保存されています。
```

原本ファイル更新時は、

```text
新しい版として保存しました。
以前の版は履歴から確認できます。
```

リバート時は、

```text
以前の版に戻しました。
この操作も履歴に保存されています。
```

抽出Markdownについては、

```text
新しい版の抽出テキストを作成中です。
完了後、検索に反映されます。
```

のように見せる。

---

# 16. 内部イベント設計

同期はイベントログで扱うとよい。

代表的なイベントは次の通り。

```text
source_file.version_created
source_file.version_reverted
source_file.archived

extract.created
extract.activated
extract.issue_created
extract.reextract_proposed

note.created
note.updated
annotation.created
tag.added
tag.removed
link.created
view.updated

sync.started
sync.completed
sync.auto_merge_succeeded
sync.auto_merge_failed

proposal.created
proposal.applied
proposal.rejected
proposal.superseded
proposal.withdrawn
```

イベントログを正本として保持し、表示や検索用にはSnapshotを作る。

---

# 17. バージョン情報

すべての変更には、少なくとも次を持たせる。

```text
object_id
version_id
parent_version_id
workspace_id
author_id
device_id
created_at
change_type
hash
```

ローカル変更には、編集開始時点の共有版を記録する。

```text
base_version_id
```

同期時には、現在の共有版と比較する。

```text
base_version_id == current_shared_version_id
  → そのまま反映

base_version_id != current_shared_version_id
  → 自動マージ判定
```

---

# 18. 推奨する同期アルゴリズム

概念的には次のようにする。

```text
同期開始
  ↓
現在の共有版を取得
  ↓
ローカル変更キューを読み込む
  ↓
変更ごとに分類する
    - 原本ファイル変更
    - 抽出関連
    - 共有データ変更
    - 個人データ変更
  ↓
原本ファイル変更:
    新しい版として登録
  ↓
共有データ変更:
    base_versionを確認
    自動マージ可能なら反映
    不可能なら修正提案化
  ↓
個人データ変更:
    自動反映または個人用提案化
  ↓
抽出Markdown:
    必要に応じて生成ジョブ作成
  ↓
インデックス更新
  ↓
同期完了
```

擬似コードは以下。

```ts
async function sync(localQueue) {
  const current = await fetchCurrentSharedState();

  for (const change of localQueue) {
    switch (change.type) {
      case "source_file_changed": {
        await createSourceFileVersion(change);
        await enqueueExtractionJob(change);
        break;
      }

      case "shared_data_changed": {
        if (change.baseVersionId === current.versionId) {
          await applyToSharedMain(change);
          break;
        }

        const result = tryAutoMerge(change, current);

        if (result.success) {
          await applyToSharedMain(result.change);
        } else {
          await createProposal({
            reason: "sync_conflict",
            baseVersionId: change.baseVersionId,
            currentVersionId: current.versionId,
            change,
          });
        }

        break;
      }

      case "personal_data_changed": {
        const result = tryAutoMergePersonal(change, current);

        if (result.success) {
          await applyToPersonalLayer(result.change);
        } else {
          await createProposal({
            reason: "personal_sync_conflict",
            change,
          });
        }

        break;
      }
    }
  }

  await updateSnapshotsAndIndexes();
}
```

---

# 19. 最終ルールまとめ

最終的な同期ルールは次でよい。

```text
1. ユーザーにはGit用語を見せない
2. 共有版を正本とする
3. 通常変更は自動同期する
4. 自動マージできる変更は共有版へ反映する
5. 自動マージできない変更は共有版を優先する
6. 反映できない変更はWeb上の修正提案にする
7. 原本ファイルは変更ごとに新しい版として保存する
8. 後から登録された原本版を最新とする
9. 過去版は保持する
10. 戻す場合は新しい版として記録する
11. 原本ファイルは自動マージしない
12. 抽出Markdownはimmutableにする
13. 抽出Markdownは修正しない
14. 誤抽出はIssueまたは再抽出提案にする
15. 未反映の修正提案は通常検索・RAG対象にしない
16. 削除は原則archiveまたは修正提案にする
17. 法務・秘匿・誤取り込みではpurgeにより全履歴から完全削除できる
18. 検索インデックスは派生データとして再構築可能にする
```

---

# 結論

この同期方針は、次のバランスを取る設計です。

```text
一般ユーザー向け:
  自動同期・共有版優先・難しい概念なし

チーム利用向け:
  競合時は修正提案としてレビュー可能

KCS/RAG向け:
  原本性・版管理・出典整合性を維持

実装向け:
  イベントログ・Snapshot・修正提案で拡張可能
```

最も重要な一文はこれです。

```text
共有版を正本とし、反映できない変更は破棄せず、Web上の修正提案として保存する。
```

原本ファイルについては、

```text
変更ごとに版を追加し、後から登録された版を最新とする。ただし過去版は保持し、戻す操作も新しい版として記録する。
```

この2つを同期設計の中心ルールにするとよいです。
