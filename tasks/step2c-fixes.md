# Step2c 監査裁定と修正指示 (2026-07-03)

4 エンジン監査 (Claude-Opus / Claude-Sonnet / GPT-5.5 / GPT-5.3-Codex-Spark) の統合裁定。
判定: **fix-required 4/4 (全会一致)**。

## 根本診断 (4 エンジン収束)

**pipeline / adapter / task / budget の各モジュールは関数単体としては概ね正しく実装されているが、
`kcs index` に一切結線されていない dead code である** (grep 実証: 非テスト呼び出し元ゼロ)。CLI は
1 ファイル 1 unit の退化 baseline をインライン直書きするだけで、52 P0 テストの多くは「テストが
テスト用の純関数だけを検証」する見かけ倒しになっている (常真 assert 2 件、vacuous 4 件を含む)。
LOC 実測はテスト除き約 2,300-2,800 行で予算下限 3,500 を大きく下回る。

**健全な部分 (再利用してよい)**: §A ベクタは 4 エンジン独立再計算で全一致 (改変なし)。identity/JCS
(serde_jcs)、V1-V6 検査関数、unit_mapping LCS、retry policy 行列、preview/approve/exit code の骨格、
C-6〜C-11 の decisions 記録。unsafe / API キー / テスト内ネットワークはゼロ。

## 必須修正 (Step 2 完了ゲート)

### F1 [critical] kcs index への pipeline 結線 (4/4)
`run_index` を scan → prepare_units → (mode 決定 choose_markdownize_mode) → Adapter.markdownize →
validate_markdownize_response (V1-V6) → persist_normalized_instance → auto snapshot の実経路に組み替える。
`write_baseline_artifacts` のインライン直書き (main.rs:451-523) は廃止。deterministic Adapter を
baseline 経路として実際に呼ぶこと (07 §2.1)。

### F2 [critical] 固定値 placeholder の全廃 (Spark/Opus/Sonnet)
- `generated_at` / `approved_at` の固定文字列 "2026-04-25T12:00:00Z" → 実 UTC 時刻 (テスト固定は
  kcs-core の fixed-now 経路 = debug gated を再利用)
- `run_id` 固定 "run_00000000000000000000000000" → kcs-core の ULID 生成を pub 化して `run_`/`task_` prefix で採番 (decisions #21)
- deterministic adapter の tool_profile_hash リテラル転記 → `identity::tool_profile_hash()` の実行時計算

### F3 [critical] mistral_ocr Adapter の実装 (4/4)
NotImplemented を解消: HTTP client (ureq (rustls) 等、依存追加可) + 起動時の版付きモデル名解決 → pin
(07 §6)、表 inline、images[] の CAS 保存 (objects/images/) + placeholder → kcs:// URI 置換 (出現順対応、
decisions #25)、bbox/confidence は unit metadata。**テストは HTTP 層を trait モックで差し替え** (CI 外部通信ゼロは維持)。

### F4 [major] task 永続化と batch の実体 (4/4)
in-memory VecDeque → `.kcs` 配下の永続 task store (04 §5.1 descriptor 全フィールド)。
`kcs batch resume` / `retry` のハードコード応答を実装に置換 (状態遷移・retry budget・冪等性・
budget pause からの --override-budget 再開)。cost ledger (decisions #22 の schema) の書き込みと
二層 cap 判定 (`evaluate_budget` の常時許可を修正) を index/batch 経路に接続。

### F5 [major] network opt-in の実体化 (4/4 + Sonnet 実機再現)
- 承認記録を (scope_id × tool_id × execution_mode) 単位に (07 §3)。revoke 手段を実装
- **実バグ**: `--online` 単独が永続 approvals.jsonl を書く → 一時 opt-in に修正 (永続記録を作らない)
- 未承認 scope では online task を発行せず pending 残留 — 「候補数カウント」の捏造ではなく実 task record で

### F6 [major] unit 列挙と C-10 準拠 (Spark/Sonnet/GPT-5.5)
- ファイル種別ごとの実 unit 列挙 (PDF は実ページ数、常に 1 unit の決め打ちを廃止)
- text layer 無し PDF: baseline artifact を作らず pending (prepare.rs の判定は実装済みだが CLI から到達不能 — 結線)
- PDF text layer 抽出・コード fence 正規化 (07 §2.1) の実装
- 受け入れ検査違反 / fallback_to_full=true 時の「全体 reject + full 1 回自動投入」(04 §3.2、
  fallback_to_full を契約違反と誤処理している現状を修正)

### F7 [major] secrets / .kcsignore / tool-lock の仕上げ
- Tier A パターン拡充 (.ssh/ .gnupg/ .aws/ .kube/config .docker/config.json 等、root-relative)
- quarantine の実体 (承認後追加 Tier A の取り込み保留 + 記録 + kcs status 表示)
- .kcsignore matcher を 03 §11.1 準拠に (`**` / rooted path / config→.kcsignore 連結 / negation 後勝ち)
- tool-lock.json に index で使う実 Adapter entry を materialize (空 {spec_version:1} のままにしない)。
  auto snapshot の tree entry に normalize {tool_profile_hash, gen} を付与 (03 §8)

### F8 [major] テストの実体化 (テスト忠実性の回復)
- 常真テストの置換: CT2-INCR-008 (incremental と full の生成物 identity を実比較)、CT2-TASK-003 (再実行で instance が増えないことを実 assert)
- vacuous の修正: CT2-SECRETS-004 (`if let Some(commit)` スキップを排除 — 非機微ファイル同時追加で commit を強制し、.env が CAS に無いことも assert)、CT2-ADAPTER-013 (手動 mkdir でなくモック online Adapter 経由で第二 instance を生成)、CT2-ACCEPT-007 (persist されないこと + full fallback 投入を assert)、CT2-SECRETS-003/NETWORK-001 (実 task record で pending を検証)
- pipeline 系 P0 (INCR/ACCEPT/TASK/BUDGET) は **CLI (kcs index) を通る結合テスト**にする — 純関数単体テストのみでの green を完了と見なさない

## 裁定メモ

- 「todo!/unimplemented ゼロ」の完了報告はリテラルには真だが、`AdapterError::NotImplemented` への
  置換で検出を回避した形になっている。以後の完了報告では「未実装経路ゼロ」を意味として満たすこと
- §A ベクタ・identity 層・検査関数群は再利用可 — 全面書き直しではなく**結線と永続化の実装ラウンド**

## 受け入れ条件 (変更なし + 追加)

```bash
cargo test --workspace          # P0 52 green (結合テスト化後) + Step 1 回帰なし
cargo clippy --all-targets -- -D warnings && cargo fmt --check
grep 検証: kcs-pipeline / kcs-adapter の主要関数に非テスト呼び出し元が存在すること
```

ブランチ `step2c-impl` に追加コミット。完了後、発注側が再監査 (4 エンジン) を実施する。
