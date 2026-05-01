はい、その設計で良いと思います。
**内部的には snapshot / commit を同じオブジェクトとして扱い、違いはメタデータで表現する**のが最もシンプルです。

## 推奨定義

KCS内部では、すべてを同じ `commit object` または `snapshot object` として扱います。

```text
KCS state object =
  id
  tree
  parents[]
  timestamp
  actor
  commit_type
  message
  protected
  metadata
```

つまり、内部的には

```text
snapshot = commit
```

でよいです。

---

## 区別はメタデータで行う

例えばこうです。

```json
{
  "id": "kcs_01H...",
  "tree": "tree_abc...",
  "parents": ["kcs_01G..."],
  "created_at": "2026-04-29T18:00:00Z",
  "actor": "system",
  "commit_type": "auto",
  "message": "autosnapshot: daily",
  "protected": false,
  "metadata": { "trigger": "timer" }
}
```

手動保存なら：

```json
{
  "id": "kcs_01J...",
  "tree": "tree_def...",
  "parents": ["kcs_01H..."],
  "created_at": "2026-04-29T19:00:00Z",
  "actor": "user",
  "commit_type": "manual",
  "message": "卒論提出前の状態",
  "protected": true,
  "metadata": {}
}
```

このように、**構造は同じで、作られ方や意味だけが違う**という扱いが自然です。

---

## 用語設計

開発者向けCLIでは：

```bash
kcs commit -m "before cleanup"
```

一般ユーザー向けUIでは：

```text
スナップショットを作成
```

内部ではどちらも同じオブジェクトを作る。

---

## 実装上の要件

`commits` テーブルまたは `objects/commits/` には、最低限これを持たせます。

```json
{
  "id": "kcs_...",
  "tree": "tree_...",
  "parents": [],
  "created_at": "...",
  "actor": "user | system | agent | remote",
  "commit_type": "manual | auto | imported | migrated | repaired | merged | purged",
  "message": "...",
  "protected": true,
  "metadata": {}
}
```

### 重要フィールド

| フィールド         | 意味                    |
| ------------- | --------------------- |
| `message`     | 人間向け説明                |
| `actor`       | 作成者                   |
| `commit_type` | commitの種別（後述の固定enum） |
| `protected`   | 自動削除対象外か              |
| `parents`     | 履歴DAG                 |
| `tree`        | その時点のファイル構造           |
| `metadata`    | type固有の追加情報           |

---

## commit_type — 固定 enum

`commit_type` は KCS が存在する限り**追加・削除・改名を行わない閉じた集合**として定義する。MVPで一部だけ実装し将来追加する、という運用は取らない。最初から全7種を契約として固定する。

```text
commit_type ∈ {
  manual,
  auto,
  imported,
  migrated,
  repaired,
  merged,
  purged
}
```

| type        | 意味                                     | 唯一性の根拠                                                       |
| ----------- | -------------------------------------- | ------------------------------------------------------------ |
| `manual`    | ユーザーまたはagentによる**意思を持った**保存            | 意思の存在は他のどのtypeにも畳めない                                         |
| `auto`      | systemによる無人保存（timer / mtime / 抽出完了など） | 意思なしの保存。意思ありとの分離は audit / GC で必須                             |
| `imported`  | KCSの**追跡対象として新たに登録**された時点              | 「初めてKCSの責任範囲に入った」は履歴の根。後続のautoと区別不能になると provenance が壊れる        |
| `migrated`  | 同一raw_hashに対する派生データの**意図的再生成**         | 内部schema/tool変更が原因。raw変更ではないことが保証される唯一のtype                    |
| `repaired`  | 検出された**破損からの回復**                       | 異常事象起点。migratedと外形は似るが、原因が「事故」か「計画」かは監査で区別必須                   |
| `merged`    | 複数parent chainの**統合**                  | 「2つの履歴を1つにする」意図。マルチデバイス同期・共有・concurrent編集の全てがこれに帰着            |
| `purged`    | **履歴の破壊的書き換え**後の到達点                    | 唯一、過去objectsを削除する。法務要件で他typeと混同不可                            |

### 直交軸（typeに混ぜない情報）

「typeを増やしたくなったら」必ず以下のいずれかで吸収できないかを先に確認する。`commit_type` には**作成原因の本質**だけを乗せ、それ以外は分離する。

```text
actor    ∈ { user, system, agent, remote }
source   ∈ { local, kcs:<id>, file:<path>, ... }   // imported / merged で意味を持つ
trigger  ∈ { mtime, timer, extraction, idle, signal }   // auto で意味を持つ
metadata json   // type固有の追加情報
```

吸収例:

| 一見「新type」が欲しくなるケース    | 実際の表現                                         |
| ----------------------- | --------------------------------------------- |
| AIエージェントが保存             | `manual`, actor=agent                         |
| 別デバイスから取り込んで統合          | `merged`, source=kcs:device-b                 |
| テンプレKCSから派生して新規作成       | `imported`, source=kcs:template-x             |
| Markdownize profile 差し替えによる再抽出 | `migrated`, metadata.tool_profile_diff=...    |
| 定期autosnapshot          | `auto`, trigger=timer                         |
| 抽出パイプライン完走起点のautosnapshot | `auto`, trigger=extraction                  |

### 却下したtypeとその理由（永久記録）

将来「追加したい」候補が出たときの予防として、検討済みかつ却下した案を以下に明示する。**この却下リストを残すこと自体が、enumを閉じ続けるための装置**である。

