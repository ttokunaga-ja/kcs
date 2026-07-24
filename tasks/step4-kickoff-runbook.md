# Step 4 着手ランブック (新セッション貼り付け用)

このファイル全体を新しい Claude Code セッションに貼れば、長い会話コンテキストを引き継がずに
Kio の Step 4 実装を開始できる。自己完結の着手手順。

---

## 0. これは何か

Kio = 開発者自身が所有する Rust 製ローカル知識アーカイブ CLI (evidence-grounded local knowledge
archive)。`<repo>` (main)。仕様正本 docs/01〜10、
実装は crates/kio-{core,pipeline,adapter,index,search,cli}。

**Step 1-3 は実装・多エンジン監査・実 API 検証まで完了して main にマージ済み** (着手時点でテスト
green ~267、clippy/fmt clean)。北極星シナリオ M3-1 は実 Gemini hybrid で Recall@10=1.0 を達成済み。
**次は Step 4。完了すると M3-2/M3-3 の Recall 判定が可能になり、北極星 3 シナリオすべてが Done 判定
に到達する** = MVP の実質完成。

着手前に必ず: `git log --oneline -30` と `git rev-parse HEAD`、`cargo test --workspace 2>&1 | grep
'test result'` で現状確認。`origin/main` に未 push があればユーザーに push を促す。

## 1. Step 4 のスコープ (正本 = docs/09-mvp-scope.md §3.1、LOC 1,500-2,500 / 1.5-2 ヶ月)

1. **restore** (`kio restore --to <commit|tag>`): working tree を過去 snapshot に戻す
   (05 §4)。shallow commit からの restore は既に KIO-E-COMMIT-SHALLOW-001 で拒否済み
2. **time-travel 検索フラグ** (`--at <commit>` / `--all-history` / `--include-deleted` / `--since`):
   05 §1.6 の chunk 集合 join 意味論。Step 3 は基盤 (tree_entries HEAD 射影 / chunks append-only /
   first_seen_commit 刻印) を用意済みで、フラグは「受理して Step 4 エラー」の状態 → 本実装に置換
3. **purge 最小形**: tombstone + `commit_type=purged` + 検索除外 + `--erase-tombstone` + ログスクラブ
   (05 §3 / 08 §4.1 / 10 §7)。完全な履歴書き換え (tree/commit 再結線・filename 秘匿) は v2+/Phase 4+ で範囲外
4. **`kio evidence verify <pointer>`** (単発 CLI): 08 §4.3。resolver 内部関数は Step 3 で実装済み、
   CLI 露出が Step 4
5. **`kio repair --verify-objects`**: CAS object の content hash 整合性検証 (10 §7.5、KIO-E-STORE-CORRUPT-001)
6. **bbox_annotation の実装** (07 §5.2、2026-07-04 実 API 境界調査で採用確定・既定 ON・+25% コスト):
   Mistral OCR の images[] 領域 (チャート/グラフ内テキスト、境界 = C3) の説明+書き起こしを取得し
   unit metadata に載せて chunk 化時に検索対象へ。`.kio/config.toml` で無効化可
7. **eval M3-2 / M3-3 の結線と Done 判定**: golden-queries.jsonl に M3-2 (16 件、`--all-history`) /
   M3-3 (16 件、`--include-deleted`) が凍結済み。time-travel 実装後に `run_eval.py --scenario M3-2/M3-3`
   で Recall@10 >= 0.8 を実測 (text-only 0.8889 / hybrid 1.0 が M3-1 の実績)
8. **online Markdownize 成果物の HEAD/search への昇格** (R8 F6、2026-07-05 裁定で Step 4 保留):
   現状 online markdownize task は Done まで走り `objects/normalized_units` に成果物を生成 (課金) するが、
   その resolved profile の normalized ref が commit tree/tree_entries へ昇格せず、`reindex` 後も検索不可
   (tree は offline deterministic profile のまま)。Step 4 で「Done 時に resolved profile の normalized ref を
   tree commit へ昇格 + SQLite rebuild + tool-lock に resolved Mistral profile を記録」を実装する
   (裁定 = `tasks/step3-bughunt8-fixes.md` §design F6)。実装まで online markdownize は課金しても成果物未使用。

**範囲外 (やらない)**: 定期 auto snapshot / on_idle GC / tiered retention は Phase 4+ (09 §2)。
purge の完全な履歴書き換えは v2+。docs 09 §3.1 で `Phase 4+` / `v2+` と明記のもの全て。

## 2. 既に用意されている前提物 (再作成不要)

- **eval ハーネス**: `eval/` にコーパス生成・履歴再現 (rename 7/edit 3/delete 9)・golden 50 件
  (M3-1:18 / M3-2:16 / M3-3:16、凍結済み・変更禁止)・run_eval.py (--scenario 対応)
- **bbox_annotation 検証 fixture**: `experiments/ocr-verification/` に境界調査 fixture 18 ページ +
  曖昧画像 15 枚。実 API 検証は実施済みで裁定も完了 (bbox_annotation 採用)
