# Agent / Adapter API

> 正本: `docs/requirements.md §2` と `docs/06_adapters/adapter-overview.md`。このファイルは Agent と Adapter が共通利用する KCS API の契約を固定する。

## 基本方針

KCS API は、人間向け CLI、AI Agent、検索代行 Agent Adapter、要約 Agent Adapter、Markdown 処理 Adapter、Embedding 処理 Adapter が共通して使う境界である。

KCS core は object store / snapshot / search / task state を管理する。Agent や Adapter は KCS API を通じて対象 object、許可された scope、既存 artifact、実行結果を書き戻す。

## API が保証すること

```text
入力 object hash を明示する
処理対象 scope を明示する
外部送信の許可状態を明示する
出力 artifact hash を記録する
tool_profile_hash / agent_profile_hash を記録する
検索時は searched scopes / excluded scopes / fallback reason を返す
```

## Adapter 種別

```text
markdown_processor:
  raw object -> normalized Markdown
  OCR はこの処理の内部能力として扱う

embedder:
  chunk object -> embedding object

search_agent:
  query + scope -> ranked context
  KCS core の検索結果、履歴検索、fallback 情報を利用する

summarizer_agent:
  normalized object / chunk / search result -> summary artifact
```

## 外部サービス接続

外部サービス、社内サービス、学部サービスへ接続する場合も、KCS API の契約は変えない。接続先固有の URL、認証情報、コマンドパスは device-local config に置き、`.kcs/` には保存しない。

```text
KCS core
  -> task descriptor
  -> device-local Adapter
  -> local / cloud / internal / faculty service
  -> artifact descriptor
  -> KCS core
```