| 却下type             | 却下理由                                      | 代替表現                                              |
| ------------------ | ----------------------------------------- | ------------------------------------------------- |
| `fetched`          | fetchはref更新でありcommit作成ではない。git同様、ローカル履歴に新commitは生まれない | remote-tracking refの更新。commit objectではない         |
| `forked`           | fork先の最初のcommitは「外部から取り込んだ」=`imported` に畳める | `imported` + `metadata.source = upstream_kcs_id`  |
| `published`        | 公開はtree変更を伴わない。同一treeに新commitを作るのは履歴汚染    | tag/refオブジェクト。commit objectではない                  |
| `proposed` / `accepted` / `rejected` | 提案は別オブジェクト(proposal)のlifecycleであり、commit自体の性質ではない | proposal object が commit_id を参照。accept時は通常の manual / merged |
| `gc`               | GCは到達不能objectsの掃除であり、tree変更ではない           | commit作成不要。実行ログのみ                                 |
| `extracted`        | 抽出完了起点のautoと区別不能                          | `auto` + `metadata.trigger = "extraction"`        |
| `synced`           | 同期は構造的にmerge（多parent）か no-op              | `merged` または ref更新のみ                              |
| `agent`            | actor軸であってtype軸ではない                       | `actor = agent`、typeは行為の性質で決まる                    |
| `genesis`          | 最初のcommitは「ファイル0個のimport」                 | `imported` with parents=[]                        |

---

## 保持ポリシー

`protected` のデフォルト値は `commit_type` から導出する。両者を完全独立にすると組み合わせ問題が発生するため、type変更時に自動同期されるか、関数として導出する実装にする（テーブル列として独立に持たない）。

```text
default_protected(commit_type):
  manual    → true
  imported  → true
  merged    → true
  purged    → true
  auto      → false
  migrated  → false
  repaired  → false
```

ユーザーは個別に上書き可能。

GC可能性も同様にtypeから導出する関数として実装する：

```text
gc_policy(commit_type):
  auto      → full      (commit削除可)
  migrated  → shallow   (tree破棄可、commit残す)
  repaired  → shallow
  manual    → none
  imported  → none
  merged    → none
  purged    → none
```

`shallow` GC は履歴DAGの連続性を保つため、commit object 自体は残しつつ tree のみ破棄する。これにより autosnapshot が manual commit の parent chain に含まれていても、parent chain が切れない。

ただし、法務・秘匿・誤取り込みのための `purge` は通常のGCとは別扱いにする。`protected = true` のsnapshotであっても、ユーザーまたは管理者が明示的に「特定ファイルの全履歴削除」を実行した場合は、対象ファイルに由来する tree / commit / raw / normalized / chunk / embedding / evidence を履歴から除去できる必要がある。これは通常削除ではなく、Gitの履歴書き換えに相当する破壊的操作として扱い、結果commitの `commit_type` は `purged` になる。

---

## SQLite CHECK 制約

`commit_type` の値域は CHECK 制約で固定する。**この制約を変更する migration は永久に発生しない**ことが、この設計のコミットメントである。

```sql
commit_type TEXT NOT NULL CHECK (commit_type IN (
  'manual', 'auto', 'imported', 'migrated',
  'repaired', 'merged', 'purged'
))
```

---

## 網羅性チェック

想定全シナリオがどのtypeに落ちるかを明示する。新たなシナリオが現れた際は、まず以下のいずれかに畳めないかを先に確認する。

| シナリオ                                | type                       |
| ----------------------------------- | -------------------------- |
| ユーザーが `kcs commit -m "..."` 実行       | manual                     |
| AIエージェントが知識を整理して保存                  | manual (actor=agent)       |
| ファイル編集を検知して自動保存                    | auto                       |
| 定期autosnapshot                      | auto                       |
| 抽出パイプライン完走後                         | auto (trigger=extraction)  |
| 新規ファイルがフォルダに置かれた（既存KCSの追跡内）         | auto                       |
| `.kcs` 初期化（ゼロ or N個のファイルから）         | imported                   |
| 別 `.kcs` をテンプレートに新規作成                | imported (source指定)         |
| 一括ファイル取り込みコマンド                      | imported                   |
| Schema v2 → v3 のマイグレーション             | migrated                   |
| Markdownize profile 変更による再抽出        | migrated                   |
| Embedding model変更による再ベクトル化           | migrated                   |
| SQLiteのfsck的修復                      | repaired                   |
| 抽出失敗の途中状態からの復旧                      | repaired                   |
| 別デバイスから同期して統合                       | merged                     |
| 共有KCSから自分の編集を取り込み統合                 | merged                     |
| concurrentに発生した2系統の自動保存の合流           | merged                     |
| `kcs forget <path>` 実行後の状態          | purged                     |
| 法務要請による特定情報の全履歴削除後                  | purged                     |
| 公開snapshot指定                        | （commitではない、ref/tag）        |
| Pull request的な提案                    | （commitではない、proposal object） |
| GC実行                                | （commitではない、ログのみ）           |

全シナリオが7typeで尽きることを確認している。

---

## 最終定義

> KCSでは、snapshot と commit を内部的に別オブジェクトとして分けない。どちらも同一の履歴オブジェクトとして扱い、`message`、`actor`、`commit_type`、`protected` などのメタデータによって、自動保存・手動保存・重要保存点・統合・修復・履歴書き換えを区別する。`commit_type` は `manual / auto / imported / migrated / repaired / merged / purged` の7種に閉じた永続契約であり、追加・削除・改名は行わない。新たに区別したい性質が現れた場合は、まず `actor` / `source` / `trigger` / `metadata` で表現可能かを確認し、それらで表現できない場合のみ設計の見直しを検討する。

この方針が一番シンプルで、Git風CLIと一般向けUIの両方に対応でき、かつ将来の共有・マルチデバイス・agent統合シナリオまで含めて閉じている。
