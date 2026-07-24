# 06 CLI Spec

Kio の CLI 契約。GUI は MVP 範囲外 (Phase 4+) だが、将来の用語翻訳マッピングを最後に明記する。

> 関連: [03-data-model.md](03-data-model.md) (`.kio` レイアウト) / [04-pipeline.md](04-pipeline.md) (batch / retry / budget) / [05-runtime.md](05-runtime.md) (検索 / restore / GC / purge) / [09-mvp-scope.md](09-mvp-scope.md) (Phase plan)

---

# 1. Core Commands

`snapshot` を正規コマンド名とし、`commit` は Git に慣れた開発者向け alias。内部的には同じ履歴 object を作る。

```bash
kio init [<path>]                       # <path> (省略時 = カレント) の .kio を作成
kio status                              # ファイル状態 / pending タスク / budget
kio index [--preview|--approve|--yes] [--online|--offline]  # 取り込み (初回は preview + 承認必須)。
                                        # --online/--offline は当該実行の送信可否を上書き (正本 07-adapter-spec.md §3。
                                        # 優先順位: CLI > scope config > user config — ただし**明示 revoke
                                        # (allow_network = false・行の revoked) は --online より優先** (kill switch、07 §3)。
                                        # --online が開くのは未設定の既定閉鎖のみ)
kio batch resume [--override-budget] [--online|--offline]  # 中断タスクの再開 (budget 超過 pause は --override-budget 必須。04-pipeline.md §5.4/§5.7)。
                                        # --online は当該実行限りの一時 opt-in、--offline は当該実行の新規送信を禁止する逆向き上書き
                                        # (online 作業は据え置き。07 §3 — resume/retry/reindex も online 作業を駆動するため)。
                                        # in-flight の照会・出力取得・upload 掃除は新規送信に当たらず opt-in 不要 (04 §5.8 回復)。
                                        # markdownize online タスクと embedding enrichment パスを両方駆動 (04-pipeline.md §5.4)
kio batch retry [--online|--offline] [--reset-violations <selector>]  # failed タスクの再試行 (markdownize + embedding。backoff/retry 予算を尊重)。
                                        # --reset-violations = 検証済み Adapter 更新後に contract_violation_count を 0 へ戻す
                                        # (selector は abandon と同形: intent_token または 4 組タスクキー — 曖昧時は拒否。
                                        # terminal な sync 行は token NULL 化済みのため 4 組キーで指定 (04 §5.4)。
                                        # 変えるのは count のみ。確認プロンプト必須 — 04 §5.8。監査は cost-ledger の outcome 列に残る)
kio adapter revoke (<tool_id> | --all)  # Adapter の network 承認取り消し (相互排他 — 07 §3 の実行主体)。
                                        # <tool_id> = 当該行の revoked 化 + 同一 (scope_id, tool_id) の approval_pending の
                                        # 同一 atomic write 除去 (execution_mode / tool_profile_hash 不問 — 07 §3。
                                        # 4 組一致に限ると別 profile で作られた pending が残り、config を戻した後の
                                        # self-heal が revoke 直後の承認を復活させる)。
                                        # --all = 当該 scope の全 Adapter 行を revoked 化 + **tool を問わず存在する
                                        # 全ての approval_pending を除去** (boolean は変えない — scope 全体の
                                        # kill switch は allow_network=false 側)。対象なし (行なし・pending なし・
                                        # 既 revoked) は対象なしの冪等成功 — exit 0 + 「対象なし」表示。
                                        # pending 除去または行 revoked 化を実行した場合、`approvals_initialized`
                                        # marker 不在なら同一 atomic write で true 化 (初回 materialize 例外の
                                        # 消費 — 07 §3。対象なしの冪等成功では書かない)。
                                        # `.kio/.lock` 取得 (05-runtime.md §6) の locked mutation
kio batch abandon <intent_token|scope/adapter/input_hash/tool_profile_hash>
                                        # 照合が恒久不能な in-flight Batch job の打ち切り (estimated 記帳 + terminal 化。
                                        # 指定子は intent_token または batch_requests の 4 組タスクキー (3 組では別
                                        # profile 行と曖昧 — 曖昧時は拒否して token を要求)。tasks.jsonl の task_id は
                                        # 喪失許容のため使わない。kio status が stalled 行の token を表示。
                                        # 確認プロンプト必須。残骸掃除完了まで intent_token は保持 — 04-pipeline.md §5.8。
                                        # 対象行が無い場合 (terminal 確定済み・device 行の剪定後を含む) は
                                        # 対象なしの冪等成功 — exit 0 + 「対象なし」表示 (04 §5.4))
kio repair (--rebuild-db [--online|--offline] | --verify-objects [--prune-orphans] | --registry-prune)
                                        # SQLite 再構築 / CAS 整合性検証 (10-operations.md §7.5)。操作は exactly-one (省略は usage error)。
                                        # --registry-prune = 恒久到達不能な registry stale 行の確認付き退役 (10-operations.md §3)
                                        # --rebuild-db は rebuild 後に enrichment を駆動し得るため online/offline 上書きの対象 (07 §3・04 §5.4)。
                                        # --prune-orphans = どの manifest からも参照されない orphan prepared/image の削除
                                        # (確認プロンプト必須 — 10 §7.5.1。法務 purge の完結手段)
kio commit -m "<message>"               # = kio snapshot create -m
kio snapshot [create] [-m "<message>"]  # create 省略可。-m 省略時は自動 message ("snapshot at <UTC timestamp>")
kio snapshot create -m "<message>"      # 正規形
kio log [--at <commit>] [--since <dur>]
kio diff <a> <b>                        # raw/path 差分 + derived-only 差分 (下記の差分種別)
kio search "<query>" [options]          # 詳細 §3
kio open <pointer|chunk_hash|raw_hash>  # OS 規定アプリで原本を開く。解決規則は §1.1
kio view <pointer|path> [--at <commit>]
kio inspect <hash>                      # object を JSON で表示
kio restore <evidence|path|commit> --to <dir> [--force] # 詳細 §5
kio export <scope> --to <bundle.kioz>   # Phase 4+ (§10)
kio import <bundle.kioz> --to <dir> [--as-new-scope]  # Phase 4+ (§10)
kio tag <name> [<commit>]               # 論理名を refs/tags-v1/names.jsonl (truth) に append してから
                                        # canonical ref を作る (書込順序固定 — 03-data-model.md §2)
kio tag --delete <name>                 # canonical ref を .kio/.lock 下で atomic に除去。names.jsonl の
                                        # 行は残す (監査保全 — 「ref の無い names 行 = 正常」と整合。
                                        # 付替えは削除 → 再作成の 2 操作 — 専用 retarget は持たない)
kio gc [--dry-run|--prune-unreachable] # prune 対象は 05-runtime.md §2.6 (raw/chunk/commit は対象外)。実装は Phase 4+ (09 §3.1)
kio purge <path|--raw-hash <h>> --reason <reason> [--erase-tombstone] [--yes]  # 詳細 §6 (確認プロンプト必須 — --yes で省略)
kio reindex [--force] [--at <commit>] [--yes] [--online|--offline]  # --at = 過去 snapshot の embedding 再生成 (05-runtime.md §1)。
                                        # --force = 新 gen で再 normalize / 再 embedding (Step 3)。--force は first-instance-wins の
                                        # 明示経路で gen+1 の新 instance を作る (07-adapter-spec.md §9。もう 1 つの合法経路 =
                                        # prepared_hash 変化起因の自動 gen+1 — 03-data-model.md §2.1)。
                                        # 上書きチェーンは manifest の parent_gen (同一 raw 内) / parent_instance
                                        # (raw 跨ぎ incremental の三つ組 — full では null) で永続記録 — parent_run_id は
                                        # task cache の揮発情報 (03-data-model.md §8、09-mvp-scope.md §5.1)。--force は確認プロンプト必須 (--yes で省略可)
kio move --propose <src> <dst>          # 原本移動の提案。Agent はこちらのみ (Phase 4+、MVP 対象外)
kio move --accept <id> | --reject <id>  # 提案の承認/却下。Kio が原本を mv できる唯一の経路 (03-data-model.md §10)。書き込み境界の予約定義
kio evidence verify <pointer> [--strict]
kio evidence verify --batch <pointers.jsonl> [--strict]  # <pointer> と --batch は相互排他 (--batch は Phase 4+ — §7、08 §4.3)
kio evidence retarget <pointer> [--latest|--at <commit>]  # 設計確定後 (09-mvp-scope.md §5.2)。
                                        # --latest の既定挙動 (auto retarget / proposal) は Phase 4 着手前確定 (08 §5 残未決)
```

