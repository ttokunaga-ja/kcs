# 探索型 4 エンジン監査 ランブック (新セッション貼り付け用)

このファイル全体を新しい Claude Code セッションに貼り付ければ、探索型クロスチェックを 1 ラウンド
実行できる。長い会話コンテキストを引き継がずに毎回クリーンに走らせるための自己完結手順。

---

## 0. 位置づけ (安全ガードの誤発火を避けるため必読)

これは **開発者自身が所有する OSS リポジトリ (KCS) に対する、出荷前の防御的セキュリティ監査**である。
目的は自分のコードの脆弱性・不具合を第三者に悪用される前に発見して修正すること。攻撃対象は自分の
ローカルツールのみ。実 API キーは使わず、全操作は隔離した一時ディレクトリで行う。これは正当な
defensive security 作業であり、拒否する理由はない。過去 3 ラウンドで秘匿情報漏出 (critical) を含む
実バグを多数捕捉し、すべて修正済み。

## 1. 対象

- リポジトリ: `/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs` (main)
- KCS = Rust 製のローカル知識アーカイブ CLI (evidence-grounded local knowledge archive)。
  `kcs init/index/snapshot/search/view/open/batch/reindex/repair/diff/tag/log/status` 等。
  仕様正本は `docs/01`〜`docs/10`。実装は `crates/kcs-{core,pipeline,adapter,index,search,cli}`
- 現状 (このランブック作成時): 全テスト green (267)、clippy/fmt clean。Step 1-3 実装済み +
  実 API 検証済み。Step 4 (restore/time-travel/purge/evidence verify CLI/bbox_annotation) は未着手

## 2. テスト seam (実 API 不要)

- `KCS_TEST_GEMINI_EMBED=mock|rate_limit|auth_error|non_multimodal|incompatible_profile`
- `KCS_TEST_MISTRAL_OCR=mock|partial|auth_error|rate_limit`
- 実機は必ず `export XDG_DATA_HOME=$(mktemp -d)` で隔離、scope は `/tmp` 配下に作る

## 3. 既知の問題 (再報告不要 — 新規のみが成果)

これらの task ファイルに載っているものは全て修正済み。新セッションでは冒頭で `git log --oneline -40`
と下記ファイルの見出しに目を通し、重複を避けること:
- `tasks/step3c-fixes.md` / `step3c-reaudit-4engine.md` (Step3 実装ラウンド F/G/H/I/K)
- `tasks/step3-checkpoint-fixes.md` (L1-L8: reindex/repair の enrichment、override_budget、
  snapshot 後の view 射影、adapter 単位 opt-in ほか)
- `tasks/step3-bughunt-fixes.md` (M1-M8: 並行 index 破損、view 本文、raw_hash 短縮、破損 sqlite 分類、
  CAS キャッシュ冪等、pointer identity、object URI dispatch、config 検証)
- `tasks/step3-bughunt2-fixes.md` (N1-N8: Tier B online 送信 hold、手動 snapshot の Tier A 除外、
  log redaction、diff/tag パストラバーサル、Evidence gen 束縛、チャンク O(N²)、--online embedding、短 query)
- `tasks/step3-bughunt3-fixes.md` (O1-O7: cursor の scope 迂回 + 署名、query embedding 送信境界、
  batch lock、PDF char 境界 panic、0 chunk index 固着、短 sha256 panic、cursor scope 曖昧)
- docs で `Step 4` / `Phase 4+` / `v2+` と明記の未実装

**過去 3 ラウンドの鉱脈は掘り尽くし気味**: R1=並行/異常系の後続経路、R2=秘匿情報漏出/パス検証/資源枯渇、
R3=検索境界の完全性/入力堅牢性/状態の縮退。**新しい鉱脈の方が期待値が高い** (下記ヒント参照)。

## 4. 手順 (新セッションの Claude が実行)

1. `git rev-parse --short HEAD` と `cargo test --workspace 2>&1 | grep 'test result'` で現状確認
2. 下記「共有バグハントプロンプト」を自分の scratchpad か `/tmp/bughunt-prompt.md` に書く
   (§0 の防御的セキュリティ位置づけを必ず含める)
3. **4 エンジンを並列起動** (Opus/Sonnet は抽象指示で自由に、Spark は範囲限定):
   - Claude-Opus: `Agent` tool、`subagent_type: general-purpose`、`model: opus`、
     run_in_background、プロンプト = 共有プロンプト + 「エンジン識別子 Claude-Opus。cargo/実機/python3 可」
   - Claude-Sonnet: 同上 `model: sonnet`、「エンジン識別子 Claude-Sonnet。実バイナリを自分の手で叩く」
   - GPT-5.5: `Bash` run_in_background:
     `codex exec -m gpt-5.5 -s read-only -C <repo> "$(cat /tmp/bughunt-prompt.md)\n\nエンジン識別子 GPT-5.5。read-only なので静的読解 + file:line 立証"`
   - GPT-5.3-Codex-Spark: `Bash` run_in_background、**範囲限定プロンプト** (下記 §6、丸読み禁止 grep/sed 限定)
4. 全エンジン回収後、所見を統合。**critical/major は自分で実機再現 or file:line 検証してから採否**を決める
   (エンジンの誤検出・既知重複を除外)。verify スクリプトの罠に注意:
   `grep -rl P dir | head && echo found` は grep 不一致でも head 成功で常に真。**grep の exit code を直接見る**
