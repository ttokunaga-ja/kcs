# 探索型 4 エンジン監査 (第 6 ラウンド) の裁定 (2026-07-04、main = 96ac7d4)

4 エンジン相当 (GPT-5.5-A / GPT-5.4-B / GPT-5.5-C-static / GPT-5.3-Codex-Spark) + オーケストレータ自身の
独立検証で探索。Claude 系 subagent は本セッションで使用できなかったため、利用可能な GPT 系 subagent に置換。
全 294 テスト green・clippy/fmt clean の状態に対して、新規 **8 件** (1 critical + 3 major + 4 minor) を採択。
すべてオーケストレータが実バイナリで再現 or file:line で立証済み。既知 (M/N/O/P/Q/K/L 各ラウンド、
docs で Step4/Phase4+/v2+ 明記) との重複はゼロを確認。

エンジン別の主な貢献:
- **GPT-5.3-Codex-Spark**: R6-1 (approvals.jsonl の存在だけで --online を許す)、tool-lock/config/schema_version 系の前方互換境界
- **GPT-5.5-C-static**: R6-3 (global search opt-out の stale registry)、R6-5/R6-6 (Evidence/tool-lock future version)
- **GPT-5.5-A / GPT-5.4-B**: R6-2 (normalized_units 破損が repair/reindex を CONFIG-SCHEMA で止める)、R6-4 (CLI 余剰引数黙殺)
- **自己検証**: R6-1 の wrong-scope approval による `--yes` 外部送信、R6-3/R6-4/R6-5 の実機再現、R6-7/R6-8 の file:line 検証

**却下 / 保留**:
- Spark の `kcs_format_version = "0.x"` が広すぎる指摘は minor 前方互換リスクとして保留。現行 `0.1.0` 系内の config
  parse は後方互換を優先しており、実害再現なし。
- `manifest.schema_version` / SQLite `user_version` 欠落は将来 migration 設計の論点。Step 4+ の schema migration で扱うべきで、
  現行 Step 3 の破壊的挙動は未再現。
- human `kcs status` が tasks/budget を非 JSON 表示しない件は UX 契約不足。JSON 出力は完全で、今回の security/agent 契約修正からは除外。

---

## 必須修正 R6-1-R6-8

### R6-1 [critical] approvals.jsonl が scope_id 未束縛で、空ファイル/別 scope の opt-in 行が online 送信を許す
発見: Spark / GPT-5.5-C-static / 自己検証

- **根本**: `approval_exists` (`crates/kcs-cli/src/main.rs`) が `approvals.jsonl.is_file()` だけを見ており、
  `network_allowed` / `persistent_network_allowed_for` の JSONL scan も `scope_id` を検証していなかった。
  opt-in 単位は docs/07 の scope × adapter だが、実装は adapter だけで判断していた。
- **再現**:
  1. `kcs init` 後に空の `.kcs/approvals.jsonl` を作る。
  2. `KCS_TEST_GEMINI_EMBED=mock kcs index --online --json` が exit 0、`approval_method:"existing"` で進む。
  3. さらに別 scope_id の `network_opt_in:true` 行を markdownize/embedding 用に置き、`kcs index --yes --json` を実行すると、
     `--yes` だけなのに `network_allowed:true` / `network_opt_in:true` となり、embedding task が done まで進んだ。
- **期待 vs 実際**: 期待 = 現在 scope_id と tool_id が一致する opt-in 行だけが online 送信を許す。
  実際 = 空ファイルまたは別 scope の行で、現在 scope の文書が外部 adapter へ送信されうる。
- **修正**: approval 判定を `scope_id(repo.kcs_dir())` + `tool_id` + `execution_mode=online_api` +
  `network_opt_in=true` に統一。既存 approval に依存する `--online` は adapter ごとの一致行を要求し、
  明示的な `--yes --online` / `--approve --online` の単発送信仕様は維持する。

### R6-2 [major] normalized_units の manifest/unit JSON 破損が repair/reindex を CONFIG-SCHEMA exit 2 で止め、writer も非アトミック
発見: GPT-5.5-A / GPT-5.4-B

- **根本**: `load_normalized_units` は manifest/unit JSON parse 失敗を `KCS-E-CONFIG-SCHEMA-001` にしており、
  `repair --rebuild-db` / `reindex --force` が store corruption ではなく usage/config error として止まる。
  さらに `persist_normalized_instance` は manifest/unit/view を最終パスへ `fs::write` しており、クラッシュで torn JSON を残しうる。
- **再現**: `index --yes` 後、`.kcs/objects/normalized_units/**/<unit>.json` を `{"torn":` に切断。
  `kcs repair --rebuild-db --json` が exit 2 `KCS-E-CONFIG-SCHEMA-001`。
- **期待 vs 実際**: 期待 = 永続 store 破損は `KCS-E-STORE-CORRUPT-001` exit 4、対象 path 付き。
  実際 = config/schema error として誤分類され、復旧対象が不明瞭。
- **修正**: normalized manifest/unit の serde error を `KCS-E-STORE-CORRUPT-001` に分類。
  pipeline writer は一時ディレクトリへ manifest/unit を揃えてから rename、normalized view は atomic replace。
  reindex の gen copy と `tool-lock.json` / network revoke config も atomic overwrite に変更。