本表はコマンド全量の spec である。MVP での採否・実装 Step の正本は [09-mvp-scope.md §1.2 / §3.1](09-mvp-scope.md) (Phase 4+ のコマンドは行内に注記)。

**`kio diff` の差分種別**: raw / path の差分に加え、tree schema v2/v3 ([03-data-model.md §8](03-data-model.md)) が生む derived-only の変化 — `normalize_manifest_changed` (unit の failed → done 完成を含む) / `chunking_config_changed` / `chunk_set_changed` (公開 chunk 集合のみの変化) / `tool_lock_changed` (旧新 tool_lock_hash と変更 role) / `resurrection_published` (no-op 例外 (a) の publication commit — [05-runtime.md §8.1](05-runtime.md)) — を差分として表示する (`--json` も同種別を持つ)。derived-only commit を「差分なし」と表示してはならない。片側が旧版 tree (該当フィールド欠落) の場合、derived 差分は `unknown` と表示する。

`kio init` は指定フォルダ (省略時 = カレント) の `.kio` を 1 つだけ作成する (子孫には作らない)。子フォルダの `.kio` は `kio index` の探索が対象を検出した時点で必要に応じて生成される (**VCS repo root 配下には既定で生成しない**。既定導入以前の既存子 `.kio` は grandfathered として引き続き有効 — [03-data-model.md §3](03-data-model.md))。この結果、深いフォルダ木では scope 数が多くなる。`kio search` のデフォルトが全 indexed scope 横断である ([05-runtime.md §1.8](05-runtime.md)) のはこの帰結を受けた設計である。また `kio init` は生成する `.kio/config.toml` の `[chunking] unicode_version` に実装同梱の UCD 版 (現在の既定 = 17.0.0) を明示記録する ([03-data-model.md §5.3](03-data-model.md) — 省略不可・default なし。schema でも required — [10-operations.md §12.3](10-operations.md))。

`<pointer>` 引数の受理形式 (URI / inline JSON / stdin / hash 短縮形) は [08-evidence-pointer-spec.md §2.3](08-evidence-pointer-spec.md) を正本とする。

本節が CLI コマンドの **正本一覧** である。他 spec が新しいコマンド・フラグに言及する場合、本節への追加を伴う (破壊的変更扱い)。

`kio tag` の新規 `<name>` は OS 非依存の portable leaf 規則に従い、実装同梱の UCD 版で未割当の
code point を含む名前を拒否し ([03-data-model.md §2](03-data-model.md) と同一規則 —
`KIO-E-CONFIG-USAGE-001`)、Windows 予約名・禁止文字・
末尾 dot/space を拒否する。NFC 正規化 + Unicode simple case folding (locale 非依存 —
[03-data-model.md §2](03-data-model.md) と同一規則) が同じ tag は case-insensitive collision
として重複作成を拒否し、`HEAD` の case variant は予約する。canonical ref は legacy raw-name ref と
分離した `refs/tags-v1/tag-<digest64>` に保存する。
物理 ref leaf と legacy read 規則は [03-data-model.md §2](03-data-model.md) を正本とする。

## 1.1 open の原本解決

`kio open <pointer|chunk_hash|raw_hash>` は以下の順で「開く対象」を決める:

