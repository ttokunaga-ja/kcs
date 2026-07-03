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

---

# 再監査ラウンド 2 の裁定 (2026-07-03、commit 70e9c07 に対して)

判定: **fix-required 4/4 (継続)**。ただし前回と質が異なる — F2 は全会一致で解消、F5/F6/F7 の骨格も
実機再現で解消確認 (Sonnet は 7 シナリオの実機再現を実施)。前回の根本欠陥 (pipeline 未結線・
インライン直書き) は解消した。残るのは以下 G1-G9。

## 裁定メモ (報告の誠実性)

`EnvMistralOcrClient` は「intentionally disabled」と書かれた常時エラー実装であり、報告の
「Mistral OCR adapter seam、model pin、画像 CAS を実装」は**実体を伴わない** (HTTP 依存ゼロ、
persist_images の呼び出し元ゼロ、pin 解決は "-latest"→"mistral-ocr-2505" の固定文字列置換)。
前回裁定メモの「NotImplemented 置換による検出回避」がまさに再演された。次回の完了報告では
**未実装の箇所を未実装と明記**すること。

## 必須修正 G1-G9

- **G1 [critical] budget cap の実効化** (4/4、Sonnet/Opus が実機立証): read_budget_caps の独自キー
  (device_monthly_usd_cap 等) は schema で拒否され、spec の正キーは読まれない → cap が構造的に無効。
  修正: device cap = `~/.config/kcs/config.toml` (XDG 対応) の `[budget] monthly_usd_cap`、
  folder cap = `.kcs/config.toml` の `[budget] monthly_usd_cap` を読む (04 §5.4 / 03 §11 準拠、
  schema 変更不要)。CLI 経由の cap=0 → pause テストを追加
- **G2 [critical] incremental の実体化** (4/4): map_units を index 経路に結線し、previous instance の
  復元・IncrementalHints の実算 (change_rate / consecutive / raw_hash_only_changed) で
  `MarkdownizeRequest.previous/hints` を充填。deterministic は incremental 非対応で正しいので、
  検証にはテスト用 incremental 対応 adapter を注入するフックを実装 (方式は decisions に記録)
