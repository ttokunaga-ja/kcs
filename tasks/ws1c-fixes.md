# WS1c 監査裁定と修正指示 (2026-07-03)

4 エンジン監査 (Claude-Opus / Claude-Sonnet / GPT-5.5 / GPT-5.3-Codex-Spark) の統合裁定。
判定: **fix-required 4/4** (ただし Opus 評: accept 境界。実装品質は高い)。

## 必須修正 (Step 1 完了ゲート — この 5 件が green になるまで完了と見なさない)

### F1 [critical] stale lock 回収の spec 非準拠 + TOCTOU (4/4 エンジン一致)
`crates/kcs-core/src/scope.rs` `is_stale_lock` ほか。
- 現状: mtime 30 分のみで判定。lock に書いた pid を一度も読まない。05 §6 の「保持プロセスが存在しない stale lock」基準に非準拠 (この一文は Step 1 ブロッカー解消のため e201d31 で追記された正本)
- 競合窓: (a) 2 プロセスが同時に stale 判定 → 片方が再取得した正当 lock をもう片方が remove_file → 二重 writer。(b) `Drop for StoreLock` が無条件 remove → stale 回収後に他者が再取得した lock を旧プロセス終了時に削除
- 修正: pid 生存確認 (kill(pid,0) 相当) で判定。回収は「remove → create_new 再試行」ではなく所有権を検証できる原子的手順に (例: lock 内容に token を含め、Drop/解放時に自 token 一致時のみ削除。回収は unlink 前に pid 再検証)
- あわせて CT-LOCK-001 の実並行テスト (2 プロセス同時起動) を追加

### F2 [major] CT-LOCK-003 テスト欠落 (4/4 一致)
lock 保持中に `kcs log` / `kcs inspect` / `status` / `diff` が成功することを検証するテストを contract_cli.rs に追加 (実装は正しい可能性が高いが契約テストが無い)。

### F3 [major] CT-HASH-007 が恒真アサーション (GPT-5.5 + Sonnet 収束)
`contract_vectors.rs` — 手組み JSON に元から無い `"tree_hash"` の不在確認のみで実質無検証。
修正: CAS へ write → read → 再 hash → 保存キー一致の実 round-trip に置換。旧フィールド `tree_id`/`commit_id` 不在も保存バイト列で確認。

### F4 [major] JSON Schema validation が手書き if/else (3/4 が major)
06 §11 / 09 §3.1 / 03 §11 は JSON Schema validation を名指し。`*.schema.json` が存在せず `jsonschema` 依存も無い。`validate_config` は kcs_format_version と [gc].mode のみで [chunking]/[budget] 等は無検査。
修正: schema ファイル同梱 + `jsonschema` crate (発注書の依存候補に記載済み)。CT-CLI-012 の残ケース (未知フラグの spawn 版 exit 2、enum 外 commit_type) もテスト追加。

### F5 [major] Step 1 status の `up_to_date` 語彙が 03 §6 と衝突 (Sonnet major / Opus minor → 裁定: 採用)
03 §6 の `up_to_date` は「最新 normalized instance あり」の意味で、CT-STATE-005 が「Step 1 で返すなら仕様矛盾」と明示。発注書 #4 の指示自体が誤りだった (発注側の責任)。
修正: Step 1 の語彙を `up_to_date` → `unchanged` に改名 (実装 + テスト + tasks/ws1c-decisions.md #4)。tasks/ws1c-kcs-core.md #4 は裁定側で修正済みとする。

## should-fix (Step 1 内で推奨、blocking ではない)

- S1: JCS を `serde_jcs` に置換 (GPT-5.5 major → 裁定 minor: Opus が Step 1 スキーマ (ASCII キー・整数) では RFC 8785 とバイト一致を実証。ただし 03 §8.1 の文言契約は「RFC 8785」であり、dormant 逸脱を Step 2 前に解消する)
- S2: manifest 再生成で deleted 行が消える (GPT-5.5 major / Opus minor → 裁定: P1。CT-STATE-003 準拠の merge 実装)
- S3: error code 過負荷の分離 — usage 系が `KCS-E-CONFIG-SCHEMA-001` を流用 / 重複 path が `KCS-E-STORE-PATH-001` を流用
- S4: `KCS_FIXED_NOW` が本番バイナリで常時有効 (created_at 偽装可能) → cfg ガード or 明示ドキュメント。自前暦変換 (`civil_from_days`) の直接テスト追加 (現状全テストが迂回)
- S5: symlink の無警告スキップ (10 §4 の「方針明示すべき境界」) → 警告出力 + decisions.md へ記録
- S6: created_at の受け入れ検証強化 (現状 "T を含み Z で終わる" のみ)、HEAD と refs/heads/main の 2 段 rename 間の power-loss 窓の注記、非 UTF-8 ファイル名 1 件で全体失敗する挙動の再考

## 裁定済み (実装変更不要 — 文書側で解決)

- **CT-COMMIT-008 (auto commit)**: Step 1 で原理的に検証不能 (4/4 一致)。ws1a 側を Step 2 ゲートへ移動する (裁定側で ws1a を改訂)
- **CT-CLI-017 (--at/--since)**: ws1a (P1: 受理して exit 0) と発注書 #9 (exit 1) の文書間矛盾。実装は発注書に忠実。裁定: Step 1 は #9 を正とし、ws1a に「Step 4 で exit 0/2 契約へ移行」と注記 (裁定側で改訂)

## 監査で確認された健全事項 (修正不要)

- §A テストベクタ: Opus / Sonnet が独立再計算し spec・テスト定数とバイト一致。改変なし
- 依存: 全て crates.io 正規 (疑義のあった `zmij` は ryu 後継の正規 crate と裏取り済み)。vendored stub なし、unsafe ゼロ
- LOC 1,849 (予算 2,500-4,000 内)。decisions.md と実装の一致 12/12。docs/ 無変更