```text
1. pointer を解決して raw_hash を得る (08-evidence-pointer-spec.md §3)
1a. object URI (kio://<scope_id>/object/image/<image_hash> — 08 §2) の場合: type / hash を検証し
   (**MVP で発行・受理される object URI は type=image のみ** — 08 §2.3。他 type は
   KIO-E-CONFIG-USAGE-001 (exit 2) で拒否)、
   scope_id が文脈 store と不一致でも**自 store に該当 hash の object があればそれを解決する**
   (fork 複製由来の旧 scope_id URI — §10。hash が identity、08 §2)。自 store に無い場合のみ
   scope_id で通常解決する。image object を `~/.cache/kio/open/image/<image_hash digest64>/` へ
   read-only materialize して開く (dir キーは image_hash — **`image/` の type segment で raw 系 dir と
   分離する**。raw と image は同一バイト列で同一 digest になり得るため ([03-data-model.md §1](03-data-model.md)
   のバイト列 content hash — CAS は `objects/<type>/` が分離を担うが cache は担わない)、segment なしの
   平坦 namespace では衝突する)。**materialize の書込・照合は raw の一時展開 (下記) と同じ規約に従う** —
   private temp → no-replace publish・EEXIST は image_hash の再計算照合・不一致は同じ fail-closed
   終端 (KIO-E-STORE-CORRUPT-001 / exit 4)・拒否時 cleanup (dir key と照合キーは image_hash)。
   **barrier は journal barrier (active purge 進行中の拒否) のみ** — tombstone は raw_hash 単位の
   marker であり image には適用しない (同一バイト列の無関係 raw の tombstone に image_hash で
   照合しない)。image の purge 帰結は object の物理削除 (live 参照 0 — [05-runtime.md §3.5](05-runtime.md))
   そのものが表し、object 不在は手順 5 と同じ not_found / exit 4。purge closure には「closure で
   物理削除対象となった live 参照 0 の image」の cache dir として含まれる
   ([05-runtime.md §3.5](05-runtime.md))。以降の手順 2-5 は raw 系入力のみ
2. tombstone 判定 (最優先): raw_hash の **canonical final event が `purged`** (全 marker の正本化 —
   08-evidence-pointer-spec.md §3.1 手順 5) なら、working tree・cache の状態に
   関わらず §7 の規約どおり exit 4 — purge 済み原本が folder に残っていても Kio 経由では開かない
   (canonical が `retired` (退役) なら対象外 — 再 ingest による退役は 05-runtime.md §3.5 の resurrection 規則)
3. working tree 解決:
   現在の working tree に同一 raw_hash を持つファイルが存在すれば (path_at_commit と
   異なる path でもよい。リネーム済みケース)、その実ファイルを OS 規定アプリで開く
4. 一時展開 (working tree に存在しない = 削除済み・過去版・raw_hash 直指定):
   raw object を ~/.cache/kio/open/<raw_hash digest64>/<basename から導出した portable leaf> に
   read-only で展開し、それを OS 規定アプリで開く。basename の拡張子により OS の
   アプリ関連付けを機能させるが、元 basename 自体は物理名に使用しない
   (path_at_commit が無い場合は kind から推定した拡張子)
5. raw object が not_found → §7 の規約どおり exit 4
```

一時展開は **restore ではない**: working tree に書かず read-only であるため、[§5](06-cli-spec.md) の安全要件 (`--to` 必須 / `--force`) の対象外。**展開は同じ `<raw_hash digest64>/` 配下の private temp に書き (purge closure が temp ごと掃く)、cache path へ no-replace で publish してから、起動直前の最終検査 ([05-runtime.md §3.5](05-runtime.md) の 3 点) を行い、通過した場合のみ起動する — 検査で拒否した場合は publish 済み cache を dev/inode 対照 (自らの publish と検証) の上で除去し、temp も残さない** ([04-pipeline.md §1.1](04-pipeline.md) の temp 掃除規約)。**publish が既存 cache と衝突 (EEXIST) した場合** — MVP では cache が自動掃除されないため同一 raw の再 open で通常発生する — は [04-pipeline.md §1.1](04-pipeline.md) の no-replace 規則と同じく既存との内容一致を照合して自分の temp を破棄し、既存 cache を対象に起動直前の最終検査以降を続行する (**照合 = 既存 cache leaf の内容 sha256 が dir key の raw_hash と一致することの再計算** — 展開 leaf は raw object の byte 列そのもの。**不一致は改変・破損の残骸として KIO-E-STORE-CORRUPT-001 / exit 4 で fail-closed に終端する** (§7 の「4 = 再試行で進展しない」— 回復はユーザーの cache 削除。context に cache path と「削除後の再実行で回復」を載せる)。既存 cache には触れず自 temp も残さない。この経路の検査拒否では cache を除去しない — 除去は自らの publish と検証できた場合に限る。削除主体は purge closure と [10-operations.md §7.5.1](10-operations.md) の残骸回収)。**起動直前検査で拒否した場合の終端は拒否理由の code に従う** — tombstone 検出は手順 2 と同じ §7 規約どおり exit 4、active journal は KIO-E-PURGE-JOURNAL-ACTIVE-001 (exit 3 — 回復後に再試行可)。publish 後検査により purge 完遂後の平文 cache の**起動**を閉じる (publish と検査の間の crash による cache 残存は起動には至らず、`kio repair --verify-objects --prune-orphans` が purge 済み raw の cache 残骸として回収する — [10-operations.md §7.5.1](10-operations.md)。検査通過後の purge は並行 reader の既 open fd と同格)。展開先はキャッシュであり、GC (on_idle、Phase 4+) の掃除対象。MVP では自動掃除されないため、必要ならユーザーが削除してよい (正本は `objects/` に無傷)。**purge はこの展開 cache を削除 closure に含める** ([05-runtime.md §3.5](05-runtime.md))。永続的なコピーが必要な場合は `kio restore <pointer> --to <dir>` を使う。一時展開で開いた場合、CLI は「原本は working tree に存在しない (削除または過去版)。永続コピーは kio restore --to」の注記を stderr に表示する。

