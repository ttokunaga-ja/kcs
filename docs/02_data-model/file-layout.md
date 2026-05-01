# File Layout

> 正本: `docs/research/git_kcs.md` と `docs/research/kcs.md`。このファイルは実装向けの物理レイアウト要約。

## Standard Layout

この構造は、知識スコープのルートに1つだけ置くものではない。基本的には各フォルダに隠しディレクトリとして生成され、子フォルダや孫フォルダにもそれぞれ `.kcs/` が存在する。

これは `.DS_Store` に近いフォルダローカルなメタデータ配置であり、KCS のスコープ制御・部分公開・部分同期の基本方針として採用する。実装は多数の `.kcs/` が存在する前提で、探索・repair・purge・export を設計する。

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
      prepared/
      normalized/
      normalized_units/
      chunks/
      embeddings/
      nodes/
      edges/
      trees/
      commits/
      tombstones/

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

## Truth And Cache

`.kcs/objects` は、正本 object と保存済み派生 artifact を置く領域である。SQLite、BM25、vector index、cache は再構築可能な派生データとして扱う。Embedding object も chunk と embedding profile から再構築可能な派生 artifact であり、正本には含めない。

```text
truth:
  objects/raw
  objects/prepared
  objects/normalized
  objects/chunks
  objects/nodes
  objects/edges
  objects/trees
  objects/commits

rebuildable:
  objects/embeddings
  index/sqlite.db
  index/bm25
  index/vector
  task state / retry queue
  cache
  tmp
```

task state は検索効率と再開性のための運用データであり、喪失を許容する。失われた場合は object store、manifest、tool profile から未完了処理を再検出してキューを再構築する。

## Scope

各 `.kcs` は自フォルダ直下のファイルと子フォルダリンクを管理する。子フォルダの中身は子フォルダ自身の `.kcs` が管理する。検索のデフォルトは全 indexed scope であり、現在フォルダだけに閉じる場合はコマンド側で scope を制限する。

初回に indexed scope として扱う範囲は、ユーザーが `.kcsignore` や設定で明示的に除外していないすべての対象範囲である。

## Purge Tombstones

`objects/tombstones/` は履歴完全削除の最小監査情報を保持する場所である。本文、normalized text、秘匿path、復元可能なraw hashを保存してはならない。
