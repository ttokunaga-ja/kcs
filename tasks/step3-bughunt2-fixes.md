# 探索型 4 エンジン監査 (第 2 ラウンド) の裁定 (2026-07-04、main = 9a3da6a)

新規 **1 critical + 6 major + 1 minor**。全件が実機再現または file:line 立証済み、M1-M8 と重複なし。
Spark の焦点監査 (JSONL 単一 write 網羅性 / search schema 照合) は問題なし (title/snippet 追加・
null 許容は許容範囲)。今回の鉱脈は **秘匿情報漏出 (3 件)**・パス検証・資源枯渇。
発注側で N1 (Tier B 送信) と N2 (手動 snapshot の Tier A CAS 混入) を実機再確認済み。

## 必須修正 N1-N8

- **N1 [critical] Tier B 秘匿情報候補が確認なしでオンライン送信される** (Sonnet 実機 + 発注側再確認):
  10 §1.1 は Tier B を「ローカル取り込みは行うが online_api 送信 task は pending 保留・status 表示・
  対話確認で承認」と規定。実装は Tier B 判定を preview 表示にしか使わず、`ignored=false` のため通常
  ファイルと同じ markdownize/embedding online task を生成 → `index --online` / `batch resume` で
  そのまま送信・done。quarantine.jsonl は Tier A のみ記録で Tier B は痕跡ゼロ。
  修正: (a) online task 生成と embedding enrichment の対象選定で
  `quarantine_reason==Some("secrets_tier_b_warning")` を hold 状態にとどめる、(b)
  record_quarantine_candidates を Tier B にも拡張し status に可視化、(c) 明示承認経路
  (`--approve-secrets` 相当フラグ or config) で hold 解除 — **対話プロンプトはこのビルドに未実装
  だが、hold + 明示フラグ承認は実装可能**。承認手段は decisions に記録。
  回帰テスト: Tier B ファイルが index --online で送信されず status quarantine に出る / 明示承認で送信される
- **N2 [major] 手動 kcs snapshot が Tier A secrets を CAS + tree に焼き込む** (Opus 実機 + 発注側再確認):
  `run_index` は excluded を auto_snapshot に渡すが、`Command::Snapshot` は
  `repo.snapshot(msg, None)` で secret フィルタを素通し。`.env` / `*.pem` の平文が objects/raw と
  最新 tree に混入 (10 §1.1 の「CAS 保存・snapshot 取り込みを行わない」違反、不可逆漏洩)。
  修正: 手動 snapshot も build_scan_preview で Tier A を算出し excluded_paths として渡す (index と同経路)。
  回帰テスト: init → .env 配置 → snapshot で .env が CAS/tree に出ないこと
- **N3 [major] errors.jsonl が redact_logs=true でも path を平文記録** (Opus + GPT-5.5):
  KcsError の context の `path`/`query`/`prompt` を append_observation が無加工で書く。10 §7 は
  「path は元から記録されない」を前提に purge のスクラブ対象を raw_hash 行に限定しているため、
  redaction 違反 + purge の取りこぼしの二重問題。修正: redact_logs 有効時に append_observation で
  context の path/query/prompt を再帰的に `[redacted]` (or basename) へマスク
- **N4 [major] diff / tag <commit> 引数のパストラバーサル** (Sonnet 実機): `resolve_commit` が
  渡された文字列を検証せず `refs/tags` に join するため、`../../..` で scope 外の任意ファイル存在を
  exit code (4=不在 / 2=非hash / 1=非UTF8+解決パス露出) で判別できるオラクル。tag() 自身の name は
  `/` を弾くのに commit 側は素通し。03 §3 のスコープ境界違反。修正: resolve_commit 先頭で name と
  同じ検証 (`/` 含む・`.`・`..`・絶対パス・components に ParentDir/RootDir を拒否)
- **N5 [major] Evidence Pointer が gen を束縛しない** (GPT-5.5): 08 §3 は tree entry の
  normalize.(tool_profile_hash, gen) で解決と規定するが resolver は tool_profile_hash のみ確認し
  gen を見ない。reindex --force 後、新 gen の chunk_hash を古い commit に混ぜた改ざん pointer が
  解決できる (M6 の identity 束縛の gen 軸漏れ)。修正: 非 shallow commit では tree entry の normalize
  を必須化し chunk.gen == normalize.gen も検証 (ct3_reindex_002 の旧 pointer 解決を壊さないこと)
- **N6 [major] チャンク分割が単一文書内で O(N²)** (Opus 実測: 1MB 3.9s / 4MB 58s の二次増大):
  slice_chars が毎回 unit markdown 先頭から chars() 再走査。10 §2 の大容量サポート宣言に反し
  8MB 単一ファイルで実用崩壊。修正: unit ごとに `Vec<char>` を 1 度作り span を O(1) インデックス化
- **N7 [major] --online の一時 opt-in が embedding enrichment に効かない** (GPT-5.5): markdownize は
  args.online を見るが embedding は args.offline のみ渡し永続 opt-in しか確認しない。
  `index --yes --online` で embedding が pending のまま。修正: embedding_online_allowed に online 引数を
  追加 (offline 優先 → online → 永続 opt-in)。回帰テスト: --online 単発で mock embedding が実行される
- **N8 [minor] 1 文字 search が scope 失敗と index_status を握りつぶす** (GPT-5.5): 短 query fast path が
  scope 解決・失敗判定の前に空応答を返し index_status を固定 1.0 に。修正: fast path を scope 解決・
  失敗判定・index_status 集計の後段へ移す

## 受け入れ条件

cargo test --workspace (回帰なし + 各 N の回帰テスト) / clippy -D warnings / fmt。
実機: (a) Tier B が index --online で未送信・status 可視・明示承認で送信、(b) 手動 snapshot で
Tier A が CAS/tree 不在、(c) errors.jsonl の path がマスク、(d) diff/tag の traversal 引数が exit 2 拒否、
(e) reindex 後の gen 混在 pointer が拒否、(f) --online 単発で embedding 実行、(g) 4MB 単一ファイル
index が線形時間 (O(N²) 解消の閾値テスト)。