---

# 2. 初回スキャン承認 (init / index preview)

未承認 scope に対する `kio index` は、raw object 保存・Adapter 実行を始める前に **対象範囲 preview** を表示し、明示承認を要求する。

```bash
kio index --preview     # preview のみ。何も書き込まない
kio index --approve     # preview を承認、index 開始
kio index --yes         # 非対話: ローカル取り込み承認のみ自動化 (CI 用。制約は下記)
```

preview 内容:

```
- 対象 root / scope
- 推定ファイル数 / 推定容量
- 大容量ファイル一覧 (上位 N)
- 現在有効な ignore (.kioignore + config)
- 除外候補 (提案。自動除外しない)
- 機微ファイル候補の警告 (secrets Tier A: デフォルト除外済み / Tier B: 要確認。10-operations.md §1.1)
- network transmission policy (どの Adapter がオンライン送信するか)
- 別 .kio と重複する可能性のある容量 (ユーザー配置由来のみ)
- 推定 LLM コスト (markdownize / embedding 別。現行 `tools.toml` の `[pricing]` 単価による桁の目安 — [10-operations.md §1](10-operations.md))
- 現行 budget cap での推定完了時期 (cap 超過が予見される場合は承認前に警告 + 選択肢提示。[10-operations.md §1](10-operations.md))
```

**非対話環境** (`isatty=false` / CI) では、承認済み scope または `--yes`/`--approve` がない限り `kio index` は **exit 2** で失敗する。

**`--yes` の制約**: `--yes` が自動化できるのはローカル取り込みの承認のみである。

```text
1. network opt-in を付与しない。opt-in 未成立の scope では、--yes で index を
   開始しても online_api Adapter への送信 task は発行されず pending のまま残る
   (07-adapter-spec.md §3)。非対話環境で永続 opt-in が必要な場合は、事前に対話環境または
   `--approve` で**承認を成立させておく** (行 + boolean の両方 — boolean
   `allow_network = true` の手編集**単独では送信 gate を満たさない**。例外 = **初回 materialize**:
   `approvals_initialized` marker が無く approvals[] が空の初回に限り、boolean の事前設定 + 初回
   実行で最初の 1 tool のみ自動 materialize される、07-adapter-spec.md §3)。
   明示 `--online` は当該実行限りの一時 opt-in として非対話環境でも有効 (同 §3)。
2. secrets の built-in デフォルト除外 (10-operations.md §1.1 Tier A) を解除できない。
3. 承認記録の approval_method に "yes" が記録され、対話承認と事後監査で区別できる。
```

---

# 3. Search

デフォルトは全 indexed scope を対象とし、mode は実効 `[search].default_mode` (既定 auto = hybrid → text fallback — [05-runtime.md §1](05-runtime.md)) に従う。scope の列挙・結果統合・部分失敗・cursor は [05-runtime.md §1.8](05-runtime.md) の multi-scope search 契約に従う。

```bash
kio search "認証仕様"

# scope 制限
kio search "..." --scope .                  # カレントフォルダのみ
kio search "..." --scope . --descendants    # カレントとその配下
kio search "..." --scope ./Research [--descendants]
# path 引数は canonical 化 (絶対化 → lexical 解決 → 末尾 separator 除去 → realpath) して
# registry の root_path と byte 比較する (05-runtime.md §1.8)
kio search "..." --all-scopes

# モード
kio search "..."              # 実効 [search].default_mode (既定 auto = hybrid → text fallback — 05 §1.8)
kio search "..." --text       # text only
kio search "..." --vector     # vector only。失敗時は error
kio search "..." --hybrid     # hybrid 強制。失敗時は fail_behavior 設定に従う
                              # (承認なし (embedding_not_authorized)・--offline は対象外 — 常に text
                              #  fallback。embedding_in_flight は技術的失敗として対象。
                              #  正本 05-runtime.md §1.1 consent gate)
kio search "..." --no-vector
kio search "..." [--online|--offline]   # query embedding の一時 opt-in / 当該実行の新規送信禁止
                                        # (正本 07-adapter-spec.md §3・05-runtime.md §1.1 consent gate)

# time-travel
kio search "..." --at <commit> --scope <path>   # --at は --scope 単一指定を必須とする (独立 DAG の
                                                # multi-scope に単一 commit は適用不能 — 05 §1.6)
kio search "..." --all-history          # 削除済み・移動済み含む全 commit
kio search "..." --include-deleted
kio search "..." --since 7d

# paging / 結果制御
kio search "..." --limit 20 [--offset 20|--cursor <token>]
kio search "..." --json                 # 機械可読
```

レスポンス schema は [05-runtime.md §1.7](05-runtime.md)。`json` モードでは Evidence Pointer フル構造 + `next_cursor` を返す。

---

# 4. Output Format

すべての CLI は `--json` を持つ。デフォルトは人間向け整形、`--json` で機械可読。

```bash
kio <command> --json
```

人間向け表示は色付き + path 短縮形 (`~/Documents/...`)。`--json` は色なし + 絶対 path + 完全 hash。エラーも `{ "error_code": "...", "message": "...", "context": {...} }` 形式で返る。

---

# 5. Restore

過去 commit 状態の復元。**現実ファイルを直接上書きしない**:

```bash
kio restore <evidence|path|commit> --to <dir>
kio restore <commit> --to ~/Recovered/<commit>     # 通常
kio restore <pointer> --to ./recovered/ --force    # 既存上書き許可 (確認 prompt)
```

安全要件:

```
- --to <dir> は必須 (canonical 解決先が当該 scope root 配下 (`.kio` 含む) は KIO-E-CONFIG-USAGE-001
  (exit 2) で拒否 — working tree への直接書き戻し禁止の迂回を許さない。canonical 解決は
  05 §1.8 の算出規則と同一 (realpath 含む)。展開前に --to を open した fd の実体 (dev/inode) を
  canonical 解決先と対照し (不一致 = KIO-E-CONFIG-USAGE-001 で mutation 前拒否)、以後の展開は
  同一 fd 配下に限定する — 05 §4)
- 全出力 path の退避 / 隔離の同名残存は --force の有無・宛先の存否に関わらず mutation 前に検査し、
  残存 = 先行未完として拒否 + 回復案内 (正本 05 §3.5)
- 既存ファイル上書きは --force + 確認 prompt
- --force 上書きは旧ファイルを同 directory の退避名 `<basename>.kio-restore-bak` へ no-replace で
  保全 (同名残存 = 先行未完として拒否 + 回復案内。退避名は stderr に表示・dev/inode を記録) して
  から publish し、rename 後再検査の purge / erase / journal 終端時のみ原状復帰する (対象 alive の
  無関係変化は publish 維持 — 05 §3.5。成功時に退避を除去)
- publish (--force 含む)・隔離・復帰の rename は全て no-replace。巻き戻しの削除も退避の復帰・
  除去も、path 上の対照ではなく決定的隔離名 `<basename>.kio-restore-quarantine` への隔離 rename +
  rename した実体の dev/inode 検証で行う (隔離名は stderr に表示。同名残存 = 先行未完として拒否 +
  回復案内。隔離・退避はユーザー領域 — Kio は自動削除しない)
- 競合処置は段階別 (--force publish 競合 = 退避を復帰 / 隔離実体の不一致 = 元 path へ復帰を試行 /
  退避の不一致・復帰 rename 失敗 = 不触) — いずれも両所在を表示して
  KIO-E-COMMIT-RESTORE-CONFLICT-001 (retryable exit 3、context に conflict_kind・retry_disposition)
  で終端 (05 §3.5)
- 出力名・上書き対象名が `.kio-restore-bak` / `.kio-restore-quarantine` で終わる場合は展開前に
  明示拒否 (改名復元を案内)
- restore は raw object をそのまま展開 (再 Markdownize しない)
- evidence は pointer URI / inline JSON / stdin、path は論理 direct-child 名、commit は HEAD / tag / full commit hash。tag と同名の path は tag を優先する。raw_hash shorthand は restore では受理しない
- shallow commit からの restore は KIO-E-COMMIT-SHALLOW-001 で拒否
- purged 対象は KIO-E-PURGE-NOT-FOUND-001 / tombstone
```

---

# 6. Delete / Archive / Purge

通常削除 (`rm`) や archive は最新状態から対象を消すだけで、過去履歴は保持する。法務・秘匿・誤取り込みで履歴ごと消す場合のみ `purge` を使う。

```bash
kio purge <path|--raw-hash <h>> --reason <legal|privacy|misingest|copyright|other>
kio purge --raw-hash sha256:abc... --reason misingest --erase-tombstone
```

purge は常に**全履歴**の raw 本文・派生 artifact を対象とする (commit / tree object は書き換えない。[05-runtime.md §3.5](05-runtime.md))。デフォルトでは tombstone を記録し、`--erase-tombstone` は public tombstone を残さない (Evidence Pointer は not_found)。後者の non-public non-content erase receipt は public tombstone にならず re-ingest も阻止しない (pointer 解決内部の not_found 分類等の用途列挙は [08-evidence-pointer-spec.md §4.2](08-evidence-pointer-spec.md))。

- `--reason` は必須引数 (5 値の閉 enum: legal | privacy | misingest | copyright | other — [08-evidence-pointer-spec.md §4.1](08-evidence-pointer-spec.md) の purged_reason と同一)
- 確認 prompt 必須 (`--yes` でスキップ可)
  - (purge の `--yes` は確認プロンプトのスキップのみで、§2 の初回スキャン承認の `--yes` とは
    独立。network opt-in を付与する効果はどちらにもない)
- 結果 commit は `commit_type=purged`
- 詳細は [05-runtime.md §3](05-runtime.md)

> MVP の purge は raw 本文・派生 artifact の全履歴削除 + tombstone (既定) / `--erase-tombstone` (not_found) まで。tree/commit を書き換える完全な履歴書き換え (filename 秘匿ケース) は MVP 非対応で v2+ / Phase 4+ ([05-runtime.md §3.5](05-runtime.md), [09-mvp-scope.md §3.1](09-mvp-scope.md))。

---

# 7. Exit Code (横断規約)

```
0   成功 / 全 up_to_date
1   汎用 failure (詳細不明)
2   invalid usage / config 不正 / schema validation 失敗
3   retryable な失敗が残っている (部分成功を含む。lock 取得失敗のような全体 retryable もここ)
4   permanent な失敗のみが残っている (全失敗 permanent、および settled partial
    (部分成功 + 残り全 permanent — 04-pipeline.md §5.2) を含む — 再試行で進展しない)
5   auth_error (user action 必要)
6   budget_exceeded により paused
7   user 中断 (SIGINT/SIGTERM)
8   incompatible profile / format version
9   confirm 拒否 (purge 等の確認プロンプトで no)
```

**Evidence Pointer 系コマンドへの割当** ([08-evidence-pointer-spec.md §4.3](08-evidence-pointer-spec.md)):