### R6-3 [major] `participates_in_global_search=false` が registry 更新まで反映されず、default search が opt-out scope を検索する
発見: GPT-5.5-C-static / 自己検証

- **根本**: `registry_all_targets` は registry に保存済みの `participates_in_global_search` だけを信用し、
  実行時の `.kcs/config.toml` を再読込していなかった。config を false に変更しても次の register まで stale true が残る。
- **再現**: scope A/B を index して registry 登録後、A の `.kcs/config.toml` を
  `[scope] participates_in_global_search = false` に変更。B から `kcs search alphaonly --json` を実行すると、
  A 固有語が default search に出た。
- **期待 vs 実際**: opt-out は現在 config が正本。実際は stale registry cache が privacy 境界を上書き。
- **修正**: registry target 列挙後、各 target の現 `.kcs/config.toml` を `participates_in_global_search` で再評価して filter。

### R6-4 [major] `view/open` の余剰引数と `reindex --at` が黙殺され、成功 JSON が返る
発見: GPT-5.5-A / GPT-5.4-B

- **根本**: `read_pointer_input` は最初の operand だけを読み、残りを捨てていた。`run_reindex` は `--force`/`--yes`
  の存在だけを `any()` で見て、`--at HEAD` や余剰 operand を無視して常に HEAD を reindex した。
- **再現**: `kcs view <valid-pointer> --definitely-invalid EXTRA --json` が exit 0 で本文を返す。
  `kcs reindex --force --yes --at HEAD --json` も HEAD reindex として成功。
- **期待 vs 実際**: agent/API 利用では unknown flag は exit 2。未実装 `--at` は明示エラーでなければならない。
- **修正**: pointer command は operand 1 個だけ許可。reindex は strict parser を導入し、`--at` は
  `KCS-E-CONFIG-NOT-IMPLEMENTED-001`、unknown/extra は invalid usage。

### R6-5 [minor] inline JSON Evidence Pointer の `schema_version` が未検証で、future pointer が現行 resolver で解釈される
発見: GPT-5.5-C-static

- **根本**: URI parser は `?sv=` を `EVIDENCE_POINTER_SCHEMA_VERSION` と照合するが、inline JSON path は
  `serde_json::from_str::<EvidencePointer>` だけで version を見ていなかった。
- **再現**: `search --json` の `evidence_pointer.schema_version` を 999 に書換え、`kcs view '<json>' --json` が exit 0。
- **期待 vs 実際**: future schema は拒否。実際は v1 として解釈。
- **修正**: inline JSON parse 後に `schema_version == EVIDENCE_POINTER_SCHEMA_VERSION` を検証。

### R6-6 [minor] `tool-lock.json` の future `spec_version` が status/snapshot hash で黙って受理される
発見: Spark / GPT-5.5-C-static

- **根本**: adapter `validate_tool_lock_value` と core `canonical_tool_lock_value` は integer かだけを見て、
  `spec_version != 1` を拒否していなかった。
- **再現**: index 後の `.kcs/tool-lock.json` を `"spec_version":999` に変更し、`kcs status --json` が exit 0。
- **期待 vs 実際**: future tool-lock schema は現行 binary が解釈できないため fail closed。
- **修正**: adapter/core の両方で `spec_version == 1` を必須化。

### R6-7 [minor] `PipelineError::Io` / `Contract` が CLI で CONFIG-SCHEMA に丸められる
発見: GPT-5.4-B / file:line 検証

- **根本**: `pipeline_to_kcs` の catch-all が `KcsError::schema(other.to_string())` で、
  `PipelineError::Io` と `PipelineError::Contract` を schema/config error に落としていた。
- **期待 vs 実際**: I/O は `KcsError::io`、adapter/pipeline contract は保持された code で返すべき。
- **修正**: `PipelineError::Io {path,message}` と `Contract {code,message}` を個別 mapping。

### R6-8 [minor] `tool-lock.json` / network revoke config / normalized gen copy が非アトミック `fs::write`
発見: GPT-5.5-C-static / GPT-5.5-A

- **根本**: `materialize_tool_lock`、`write_network_revoke_record` の config 更新、`copy_normalized_instance_gen`
  が最終パスへ直接 `fs::write` していた。派生メタデータの torn write は次回起動や reindex を止めうる。
- **修正**: CLI 側に temp + `sync_all` + rename の `atomic_overwrite_file` を追加し、対象書込を置換。

---

## 探索したが問題なしと確認した領域
- `chunks.jsonl` torn tail は R5 Q1 修正後、今回の R6 実機でも index→repair→index が green。
- cursor scope 迂回、query embedding の opt-in 境界、diff/tag path traversal、open cache 位置は既存 O/P 修正が有効。
- JSONL approval dedup は P7 修正後、同一 `(scope_id, tool_id, network_opt_in, execution_mode)` で増殖しない。
- `search --at` は既存 P/O 系テストどおり未実装として拒否される。

## 総合所感
R6 は過去の「秘匿漏出/並行性/encoding」から少し外れ、**永続レコードの identity binding と前方互換 fail-closed** が主な鉱脈。
特に R6-1 は「ファイルがある」だけを承認と見なす古い seam が adapter 単位 opt-in 修正後も残っていたもので、
scope × adapter という security boundary を横断していた。R6-2/R6-8 は R5 の crash-atomicity 鉱脈の派生で、
chunks 以外の派生 store にも同じ設計原則を広げた。
