# Folder-local KCS

> 正本: `docs/research/git_kcs.md` の「修正後の `.kcs` の考え方」。

## 基本定義

`.kcs/` は、知識スコープのルートに1つだけ置くものではない。基本的には、`.DS_Store` のように各フォルダに隠しディレクトリとして生成されるフォルダローカルな管理単位である。

```text
Documents/
  .kcs/
  report.pdf
  Research/
    .kcs/
    paper.pdf
    Notes/
      .kcs/
      note.md
  Work/
    .kcs/
    spec.docx
```

子フォルダや孫フォルダに `.kcs/` が存在しない、という前提を置いてはならない。

## 管理範囲

各 `.kcs/` は、自分が配置されているフォルダ直下のファイルと子フォルダリンクだけを管理する。

```text
folder/.kcs:
  folder直下のファイル
  子フォルダへのリンク

folder/child/.kcs:
  child直下のファイル
  childの子フォルダへのリンク
```

親フォルダや兄弟フォルダの内容を、個々の `.kcs/` が直接保持しない。

## 検索との関係

デフォルト検索は全 indexed scope を対象にする。これは、検索実行側が scope registry または探索済み `.kcs/` 一覧を束ねることで実現する。

```text
default search:
  all indexed scopes

restricted search:
  --scope .
  --scope . --descendants
  --scope <path>
  --scope <path> --descendants
```

つまり、`.kcs/` の配置はフォルダローカルだが、検索体験はデフォルトで全体横断である。

## 設計上の注意

`.kcs/` を「リポジトリルートに1つだけある `.git/`」のように扱わない。KCS は Git の content-addressing や snapshot DAG を参考にするが、物理配置は Git より `.DS_Store` に近い。