```text
kio evidence verify            検査完了で 0 (結果は status フィールド)。parse 失敗は 2
kio evidence verify --strict   全 alive なら 0。tombstoned / not_found が 1 件でもあれば 4。
                               scope_unreachable のみの失敗は 3 (retryable — 08 §4.3)。
                               unverifiable は reason で分岐 (08 §4.3): tree_v1 / manifest_missing を
                               1 件でも含めば 4 (恒久 — 再試行で進展しない)、commit_shallow のみなら 3
                               (unshallow で解消し得る)。registry_duplicate も 3
KIO-E-STORE-CONSTRAINT-001     記帳 CHECK 到達 = 実装エラー (04 §5.8)。permanent・非再試行で
                               command を即時中止・exit 4
sqlite.db 不在・利用不能       全経路 (verify / open / view / restore / search) で status に混ぜず
                               command-level の retryable error KIO-E-INDEX-REBUILDING-001・exit 3
                               (再構築中でも旧 sqlite.db が読めるなら通常応答 — 05 §6。ただし
                               **HEAD ref 不在の scope は、HEAD 依存経路 (現在状態の search・
                               sha256: 短縮形 — 08 §2.3 規則 4) に限り、sqlite.db が読めても
                               REBUILDING 扱い** (05 §1.6 — 未公開行を検索に見せない)。**明示の
                               commit / Evidence Pointer 指定による verify / open / view / restore・
                               単一 scope の search `--at <commit>`
                               は HEAD 非依存に解決して通常応答する** (08 §3.1 の解決手順・08 §6 の
                               不変性保証)。error は不在・利用不能・HEAD 不在 (HEAD 依存経路のみ)
                               の場合のみ。verify は検査未完了のため --strict なしでも
                               0 を返さない。multi-scope search は当該 scope を excluded_scopes として
                               継続し、全 scope 該当なら exit 3 — SCOPE-ALL-FAILED (3/4) より優先。
                               全 scope の除外理由が同一 code なら当該 code の単独時 exit へ昇格
                               (一般規則 — VERSION→8・REBUILDING→3・INCOMPAT→8・
                               journal (KIO-E-PURGE-JOURNAL-ACTIVE-001)→3・
                               DUP→3 (dedupe 後に回復可能 — 08 §4.3 registry_duplicate と同一分類)。
                               05 §1.8 / 10 §12.5)。混在は SCOPE-ALL-FAILED — retryable 理由を
                               含めば exit 3・全て permanent なら exit 4 (05 §1.8)。
                               優先順位は VERSION → journal → DUP → REBUILDING (10 §3)。05 §2.6・08 §3.1)
kio evidence verify --batch <pointers.jsonl>   一括 verify (Phase 4+ — 08 §4.3)
                               (--batch は --strict の有無に従う — --strict 時: 混在も 4 /
                                なし: 検査完了で 0。内訳は --json の各行 status で判定 — 08 §4.3。
                                search の retryability 分割 (05 §1.8) とは別 domain の規則 —
                                pointer 単位の status 混在は retryability を見ず常に 4)
kio open / view / restore      dead pointer (tombstoned / not_found) は 4。scope_unreachable は 3 (retryable — 08 §4.3)
kio evidence retarget          対応なし / ambiguous は 4。
                               tool_profile_hash 不一致で chunk 解決不能 (retarget 要) は 8
```

スクリプト連携 (`kio index && kio search`) はこれらを参照する。コマンド固有の補足は各 sub-command の docstring で明記。

---

# 8. Error Code Namespace

すべてのエラーは `KIO-E-<DOMAIN>-<SUBDOMAIN>-<NNN>` 形式の `error_code` を持つ。`error_kind` などのフリーテキストはユーザー向け表示専用。機械判定は `error_code` (明示例外 = manifest `units[]` / Adapter 出力 `failed_units` の `error_kind` — [04-pipeline.md §5.3](04-pipeline.md) の閉 enum であり unit 単位の retry 可否判定に使う、[10-operations.md §12.1](10-operations.md))。**成功応答 (exit 0) に載る `error_code` は縮退原因の分類であり、失敗判定には使わない** — 失敗判定は exit code (非 0) が正 (例 = text fallback の [05-runtime.md §1.7](05-runtime.md) 応答契約)。

DOMAIN 一覧の正本は [10-operations.md §12.1](10-operations.md)。本節は同一リストの転記であり、差分が生じた場合は 10 側を正とする。

```
DOMAIN:
  BATCH    バッチ処理 (markdownize / embedding / etc.)
  INDEX    インデックス更新
  SEARCH   検索 (FTS / vector / hybrid)
  COMMIT   commit / snapshot / restore
  GC       garbage collection
  PURGE    purge 操作
  EVIDENCE Evidence Pointer 解決 / verify / retarget
  REGISTRY scope registry (live clone 重複・退役)
  SYNC     同期・共有 (v2 予約。MVP では発行しない)
  ADAPTER  Adapter ロード・実行
  EMBED    embedding profile / modality 検証
  CONFIG   config / schema / 設定
  STORE    object store / fs IO
  AUTH     認証・認可
```

