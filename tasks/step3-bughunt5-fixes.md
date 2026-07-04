# 探索型 4 エンジン監査 (第 5 ラウンド) の裁定 (2026-07-04、main = c0ad6d8)

4 エンジン (Claude-Opus / Claude-Sonnet / GPT-5.5 / GPT-5.3-Codex-Spark) + オーケストレータ自身の
独立検証で探索。焦点ヒントは「決定性・再現性 / クラッシュ・中断アトミシティ (単一プロセス) /
Unicode・エンコーディング境界 / 数値安全 / 状態機械・ライフサイクル / 冪等性」。
全 284 テスト green・clippy/fmt clean の状態に対して、新規 **6 件** (0 critical + 4 major + 2 minor)。
すべてオーケストレータが実バイナリで再現 or file:line で立証済み。既知 (M/N/O/P/K/L 各ラウンド、
docs で Step4/Phase4+/v2+ 明記) との重複はゼロを確認。

エンジン別の主な貢献:
- **Claude-Opus**: Q4 (NUL/UTF-16 が index 成功なのに検索不可の沈黙偽陰性)、Q1 の 3 重独立再発見 (復旧不能性 + 分類不整合の裏付け)、Q5
- **Claude-Sonnet**: Q3 (online task の Running 恒久固着 + heartbeat_at 未配線)、Q1 独立再発見 (M1(c) 規約からの逸脱を明示)、Q5
- **GPT-5.5**: Q2 (prepared/image の非アトミック書込 + 無検証 serve → 破損 object を真正 evidence として提供)、Q6 (input_hash 未検証 → slice panic)
- **Spark / 自己検証**: Q1 の完全再現 (index/reindex/repair 全ブリック)、Q2 の serve 経路の無検証裏付け、GPT-5.5 #1 (chunking_config) の反証

**却下**:
- **GPT-5.5 #1 [major] chunking_config 変更後の沈黙検索欠落** = 偽陽性。実機で反証: max_chars を 6000→8000 も
  6000→6001 も、reindex は現行 config hash の chunk 行を必ず追記し (chunk_id が config 変更で必ず変わる)、
  search は現行 config で HIT する (5 クエリ全命中)。残渣は旧 config chunk の蓄積 (append-only、GC は Step4 明記) で minor 相当・非採用。
- **Spark 検証1(a) lossy→identity** = 偽陽性。identity/fingerprint は raw **bytes** を hash (prepare.rs:74
  `hash_bytes(&bytes)`, `prepared_unit_hashes: vec![raw_hash]`)。from_utf8_lossy は表示/チャンク text 専用で identity に非関与。
- **Spark 検証2 #1 (HEAD/refs 二段 rename 窓)** = 既知 (scope.rs:411 に WS1c S6 の限界コメントあり)。
- **Spark 検証2 #5/#6 (append_jsonl / 親 dir の fsync 欠如)** = minor 耐久性、既知の許容トレードオフ。ただし Q1 の torn line の
  遠因 (fsync 無し) として関連 (Q1 の修正は読取寛容化が主、fsync は副次)。

---

## 必須修正 Q1-Q6