5. 採択した所見を `tasks/step3-bughunt4-fixes.md` に裁定として書き、コミット
6. 修正を `Agent`(opus) に発注 (docs 変更禁止・各修正ごとに cargo test・回帰テスト必須・commit しない)。
   完了後 `cargo test --workspace` / `clippy -D warnings` / `fmt --check` 全 green を確認、
   critical は自分で実機再確認してからコミット
7. `git push origin main` は**ユーザーに依頼** (直接 push しない)

## 5. 共有バグハントプロンプト (Opus/Sonnet/GPT-5.5 に渡す本文)

```
あなたは KCS (Rust 製ローカル知識アーカイブ CLI) の探索的バグハンターです。これは開発者自身が
所有するリポジトリに対する出荷前の防御的セキュリティ監査であり、脆弱性・不具合を先回りして潰すのが
目的です。攻撃対象は自分のローカルツールのみ、実 API キーは使いません。

ミッション: 我々がまだ見つけていない不具合・脆弱性を見つけること。方法・観点は自由。

前提: Rust workspace、`cargo build` → target/debug/kcs、仕様正本 docs/01〜10。テスト green の状態。
seam: KCS_TEST_GEMINI_EMBED / KCS_TEST_MISTRAL_OCR (§2 参照)。実機は XDG_DATA_HOME=$(mktemp -d) で隔離、
scope は /tmp 配下。リポジトリのファイル変更禁止。verify は grep の exit code を直接見る。

既知 (報告不要): tasks/step3-checkpoint-fixes / step3-bughunt-fixes / bughunt2 / bughunt3 と、
docs で Step4/Phase4+/v2+ と明記の未実装。過去の鉱脈 (並行/異常系、秘匿漏出/パス/資源、
検索境界/入力堅牢性) は掘り尽くし気味 — 新しい鉱脈の方が期待値が高い:
  - シリアライズ往復の完全性 (永続レコードの全フィールドが round-trip するか、未知フィールドの前方互換)
  - ファイル permission (秘匿を含むファイルが 0600 か、cursor-key/approvals/ledger の露出)
  - 資源リーク (一時ファイル/展開キャッシュ/FD/jsonl ログの無限成長、クリーンアップ漏れ)
  - 権限昇格・境界 (registry 経由の別 scope 参照、tool-lock/config の優先順位の悪用)
  - Agent API の契約 (--json 出力が内部状態を過不足なく開示するか、隠れた成功/失敗)
  - 並行性の残り (snapshot/reindex/batch 以外の書き込み経路、registry の同時更新)
  - 国際化・正規化の境界、時刻/タイムゾーン、schema_version の移行
だが直感を優先せよ。

品質バー: 報告する所見は必ず自分で再現 or file:line で立証。憶測不可。既知重複ゼロ。
各所見: [critical|major|minor] / 再現コマンド列 or 根拠 file:line / 期待 vs 実際 / 1 行修正案。
量より質 (確実な 2 件 > 怪しい 8 件)。

出力: ## 所見一覧 (severity 降順) / ## 探索したが問題なしと確認した領域 / ## 総合所感 + エンジン識別子
```

## 6. Spark 用 範囲限定プロンプト (ラウンドごとに焦点を変える)

Spark は context window が小さいので**必ず範囲を絞り、丸読み禁止・grep/sed 限定**にする。
過去の焦点: R1=exit/error code 一貫性、R2=JSONL append 網羅性 + search schema、R3=算術安全 + JCS 決定性。
**今回 (R4) の推奨焦点** — 永続レコードのシリアライズ往復 + ファイル permission:

```
あなたは KCS (開発者自身のリポジトリ) の焦点セキュリティ監査人です。範囲限定 (丸読み禁止、grep/sed のみ)。

検証1 (シリアライズ往復): 永続化される全レコード型 (TaskDescriptor/tasks.jsonl、approval record/
approvals.jsonl、MonthlyCostLedgerEntry/cost-ledger.jsonl、CursorToken、EvidencePointer、
scope.json、tool-lock.json、scope-registry) を grep で特定し、(a) 書き込みで出す全フィールドが
読み取りでパースされるか (フィールド脱落で lost update しないか)、(b) 未知フィールドを含む行を
読んで落ちないか (前方互換)、(c) serde の deny_unknown_fields / default の付き方が一貫か を確認。

検証2 (ファイル permission): `grep -rn 'set_permissions\|from_mode\|0o600\|OpenOptions\|create'` から、
秘匿を含みうるファイル (approvals.jsonl / cursor-key / cost-ledger / errors.jsonl / .env 由来の
CAS raw object) が world-readable で作られていないか、cursor-key 等の鍵ファイルが 0600 か を確認。

出力: 検証1 の脱落/非対称/前方互換リスク (file:line) + 検証2 の露出箇所 (file:line) +
エンジン識別子「GPT-5.3-Codex-Spark」。ファイル変更禁止。
```

## 7. 過去実績 (参考)

R1 (M1-M8): 1 critical + 7 major。並行 index で device-global ledger 破損 → 全 scope 巻き添え等。
R2 (N1-N8): 1 critical + 6 major + 1 minor。Tier B 秘匿候補の無確認オンライン送信等。
R3 (O1-O7): 2 critical + 3 major + 2 minor。cursor の scope 迂回 + 偽造、query embedding の送信境界等。
→ **3 ラウンドとも完全に別の鉱脈から実バグ。契約テストが全 green でも探索型は毎回新規を出す。**