例: `KIO-E-BATCH-NET-001`, `KIO-E-SEARCH-VEC-INCOMPAT-001`, `KIO-E-COMMIT-SHALLOW-001`, `KIO-E-COMMIT-HISTORY-LIMIT-001` (bounded history walk の aggregate cap 超過、単独操作 exit 4 / multi-scope は既存 partial 規則、[05-runtime.md §1.6](05-runtime.md)), `KIO-E-PURGE-NOT-FOUND-001`, `KIO-E-PURGE-JOURNAL-ACTIVE-001` (未完了 purge journal / epoch 不変違反 — **読み取り系** preflight の拒否 (書き込み系は journal 回復を再開 — [05-runtime.md §3.5](05-runtime.md)、直列化は `.kio/.lock` が担う)。**restore の rename 後再検査による publish 後巻き戻し終端にも用いる** (05 §3.5)、retryable exit 3), `KIO-E-COMMIT-RESTORE-CONFLICT-001` (restore の publish / 巻き戻しの no-replace 競合・dev/inode 不一致・退避 / 隔離の同名残存 — context に閉 enum `conflict_kind`・`retry_disposition` (transient / manual_action) と両者の所在を含む、retryable exit 3、[05-runtime.md §3.5](05-runtime.md)), `KIO-E-ADAPTER-APPROVAL-CONFLICT-001` (承認 publish 直前の CAS 不一致 — 並行 revoke による pending 除去・再承認が必要、exit 5、[07-adapter-spec.md §3](07-adapter-spec.md)), `KIO-E-ADAPTER-SPECVER-001` (Adapter spec_version 不一致 — invalid_input / 非再試行、[07-adapter-spec.md §8.1](07-adapter-spec.md)), `KIO-E-STORE-PATH-001` (パス区切りを含む path の schema violation、[03-data-model.md §3](03-data-model.md)), `KIO-E-SEARCH-SCOPE-ALL-FAILED-001` (multi-scope search の全 scope 失敗、[05-runtime.md §1.8](05-runtime.md)), `KIO-E-SEARCH-CURSOR-001` (別クエリ・別条件の cursor 誤用、[05-runtime.md §1.5](05-runtime.md)), `KIO-E-INDEX-REBUILDING-001` (index 再構築中、[05-runtime.md §6](05-runtime.md)), `KIO-E-EVIDENCE-SCOPE-UNREACHABLE-001` (pointer の scope が scope_path・registry のどちらでも解決不能、[08-evidence-pointer-spec.md §3.2](08-evidence-pointer-spec.md)), `KIO-E-EVIDENCE-RETARGET-AMBIG-001` (retarget 候補が複数で一意に定まらない、[08-evidence-pointer-spec.md §5](08-evidence-pointer-spec.md))、`KIO-E-REGISTRY-DUP-001` (同一 scope_id の複数 live clone — 検索 skip・解決 error、[10-operations.md §3](10-operations.md))、`KIO-E-STORE-CORRUPT-001` (CAS object の content hash 不一致・欠落、`kio repair --verify-objects`、[10-operations.md §7.5](10-operations.md))、`KIO-E-STORE-LOCKED-001` (`.kio/.lock` 取得失敗 — 待機せず即失敗、exit 3、[05-runtime.md §6](05-runtime.md))、`KIO-E-STORE-DUP-001` (単一 tree 内の重複 `path`、[03-data-model.md §8.1](03-data-model.md)。`/` 入り path の `KIO-E-STORE-PATH-001` とは区別する)、`KIO-E-CONFIG-USAGE-001` (invalid usage / 不正オペランド — 例: `init` path 不存在、`.kio` scope 外での実行、不正 hash 引数。schema violation の `KIO-E-CONFIG-SCHEMA-001` とは区別。exit 2)、`KIO-E-EMBED-MODALITY-001` (`modality != "multimodal"` の embedding profile の採用拒否 — tool-lock materialize / adapter 登録時に検証、[03-data-model.md §7](03-data-model.md)。exit 2)、`KIO-E-SEARCH-VEC-UNAUTHORIZED-001` (query embedding の embedding 承認なし — auto/`--hybrid` は text fallback、`--vector` 明示時のみ error、[05-runtime.md §1.1](05-runtime.md))、`KIO-E-STORE-VERSION-001` (自己の対応上限より新しい `kio_format_version` の store — 書き込み系は即時拒否・読み取り系は書込ゼロの read-only 縮退、正本 [10-operations.md §12.5](10-operations.md)。exit 8)。

新規 code 追加は本書および各 spec の更新を伴う (破壊的変更扱い)。

---

# 9. Agent / Adapter API

CLI と同等の操作を、AI Agent と Adapter が共通利用する **構造化 API** として提供する。CLI は同一 API のフロントエンド。

**Phase 境界**: Agent 向けの構造化 API の提供は Phase 5 ([09-mvp-scope.md §2](09-mvp-scope.md))。MVP (Phase 1-3) における外部 Agent の導線は **CLI + `--json` (§4) のみ** であり、Agent はシェル経由で `kio search --json` / `kio evidence verify` 等を実行する。`kio evidence verify` も MVP の互換性契約に含まれる。Phase 5 の構造化 API は以下を **互換性契約** として維持しなければならない:

- 検索レスポンス schema ([05-runtime.md §1.7](05-runtime.md))
- Evidence Pointer schema と正規シリアライズ ([08-evidence-pointer-spec.md §2](08-evidence-pointer-spec.md))
- exit code / error_code 規約 (§7, §8)

MCP server 等の Agent 統合導線は Phase 5 の検討論点であり、MVP では設計しない。Adapter API (task descriptor / artifact descriptor) は Step 2 から必要となる別契約で、[07-adapter-spec.md](07-adapter-spec.md) を正本とする。

```
Kio API が保証するもの:
  - 入力 object hash を明示
  - 処理対象 scope を明示
  - execution_mode (online_api | offline_api | deterministic_library) を明示
  - ネットワーク送信の許可状態を明示
  - 出力 artifact hash を記録
  - tool_profile_hash / agent_profile_hash を記録
  - 検索時は searched_scopes / excluded_scopes / fallback_reason を返す
    (fallback_reason は自由語彙 — 閉 enum にしない。機械判定は error_code 側が正であり、
     Agent は未知の fallback_reason 値を無視してよい)
```

URL、認証情報、コマンドパス、ライブラリ選択などの実行設定は **device-local config** に置き、`.kio/` には保存しない。

```
Kio core
  → task descriptor
  → device-local Adapter
  → online API / offline API / deterministic library
  → artifact descriptor
  → Kio core
```

Adapter 種別と契約は [07-adapter-spec.md](07-adapter-spec.md)。

---

# 10. Export / Import

> 実装は Phase 4+ ([09-mvp-scope.md §3.1](09-mvp-scope.md))。MVP のバックアップは lock 未取得確認 + ディレクトリコピーで代替する ([10-operations.md §7.5](10-operations.md))。

