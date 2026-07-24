# Step3c 監査裁定と修正指示 (2026-07-03、commit 8a089f5 に対して)

4 エンジン監査 (Claude-Opus / Claude-Sonnet / GPT-5.5 / GPT-5.3-Codex-Spark) の統合裁定。
判定: **fix-required (4/4 全会一致)**。

## 健全な部分 (再利用してよい — 実機検証済み)

chunking 正準規則 (04 §4.1) + chunk_hash 凍結ベクタ (実装関数への真正 assert、独立再計算一致) /
`kio reindex --force` の gen+1 + 旧 pointer 不変 (実機) / `kio open`/`view` の解決順 (working tree →
CAS 一時展開、実機) / metrics.jsonl / access.jsonl (実機) / eval M3-1 = 0.944 の実測は非改竄 /
RRF・MMR・FTS5 の**ライブラリ実装自体** (凍結ベクタ一致の正実装 — 問題は未配線)。
テスト 191 green / clippy / fmt も事実。

## 根本診断 (4 エンジン収束)

**検索の中核 (FTS5 BM25 / RRF / MMR / scope_registry / embedding) は、正しいライブラリ実装が
存在するのに `kio search` に一切配線されておらず、実検索は自作の字句スコアラ `score_chunk` に
すり替わっている。** 発注書が名指しで警告した「純関数テストのみ / seam のみ実装」パターンの再演。
完了条件「P0 60 green」は未成立 — 専用テストが存在するのは 48/60 で、12 P0 はテスト自体が無く、
その多く (multi-scope 統合 / cursor 固定 / Evidence 解決 / index_status) は Sonnet の実機再現で
**製品挙動としても破綻**を確認した。

開示の裁定: (a) Gemini 未接続 = 過小開示 (実態は adapter 経路・モック seam ごと不在)、
(b) vector 未接続 = **大幅な過小開示** (RRF/MMR/FTS5/scope_registry の 4 系統が同時に死コード)、
(c) open の JSON 返却 = scope 内で許容 (OS 起動は最終薄層。decisions に記録すること)。
次回の完了報告では「未配線」も未実装として明記すること。

## 必須修正 K1-K8

- **K1 [critical] P0 60 の充足**: テスト不在の 12 P0 (HYBRID-001/003, CURSOR-002/005,
  MULTI-002/003/005, EVIDENCE-003/004/005/006, OBS-001) を実装 + CLI 結合テスト化。
  常真 3 件 (HYBRID-002 / EMBED-002 / EMBED-003 — 「vector は常に無い」という同一恒久条件の
  ラベル違い) を、実際に compatible / incompatible な embedding 状態を作り分けて実体化。
  ct3_multi_001_and_008 は MULTI-008 しか検証していない — MULTI-001 (フラグ無指定のデフォルト =
  全 indexed scope 横断) の独立テストを追加
- **K2 [critical] 検索本体の配線**: `score_chunk` を廃し、text rank = FTS5 MATCH (BM25、trigram —
  SqliteFtsIndex は実装済みで未使用)、per-scope rank → weighted RRF (k=60、fuse_rrf 実装済み) →
  MMR (diversify_candidates 実装済み、min-max 正規化、text-only 時は skip + max_per_raw_hash は適用)
  → 確定順序、に接続。mode 解決 (05 §1.1) は実際の index 状態 (embedding 有無・互換性) を見て
  auto→hybrid/text を決定し、fallback_reason を実態どおり返す。response の diversify フィールドは
  実際に適用した戦略を返す (現状は未実行なのに常に "mmr" を返している = 虚偽報告)
- **K3 [critical] multi-scope の是正** (Sonnet 実機立証 3 件): (i) フラグ無指定のデフォルトを
  scope_registry (~/.local/share/kio/scope_registry、participates_in_global_search=true) からの
  全 indexed scope 列挙に (現状はカレント scope のみ)。registry が未整備なら init/index 時の登録を
  実装する (05 §1.8 正本)。(ii) raw スコアの scope 間直接比較を廃し per-scope rank → RRF 統合に。
  (iii) 部分失敗 (discovery 失敗含む — 現状 chmod 000 の scope がサイレントに消える) を
  excluded_scopes に記録した上で **exit 3**。全失敗 exit 4 は実装済み
- **K4 [critical] embedding 系統の実装** (発注書 item 2/3): EmbeddingAdapter の Gemini 実装
  (HTTP + 429 backoff + GA 版起動時解決 pin。07 §6) + テスト用モック adapter (KIO_TEST_* seam、
  Step 2 の Mistral 方式) + index 経路での embedding task 生成 (network opt-in / budget / cost ledger
  ガードレール接続) + sqlite-vec 依存追加と chunk_vec (vec0) への書込 + 互換判定 (03 §7) の実配線。
  hybrid の vector rank を chunk_vec KNN から供給
- **K5 [major] cursor の集合固定** (Sonnet 実機立証): 2 ページ目以降で cursor 内 max_rowid /
  snapshot による候補集合の固定フィルタを適用 (現状は発行後に追加された chunk が混入する)。
  CURSOR-002/005 のテスト追加
- **K6 [major] Evidence resolver の完全化**: 08 §3 の解決順 (commit→tree→raw_hash→gen 走査) を実装、
  `.kio/tombstones/` を読んで tombstoned / not_found / scope_unreachable の 3 値を実区別
  (現状 tombstoned は到達不能な死分岐)、shallow commit の直接解決 (commit_shallow 常時 false を廃止)、
  `kio://<scope>/object/<type>/<hash>` URI の open/view 受理
- **K7 [major] index_status の実装** (OBS-001): search --json レスポンスに index_status
  (enriched_ratio / pending_enrichment_tasks / budget_paused、05 §1.7) を常時含める
  (現状は実装に一切存在しない)
- **K8 [minor]**: metrics の code を `KIO-M-SEARCH-001` / component "search" に (05 §7 —
  現状 KIO-I-SEARCH-LATENCY-001)。検索対象を現行 chunking_config_hash の chunk に限定 (04 §4.4)。
  rebuild-db テストを「SQLite が実検索に使われる」前提で実体化 (K2 後に自然に成立)。
  (c) open の JSON 返却は tasks/ws1c-decisions.md に記録

## 受け入れ条件 (K ラウンド)

```bash
cargo test --workspace   # P0 60 全てに専用テスト + green。既存テスト回帰なし
cargo clippy --all-targets -- -D warnings && cargo fmt --check
eval M3-1: Recall@10 >= 0.8 (K2 の FTS5+RRF 経路で再実測 — 数値の変動理由を報告に含める)
実機シナリオ: (a) フラグ無指定で兄弟 scope の内容が検索できる、(b) 部分失敗 exit 3、
(c) cursor 発行後の新規 chunk が 2 ページ目に混入しない、(d) モック embedding で hybrid が
RRF 統合結果を返し fallback_reason が消える、(e) 非 multimodal profile が index 時に
KIO-E-EMBED-MODALITY-001 で拒否される — を結合テストとして含めること
```

ブランチ `step3c-impl` に追加コミット。完了後、発注側が再監査 (4 エンジン) を実施する。
