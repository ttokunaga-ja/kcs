# folder-history 設計書 r20 クロスシステム最終裁定記録

- 日付: 2026-07-18
- 対象: `docs/research/folder-history-sqlite-design.md` (裁定前 3,348 行 → 適用後 3,392 行、16 編集)
- 監査プロンプト: r20 版 3,375 行 (C9=494 = +V01〜V20、X75〜X78、新規 W 採番、見出し出力禁止の明文化)
- パネル: **6 系統** = codex GPT-5.6 sol Ultra ×3 / terra Ultra ×2 + kimi-k2.7。全系統が有効報告・全系統「不合格」。
- 名寄せ・裁定: Fable (抽出 subagent 6 本 → 争点 9 点を原文書突合 + SQLite 実機検証)。

## 0. 判定と降格

| 系統 | 判定 | 新規検出 | C9 例外主張 |
|---|---|---|---|
| sol1 | 不合格 | major 6 (W01-W06) | V02 regression / V09 (SQL 実行で実証) |
| sol2 | 不合格 | major 5 + minor 1 (W01-W06) | V01 / V02 / V09 regression |
| sol3 | 不合格 | fatal 2 + major 3 + minor 3 (W01-W08) | V01 / V02 / V09 |
| terra1 | 不合格 | major 1 (W01 = V09 同根のみ) | V09 not-fixed |
| terra2 | 不合格 | major 1 + minor 1 (W01/W02) | V09 / V15 partially-fixed |
| kimi | **不合格 (初の実内容つき)** | 0 (ただし U07/V09 を自力検出) | U07 partially-fixed / V09 not-fixed |

- fatal 主張 **2 → 全降格 0** (sol3 W01 = 文書内不整合で規範側は完全 → R1 補修 / sol3 W04 = 運用前提 + 実装明記で足りる → m2)。
- **X75/X76/X77/X78 の新種子 4 本が全弾命中 — 「fix が開けた穴」25〜27 例目** (M1 = r19 M2 の scope_id が相 1 リスト非追加 (X75)、M2 = r19 M4 の即時 NULL 化が掃除キー喪失 (X76)、M3 = r19 M1 ガード × §5.3 reset の順序未固定 (X78))。M4 は X77/X27 系。
- kimi が初めて実内容を伴う不合格を返した (V09 = DDL↔規範の機械照合型 — kimi の検出様式に合致)。判定と内容の矛盾なし・作業ログ混入ゼロ (見出し出力禁止の明文化が有効)。

## 1. 回帰補修 3 (r19 の適用漏れ — 全て原文書照合で確定)

1. **R1 (V09 — 6/6 全会一致、r20 の最重要)**: r19 M3 を §20.5 の規範文 + 「(列追加)」注記だけで適用し、**§9.1 scan_cache DDL への列追加を落とした** (grep 検証が規範側の出現でパスした転記漏れ型)。→ DDL に syntax_fail_count (NOT NULL DEFAULT 0, CHECK >= 0) / first_failure_at + 対応 CHECK ((count=0)=(first_failure_at IS NULL)) を追加し、in-memory SQLite で INSERT/UPDATE/reset/CHECK 拒否まで実機検証。**sol1 W05 の深掘りを統合**: 段 1 に「count > 0 の行は stat 一致・非 racy でも段 2 へ」の再入条件 + §20.5 の reset に「bytes コミット確定」を追加 (無いと発動後も毎 tick 段 2 へ再入し続ける / そもそも 2 回目の失敗観測が発生しない)。fp 非更新リストにも構文検証保留を明示
2. **R2 (V02 — 3/6)**: completed_at DDL コメントの全終端列挙の直後に旧「(書込点は §10 collect)」が残存 → 「(未終端 NULL は status の滞留検知に使う)」へ (有用な後半だけ保持)
3. **R3 (V01 — 2/6)**: §9.1 相 2a「TTL まで機密原本が追跡不能で残る」= r19 U01 入力語統一の第 5 の取りこぼし → 「機密入力 (原本 — Office 文書は変換 PDF、§6)」

## 2. major 4