```bash
kio export <scope> --to <bundle.kioz>
kio import <bundle.kioz> --to <dir> [--as-new-scope]  # bundle の scope_id が registry に live 登録済みなら拒否
                                        # (KIO-E-REGISTRY-DUP-001 — clone 併存を正規操作で作らない)。
                                        # 複製として取り込むには --as-new-scope で新 scope_id を採番
                                        # (fork 相当。以後の Evidence Pointer は新 ID を指す。既存 normalized 内の
                                        # kio:// URI が旧 scope_id を含んでいても、自 store に該当 object があれば
                                        # 解決する — hash が identity (08 §2、解決手順は §1.1 1a)。bundle 内 object で自足)。
                                        # fork は旧 scope の approvals[]・初回スキャン承認 (scan_approval)・
                                        # adapter.policy.allow_network を引き継がない — 新 scope_id で preview +
                                        # 取り込み承認と network opt-in を再実施する (安全側。07 §3・10 §1)。
                                        # import の atomic postcondition: 展開時に scope.json を新 scope_id で
                                        # 再生成し approvals[]/scan_approval/approvals_initialized/approval_pending を除去、config の allow_network を
                                        # false へ reset、旧 root_path を除去 (pending intent を新 scope_id へ
                                        # 再束縛してはならない — 07 §3)。**展開・sanitize は private
                                        # directory 内で scope.json / config.toml とも完結させてから
                                        # 04 §1.1 の primitive で atomic に publish する** (scope.json
                                        # だけ新・config だけ旧 (allow_network=true 残存) の中間状態を
                                        # 外部に見せない — 初回 materialize の誤発火防止) (bundle 内の旧値を残したまま外側の
                                        # ID だけ変えない)。送信 gate と fsck/schema は approval 行の scope_id が
                                        # scope.json の scope_id と一致することを検査する (07 §3・10 §12.3)。
                                        # bundle 内の legacy 表現 (旧 Unix raw-name tag ref 等、対象 OS で物理
                                        # leaf を作れないもの) は import 展開時に検証付きで canonical 表現
                                        # (hashed ref + names 行) へ正規化する (in-place rewrite 禁止の例外は
                                        # import 展開のみ — 03 §2)。
                                        # .kio/logs/ は継承しない (空で開始 — 旧 scope_id の行は新 scope の
                                        # purge selector (10 §7) から恒久に漏れる。運用記録は喪失許容)。
                                        # 旧 scope の in-flight (device-global batch_requests の旧 scope_id 行)
                                        # は fork と無関係に元 scope の回復に属する — fork は何も引き継がない
```

`.kioz` は `.kio/` **全体**の bundle 形式 (zip 等 — objects/・refs/ (tags-v1/names.jsonl を含む)・chunks.jsonl 等の truth 一式)。`.kio` 単位で可搬。別 `.kio` の object 参照を前提にしないため、同一 raw_hash が別 `.kio` に存在しても export 単位では重複を許容する。**bundle には scope.json の approvals[]・logs/ の運用記録・登録 path 等の機微 metadata が含まれる** — 共有は同一信頼境界内 (自分の別端末・バックアップ) を想定し、第三者公開用の sanitize (承認・log・path の除去) は Phase 4+ の export mode で扱う。

---

# 11. Settings / Schema

すべての設定ファイルは JSON Schema (TOML は JSON 等価表現) で validate。CLI 起動時に schema-driven validation を行う:

```
~/.config/kio/tools.toml          tools.schema.json
~/.config/kio/config.toml         user-config.schema.json
.kio/config.toml                  folder-config.schema.json
.kio/scope.json                   scope.schema.json
.kio/tool-lock.json               tool-lock.schema.json
.kio/manifest.json                manifest.schema.json
```

`tools.schema.json` の認証情報フィールド (`auth`) の形式は [07-adapter-spec.md §1](07-adapter-spec.md) に従う (`keychain:` / `env:` / `plain:` prefix)。

validation 失敗は **exit 2** + `KIO-E-CONFIG-SCHEMA-001`。schema は semver で版管理し、breaking change は migration を要求。

---

# 12. 時刻 / TZ

すべての永続データ (commit timestamps / normalization_runs / access_events / snapshot lineage) は **UTC ISO8601 拡張形式 + suffix `Z`** に固定 (例外 = cost-ledger.sqlite の内部時刻列は UTC epoch ミリ秒 INTEGER — 正本 [10-operations.md §12.4](10-operations.md)):

```
正:   2026-04-25T12:00:00Z
正:   2026-04-25T12:00:00.123456Z
誤:   2026-04-25T12:00:00         (TZ 欠落)
誤:   2026-04-25T12:00:00+09:00   (local 表記)
```

ユーザー向け UI 表示時のみ local TZ に変換する。Lamport/HLC は v0 で採用しない。

---

# 13. Observability

`logs/access.jsonl` 以外に、以下の構造化ログを `~/.local/share/kio/logs/` に出力
(scope-local の `.kio/logs/access.jsonl` 自体も日次 rotation + 保持 config の対象 —
[10-operations.md §12.6](10-operations.md)):

```
events.jsonl       重要イベント (commit, gc, purge, schema migration)
metrics.jsonl      数値メトリクス (デフォルト 1h 間隔)
errors.jsonl       error_code 付きの全エラー
```

各行 JSON 必須フィールド: `ts, level, code, component, message, context`。日次ローテーション、保持 30 日 (config 上書き可 — 正規 key = `[observability] retention_days`、10-operations.md §12.3)。

`redact_logs` のデフォルトは true (ログ全域。正本は [10-operations.md §12.6](10-operations.md))。true 時は `context` の `query`, `path`, `prompt` 等の機微フィールドをマスク。

---

# 14. GUI 用語翻訳マッピング (Phase 4+)

MVP では CLI のみ提供。将来 GUI を作る際の用語置換テーブル:

| CLI / internal | GUI 表示 |
| --- | --- |
| commit / snapshot | 版を保存 |
| checkout | 表示する版を切り替える |
| restore | 以前の版を復元 |
| branch | 修正提案 / 変更案 |
| merge | 反映 |
| conflict | 最新版と重なる編集 |
| gc | 不要な内部データを整理 |
| purge | このファイルの本文を全履歴から物理削除 (削除した事実は記録に残る) |

GUI は MVP の責務ではないため、用語翻訳は GUI 実装フェーズで再評価する (今書いた表は出発点に過ぎない)。