- **decisions**: `tasks/ws1c-decisions.md` に #1〜#59 の実装判断。Step 4 の新判断は #60 以降に追記
- **Step 3 の全コード**: chunk identity / Evidence Pointer 発行・解決 / tree_entries 射影 /
  first_seen_commit / snapshot DAG / CAS が揃っている。time-travel はこの上に build する

## 3. Step 1-3 で確立した進め方 (踏襲する)

1. **契約テスト先行** (step4a): 実装より先にテストを固定する仕様書を書く。ID 体系 (CT4-RESTORE /
   CT4-TIMETRAVEL / CT4-PURGE / CT4-VERIFY / CT4-BBOX 等)、P0/P1、Given-When-Then、実計算テストベクタ、
   全テストに docs 根拠 §。step3a-contract-tests.md が体裁の手本
2. **scaffold** (必要なら): 新規型・trait の骨格のみ (ロジックは todo!)
3. **発注書** (step4c): 実装範囲・受け入れ条件・spec 未定義の暫定判断を明記
4. **実装の委譲**: 別セッションの Claude Code か Codex APP に発注 (どちらでもよい。前者は
   `cargo add` 可・git 可で検証しやすい)。**発注側 (このセッション) は裁定・マージ・監査に専念**
5. **多エンジン監査**: 実装完了ごとに 4 エンジン (Opus/Sonnet/GPT-5.5/GPT-5.3-Codex-Spark) で
   クロスチェック → 統合裁定 → 修正ラウンド。手法は `tasks/exploratory-audit-runbook.md` を参照
6. **探索型監査を各チェックポイントで実施**: 契約検証型が全 green でも、探索型は毎ラウンド別の鉱脈から
   実バグを出してきた (R1 並行/異常系、R2 秘匿漏出/パス/資源、R3 検索境界)。Step 4 でも
   restore/purge のような破壊的操作は特に念入りに
7. **push はユーザーに依頼** (直接 push しない)。docs 変更は最小限、矛盾は decisions に記録

## 4. Step 4 で繰り返してはいけないバグクラス (Step 1-3 の教訓)

新機能を足すとき、過去に同型で刺さった以下を先回りで潰す:
- **未配線**: 正しいライブラリ実装が CLI に繋がっていない (Step 3 の FTS5/RRF/MMR)。
  「テスト green ≠ 契約充足」— pipeline 系は CLI を通る結合テストで確認
- **並行破損**: 新しい書き込み経路 (restore の tree 書き戻し、purge の tombstone 書き込み) は
  `repo.lock_store()` を取る。JSONL append は 1 レコード単一 write_all
- **秘匿の取り扱い**: 新しい経路 (restore で過去の .env を復元しないか、purge のログスクラブが
  path/query/prompt を残さないか) で Tier A/B・redact_logs を尊重
- **char 境界 / 入力堅牢性**: バイト列を str スライスするとき char 境界安全に (PDF panic の教訓)
- **opaque token / pointer**: 範囲制約との交差 + 署名/検証 (cursor の教訓)。Evidence Pointer は
  raw/tool/gen を束縛
- **exit code / error code 規律**: 06 §7 (2=usage, 3=retryable/partial, 4=permanent/not-found,
  8=incompatible) と §8 の命名。破壊的操作は確認プロンプト or 明示フラグ
- **状態の縮退**: 0 chunk / 空 scope / shallow commit / tombstoned pointer での挙動

## 5. 具体的な最初のアクション

1. 現状確認 (§0)、docs/05 §1.6/§3/§4、08 §4、10 §7、07 §5.2 と `tasks/step3a-contract-tests.md` の
   §D (Step 4 除外リスト) を読む
2. **step4a 契約テスト設計を発注** (Agent opus、抽象度を保ちつつ CT4 の ID 体系・P0・ベクタ・
   docs 根拠を要求)。M3-2/M3-3 の eval 結線契約も含める
3. 上がってきた step4a を 4 エンジンでクロスレビュー → 裁定 → r2
4. scaffold (必要なら) → step4c 発注書 → 実装委譲 → 多エンジン監査 → 修正ラウンド → merge
5. **完了ゲート**: `cargo test --workspace` 全 green + `run_eval.py --scenario M3-2` と `M3-3` で
   Recall@10 >= 0.8 実測 + restore/purge/verify の実機シナリオ。これで**北極星 3 シナリオ Done**
6. Step 4 完了後、`tasks/exploratory-audit-runbook.md` で探索型監査を最低 1-2 ラウンド

## 6. 参考: 北極星シナリオ (Done 条件、詳細は memory / docs/09 §4)

- M3-1: 「本文の数値・用語の一部だけ覚えている」→ hybrid 検索で発見 (Step 3 で Done、Recall 1.0)
- M3-2: 「リネーム前の名前で探す」→ `--all-history` (Step 4 で判定)
- M3-3: 「削除した数字を再発見」→ `--include-deleted` (Step 4 で判定)
3 つすべてが Recall@10 >= 0.8 + 実機成功確認で **MVP (Phase 1-3 相当) の Done**。