- **M1 相 1 × scope_id (sol1 W01, sol2 W01 — X75 = **25 例目**)**: 相 1 の NULL 戻しリストに scope_id 非含 → 旧世代 scope が未着手行に残存し、資格情報切替後の照合が scope 不一致の恒久 unknown へ誤誘導 (実 job 不存在なのに stalled → 明示 abandon で偽 estimated 記帳)。→ リストへ scope_id 追加 (started_at と「対の不変条件」) + 照合規範に「job_create_started_at IS NULL の行は一覧照合の対象にしない — token 時刻起点の期限判定が載せ直しを処理」の前段を明記
- **M2 abandon × JSONL 発見キー (sol1 W02, sol2 W02, sol3 W06 — X76/X72 = **26 例目**)**: JSONL id は列に持たず token 埋込 filename で発見する規範 (§6) に対し、abandon (iv) の即時 NULL 化が唯一の発見キーを消し、機密 JSONL が provider TTL まで残留。→ **ユーザー裁定 = sweep 例外拡張方式** (cleanup_token 別列・子表案は却下): abandon Tx では NULL 化せず、sweep の submit_rejected 例外を error IN ('submit_rejected', 'abandoned') へ拡張 — 照合・記帳なしで残骸掃除 → 全削除成功 (404 含む) で NULL 化。掃除が恒久不能の間は token 残存 = 削除ガード対象のまま「既知の残余」として可視化。§9.1 の明示 abandon 再掲 (脱出路) も同期。あわせて (i) の「発見 job id」→「行の batch_job_id (非 NULL の場合)」で語を明確化
- **M3 明示再生成 × ガード順序 (sol1 W04, sol2 W03, sol3 W08 — X78 = **27 例目**)**: attempts=0 リセット Tx と rotation ガードの順序が未固定 — 逆順だとガードの found 記帳 (attempts +1) が新世代の再試行予算を消費。→ 「ガード完了 → §5.3 の floor/attempts Tx → 相 1」を §5.3 と §9.1 ガード文の両方に明記
- **M4 fp × journal 回復保留 (sol1 W03 — X77/X27 系)**: fp 非更新リストに journal 系が無く、回復保留 (一時読取不能・damaged 表示中) のまま fp 確定すると次回以降スキップで恒久遮断。加えて skip 例外の journal probe が「登録フォルダ」限定で、未完 fork の目標・conflict copy (非登録) を見ない。→ 非更新リストへ「journal 回復未完了の枝」追加 + 例外を「`.folder-history` を持つフォルダ (登録有無不問)」へ拡張 + 深部出現 (sync 伝播) の検出上限 = deep-scan 周期の注記

## 3. minor 4

- **m1 journal digest バイト形式 (sol1 W06)**: UTF8(JCS(record)) ‖ LF ‖ lower_hex64(SHA-256(…)) ‖ LF・BOM 禁止に固定 (§20.3 fp 表現と同水準 — 固定しないと実装間で正常 journal を damaged 誤判定)
- **m2 scope 記録 = 呼出の同一 context (sol3 W04 fatal→降格)**: scope_id は「これから呼び出す client instance」から取得し、job 作成も同一 instance で行う (記録後に設定を再読みしない)
- **m3 scope_id canonical 構成 (sol3 W05, sol2 W01 後半, kimi #108)**: 構成 = adapter 名前空間 + account 不変 ID + workspace 不変 ID の連結・可変値禁止 + stable id を提供できない provider は server-side intent 回復の採用条件外 (NULL = fail-closed → abandon 脱出路)
- **m4 「99%」の限定 (terra2 V15/W02)**: §1 L10 に「受容前提の表明で、実装は一致率を測定・保証しない。再利用は §5.6 の text_hash 一致のみ」を追記 (§5.3 側は r16 で「同一 (content, tool) の置換の話」と限定済み — 参照は §1 の注記を継承)

## 4. 却下 1

- **sol3 W07 (abandon の seq 二重カウント)**: (i) の IN 判別 (行 batch_job_id・token の 2 キー) が記帳済みを吸収し、found 側も同判別で二重計上しない設計どおり。submission_seq は ledger UNIQUE 用の行内連番で job 数の不変量ではない。「発見 job id」の語の曖昧さのみ M2 編集で解消

## 5. 適用サマリと検証

- 3,348 → **3,392 行** (16 編集)。fence 80。旧表現 (「書込点は §10」「機密原本」「(列追加)」「例外 — 登録フォルダは」「(iv) intent_token NULL 化」) 残存 0。新規範 (syntax_fail_count ×5・abandoned 例外・scope_id 相 1・ガード順序 ×2・digest 形式・99% 限定・未着手照合対象外・client instance) 全同期確認。
- スキーマ変更: scan_cache に **syntax_fail_count・first_failure_at + CHECK 2 本** (r19 M3 裁定の完遂)。**in-memory SQLite 3.x で DDL・counter 遷移・CHECK 拒否を実機検証済み**。

## 6. r21 への申し送り

1. 検証リスト (W01 相当〜): 補修 3 の再発検査 (V09 は DDL↔規範↔migration の 3 面一致 + 段 1 再入条件) + M1〜M4 + m1〜m4。特に M2 の abandoned 例外は「abandon Tx・sweep 例外・削除ガード・明示 abandon 再掲」の 4 面一致
2. 探索重心候補: (a) abandoned 例外が開ける穴 (掃除恒久不能 token の滞留 × folder purge / 再登録、submit_rejected との分岐差)、(b) 相 1 scope_id NULL 戻し × migration 済み旧行 (started_at 非 NULL + scope NULL) の共存、(c) 段 1 再入 (count > 0) × racy × fp 非更新の三者干渉、(d) fp skip 例外拡張のコスト (`.folder-history` 保持フォルダ多数時)
3. 監査プロンプトの改良: 新規探索の自由シナリオに X 番号を再利用しない (sol1 が X75〜X78 を 2 回使用 — 採番衝突)。kimi の証明 1 行ズレ癖は継続受理
4. dsv4 再採用は入力縮小か provider 修正待ち (変更なし)。k3 は probe ハング継続 — k2.7 fallback
