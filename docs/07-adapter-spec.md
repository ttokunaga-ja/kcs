# 07 Adapter Spec

Adapter (Prepare / Markdownize / Embedding / Summary / Classification / Rerank) の trait 契約 + 実行形態 + Markdown incremental プロンプト規約。

> 関連: [03-data-model.md §5](03-data-model.md) (`tool_profile_hash` 計算規約) / [04-pipeline.md §3](04-pipeline.md) (incremental Markdownize) / [06-cli-spec.md §9](06-cli-spec.md) (Agent/Adapter API)

---

# 1. 基本方針

Prepare / Markdownize / Embedding / Summary / Classification / Rerank は KCS core に含めず、**Adapter に委譲** する。OCR は Markdownize Adapter の **内部能力 (capability)** として扱う。Embedding は Text / Image を分離せず、**単一マルチモーダル Embedding Adapter** に統合する。

```
KCS core:                 Adapter:
  object store              Prepare
  snapshot                  Markdownize (OCR は内部能力)
  restore                   Embedding (multimodal)
  search                    Summary       optional
  task state                Classification optional
  common KCS API            Rerank        optional
```

Adapter の実行設定 (cmd / args / url / 認証情報) は **`.kcs/` の共有対象に含めない**。各デバイスの `~/.config/kcs/tools.toml` や OS keychain に保存する。`.kcs/` は生成済み artifact の provenance と互換性判定に必要な `profile_hash` だけを保持する。

認証情報の保存規約:

```text
推奨 (優先順):
1. OS keychain 参照:   auth = "keychain:<service_name>"
2. 環境変数参照:       auth = "env:GEMINI_API_KEY"

許容 (非推奨):
3. tools.toml 直書き:  auth = "plain:<api_key>"
   - tools.toml の permission が 0600 (owner read/write のみ) でない場合、
     KCS は起動時に warn を出す (errors.jsonl に level=warn で記録)

禁止 (既定どおり):
   .kcs/ 配下・tool-lock.json・tool_profile_hash の入力への認証情報の混入
```

`tools.schema.json` は `auth` フィールドを `^(keychain|env|plain):` にマッチする文字列
として規定する ([06-cli-spec.md §11](06-cli-spec.md))。

---

# 2. 実行形態

Adapter は **提供主体ではなく実行形態と決定性** で分類する。

```
online_api               LLM 等のネットワーク越し API (frontier AI が中心)
                         明示的な network opt-in が必要
offline_api              ローカル LLM / ローカル embedding server
                         ネット送信なし。非決定的出力はあり得る
deterministic_library    決定論的ライブラリ (PDF text extraction, parser)
                         同じ入力 + 同じ profile なら同じ出力
```

KCS API の契約は実行形態に依らず同じ。

```
KCS core
  → task descriptor (task_id, adapter_kind, input_hash, allowed scope, network permission)
  → device-local Adapter
  → artifact descriptor (output_hash, status, error_kind)
  → KCS core
```

## 2.1 同梱 deterministic Adapter (ベースライン index)

KCS は `deterministic_library` の Prepare / Markdownize Adapter を同梱する。対象: plain text / Markdown / コード (passthrough + fence 正規化)、PDF text layer 抽出。OCR・レイアウト解析・画像理解は行わない。

- online Adapter が未設定または network 未承認のとき、Markdownize タスクは同梱 deterministic Adapter で実行する (タスクを止めない)。Embedding タスクは生成しない (検索は text fallback、[05-runtime.md §1](05-runtime.md))
- この状態を **ベースライン index** と呼ぶ。`init → snapshot → search → open` の最低体験ライン ([01-positioning.md §3](01-positioning.md)) はベースライン index のみで成立しなければならない
- online Adapter を承認した後の AI 強化は、別 `tool_profile_hash` の artifact として通常の Markdownize / Embedding タスクで生成する (identity 規約 [03-data-model.md §5](03-data-model.md) のとおり。ベースライン artifact とその Evidence Pointer は不変のまま残る)

---

# 3. ネットワーク送信原則と opt-in (正本)

KCS core は、**明示オプトインなしにネットワーク越し API へファイル内容を送信してはならない**。
本節を network opt-in の正本とし、[06-cli-spec.md §2](06-cli-spec.md) / [10-operations.md §1](10-operations.md) / [01-positioning.md §1.1](01-positioning.md)
は本節を参照する。

```text
default: no network transmission (opt-in 未成立の scope からはオンライン送信しない)
```

