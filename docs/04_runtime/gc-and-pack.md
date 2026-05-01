# GC / Pack / Purge

> 正本: `docs/research/git_kcs.md` の `KCS GC`、`docs/research/philosophy.md` の履歴保持方針。

## 通常削除

通常の削除は、最新の tree / manifest から対象 path を消す操作である。過去の snapshot / commit から到達可能な raw / normalized / chunk / embedding / tree / commit object は保持する。

```text
delete / archive:
  最新状態から消える
  過去履歴からは復元できる
```

KCS の通常思想は「知識を失わないこと」なので、通常削除で過去版を破壊してはならない。

## GC

GC は到達不能 object の物理削除である。

```bash
kcs gc --dry-run
kcs gc --prune-unreachable
```

`gc --prune-unreachable` が削除できるのは、どの commit / snapshot / tag / protected object からも到達不能な object だけである。過去 snapshot から到達可能な object は、最新状態から削除済みでも GC 対象外とする。

GC の到達可能性判定は、原則として対象 `.kcs/objects` 内で完結する。別 `.kcs/` に同じ raw_hash の object があっても、同一物理 object として共有している前提を置かない。

## Pack

object 数が増えた場合、pack file にまとめる。

```text
objects/raw/...          -> packs/raw-0001.kcspack
objects/normalized/...   -> packs/normalized-0001.kcspack
```

MVP では pack は必須ではないが、pack 済み object も purge の対象になる。

## 履歴完全削除 / Purge

GC だけでは、削除・秘匿・法務要件には足りない。特定ファイルを過去履歴からも消す必要がある場合、KCS は Git の履歴書き換えに相当する `purge` を提供する。

```bash
kcs purge docs/secret.pdf --all-history --reason "legal erasure request"
kcs purge --raw-hash sha256:abc... --all-history
```

GUI では、検索結果・履歴ビュー・ファイル詳細画面から **このファイルの履歴を完全削除** を実行できるようにする。

`purge` の保証範囲は KCS 管理下の object store、snapshot DAG、index、pack、cache、tombstone である。OS backup、Time Machine、クラウド同期の過去版、外部 export、ユーザーが手動コピーしたファイル、KCS 外のログまでは KCS 単体では保証しない。UI では「KCS 管理下の履歴から完全削除」という意味で扱う。

`.kcs` がフォルダローカルであるため、path 指定 purge は、その path を所有する `.kcs` の履歴と object store を対象にする。raw_hash 指定 purge を複数 `.kcs` にまたがって実行する場合は、対象 `.kcs` 一覧を preview し、それぞれの object store で独立に削除する。

purge は次を行う。

```text
対象 path / raw_hash を参照する全 tree / commit / manifest を書き換える
対象 raw object を到達不能にする
対象 raw object 由来の normalized / prepared unit / chunk / embedding / node / edge / evidence を到達不能にする
対象を含む index / pack / cache を無効化または再構築する
到達不能化された object を GC で物理削除する
```

purge は破壊的操作なので、確認 UI、影響範囲 preview、理由入力を必須にする。

## Tombstone

purge 後も監査のために最小限の tombstone を残してよい。ただし、内容・本文・秘匿 path を復元できる情報を残してはならない。

```text
purge_id
actor
executed_at
reason
object_count_removed
redacted_target_label
```
