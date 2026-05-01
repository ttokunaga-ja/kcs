# MVP Scope

> 正本: `docs/research/`。このファイルはMVP実装時の作業境界を固定するための要約。

## Product Intent

KCS は、AI を契機としてローカルの知識空間を再定義する。PDF / Office / 画像のような検索しづらいファイルを、Markdown を主とした統一テキスト表現へ変換し、ローカルファイル空間に横断検索・履歴検索・出典追跡を提供する。

副目的として、Git の履歴付き知識アーカイブの恩恵を一般ユーザーにも広げる。

## MVPの定義

KCS の MVP は、検索体験を削った薄いデモではない。初期ユーザーは CLI に慣れた開発者を想定するが、将来の一般ユーザー向け UX を損なわない設計で、ローカル知識検索の基本機能を一通り実装する。

時間を短縮するために、横断検索、履歴検索、出典追跡、復元、安全な削除境界などの中核体験を落とさない。MVP は **検索体験を検証できる最小の完全系** として扱う。

## MVPでやる

```text
content-addressed object store
snapshot DAG
raw object保存
normalized markdown artifact保存
chunk object
Evidence Pointer
SQLite / FTS5 による全文検索
sqlite-vec が使える場合のhybrid検索
embedding不可時の全文検索fallback
デフォルト全 indexed scope 検索
scope指定による現在フォルダ/配下検索
time-travel search
restore --to
resume / retry / repair
gc --dry-run / --prune-unreachable
purgeによる特定ファイルの全履歴削除
```

## MVPでやらない

```text
複数端末同期
Web上の共有版
Web修正提案
複数ユーザー権限管理
branch UI
pack file
delta compression
高度なsemantic diff
Tauri GUI本実装
```

ただし、GUIで提供予定の **このファイルの履歴を完全削除** は、MVPのCLI `kcs purge` と同じ意味を持つ将来UIとして仕様に含める。

## 検索デフォルト

デフォルト検索は全 indexed scope。

初回の indexed scope は、ユーザーが明示的に `.kcsignore` や設定で除外していないすべての対象範囲とする。

```bash
kcs search "query"
```

制限検索:

```bash
kcs search "query" --scope .
kcs search "query" --scope . --descendants
kcs search "query" --scope ./Research
kcs search "query" --scope ./Research --descendants
```

## 完了条件

```text
同じ原本hashを重複保存しない
SQLiteが壊れてもobjectsから再構築できる
normalized objectを直接編集対象にしない
検索結果にscopeと検索modeを含める
vector unavailableでも全文検索できる
restoreが現実ファイルを直接上書きしない
purge後に対象ファイル由来objectが検索・復元できない
purge tombstoneから本文や秘匿pathを復元できない
```