- **G3 [critical] mistral HTTP の実装**: ureq (rustls) 等を追加し EnvMistralOcrClient を実装 (キー
  未設定は明示エラー)。pin はモデル一覧 API で解決 (固定文字列置換の廃止、07 §6)。
  **persist_images を markdownize 実経路で呼ぶ** (現状 kcs:// URI が全て dangling)。複数画像の
  bbox/confidence metadata (現状 first() のみ)
- **G4 [major] task executor の実装** (Sonnet: TaskStatus::Running 使用箇所ゼロ): pending task を
  実行して Done/Failed/Partial へ遷移させる経路が存在しない。batch resume に executor ループを実装
- **G5 [major] 受け入れ検査違反 → full 1 回自動再投入** (04 §3.2。validate Err の `?` 伝播を修正)
- **G6 [major] PDF ページ単位抽出** (Sonnet 実機: 2 ページ PDF で両ページが同一 markdown になる実バグ)
- **G7 [major] .kcsignore の `**` 対応** (Sonnet 実機: `**/*.log` が no-op)
- **G8 [major] opt-in の仕上げ**: (a) revoke 後の `--online` が opt-in を復活させる抜け穴 (Sonnet 実機)、
  (b) revoke 機構を 07 §3 の `adapter.policy.allow_network` config と整合させる (独自 sentinel file を
  廃止 or 併記)、(c) `--online` が初回スキャン承認を迂回しないことを確認・修正 (GPT-5.5 指摘、
  承認と opt-in は独立)。`--revoke-network` フラグの 06 §1 正本登録は意味論確定後に発注側が行う
- **G9 [major] テスト実体化の完遂**: CT2-INCR-008 (G2 後に CLI で full/incremental 両生成し identity
  実比較 — 現状は同一引数比較の常真)、CT2-ACCEPT-007 (CLI 経由で違反 → persist されない + full
  再投入を assert)、INCR/ACCEPT/BUDGET 系 P0 の CLI 結合化、CT2-ADAPTER-013 の CLI 経由化、
  quarantine.jsonl の重複 append 修正

minor (可能なら): markdownize_units 残骸の削除 or 結線、root-relative の secrets 判定
(.kube/config 等)、device/folder spent のループ内再計算。

## 受け入れ条件 (G ラウンド)

前回条件に加え: 実機シナリオ (a) cap=0 で index → task が paused、(b) 2 ページ PDF で
ページ別 markdown、(c) `**/*.ext` ignore が機能、(d) revoke 後 --online で送信されない、
(e) 軽微変更の再 index が (mock incremental adapter で) mode=incremental になる — を
結合テストとして含めること。

---

# 再監査ラウンド 3 の裁定 (2026-07-03、commit 3b50397 に対して)

判定: **fix-required 4/4 (継続)**。解消確認 (実機): G1 骨格 / G2 incremental (4 ページ PDF の
1 ページ編集で mode=incremental + reused_from を確認) / G5 / G6 基本 / G8 基本 / G9 の 5 シナリオ
CLI 結合化。**ただし今回も修正が新規 critical 退行を 2 件持ち込んだ。**

## 必須修正 H1-H12

- **H1 [critical] 再帰スキャンのスコープ境界違反** (4/4、Opus/Sonnet 実機立証): `**` ignore 対応で
  導入された再帰走査が、非 ignore のサブフォルダ配下ファイルを親 scope の markdownize/persist/
  task/課金に流し込む (03 §3「直下のみ」違反)。commit tree 側は正しく拒否するため orphan
  normalized instance + phantom cost + **プライバシー越境** (親の承認だけでサブフォルダ内容が
  online 送信対象になる) が発生。修正: 再帰は ignore 判定と子 .kcs 検出のみに使い、候補化は
  直下ファイル限定。**回帰ガード**: 「サブフォルダのファイルが親の objects/tasks/ledger に
  一切現れない」ことを assert する境界契約テストを追加。ct2_ignore_001 が違反挙動を「正」として
  固定しているので修正
- **H2 [critical] オンライン費用が cost ledger に未記録** (Sonnet): append_monthly の呼び出しは
  無料 baseline 側のみで、実際に課金される Mistral 呼び出しのコストが記録されない = budget
  guardrail が本来の対象に無効。online task 実行成功時に実コストを記帳し、cap 判定に反映
- **H3 [major] retry_policy 未接続**: AdapterError にエラー種別が無く、batch retry が全 Failed を
  無条件再試行 (auth_error の max_attempts=0 も無限再試行)。executor/retry の両方で retry_policy
  (backoff / max_attempts / next_retry_at) を参照
- **H4 [major] Partial 遷移不在**: executor が Done/Failed のみ。unit 単位の部分失敗から
  task_status_from_unit_counts で Partial を永続化
- **H5 [major] allow_network=true の正系未実装**: config による恒久 opt-in (07 §3) を
  network_allowed へ (優先順位 CLI > scope > user)
- **H6 [major] --online の opt-in 誤報告** (Sonnet 実機): approvals.jsonl の存在有無だけで判定し
  内容 (network_opt_in) を見ない。ct2_network_002 が誤挙動を assert しているので修正
- **H7 [major] 画像 placeholder 置換がハイパーリンクを破壊** (Sonnet 実機): `](` の最初の出現を
  無差別置換するため、画像より前のリンク URL が kcs:// URI に化け、実 placeholder は dangling。
  画像構文 `![...](...)` のみをマッチ対象に
- **H8 [major] PDF 疑似ページ分割の内容漏出** (Sonnet 実機: 3 ページ不均等 PDF で隣接ページへ
  漏出): 均等分割ヒューリスティックを廃し、content stream 境界とテキストの対応で分割
- **H9 [major] full 再投入も失敗した場合に index 全体が abort**: per-candidate で catch して
  TaskStatus::Failed を永続化しループ継続。exit code は部分失敗 (3) 系へ
- **H10 [major] device cap 既定 $50 未適用** (04 §5.4): 設定欠如時は無制限ではなく既定値
- **H11 [major] cap_kind (device/folder) が status に出ない** (04 §5.4 要件)
- **H12 [major] per_adapter cap 未読 + schema が spec 例示 config を拒否**: 実装するか、
  spec/schema 側の矛盾を発注側へ報告して裁定を仰ぐ

minor: HTTP 実装のテストゼロ (with_base_url 未使用 — ローカル HTTP サーバで実 HTTP テストを追加、
テスト注入 env var は debug_assertions ゲート)、profile() が環境に API キーがあると実通信し得る
(hermetic 化)、pin 解決を /v1/models の aliases フィールド利用に、media_type フォールバック、
死 sentinel (network-revoked 拡張子無し) 削除、markdownize_units 残骸、INCR-008 の常真残存、
cost ledger の jsonl 実装名 (仕様は sqlite — decisions に記録の上どちらかに寄せる)

## 受け入れ条件 (H ラウンド)

前回条件に加え: (f) サブフォルダ境界の回帰ガードテスト、(g) online task 成功 → ledger 記帳 →
次回 cap 判定に反映、(h) リンク + 画像混在 markdown の置換正しさ、(i) 不均等 3 ページ PDF の
ページ忠実性、(j) auth_error task が retry されないこと — を結合テスト化。
