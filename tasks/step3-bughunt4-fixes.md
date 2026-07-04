# 探索型 4 エンジン監査 (第 4 ラウンド) の裁定 (2026-07-04、main = 1f959bf)

4 エンジン (Claude-Opus / Claude-Sonnet / GPT-5.5 / GPT-5.3-Codex-Spark) + オーケストレータ自身の
独立検証で探索。焦点ヒントは「シリアライズ往復 / ファイル permission / 資源リーク / Agent 契約」。
全 267 テスト green・clippy/fmt clean の状態に対して、新規 **9 件** (1 critical + 4 major + 4 minor)。
すべてオーケストレータが実バイナリで再現 or file:line で立証済み。既知 (M/N/O/K/L 各ラウンド、
docs で Step4/Phase4+/v2+ 明記) との重複はゼロを確認。

エンジン別の主な貢献:
- **Claude-Opus**: F1 (非アトミック sqlite 再構築 → 並行 search の沈黙偽陰性、67% 再現)、cursor-key TOCTOU、approvals 増殖
- **Claude-Sonnet**: P5 (redact_logs が message を検査せず絶対パス漏出、N3 の不完全修正)、open cache 位置、permission
- **GPT-5.5**: P1 (tasks.jsonl input_path の scope 逸脱 → 外部送信)、registry WAL 欠落
- **Spark / 自己検証**: permission 非対称の裏付け、P1 の完全再現、P2 争点の決着

---

## 必須修正 P1-P9

### P1 [critical] tasks.jsonl の input_path が scope 境界未検証 → 任意ファイル読み出し + online API への流出
発見: GPT-5.5 / 完全再現: オーケストレータ

- **根本**: docs/03 §3.3 は「task の `input_path` は `/` を含まないファイル名。`/` を含む path は
  `KCS-E-STORE-PATH-001` で拒否」と規定。tree entry ではこの guard が効く (`crates/kcs-core/src/dag.rs:41`
  `if self.path.contains('/')`) が、**task 実行経路には guard が無い**。
  `execute_online_markdownize_task` (`crates/kcs-cli/src/main.rs:3927`) は保存済み tasks.jsonl の
  `task.input_path` を無検証で `repo.root().join(&task.input_path)` し、`run_mistral_adapter`
  (`main.rs:3946`) → Env クライアント (`crates/kcs-adapter/src/mistral_ocr.rs:104` `std::fs::read(path)`)
  でその内容を `POST /v1/ocr` の payload に入れる。`PathBuf::join` は右辺が絶対パスなら root を捨て、
  `..` はそのまま外へ抜ける。
