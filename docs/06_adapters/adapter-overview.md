# Adapter Overview

> 正本: `docs/research/kcs.md` の device-local Adapter 方針、および `docs/requirements.md §2` の offline-first 方針。

## 基本方針

Markdown 処理（OCRを含む） / Embedding 処理 / 検索代行 Agent / 要約 Agent は KCS core に含めず、Adapter に委譲する。OCR は Markdown 化と並列の Adapter 種別ではなく、スキャン PDF や画像を Markdown 化するための Markdown 処理 Adapter の内部能力として扱う。

```text
KCS core:
  object store
  snapshot
  restore
  search over existing artifacts
  task state
  common KCS API

Adapter:
  Markdown processing (includes OCR)
  Embedding processing
  Search delegation Agent
  Summarization Agent
```

Adapter の実行設定、コマンドパス、URL、認証情報は `.kcs/` の共有対象に含めない。各デバイスは自分の `~/.config/kcs/` や OS keychain に Adapter 設定を持つ。`.kcs/` は Adapter を管理せず、生成済み artifact の provenance と互換性判定に必要な profile hash だけを保持する。

## 選択可能な Adapter

MVP 以降、ユーザーは用途ごとに Adapter を選択できる。

```text
Markdown 処理 Adapter:
  raw object -> normalized Markdown
  PDF / Office / 画像 / 音声の変換と、必要な OCR を含む

Embedding 処理 Adapter:
  chunk object -> embedding object
  dimensions / distance / model family を profile に残す

検索代行 Agent Adapter:
  KCS API を使って検索、再ランキング、回答用コンテキスト収集を行う
  KCS core の既存検索機能を迂回せず、検索 scope と fallback 情報を返す

要約 Agent Adapter:
  normalized object / chunk / search result -> summary
  summary artifact は input hash と agent profile に紐付ける
```

すべての Adapter は共通の KCS API を通じて KCS core と接続する。ローカルコマンド、クラウドサービス、社内サービス、学部サービスのいずれを使う場合でも、KCS core から見える契約は同じにする。

```text
KCS API boundary:
  task_id
  adapter_kind
  input object hash
  output object hash
  tool_profile_hash
  allowed scope
  network permission
  status / error_kind
```

## 外部送信の原則

KCS core は、明示オプトインなしに外部サービスへファイル内容を送信してはならない。

```text
default:
  no external transmission

explicit opt-in:
  --online
  adapter config allow_network = true
```

クラウド Adapter、社内サービス Adapter、学部サービス Adapter を使う場合でも、ユーザーがどの scope / file / task を外部送信対象にしたかを記録する。

## Adapter実行制約

Adapter には最低限以下を設定できるようにする。

```toml
[adapter.policy]
allow_network = false
max_input_bytes = 104857600
timeout_seconds = 300
redact_logs = true
store_request_body = false
store_response_body = false
```

## ログ

ログに原文本文、normalized本文、API request body、API response body、秘密情報を残してはならない。

記録してよいもの:

```text
task_id
adapter_id
tool_profile_hash
input_raw_hash
output_hash
status
error_kind
started_at
finished_at
```

## 再現性

Adapter の完全な再実行決定性は要求しない。KCS が保証するのは、一度生成された artifact を `raw_hash + tool_profile_hash` に紐付けて固定し、同じ raw hash では既存 artifact を尊重することである。

```text
raw_hash unchanged
  -> reuse existing artifact

raw_hash changed
  -> create new artifact candidate

explicit re-normalize
  -> create another artifact for same raw_hash
```
