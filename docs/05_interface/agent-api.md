# Agent / Adapter API

> 正本: `docs/requirements.md §2` と `docs/06_adapters/adapter-overview.md`。このファイルは Agent と Adapter が共通利用する KCS API の契約を固定する。

## 基本方針

KCS API は、人間向け CLI、AI Agent、Prepare Adapter、Markdownize Adapter、Embedding Adapter、optional Summary / Classification / Rerank Adapter が共通して使う境界である。

KCS core は object store / snapshot / search / task state を管理する。Agent や Adapter は KCS API を通じて対象 object、許可された scope、既存 artifact、実行結果を書き戻す。

## API が保証すること

```text
入力 object hash を明示する
処理対象 scope を明示する
execution_mode を明示する
ネットワーク送信の許可状態を明示する
出力 artifact hash を記録する
tool_profile_hash / agent_profile_hash を記録する
検索時は searched scopes / excluded scopes / fallback reason を返す
```

## Adapter 種別

```text
prepare:
  raw object -> prepared object / prepared unit

markdownize:
  prepared unit / raw text -> normalized Markdown
  OCR はこの処理の内部能力として扱う

embedding:
  markdown chunk / image object / query text -> vector
  Text / Image Adapter には分けない

summary optional:
  normalized object / chunk / search result -> summary artifact

classification optional:
  raw / normalized / chunk / image object -> labels / categories

rerank optional:
  query + candidate results -> reranked results
```

## 実行形態

Adapter は提供主体ではなく、実行形態と決定性で分類する。

```text
online_api:
  LLM などのネットワーク越し API

offline_api:
  ローカル LLM などのオフライン API

deterministic_library:
  決定論的なライブラリやローカル処理
```

いずれの実行形態でも、KCS API の契約は変えない。URL、認証情報、コマンドパス、ライブラリ選択などの実行設定は device-local config に置き、`.kcs/` には保存しない。

```text
KCS core
  -> task descriptor
  -> device-local Adapter
  -> online API / offline API / deterministic library
  -> artifact descriptor
  -> KCS core
```