### Q1 [major] chunks.jsonl の torn/破損末尾行が index/reindex/repair を恒久ブリック (STORE-CORRUPT でなく CONFIG-SCHEMA に誤分類、自己修復不能)
発見: **3 エンジン独立収束** (オーケストレータ ORCH-A / Claude-Sonnet #1 / Claude-Opus #2) — 本ラウンドの目玉

- **根本**: `read_stored_chunks` (`crates/kcs-cli/src/main.rs:2405-2414`) は全行を
  `serde_json::from_str(...).map_err(KcsError::schema)` で `.collect::<Result<Vec>>()` するため、**1 行でも
  parse 失敗すると全体が Err** になり、しかも `KCS-E-CONFIG-SCHEMA-001` (exit 2、対象パス無し) に誤分類。
  この関数は `rebuild_step3_index` 冒頭 (`main.rs:2216`) で呼ばれ、`index` (`run_index`) と
  `reindex` と `repair --rebuild-db` (`run_repair`) の**唯一の chunk 読取経路**。
  append 側 `append_stored_chunks` (`main.rs:2416`) / `append_jsonl` (`crates/kcs-core/src/cas.rs:190`) は
  ともに **fsync 無し**なので、クラッシュ/一過性 ENOSPC で `write_all` 途中終了 → 末尾行が torn になる。
- **再現** (隔離 tmp、実バイナリ):
  1. `init` → `index --yes` (chunks.jsonl に 2-3 行)。
  2. `head -c $((size-25))` で末尾行を途中切断 (crash/ENOSPC の post-state、改行なし)。
  3. `index --yes` → exit 2 `KCS-E-CONFIG-SCHEMA-001` (EOF while parsing …)。
     `reindex --force --yes` → exit 2 同。
     **`repair --rebuild-db` (唯一の公式復旧コマンド) → exit 2 同 = repair 自身が同じ poison で道連れ死**。
     `search`/`status` は exit 0 (派生 sqlite は無傷なので破損が可視化されない)。
  4. 末尾 torn 行を手で削除 → `index --yes` exit 0 に復帰 (回避策はソース以外未文書化)。
- **期待 vs 実際**: torn 末尾行の chunk は次回 rebuild で normalized_units / tree_entries から再生成される
  (known-seed 専用) ため、破損末尾行は破棄して自己修復すべき。実際は全書込経路 + repair が恒久 exit 2、
  誤分類 (CONFIG-SCHEMA、あたかも設定/コマンド誤り) で対象ファイルも不明。
- **規約からの逸脱**: 同種の JSONL 破損は既に `TaskStore::all` (`crates/kcs-pipeline/src/task.rs:130-132`、
  M1(c)) と cost-ledger (`crates/kcs-pipeline/src/budget.rs:127-130` 付近) で `KCS-E-STORE-CORRUPT-001`
  (exit 4、パス付き) に分類済み。`read_stored_chunks` だけ取り残されている (自己整合性欠如)。
- **severity 根拠**: データ損失なし (CAS/commit 無傷・読取生存・手動復旧可) だが「公式復旧コマンド repair が
  自身の欠陥経路で道連れ死 = 自己修復不能」なので minor 超え major。
- **修正案**: `read_stored_chunks` を (a) **最終非空行**の parse 失敗のみ torn crash-artifact として破棄
  (skip)、(b) 非末尾行の破損は `KCS-E-STORE-CORRUPT-001` + `chunks_jsonl_path` で分類、にする。
  これで index も repair も自己修復し、破損分類も task.rs/budget.rs と整合する。

### Q2 [major] prepared/image CAS object が非アトミック書込 (fs::write + exists-skip) かつ無検証 serve → torn/破損 object を真正 evidence として恒久提供
発見: GPT-5.5 #2 / file:line 立証: オーケストレータ

- **根本**: raw/tree/commit は `atomic_write` (temp + `sync_all` + rename、`cas.rs:155`) で書くが、
  **prepared** (`main.rs:5846-5858` `if !path.exists() { fs::write(&path, object_bytes) }`) と
  **image** (`crates/kcs-adapter/src/mistral_ocr.rs:459-463` 同型) は最終 CAS パスへ直接 `fs::write`。
  非アトミックなので crash/ENOSPC 途中終了で partial file が最終 `sha256:` 名の下に残り、
  `if !path.exists()` により再 index でも**上書きされず恒久採用**される。
- **無検証 serve**: `open`/`view` の serve 経路 `open_cas_byte_object` (`main.rs:3443-3481`) は
  `object_path.is_file()` の存在確認だけで `fs::copy` して cache/serve し、**hash 検証をしない**。
  対照的に CAS の `ObjectStore::read_by_hash` (`cas.rs:78-105`) は `hash_bytes(bytes) != hash` を
  `KCS-E-STORE-CORRUPT-001` で弾く。prepared/image の serve だけこの検証を迂回している。
- **期待 vs 実際**: 期待 = CAS path の中身は常に filename hash と一致し、途中破損は検出・修復される。
  実際 = partial/破損 prepared/image が正しい `sha256:` 名の下で無検証提供され、`kcs view/open` が
  壊れた bytes を真正 evidence として返す。evidence-grounded の整合性保証が破れる。
- **修正案**: (1) prepared (`main.rs:5857`) と image (`mistral_ocr.rs:460`) を temp + rename の
  アトミック書込にする (kcs-adapter からは cas::atomic_write が pub(crate) で不可視なので、
  ObjectStore 経由か adapter 内 helper で同等実装)。(2) `open_cas_byte_object` で cache/serve 前に
  `hash_bytes(bytes) == hash` を検証し、不一致は `KCS-E-STORE-CORRUPT-001`。(2) が沈黙提供を塞ぐ主眼。

### Q3 [major] online task が Running 中のプロセス終了で恒久固着 — Running からの流出遷移が皆無、heartbeat_at は書くだけで読まない
発見: Claude-Sonnet #2 / 再現: オーケストレータ

- **根本**: 実行対象フィルタ (`main.rs:3908-3923` 付近) は `status == Pending` のみ拾う。実行直前に
  `status=Running` + `heartbeat_at=now` を永続化 (`main.rs:3966-3976` 付近、replace_all→rename)、
  完了後にのみ Done/Partial/Failed に遷移 (`main.rs:3987-3999` / `4012-4025`)。
  `batch resume` は Paused→Pending、`batch retry` は Failed→Pending のみを扱い、**Running からの
  遷移がコード全体に存在しない**。`heartbeat_at` (`crates/kcs-pipeline/src/task.rs:54`) は 3 箇所で
  書かれるだけで、リポジトリ全体で staleness 比較の**読取が一度も無い** (配線されなかったフィールド)。
- **再現** (Running 状態は crash が Running-persist と Done-persist の間で止まった状態とビット同一):
  1. `index --yes` → `.kcs/tasks.jsonl` に pending の `online:mistral_ocr_markdownize` task。
  2. その task を `status=running`, `heartbeat_at=2020-01-01T…` に書換 (crash 模擬)。
  3. `batch resume` → tasks_updated=0 / `batch retry` → 0 / `index --yes` → status=noop,
     `pending_online_tasks=0` (Running は pending カウンタから不可視)。最終 task は running のまま不変。
- **期待 vs 実際**: 期待 = 異常終了で Running のまま残った task は再 index / resume / retry / stale-heartbeat
  検知のいずれかで Pending/Failed に戻り再試行。実際 = Running は流入のみ・流出無しの吸収状態。
  `search` の `enriched_ratio` は 1.0 に到達しなくなる (Running を pending 扱いで数える `main.rs:1840`) が、
  直す手段がツール内に存在しない。
- **修正案**: KCS は単一ユーザで batch は folder store lock を保持するため、**lock 取得時点で見える Running task は
  必然的に orphan** (他プロセスは lock を取れない)。batch resume/retry と index の enrichment 起動時に、
  Running task を Pending へ reclaim して再実行する (もしくは heartbeat_at 閾値による stale-reclaim を配線)。

### Q4 [major] NUL バイトを含むテキスト (UTF-16 .txt 等) は「indexed」成功扱いなのに全文検索から無言で消える
発見: Claude-Opus #1 / 再現: オーケストレータ

- **根本**: 決定的 markdownize が `String::from_utf8_lossy` で読む (`crates/kcs-adapter/src/deterministic.rs:231`)
  ため NUL(U+0000) がそのまま chunk text に残る。FTS5 trigram tokenizer は NUL でトークン化を止めるので
  NUL 以降 (= UTF-16-LE では 2 バイト目以降ほぼ全部) が索引されない。`index_chunk`
  (`crates/kcs-index/src/fts.rs:57-77`) は `row.text` を無サニタイズで束縛。`scan` の quarantine 判定
  (`crates/kcs-pipeline/src/scan.rs:120-124`) にも非 UTF-8/NUL チェックが無い。
- **再現** (隔離 tmp):
  1. `python3 -c 'open("notes.txt","wb").write("distinctiveword platypus".encode("utf-16-le"))'`
  2. `index --yes` → `status=indexed` (exit 0)、quarantine=[]、sqlite の chunk text は
     `X'640069007300…'` (= `d\0i\0s\0…`、本文は保存されている)。
  3. `search distinctiveword` (UTF-16 ファイル固有語) → **0 results**。ASCII 別ファイル固有語は 1 hit。
- **期待 vs 実際**: 期待 = 索引した本文は検索可能、あるいは非 UTF-8/NUL ファイルは quarantine + 警告。
  実際 = index は成功を報告し本文も CAS/sqlite に保存されるのに、当該文書は検索で完全に不可視
  (silent false-negative)。Windows「Unicode」保存の .txt など現実的入力で発火。
- **修正案**: 最小修正 = FTS 索引直前 (`fts.rs` の index_chunk) で chunk text から NUL を **除去**
  (`text.replace('\u{0}', "")`。UTF-16-LE の ASCII は NUL 除去で可読 ASCII に復元 → 検索可能に)。
  理想 = scan/prepare で NUL 含有/非 UTF-8 を検知して quarantine + 警告し「成功なのに検索不可」を無くす。

### Q5 [minor] 先頭 UTF-8 BOM が最初の ATX 見出しを無効化し、Evidence の heading_path/section_id が消える
発見: Claude-Sonnet #3 / Claude-Opus #3 (2 エンジン収束) / 再現: オーケストレータ

- **根本**: `read_source_text` (`crates/kcs-adapter/src/deterministic.rs:225-232`) が
  `from_utf8_lossy` で BOM (EF BB BF → U+FEFF) を除去せず正規化 markdown にそのまま流す。
  `parse_atx_heading` (`crates/kcs-index/src/chunking.rs:266-284`) は行頭が `#` かのみ見るため、
  先頭に U+FEFF が乗ると level=0 で `(1..=6)` に落ち、その見出しが完全に非検出。
- **再現**: BOM のみ差分の A/B。`printf '\xef\xbb\xbf# Heading\n\nbody\n'` (bom.md) vs 非 BOM。
  bom.md → `heading_path=[]`, `section_id=null`。nobom.md → `heading_path=["Heading One"]`,
  `section_id="heading-one"`。
- **期待 vs 実際**: 可視テキストが同一なら BOM の有無に関わらず同じ heading_path/section_id。実際は
  BOM 付き (Windows メモ帳/Excel/PowerShell 既定) は文書先頭見出しを常に取りこぼし、以降別見出しまでの
  本文が「見出しなし」に混入 (見出し 1 個の文書は全体が恒久的に heading_path 空)。警告なし。
- **修正案**: `read_source_text` 読込直後に先頭 `'\u{feff}'` を `strip_prefix` してから markdown 化。

### Q6 [minor] 細工した tasks.jsonl の input_hash 未検証 → normalized_instance_dir の slice panic (exit 101)
発見: GPT-5.5 #3 / 再現: オーケストレータ

- **根本**: `TaskStore::all` (`crates/kcs-pipeline/src/task.rs:130-141`) は M1(c) で破損行分類、P1 で
  `input_path` の scope 検証を追加したが、**`input_hash` の hash 形式検証が無い**。online markdownize 実行
  (`execute_online_markdownize_task`、`main.rs:4114/4138/4162/4174`) がその値を raw hash として渡し、
  最終的に `persist_normalized_instance` → `normalized_instance_dir`
  (`crates/kcs-pipeline/src/markdownize.rs:305-317`) が `digest[0..2]` / `digest[2..4]` を無条件 slice。
- **再現** (mock seam + 既存 online opt-in):
  1. `index --approve --online --yes` (mock) で persistent opt-in を作り task を一度 done に。
  2. その task を `status=pending`, `input_hash="sha256:ab"` (digest 長 2) に poison。
  3. `KCS_TEST_MISTRAL_OCR=mock batch resume` → **exit 101、panic**:
     `markdownize.rs:316:22: end byte index 4 is out of bounds of 'ab'`。
- **precondition**: tasks.jsonl の内容を攻撃者が制御 (共有/同期/クローンされた scope) — P1 と同型。
  `.kcs` は owner-write なので別ローカルユーザからの直書きは不可。実害 = crash/DoS (漏出は無し)。
- **修正案**: `TaskStore::all` で `input_hash` (と存在すれば previous_raw_hash 等 hash 形状 ref) を
  `is_hash` で検証し、違反は `KCS-E-STORE-CORRUPT-001` / path error で弾く (P1 と同じ単一チョークポイント)。
  併せて `normalized_instance_dir` の slice も防御 (digest.len() ガード) すると多層防御。

---

## 探索したが問題なしと確認した領域 (複数エンジン収束)
- **identity 決定性**: 独立 2 scope で同一内容 → chunk_id / commit HEAD / tool_profile_hash がバイト一致。
  JCS は serde_jcs、float 非混入。auto-commit の created_at は wall-clock だが (raw_hash, tool_profile_hash)
  identity には非影響 (Opus + GPT-5.5)。
- **数値安全 (cosine/RRF/MMR)**: cosine の zero-vector は明示ガードで NaN 化せず (mmr.rs:163)。RRF k=60
  ハードコードで overflow 不能、tie-break は total_cmp + (scope_path, chunk_hash) で安定 (Sonnet + Opus + GPT-5.5)。
- **byte/char オフセット**: チャンクは Vec<char> ベースで境界 panic なし、view は保存 text を返し再スライスしない (Sonnet + Opus)。
- **.lock の stale reclaim**: PID + ps ベースで SIGKILL 後も次回取得時に回収 (単一ユーザ想定で許容) (Sonnet)。
- **冪等性**: index 再実行・reindex で objects/chunks/HEAD 不変、二重計上なし (Opus)。
- **サブディレクトリ非走査**: scope 直下のみ処理は docs/03 明記の意図的仕様、非バグ (Sonnet + Opus)。
- **CLI fuzz**: 空/1 文字/巨大/emoji/NUL query/不正 FTS 演算子/壊れた pointer・cursor・hash/巨大 offset で
  panic 皆無 (Opus)。※ ただし tasks.jsonl 経由の input_hash は Q6 で panic (別経路)。

## 総合所感
3 ラウンド (R2/R3/R4) で掘った鉱脈 (秘匿漏出/検索境界/permission・serialize) を離れ、R5 は
「エンコーディング境界 (NUL/UTF-16・BOM)」「派生 CAS object と append-only pointer の crash-atomicity」
「task ライフサイクル (Running の吸収状態)」という新鉱脈から 4 major を捕捉。critical は 0 だが、
Q1 が 3 エンジン独立収束 (復旧コマンド自身が復旧不能) で最重要。中核 identity・数値・並び順の決定性は
複数エンジンで堅牢確認。契約テスト全 green でも探索型は 5 ラウンド連続で新鉱脈から実バグを産出。
