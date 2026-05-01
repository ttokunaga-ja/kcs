# CLI Spec

> 正本: `docs/research/git_kcs.md`。GUI では Git 用語を一般向けに言い換える。

## Core Commands

`snapshot` を正規コマンド名とし、`commit` は Git に慣れた開発者向け alias として扱う。どちらも内部的には同じ履歴 object を作る。

```bash
kcs init
kcs status
kcs index
kcs resume
kcs retry
kcs repair
kcs search "query"
kcs open <result>
kcs commit -m "message"
kcs snapshot create -m "message"
kcs log
kcs diff
kcs restore <snapshot> --to <dir>
kcs tag <name>
kcs gc --dry-run
kcs gc --prune-unreachable
kcs purge <path> --all-history --reason <reason>
```

`kcs init` は現在フォルダの `.kcs` を作成する。子フォルダの `.kcs` は `kcs index` や探索処理が対象を検出した時点で必要に応じて生成する。

## Search

デフォルト検索は全 indexed scope を対象にする。

```bash
kcs search "認証仕様"
```

検索範囲を絞る場合:

```bash
kcs search "認証仕様" --scope .
kcs search "認証仕様" --scope . --descendants
kcs search "認証仕様" --scope ./Research
kcs search "認証仕様" --scope ./Research --descendants
kcs search "認証仕様" --all-scopes
```

検索モード:

```bash
kcs search "..."              # auto: hybrid if possible, otherwise text
kcs search "..." --text       # text only
kcs search "..." --vector     # vector only, vector unavailableならerror
kcs search "..." --hybrid     # hybrid強制、失敗時は設定に従う
kcs search "..." --no-vector  # vector無効
```

## Restore

過去状態の復元は、現実ファイルを直接上書きしない。

```bash
kcs restore kcs_123 --to ~/Recovered/kcs_123
```

## Delete / Archive / Purge

通常削除や archive は最新状態から対象を消すだけで、過去履歴は保持する。

法務・秘匿・誤取り込みで履歴ごと消す場合は `purge` を使う。

```bash
kcs purge docs/secret.pdf --all-history --reason "legal erasure request"
kcs purge --raw-hash sha256:abc... --all-history --reason "mistaken import"
```

`purge` は破壊的操作であり、CLI では確認 prompt または `--yes` を要求する。GUI では **このファイルの履歴を完全削除** と表示し、影響範囲 preview と確認を必須にする。

## GUI Vocabulary

| CLI / internal | GUI |
| --- | --- |
| commit / snapshot | 版を保存 |
| checkout | 表示する版を切り替える |
| restore | 以前の版を復元 |
| branch | 修正提案 / 変更案 |
| merge | 反映 |
| conflict | 最新版と重なる編集 |
| gc | 不要な内部データを整理 |
| purge | このファイルの履歴を完全削除 |