- **再現** (隔離 tmp、mock seam):
  1. scope で `index --approve --online` して正規の markdownize online opt-in を作る。
  2. `.kcs/tasks.jsonl` に poison 行を追記: `input_path` を絶対パス `/…/外部.txt` および
     `../../../../../../../../etc/hosts`、`output_ref:"online:mistral_ocr_markdownize"`、`status:"pending"`。
  3. `kcs batch resume` → **両 poison が status=done に到達**、`/etc/hosts` の内容が CAS に取り込まれた。
  4. 差分確認: 存在しない外部絶対パスは `failed` (= Done は外部ファイルの実読み出しに依存)。
  - `execute_pending_tasks` (`main.rs:3697`) は `persistent_network_allowed` で markdownize online を
    ゲートするが、通過後は input_path を無検証で読む。既存 opt-in を持つ victim が細工/共有された
    tasks.jsonl を `batch resume` すると、SSH 鍵・/etc/* 等の任意ファイルが Mistral OCR API に送信される。
- **期待 vs 実際**: 期待 = task は scope 直下ファイルのみ参照、opt-in 境界内だけ送信。実際 = 絶対パス・
  `..` トラバーサルで scope 外ファイルが読まれ外部 API に流出。
- **precondition**: tasks.jsonl の内容を攻撃者が制御 (共有/同期/クローンされた scope、または
  非 bare な input_path を書く将来の経路)。`.kcs` は 0755/owner-write なので別ローカルユーザからの直書きは不可。
- **修正**: `TaskStore::all` の読取時 (全 consumer を一括保護)、少なくとも `execute_online_markdownize_task`
  とファイルサイズ stat (`main.rs:3746`) の直前で、`input_path` が単一 `Component::Normal` (非絶対・
  区切りなし・`..` 無し) であることを検証し、違反は `KCS-E-STORE-PATH-001` で拒否する。dag.rs:41 と同じ規約。

### P2 [major] `.kcs/` + デバイス data dir が world-readable (0644/0755)、CAS raw に文書内容 (秘匿含む) が露出。cursor-key だけ 0600
発見: 自己検証 / Sonnet / Spark

- **根本**: `atomic_write` / `atomic_overwrite` / `append_jsonl` (`crates/kcs-core/src/cas.rs:155,175,190`) は
  `File::create` / `OpenOptions::create` で umask 既定 (022 → 0644) のまま作成。`.kcs` ディレクトリも
  `create_dir_all` (0755)。`set_permissions`/`PermissionsExt` を使うのは cursor-key 生成 (`main.rs:6659`) の
  **1 箇所のみ**。
- **実測** (umask 022、`kcs init && index --yes`): `.kcs/objects/raw/**` (取込み済み全文書の生バイト)、
  `.kcs/objects/{prepared,normalized}/**`、`quarantine.jsonl`、`approvals.jsonl`、`tasks.jsonl`、
  `.kcs/index/sqlite.db`、`$XDG_DATA_HOME/kcs/{cost-ledger.jsonl,logs/*.jsonl,scope-registry.sqlite}` が
  軒並み 0644、親 `.kcs` は 0755。
- **争点の決着**: Opus は「秘匿*内容*は CAS に格納しない設計」と本件を否定したが、**誤り**。AWS canary
  (`aws_secret_access_key=…-CANARY-7z9`) を含む `creds.env` を index したところ、`.kcs/objects/raw/c6/ce/…`
  (mode 0644) に canary がそのまま格納されていた (quarantine 分類すらされず = 未分類の秘匿も無条件で world-readable)。
- **期待 vs 実際**: プロジェクト自身が cursor-key で 0600 基準を確立し、docs/07 §1 / CT2-ADAPTER-010 で
  「認証情報を `.kcs/` に混入しない」機密方針を掲げるのに、実際の文書内容・秘匿・利用パターン
  (cost-ledger)・actor 名 (approvals) がマルチユーザ機で他ローカルユーザから読める。
- **修正**: `Repository::init` で `.kcs` 作成直後に `fs::set_permissions(&kcs_dir, 0o700)`、
  `data_home()/kcs` にも同様に 0700 を 1 回適用 (ディレクトリ単位が個々ファイルより保守しやすく、
  子ツリー全体を traversal 遮断で守れる)。

### P3 [major] tools.toml の 0600 permission 警告が未実装 (CT2-ADAPTER-010 / docs/07 §1 の P1 契約)
発見: 自己検証 / GPT-5.5 / Sonnet の 3 エンジン一致

- **根本**: docs/07-adapter-spec.md:33-35 と契約 CT2-ADAPTER-010 は「`auth = "plain:<api_key>"` かつ
  tools.toml が 0600 でなければ起動時に warn (`errors.jsonl` level=warn)」を要求。`validate_user_tools_config`
  (`main.rs:6559`、全コマンド起動時 `main.rs:279` で呼ばれる) は `validate_tools_toml` で auth 書式のみ検証し、
  **permission を一切見ない**。`errors.jsonl` への warn 発火経路も存在しない (grep 空)。契約テストも無し。
- **再現**: `~/.config/kcs/tools.toml` に `plain:` の平文 API key を 0644 で置き `kcs init && status` →
  stdout/stderr/errors.jsonl のいずれにも警告なし (exit 0)。
- **期待 vs 実際**: world/group-readable な平文 API key config を warn として観測ログに残すはずが、無警告で起動。
- **修正**: `validate_user_tools_config` 先頭で (unix) `fs::metadata(&path)?.permissions().mode() & 0o077 != 0`
  かつ config が `plain:` を含むなら `append_observation("errors.jsonl","warn","KCS-E-ADAPTER-TOOLS-PERM-001",…, json!({}))`。

### P4 [major] redact_logs が message 文字列を検査せず、絶対パスが errors.jsonl に無条件平文記録 (N3 の不完全修正)
発見: Sonnet / 再現: オーケストレータ

- **根本**: `append_observation` (`crates/kcs-core/src/scope.rs:891-919`) は `redact_context(&mut context)` を
  `context: Value` にしか適用せず、`message: &str` を `json!({…, "message": message, …})` に verbatim で書く
  (`scope.rs:915`)。`redact_context` (`scope.rs:940`) のキー allowlist は `path|query|prompt` の 3 つのみ。
  漏出源: `PipelineError::Io/Corrupt` と `AdapterError::Io` の Display が `"io error at {path}: …"` を作り、
  `pipeline_to_kcs` (`main.rs:6693` 近傍) のキャッチオールで context 空・message にパスだけが伝播。
- **再現** (redact_logs 既定 true):
  - 破損 JSONL 行 → `context:{"path":"[redacted]"}` (正) だが `message:"corrupt store file at /private/var/…/.kcs/tasks.jsonl: …"` (**同一行で矛盾**)。
  - `chmod 000 .kcs/tasks.jsonl` の通常 I/O エラー → `context:{}` 空・`message:"io error at /private/var/…/.kcs/tasks.jsonl: Permission denied"`。
  - grep で scope の絶対パスが errors.jsonl に平文出現を確認。
- 副次: context allowlist が `scope_path` (`purge_not_found_error` main.rs:3390 近傍)・`candidates`
  (`scope_ambiguous_error` main.rs:3433 近傍) を漏らす。
- **期待 vs 実際**: docs/10-operations.md:349-350 は「redact_logs 既定 true では path は元から記録されない」と明記。
  実際は message 経由で設定に関わらず絶対パスが記録され、この前提が崩れる (将来 purge のログスクラブも取りこぼす)。
  P2 (errors.jsonl が 0644) と複合し、他ローカルユーザが漏出パスを読める。
- **修正**: `redact_logs_enabled()` の時は `message` 文字列も絶対パスパターンをマスク、または
  `PipelineError::Io/Corrupt`・`AdapterError::Io` の Display から path を除去し context 経由に一元化しつつ
  `redact_context` の allowlist を `scope_path`/`candidates`/`root_path`/`kcs_path` に拡張。

### P5 [major] index/reindex/repair 中の並行 search が沈黙して空/部分結果 (exit 0) を返す — 非アトミック sqlite 再構築 (docs 明記の並行契約に違反)
発見: Opus (67% 再現) / コード+spec でオーケストレータ確認

- **根本**: `rebuild_sqlite_index` (`main.rs:2367`) は現用 `sqlite.db` を `fs::remove_file` で削除 →
  `SqliteFtsIndex::open` で新規空 DB を同じ path に作成 → chunk / tree_entries / embeddings を
  **1 行ずつ auto-commit で再投入** (`main.rs:2380-2413`) する。temp+rename でない **in-place 非アトミック再構築**。
  `run_search` (`main.rs:825`) は store lock を取らず・WAL 無効でこの DB を直読。WAL は全リポジトリで
  未有効化 (`rg 'wal|journal_mode|busy_timeout'` 実ヒット 0)。この経路は index/repair/reindex の全ミューテート系が通る。
- **spec 違反 2 点**:
  - docs/05:561「index と search の同時実行は許容 (WAL でリーダーは旧スナップショット)」← WAL 未有効化で不成立。
  - docs/05:564「repair 中の search は旧 sqlite.db を読むか `KCS-E-INDEX-REBUILDING-001`。再構築の完了は
    atomic rename (sqlite.db.tmp → sqlite.db)」← remove_file+in-place で違反。
- **再現**: Opus が 178 回の並行 search 中 **119 回 (≈67%) が exit 0 + results=0** (静止時 20 件)、
  `searched_scopes` 記録あり・`excluded_scopes` 空で正当な「該当なし」と区別不能。オーケストレータの
  別環境では reader が窓のどこに当たるかで exit≠0 (remove 後・新 DB 前) と silent-empty (空 DB 後・投入前) の
  両モードを観測。証拠グラウンディング製品の中核 (search) が沈黙して偽陰性を返す。
- **修正**: `rebuild_sqlite_index` を「一意な temp DB (`sqlite.db.<unique>.tmp`) に完成させ `fs::rename` で
  原子置換」に変更 (docs/05:564 の規約どおり、既存 `atomic_overwrite`/`replace_all` と同型)。remove_file 方式を廃止。

### P6 [minor] scope-registry.sqlite が WAL + busy_timeout 未設定 → 並行時に書込側 silent drop / 読取側 偽 exit 4
発見: GPT-5.5 (書込側) / Opus F2 (読取側)

- **根本**: `RegistryDb::open` (`crates/kcs-index/src/registry.rs:47-64`) は `Connection::open` +
  `CREATE TABLE IF NOT EXISTS` (毎回書込) のみで、`busy_timeout`/`journal_mode=WAL` を設定しない
  (rollback-journal + timeout=0)。docs/05:565 は「WAL + busy_timeout (既定 5000ms) で同時書込を直列化」と規定。
- **帰結 2 面**:
  - 書込側: `register_scope` は best-effort (`main.rs:2568`「registry write never fails init/index」)。
    並行 init/index で SQLITE_BUSY → upsert が黙って落ち、scope が registry から欠落 → default 横断検索から消える。
  - 読取側 (Opus F2): `main.rs:2545` / evidence の `main.rs:3157` が registry open の一過性失敗を「空 registry」に
    握り潰す。外部で `BEGIN EXCLUSIVE` 保持下の連打で 2/12 が exit 4 `KCS-E-SEARCH-SCOPE-ALL-FAILED-001`
    "no indexed scopes are registered" を返し健全な現 scope ごと消える。実並行での発火率は低い (単発 upsert の極短窓)。
- **期待 vs 実際**: registry は復旧可能なキャッシュ (docs/03 §4)。一過性競合は busy_timeout で待機するか現 scope に
  縮退すべき。実際は silent drop / 誤誘導 exit 4。
- **修正**: `RegistryDb::open` で `conn.busy_timeout(Duration::from_millis(5000))?` と
  `PRAGMA journal_mode=WAL` を設定。加えて読取側の registry open 失敗を「空」に握り潰さず現 scope 縮退と区別。

### P7 [minor] approvals.jsonl が index 実行ごとに単調増加 (コンパクションなし)
発見: Opus

- **根本**: `write_approval_record` (`main.rs:6512`) は構成済み online adapter ごと (markdownize + embedding = 2 行) を
  **毎回無条件追記**。既存同値行の dedup が無い。opt-in 判定 `approval_row_present` (`main.rs:6274`) は全行走査 O(n)。
- **再現**: 8 回 index → 16 行、2 回 → 4 行 (2 行/回) を実機確認。
- **期待 vs 実際**: 冪等な永続 opt-in なので行数は有界であるべき。実際は 2 行/回で単調増加、読取も O(n)。
- **修正**: 追記前に同値 `(scope_id, tool_id, network_opt_in, execution_mode)` 行の存在を確認しスキップ (または書込時コンパクト)。

### P8 [minor] cursor-key (HMAC 署名鍵) が chmod 0600 の前に 0644 で平文書込 (TOCTOU 窓)
発見: Opus

- **根本**: `cursor_signing_key` (`main.rs:6648-6662`) は `OpenOptions::new().write(true).create_new(true).open`
  (mode は umask 既定 = 0644) → `write_all(&key)` (6650) → `set_mode(0o600)` (6659) の順。32byte 署名鍵が
  **write 完了後・chmod 前の窓で 0644** として他ユーザから読める。O1(b) が「0600 生成」とした資産の露出窓。
- **期待 vs 実際**: 秘匿鍵は常に ≤0600。実際は生成直後に一瞬 0644 (単一ユーザ前提で実害小、defense-in-depth)。
- **修正**: unix で `OpenOptions::new().mode(0o600).write(true).create_new(true)` により**書込前に 0600** で作成
  (chmod 後置を廃止)。`std::os::unix::fs::OpenOptionsExt` を使う。

### P9 [minor] open/view の一時展開キャッシュが XDG_CACHE_HOME でなく XDG_DATA_HOME 配下 (spec 逸脱)
発見: Sonnet / 確認: オーケストレータ

- **根本**: 展開キャッシュ生成 (`main.rs:3270` `data_home().join("kcs/open")`) は `XDG_DATA_HOME`/`~/.local/share` 配下。
  `XDG_CACHE_HOME`/`~/.cache` は全リポジトリで未参照 (grep 0 件)。docs/06-cli-spec.md:60 は
  「raw object を `~/.cache/kcs/open/<raw_hash 先頭12桁>/<basename>` に read-only 展開」と明記。
- **期待 vs 実際**: 格納先が spec と異なる。汎用キャッシュ整理や「`~/.cache` は消してよい」というユーザ期待から
  このディレクトリが外れる。展開コピーは `set_readonly`=0444 で world-readable な文書内容でもある (P2 と関連)。
- **修正**: `XDG_CACHE_HOME` (無ければ `~/.cache`) を返す `cache_home()` を新設し `kcs/open` をそちらへ移す。
  自動掃除が MVP 未実装なのは docs/06 §1.1 明記の許容事項 (格納先の逸脱のみ本件)。

---

## 受け入れ条件 (P ラウンド)

- P1: 非 bare な input_path (絶対 / `/` / `..`) を持つ poison tasks.jsonl で `batch resume` が
  `KCS-E-STORE-PATH-001` で拒否し、scope 外ファイルを読まない・送らない (回帰テスト付き)。
- P2: `kcs init` 後に `.kcs` と `$XDG_DATA_HOME/kcs` が 0700、配下の秘匿含みファイルが他ユーザから読めない。
- P3: `plain:` 平文 auth の tools.toml が 0600 でない時に `errors.jsonl` へ level=warn 記録 (契約テスト付き)。
- P4: redact_logs=true で破損 JSONL / permission-denied を起こしても errors.jsonl の message に絶対パスが出ない。
- P5: `reindex --force` 実行中の並行 search が旧完全結果 or 明示 REBUILDING を返し、exit 0 の空/部分結果を返さない。
- P6: registry open で busy_timeout + WAL が設定され、並行 init/index で scope が registry から欠落しない。
- P7: 同一 opt-in で複数回 index しても approvals.jsonl の等価行が増えない。
- P8: cursor-key が生成の瞬間から 0600 (0644 窓が無い)。
- P9: open/view の展開キャッシュが `$XDG_CACHE_HOME/kcs/open` (or `~/.cache/kcs/open`) に作られる。
- 全 267+ テスト green、`clippy -D warnings`、`fmt --check` clean を維持。各修正に回帰テストを追加。
- docs は変更しない (実装を docs に合わせる)。P1/P5 は critical/中核につきオーケストレータが実機再確認してからコミット。