opt-in の単位・成立・寿命:

```text
単位:   scope × adapter
        (どの .kcs のファイルを、どの online_api Adapter (tool_id) に送るか)

成立:   (a) 初回スキャン承認フローで network transmission policy を承認
            (対話承認 または --approve。--yes では成立しない: 06-cli-spec.md §2)
        (b) 明示設定: .kcs/config.toml の adapter.policy.allow_network = true

寿命:   永続 (revoke まで)。ただし対象 Adapter の tool_id または execution_mode が
        変わった場合は失効し、再承認を要する。

revoke: adapter.policy.allow_network = false に設定する。
        以後、当該 scope の新規オンライン送信 task は発行されない
        (送信済みデータの取り消しは保証しない)。

記録:   承認記録 (10-operations.md §1) に scope_id / tool_id / approved_at /
        approval_method を残す。
```

CLI フラグ `--online` は **その 1 回の実行に限る一時 opt-in** で、永続記録を作らない。
優先関係は次のとおり:

```text
CLI (--online / --offline)  >  .kcs/config.toml (scope)  >  ~/.config/kcs/config.toml (user)
```

**01-positioning.md との整合**: デフォルト同梱 Adapter は online_api (frontier AI) だが、
初回スキャン承認で network transmission policy に同意するまで送信は始まらない。
"frontier AI default" は同梱・推奨構成を指し、"default: no network transmission" は
opt-in 未成立状態の既定値を指す。両者は矛盾せず、初回スキャン承認フローが接続する。

オンライン API Adapter を使う場合、ユーザーがどの scope / file / task を送信対象にしたかを
記録する。オフライン API / 決定論的ライブラリの場合も `execution_mode` と `profile_hash` は
記録する。

---

# 4. 共通メタデータ

すべての Adapter は次を返す:

```
AdapterProfile:
  adapter_kind          "prepare" | "markdownize" | "embedding" | ...
  adapter_id
  execution_mode        "online_api" | "offline_api" | "deterministic_library"
  tool_profile_hash     計算規約は 03-data-model.md §5.1
  version
  capability_flags      ["ocr", "layout_detection", "incremental_update", ...]
  allow_network

AdapterRun:
  task_id
  input_hashes
  output_hashes
  status                "pending" | "running" | "done" | "partial" | "failed"
                        (partial = unit 単位の部分失敗, 04-pipeline.md §5.2)
  error_kind            error_code (06-cli-spec.md §8)
```

---

# 5. 各 Adapter の trait

## 5.1 Prepare

```
input:
  raw_hash, media_type
output:
  prepared_object_hashes
  prepared_unit_hashes        (page / slide / sheet / image 単位)
  image_object_hashes         (画像抽出があれば)
metadata:
  unit_kind, page_number, mime, fingerprint (semantic_fingerprint)
```

PDF page image、Office intermediate、抽出済み image など、後続 Markdownize / Embedding が扱いやすい単位を作る。

## 5.2 Markdownize

OCR は独立 Adapter ではなく **本 Adapter の capability** として表現する。

```
input:
  raw_hash, media_type
  prepared_unit_hint          (optional)
  mode                        "full" | "incremental"
  previous (incremental 時のみ): { raw, normalized_units, tool_profile_hash }
  hints (incremental 時のみ):   { changed_unit_keys, added, removed, page_fingerprints }
  tool_profile_hash
  spec_version
output:
  mode_used                    "full" | "incremental"
  updated_units / added_units / removed_unit_keys / unchanged_unit_keys
  evidence_pointers
  fallback_to_full             bool
  reason
capability_flags:
  ocr, layout_detection, table_extraction, speech_to_text, incremental_update
```

incremental の詳細プロンプト規約は §8 (生成 LLM 系のみ。§8 冒頭の適用範囲を参照)。

**標準 Adapter (非 text-native)**: PDF / DOCX / PPTX / 画像の Markdownize 第一候補は Mistral OCR 系文書処理 API (`mistral_ocr_markdownize`) とする (経緯: [research/markdown.md](research/markdown.md))。規約:

- 表は Markdown 本文に inline で保持する (`table_format=null` 相当)。独立 table object は作らない。
- 文書内 embedded image は抽出して image object ([03-data-model.md §2](03-data-model.md)) として保存し、Markdown 内の参照は `kcs://<scope_id>/object/image/<image_hash>` に置換する ([08-evidence-pointer-spec.md §2.3](08-evidence-pointer-spec.md))。実装は Step 2 ([09-mvp-scope.md §3.1](09-mvp-scope.md))。
- bbox / page / confidence score は unit metadata に記録する。**Evidence Pointer の必須 schema には含めない** (optional フィールドとしての露出は Phase 4+ 判断。forward compatibility は [08-evidence-pointer-spec.md §8](08-evidence-pointer-spec.md))。
- 生成 LLM (Gemini / Claude / GPT 等) は Markdownize の主処理ではなく、OCR 後の品質検証・図表解釈・summary (§5.4) に使う。

> **実地検証済み (2026-07-03、設計宿題 #6 解消 [09-mvp-scope.md §5.5](09-mvp-scope.md))**: 合成 fixture (複雑表・日本語・数式・埋め込み画像、4 ページ) を sync / Batch 両モードで検証: 表セル一致率 1.0 (17/17)、日本語 CER 0.0、画像抽出 1/1 (placeholder 形式も §5.2 想定どおり)、数式は LaTeX でテキスト化。単価は公称一致 (API $4 / Batch $2 per 1,000 pages)、Batch のジョブ往復は 4 ページで約 24 秒。ハーネスと実測ログは `experiments/ocr-verification`。検証が崩れた場合の fallback (生成 LLM 系 §8.2 へ戻す) の設計は維持する。

## 5.3 Embedding (multimodal)

```
input_type:           "text" | "image" | "markdown_chunk" | "image_object" | "query"
input:
  items: [{ id, text|path, mime? }]
output:
  vectors: [{ id, vector }]
  dimensions, distance, modality
metadata:
  adapter_id, model_family, version, embedding_profile_hash
```

Text Embedding Adapter / Image Embedding Adapter は**採用しない**。同一 Embedding Adapter が同一 profile で多モダリティを単一 vector space へ写像する。

> **実地検証済み — 単一 multimodal profile を採用 (2026-07-03 再検証で確定)**: 初回調査は「Gemini Embedding 2 multimodal は preview で pin 不可」を根拠に text-only 緩和を適用したが、事実誤認 (`gemini-embedding-2` は 2026-04-22 に GA、pinned stable 版あり) が判明し**撤回**。再検証 (`tasks/step3-embedding-verify.md` の再検証節) により本節冒頭の本来の契約どおり **単一マルチモーダル Embedding Adapter** を採用する。確定 profile: **`gemini-embedding-2` (GA 版を Adapter が起動時解決して pin、§6) / 768 次元 (MRL 切り詰め — 切り詰め後次元も profile に固定) / cosine / `modality="multimodal"` / `mode="online"`** (Vertex はバッチ推論非対応のため client 側で並列 + 429 backoff)。MVP で実際に embed するのは text chunk のみだが、profile を multimodal にしておくことで Phase 4+ の image/audio embedding を [03-data-model.md §7](03-data-model.md) の全 re-index なしに追加できる。text 品質は MTEB で前世代 text 専用モデルを上回り日本語も同格 (再検証節)。コスト: 10 万 chunk 初回 ≈ $10 (単月 budget 内)。**非 multimodal の embedding profile (`modality="text"` 等、別ベクトル空間への埋め込み) は採用不可** — tool-lock materialize / adapter 登録時に `KCS-E-EMBED-MODALITY-001` (exit 2) で拒否する ([03-data-model.md §7](03-data-model.md))。

```sql
CREATE TABLE embeddings (
  id TEXT PRIMARY KEY,
  target_type TEXT NOT NULL,    -- chunk | image | node | query_cache
  target_id TEXT NOT NULL,
  modality TEXT NOT NULL,       -- "multimodal" のみ (非 multimodal は KCS-E-EMBED-MODALITY-001 で採用不可、07 §5.3)
  vector BLOB NOT NULL,
  dimensions INTEGER NOT NULL,
  distance TEXT NOT NULL,
  profile_hash TEXT NOT NULL
);
```

sqlite-vec の制約で vector table を物理分割してもよいが、概念上は単一の Embedding Adapter / 単一の `profile_hash`。profile が一致しない場合、KCS は vector 検索を強行せず再生成または text fallback。

## 5.4 Summary (optional)

```
input:   normalized_refs | chunk_hashes | search_result_ids
output:  summary_hash
metadata: profile_hash, source_hashes, summary_kind
```

`normalized_refs` は normalized instance への参照 `(raw_hash, tool_profile_hash, gen)` ([03-data-model.md §2.1](03-data-model.md))。normalized の content hash は存在しない ([03-data-model.md §5](03-data-model.md))。

## 5.5 Classification (optional)

```
input:   raw_hashes | normalized_refs | chunk_hashes | image_object_hashes
output:  labels, categories, confidence, routing_metadata
metadata: profile_hash, label_schema_hash
```

## 5.6 Rerank (optional)

```
input:   query, candidate_result_ids, candidate_features
output:  reranked_result_ids, scores
metadata: profile_hash, searched_scopes, fallback_reason
```

Rerank Adapter は KCS の検索結果を再順位付けするだけで、**searched_scopes / fallback_reason を隠蔽してはならない**。

---

# 6. tool-lock.json

`.kcs/tool-lock.json` は使用 Adapter の identity を記録する。実行可能情報 (`cmd`, `args`, `url`, 認証情報) は **絶対に含めない**:

```json
{
  "spec_version": 1,
  "prepare": {
    "tool_id": "prepare_default",
    "kind": "deterministic_library",
    "profile_hash": "sha256:..."
  },
  "markdown": {
    "tool_id": "mistral_ocr_markdownize",
    "kind": "online_api",
    "profile_hash": "sha256:...",
    "capabilities": ["ocr", "layout_detection", "table_extraction"]
  },
  "embedding": {
    "tool_id": "gemini_embedding_2",
    "kind": "online_api",
    "mode": "online",
    "dimensions": 768,
    "distance": "cosine",
    "modality": "multimodal",
    "profile_hash": "sha256:..."
  }
}
```

`tool_lock_hash` は `tool-lock.json` 全体を JCS 畳み込みした identity ([03-data-model.md §5.2](03-data-model.md))。

config (`~/.config/kcs/tools.toml`) では `mistral-ocr-latest` のような可変 alias を指定してよい。ただし **OCR API は応答内で alias を実バージョンに解決しない** (2026-07-03 実測: 応答の `model` フィールドは `mistral-ocr-latest` のまま返る。`experiments/ocr-verification`)。したがって Adapter は **API 呼び出し自体を版付きモデル名で行う**: alias が設定されている場合は、Adapter が実行開始時に提供元のモデル一覧 API から現行の版付き名を解決してから呼び出し、その版を `tool_profile_hash` の `model_version_pin` に記録する ([03-data-model.md §5.1](03-data-model.md) — 可変 alias の pin は禁止)。モデル更新は `tool_changed` として扱われ、再 Markdownize は first-instance-wins / gen の既存機構 (§9) に乗る。

---

# 7. Adapter 実行制約 (policy)

```toml
[adapter.policy]
allow_network = false
allowed_scope = "."
max_input_bytes = 104857600        # 100 MB
timeout_seconds = 300
redact_logs = true
store_request_body = false
store_response_body = false
require_command_confirmation = true
```

任意コマンド/任意 URL を使う Adapter は、**初回実行時** に command / URL / scope / network policy を preview し、ユーザー承認を得る。実装は command allowlist、secret redaction、ログ本文禁止を前提にする。

ログに残してよいもの:

```
task_id, adapter_id, tool_profile_hash
input_raw_hash, output_hash
status, error_kind
started_at, finished_at
```

残してはならないもの:

```
原文本文 / normalized 本文 / API request body / API response body / 秘密情報
```

## 7.1 強制モデルと信頼境界 (MVP)

MVP における Adapter の脅威モデルを次のとおり確定する。

```text
1. Adapter は trusted code として扱う。
   実行されるのは、ユーザーが明示的にインストールし ~/.config/kcs/tools.toml に
   設定した Adapter のみ。

2. [adapter.policy] は「KCS 側の入力制御 + 事後監査」の規約であり、
   sandbox による強制保証ではない。
   - KCS は allowed_scope 外のファイルを Adapter に渡さない (入力制御)
   - KCS は allow_network=false の Adapter にオンライン送信前提の task を発行しない
   - AdapterRun (task_id / input_hashes / output_hashes / status) を監査ログとして残す

3. 悪意ある・侵害された Adapter プロセス自体の挙動 (allowed_scope 外の読み取り、
   allow_network=false 下での無断送信) は MVP では防御しない。
   OS レベルのサンドボックス強制は Phase 4+ の再設計論点とする。

4. 第三者 Adapter の配布・署名・検証 (サプライチェーン) は v2 以降のスコープ外。
   MVP で同梱・文書化するのは KCS 公式 Adapter のみ。
```

初回実行時の承認 UI はこの前提を反映した文言にする (例: 「この Adapter はあなたの権限で
実行されます。信頼できる提供元のものだけをインストールしてください」)。

---

# 8. Incremental Markdownize プロンプト規約

[04-pipeline.md §3.1](04-pipeline.md) で発動条件と入出力 schema を定義した。本節は **Adapter 内部のプロンプト規約** を固定する (Adapter ごとの揺れを防ぐため)。

**適用範囲**: 本節のプロンプト規約は**生成 LLM 系 Markdownize Adapter** に適用する。文書処理 API 系 (Mistral OCR 等、§5.2) は unit (page) fingerprint の再利用により変更 unit のみを再処理する経路 ([04-pipeline.md §2.2](04-pipeline.md)) で incremental を実現するため、プロンプト規約は適用されない。ただし §8.1 の 6 (受け入れ検査) と入出力 schema は**全 Markdownize Adapter 共通**。

## 8.1 Adapter が守るべき規約

```
1. "unchanged" と判断した unit は出力に含めない (旧 unit を再利用)
2. 変更 unit は完全に書き直す (部分編集ではなく full unit replacement)
   → Markdown の局所一貫性を保つ
3. heading 構造の変更は KCS には影響しない (chunk side で対応)
4. Adapter が「軽微とは言えない」と判断したら fallback_to_full=true で短絡
   閾値の Adapter 側 hint は KCS 側 hint と衝突したら **KCS 側を優先**
5. spec_version 不一致なら、Adapter は invalid_input として失敗
6. 出力は KCS 側の受け入れ検査 (04-pipeline.md §3.2) を通過しなければ persist されない。
   違反は KCS-E-ADAPTER-CONTRACT-001 として reject され full に fallback する
```

`spec_version` の bump 規約は [10-operations.md §12.5](10-operations.md) を正とする。不一致時、KCS は当該 Adapter を capability なし扱いにして full モードで呼び直す (§8.4)。

## 8.2 推奨プロンプト構造 (frontier AI 系)

```
SYSTEM:
  You are a markdownization adapter for KCS.
  Given the previous markdown of <unit_key> and the new raw input,
  produce updated markdown for changed units only.
  Keep unchanged units out of the output.

USER:
  Mode: incremental
  Tool profile: <hash>
  Previous markdown for changed units:
    <unit_key_1>: <markdown_1>
    <unit_key_2>: <markdown_2>
  New raw content (relevant pages only):
    <raw_excerpt>
  Hints:
    changed_unit_keys: [...]
    page_fingerprints: {...}

  If you judge the change as non-minor, return fallback_to_full=true
  with a brief reason. Otherwise return updated_units.
```

具体的な system prompt は Adapter 実装で固定し、`prompt_template_hash` (`tool_profile_hash` 入力フィールド) で identity に含める。

## 8.3 ストリーミング応答

大型 PDF (100+ pages) では TTFB を抑えるためストリーミング出力を許容する。KCS は Adapter からの SSE / chunked JSON を受け取り、unit 完了ごとに persist する。

ストリーミング中の unit は staging 領域に persist し、応答完了後に受け入れ検査
([04-pipeline.md §3.2](04-pipeline.md)) を通過した時点で manifest へ一括確定する。
ストリーミング失敗時は staging の完了済み unit のみ確定し、未完了は `pending` で再開可能にする
(再開後の全体集合に対して受け入れ検査を適用する)。

## 8.4 Capability 宣言なしの Adapter

`capabilities` に `incremental_update` を含まない Adapter は、KCS が **常に full モード** で呼ぶ。これにより既存 Adapter との後方互換が保たれる。

---

# 9. 再現性ポリシー

Adapter の完全な再実行決定性は要求しない。KCS が保証するのは:

```
raw_hash 不変                既存 artifact を尊重 (first-instance-wins)
raw_hash 変化                 新 artifact 候補を作る
explicit re-normalize         同 (raw_hash, tool_profile_hash) に対して gen+1 の新 normalized
                              instance を作る (kcs reindex --force のみ許可)。旧 instance は
                              保全され、既存 commit / Evidence Pointer は旧 gen を参照し続ける
                              (03-data-model.md §2.1)
```

Markdown の content hash は持たない ([03-data-model.md §5](03-data-model.md))。同一 `(raw_hash, tool_profile_hash)` から複数回生成した結果が異なっても、**最初に確定したインスタンスを永続化** し、以後は再生成しない (first-instance-wins)。
