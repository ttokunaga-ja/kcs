# Adapter Overview

> 正本: `docs/research/kcs.md` の device-local Adapter 方針、および `docs/requirements.md §2` の offline-first 方針。

## 基本方針

Prepare / Markdownize / Embedding / Summary / Classification / Rerank は KCS core に含めず、Adapter に委譲する。OCR は Markdownize Adapter の内部能力として扱う。Embedding は Text / Image で分離せず、Gemini 等のマルチモーダル Embedding を前提に単一の Embedding Adapter に統合する。

```text
KCS core:
  object store
  snapshot
  restore
  search over existing artifacts
  task state
  common KCS API

Adapter:
  Prepare
  Markdownize (includes OCR)
  Embedding (multimodal)
  Summary optional
  Classification optional
  Rerank optional
```

Adapter の実行設定、コマンドパス、URL、認証情報は `.kcs/` の共有対象に含めない。各デバイスは自分の `~/.config/kcs/` や OS keychain に Adapter 設定を持つ。`.kcs/` は Adapter を管理せず、生成済み artifact の provenance と互換性判定に必要な profile hash だけを保持する。

task state は正本ではなく、検索効率と再開性のための運用データである。失われた場合は object store と tool profile から未完了 Adapter work を再検出して再キューイングする。

## MVP Adapter 一覧

MVP で必要な Adapter は以下である。

```text
1. Prepare Adapter
2. Markdownize Adapter
3. Embedding Adapter
4. Summary Adapter optional
5. Classification Adapter optional
6. Rerank Adapter optional
```

廃止する Adapter:

```text
Image Embedding Adapter
Text Embedding Adapter
```

## Adapter の役割

```text
Prepare Adapter:
  raw object -> prepared object / prepared unit
  PDF page image、Office intermediate、image object など、後続処理に渡す単位を作る

Markdownize Adapter:
  prepared object / raw text -> normalized Markdown
  OCR、layout detection、table extraction はこの Adapter の内部能力として扱う

Embedding Adapter:
  markdown chunk / image object / query text -> embedding vector
  text と image を同一のマルチモーダル Embedding 空間へ写像する

Summary Adapter optional:
  normalized object / chunk / search result -> summary

Classification Adapter optional:
  raw / normalized / chunk / image object -> label / category / routing metadata

Rerank Adapter optional:
  query + candidate results -> reranked results
```

すべての Adapter は共通の KCS API を通じて KCS core と接続する。オンライン API、オフライン API、決定論的ライブラリ、ローカルコマンドのいずれを使う場合でも、KCS core から見える契約は同じにする。

## Embedding 統合方針

KCS では、Embedding 処理を Text / Image で分離しない。

```text
same Embedding Adapter
same profile_hash
same vector space
```

Embedding Adapter は次を入力として受け取れる。

```text
text
image
markdown_chunk
image_object
query
```

インデックスは実装都合で `chunk_vec` / `image_vec` のように物理分割してもよい。ただし概念上は単一の Embedding Adapter が同一 profile のベクトルを生成する。

## 実行形態

Adapter は提供主体ではなく、実行形態と決定性で分類する。

```text
online_api:
  ネットワーク越しに呼び出す API
  例: hosted LLM / hosted embedding / hosted OCR API
  明示的な network opt-in が必要

offline_api:
  同一端末またはローカル環境で呼び出す API
  例: local LLM server / local embedding server
  ネットワーク送信なしで使えるが、非決定的な出力はあり得る

deterministic_library:
  決定論的なライブラリやローカル処理
  例: PDF text extraction / parser / rule-based normalizer
  同じ入力と同じ profile なら同じ出力を期待できる
```

```text
KCS API boundary:
  task_id
  adapter_kind
  input object hash
  output object hash
  tool_profile_hash
  allowed scope
  network permission
  execution_mode
  status / error_kind
```

## ネットワーク送信の原則

KCS core は、明示オプトインなしにネットワーク越しの API へファイル内容を送信してはならない。

```text
default:
  no network transmission

explicit opt-in:
  --online
  adapter config allow_network = true
```

オンライン API Adapter を使う場合は、ユーザーがどの scope / file / task をネットワーク送信対象にしたかを記録する。オフライン API や決定論的ライブラリの場合も、execution_mode と profile hash は記録する。

## Adapter実行制約

Adapter には最低限以下を設定できるようにする。

```toml
[adapter.policy]
allow_network = false
allowed_scope = "."
max_input_bytes = 104857600
timeout_seconds = 300
redact_logs = true
store_request_body = false
store_response_body = false
require_command_confirmation = true
```

任意コマンドや任意URLを使う Adapter は、初回実行時に command / URL / scope / network policy を preview し、ユーザー承認を得る。実装では command allowlist、secret redaction、ログ本文禁止を前提にする。

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
