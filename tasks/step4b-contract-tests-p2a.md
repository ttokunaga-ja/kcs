# Step4b 契約テスト仕様書: open cache / restore / purge 挙動 (P2-A)

> 本書は **実装より先にテストを固定する** ための契約仕様。Rust 実装コードは含まない。
> 正本は `docs/05-runtime.md` **§3 (Purge の機構) / §4 (Restore / Time-travel)**、
> `docs/06-cli-spec.md` **§1.1 (open の原本解決) / §5 (Restore) / §6 (Delete / Archive / Purge)**、
> `docs/02-philosophy.md` **§2.4 (履歴改変) / §6.1 (原本ファイルは証拠として扱う)** — 期待値はこれら
> (および直接引用する隣接節) の規範文からのみ導く。系譜は `tasks/step4b-contract-tests-{ledger,lifecycle}.md`
> (Phase 1) の ID 体系・優先度規約・「未定義/曖昧の切り出し」方針。記法は本タスクの共通指示書
> (`step4b-contract-instructions.md`) が定める `### PA<連番> ... - 正本 / 前提 / 操作 / 期待` 形式。

**担当グループ**: P2-A (open cache / restore / purge 挙動)。

**対象 U 項目 (`tasks/step4b-spec-gap.md`)**: C 領域 **U22, U23, U24**、D 領域 **U25, U26, U27**、
E 領域の残り **U28, U29, U30, U31, U32, U33, U34, U37, U38**（**U35, U36 は Phase 1 で実装済みのため
再契約しない — 参照のみ**）。加えて Phase 1 からの引き継ぎ 2 件:
**LC46 の継続 (purge closure 完全化 — journal closure を prepared 相で確定し resume 時再利用)** と
**restore の canonical dispatch 分岐 ii〜iv**（open/view には Phase 1 で配線済みだが restore には
未配線 — 詳細は §N・§O）。

**対象外 (他グループ・他 Phase — 混同注意)**:

- events[] lifecycle スキーマ自体 (kind enum・遷移文法・legacy 変換・canonical final event 算出関数
  `kio_core::purge::canonical_final_event`・epoch/lifecycle-epoch カウンタ・§I 読取 barrier の
  2 点/3 点検査機構) — Phase 1 (`tasks/step4b-contract-tests-lifecycle.md` LC1-57) で契約済み・実装済み。
  本書は **これらを所与として使う側**（restore への配線状況・purge closure の内容）のみを契約する。
- cost-ledger.sqlite / Online Batch 2 相プロトコルの内部規則 (状態機械・冪等記帳・outcome enum 等) —
  Phase 1 (`tasks/step4b-contract-tests-ledger.md` CL1-71) で契約済み・実装済み。§L (U37) は
  この機構を**呼び出す境界**のみを扱い、内部規則を再契約しない。
- fsck 拡大 / `--prune-orphans` の fsck 側検証ロジック・registry-prune (F 領域, U39-U47) — 別グループ。
- canonical final event 4 分岐の**一般アルゴリズム自体** (LC8-14) — Phase 1 で契約済み。本書が契約する
  「restore の分岐 ii〜iv」は、この既存アルゴリズムへの **配線** (未配線という実装ギャップ) のみを扱う。
- 検索 gate / cursor / 時点条件 / multi-scope (H 領域) — 別グループ。
- A 領域 (cost-ledger 全体) の残り (U1-U4, U11, U12)、B 領域の残り (U20, U21) — 対象外 (別 Phase/領域)。

## 実装対象ファイルの見込み (現状把握の記録 — 実装方針を指図するものではない)

- `crates/kio-cli/src/main.rs` — `parse_object_uri` (7281-7315, `VALID_TYPES` 5 型)・`resolve_object_uri`
  (7319-)・`open_cas_byte_object`/`open_raw_object` (6460-6539)・`open_cache_path` (6632-6637, 型分離
  なしの平坦 namespace)・`write_open_cache_atomic` (6645-)・`resolve_scope_target` (6413-6437, self-store
  fallback 無し)・`enforce_canonical_marker_barrier` (7055-7086, open/view 用のフル分岐)・
  `resolve_pointer_for_cli` (6170-6356)
- `crates/kio-cli/src/restore.rs` — `validate_destination` (546-566, `unsafe_restore_error` =
  `KIO-E-COMMIT-RESTORE-UNSAFE-001`/exit1 のまま)・`open_destination_dir` (725-812, dev/inode 対照なし)・
  `check_purge_state` (1037-1078, 分岐 (i) のみ実装 — 関数自身の doc comment がこれを明記)・
  `publish_one`/`atomic_replace_handle` (1285-1456, no-replace でない単純 rename・bak/quarantine 皆無)
- `crates/kio-cli/src/purge.rs` — `delete_content_surfaces`/`delete_derived_surfaces`/
  `scan_derived_inventory` (487-788, `journal.closure` を一切参照せず毎回ライブ再走査)・`evict_open_cache`
  (1111-1125, 平坦 namespace)・`scrub_logs` (1127-1174, scope_id 条件なし)・`delete_target_tasks`
  (939-1030, tasks.jsonl 駆動)・`refuse_live_working_copy`/`refuse_live_working_copy_for_phase`
  (1537-1554, 1925-1943, working tree 残存を警告でなく完全拒否)
- `crates/kio-core/src/purge.rs` — `PurgeJournal`/`ClosureItem` (596-654, `object_type: "raw"` のみを
  記録する簡略実装 — struct 自身の doc comment がこれを明記)・`PurgePhase`
  (`Prepared/Tombstoned/Deleted/Committed`, Phase 1 で確定済み — 参照のみ)

---

## 0. ID 体系と優先度

| 接頭辞範囲 | 対象契約領域 | 対応 U 項目 |
| --- | --- | --- |
| PA01-PA07 (§A) | `kio open` 手順全面改訂 (object URI type 限定・tombstone 最優先判定) | U22 |
| PA08-PA10 (§B) | raw/image 一時展開の耐久 publish + 起動直前 3 点検査 | U23 |
| PA11-PA15 (§C) | open cache の purge/prune-orphans 時冪等削除 | U24 |
| PA16-PA19 (§D) | restore 宛先の安全検査 (scope root 拒否 + dirfd containment) | U25 |
| PA20-PA26 (§E) | restore の退避・隔離・no-replace publish protocol | U26 |
| PA27-PA29 (§F) | restore 競合のエラー分類統一 | U27 |
| PA30-PA32 (§G) | purge CLI 構文・保証範囲反転・削除対象拡大 (圧縮) | U28, U29, U30 |
| PA33-PA34 (§H) | SQLite / chunks.jsonl の purge 範囲の具体化 | U31 |
| PA35 (§I) | staging の purge 範囲拡大と帰属列挙方式 | U32 |
| PA36 (§J) | purge のログ scrub 範囲を scope_id 単位に限定 | U33 |
| PA37-PA39 (§K) | working tree 残存原本の警告義務化 | U34 |
| PA40-PA41 (§L) | purge 時の in-flight 外部実行タスクとの整合 | U37 |
| PA42 (§M) | 二重 purge (再 purge) の挙動確定 — Phase 1 で充足済み、参照のみ | U38 |
| PA43-PA46 (§N) | purge closure 完全化 (LC46 継続) | Phase 1 引き継ぎ |
| PA47-PA50 (§O) | restore canonical dispatch の分岐 ii〜iv | Phase 1 引き継ぎ |

**優先度**: **P0** = このロットの完了条件 (安全性・監査可能性・自動化契約 (exit code) に直結)。
**P1** = 推奨 (堅牢性・hygiene・観測性)。**P2** = 参考 (稀な edge・表示文言)。
P0/P1/P2 集計は末尾 §Q。

---

## A. `kio open` 手順全面改訂 (U22)

> 正本: 06 §1.1 L111-148 (「`kio open <pointer|chunk_hash|raw_hash>` は以下の順で『開く対象』を決める」)、
> 08 §2.3 L107-117 (object URI の受理規則)。

### PA01 object URI の type 限定 (MVP は image のみ受理、他型は拒否) [P0]
- 正本: 06 §1.1 L117-119『object URI (`kio://<scope_id>/object/image/<image_hash>` — 08 §2) の場合:
  type / hash を検証し (**MVP で発行・受理される object URI は type=image のみ** — 08 §2.3。他 type は
  KIO-E-CONFIG-USAGE-001 (exit 2) で拒否)』/ 08 §2.3 L110-113『受理側も image 以外は拒否』
- 前提: `kio://<scope_id>/object/<type>/<hash>` 形式の URI を `kio open`/`kio view` に渡す。`<type>` は
  (a) `raw`、(b) `chunk`、(c) `prepared`、(d) `normalized`、(e) `image` の 5 通り (いずれも `<hash>` は
  対応する型の object として実在する)。
- 操作: 各 type で `kio open <uri>` を実行する。
- 期待: (a)(b)(c) は `KIO-E-CONFIG-USAGE-001` (exit 2) で拒否される。(d) も同エラーで拒否される
  (既に成立 — 後述の不整合ノート参照)。(e) のみ正常に解決される。
  **現行実装との既知の不整合**: `parse_object_uri` (main.rs:7299 `VALID_TYPES`) は
  `["raw", "image", "chunk", "normalized", "prepared"]` の 5 型を **parse 段階で無条件に受理**する。
  後続の `resolve_object_uri` (main.rs:7350-7359) の dispatch は `"raw"`/`"image"`/`"prepared"` を
  実際に解決し、`"normalized"` のみが `other` 分岐で `KioError::invalid_usage` (= `KIO-E-CONFIG-USAGE-001`)
  に落ちる (これは新規則と偶然一致)。したがって (a) raw と (c) prepared は現状**誤って解決される**
  (新規則に反する) — (b) chunk も同様に line 7326-7341 の専用早期 return で解決されてしまう。

### PA02 image URI の scope_id 不一致時の自 store fallback (fork 複製由来) [P1]
- 正本: 06 §1.1 L120-122『scope_id が文脈 store と不一致でも**自 store に同一 hash の object があれば
  それを解決する** (fork 複製由来の旧 scope_id URI — §10。hash が identity、08 §2)。自 store に無い
  場合のみ scope_id で通常解決する。』/ 08 §2.3 L115-117『fork 複製 (`kio import --as-new-scope`) 内の
  旧 scope_id を含む object URI は、文脈 store に該当 hash の object があれば自 store で解決する』
- 前提: 現在の scope (scope_id=`S2`) が `kio import --as-new-scope` で別 scope (scope_id=`S1`) から
  複製されており、image object `<image_hash>` を両 store が共有する。ユーザーが `S1` を scope_id に
  持つ古い URI `kio://S1/object/image/<image_hash>` を現在の scope (`S2` がカレント) で `kio open` する。
- 操作: `kio open kio://S1/object/image/<image_hash>` を `S2` の scope 内で実行する。
- 期待: `S1` が registry にも scope_path hint にも存在しない (未到達) 場合でも、カレント store (`S2`)
  に同一 `image_hash` の object が存在すれば、それを解決して成功する — `scope_unreachable` エラーに
  ならない。**現行実装との既知の不整合**: `resolve_object_uri` (main.rs:7321) は
  `resolve_scope_target(&object.scope_id, None)` を無条件に呼ぶのみで、`resolve_scope_target`
  (main.rs:6413-6437) の 3 段階 fallback (hint 一致 / registry 一致 / CWD 一致) は**いずれも
  `target.scope_id == scope_id` の一致を要求**しており、「一致しなければ自 store で hash 直接照合」
  という経路が存在しない。`S1` が到達不能なら `scope_unreachable_error` で終端し、自 store fallback は
  発生しない。

### PA03 image cache の型分離 (`image/` segment で raw 系 dir と分離) [P0]
- 正本: 06 §1.1 L122-125『image object を `~/.cache/kio/open/image/<image_hash digest64>/` へ
  read-only materialize して開く (dir キーは image_hash — **`image/` の type segment で raw 系 dir と
  分離する**。raw と image は同一バイト列で同一 digest になり得るため...segment なしの平坦 namespace
  では衝突する)』/ 05 §3.5 L707-709 (purge closure 側の対称記述、§C で引用)
- 前提: raw object `X` (raw_hash=`sha256:h`) と image object `Y` (image_hash=`sha256:h`、**同一 digest**
  — 同一バイト列の画像ファイルが raw としても image としても取り込まれたケース) が同一 store に存在する。
- 操作: `kio open <raw の pointer/hash>` と `kio open kio://<scope>/object/image/sha256:h` を順に実行する。
- 期待: 2 つの展開先は異なる directory (`~/.cache/kio/open/<h>/...` と
  `~/.cache/kio/open/image/<h>/...`) に分離される — 一方の展開が他方の cache ファイルを上書き・混同
  しない。**現行実装との既知の不整合**: `open_cache_path` (main.rs:6632-6637) は
  `cache_home().join("kio/open").join(hash...)` という**型 segment のない平坦 namespace**を raw・
  prepared・image 全てに共通で使う (`open_cas_byte_object` の `subdir` 引数はどの CAS ディレクトリから
  読むかを決めるだけで、cache path 計算には反映されない)。同一 digest の raw と image は同じ
  `<h>/` directory を共有し、type 分離が成立しない。

### PA04 tombstone 判定 (手順2) は working tree/cache の状態に関わらず最優先で独立に適用される [P0]
- 正本: 06 §1.1 L135-138『2. tombstone 判定 (最優先): raw_hash の **canonical final event が
  `purged`**...working tree・cache の状態に**関わらず** §7 の規約どおり exit 4 — purge 済み原本が
  folder に残っていても Kio 経由では開かない』
- 前提: raw_hash `X` の canonical final event が `purged`。working tree に `X` と同一 raw_hash の
  ファイルが実在し、かつ `~/.cache/kio/open/<X digest64>/` に過去の展開 cache も残存している。
- 操作: `kio open` に `X` を指す pointer/raw_hash を渡す。
- 期待: 手順 3 (working tree 解決) や手順 4 (cache 再利用) が先に試みられて成功することはなく、
  手順 2 の tombstone 判定で exit 4 (`KIO-E-PURGE-TOMBSTONED-001`, `status:"tombstoned"`) が優先して
  返る。これは `resolve_pointer_for_cli` が `enforce_canonical_marker_barrier` を `open_raw_object`
  呼び出し**前**に評価する現行の実装 (main.rs:6268-6274) で既に成立している (Phase 1 が配線した
  LC8-14 canonical dispatch の消費側としての確認 — 本契約は「参照」ではなく「open コマンドとしての
  最終挙動」を固定する回帰防止契約)。

### PA05 image object への barrier は journal barrier のみ、tombstone は不適用 [P1]
- 正本: 06 §1.1 L129-131『**barrier は journal barrier (active purge 進行中の拒否) のみ** —
  tombstone は raw_hash 単位の marker であり image には適用しない (同一バイト列の無関係 raw の
  tombstone に image_hash で照合しない)』
- 前提: image object `Y` (image_hash=`sha256:h`) が purge されていない状態で、**別の**無関係な
  raw object の raw_hash が偶然同じ `sha256:h` であり、その raw の方は tombstone 済み (canonical
  final event = `purged`) である。
- 操作: `kio open kio://<scope>/object/image/sha256:h` を実行する。
- 期待: image の解決は成功する (raw 側の tombstone は image_hash 照合に一切影響しない)。同時に、
  当該 scope で active な purge journal (どの raw_hash が対象かを問わない — journal 存在自体) が
  ある場合のみ、image 解決は `KIO-E-PURGE-NOT-FOUND-001` で一時的に拒否される。**現行実装の確認**:
  `resolve_object_uri` の非-raw 分岐 (main.rs:7369-7385, 7394-7397) は `PurgeState::read_journal()`
  の `phase.is_barrier_visible()` のみを見ており、`enforce_canonical_marker_barrier` (tombstone 判定)
  は raw 型にのみ適用される (line 7390 `if object.object_type == "raw"`) — 新規則と一致。本契約は
  この既存の正しい挙動を回帰から守るために固定する。

### PA06 image materialize は raw の一時展開と同一の耐久 publish + EEXIST 照合規約に従う [P0]
- 正本: 06 §1.1 L126-128『materialize の書込・照合は raw の一時展開 (下記) と同じ規約に従う —
  private temp → no-replace publish・EEXIST は image_hash の再計算照合・不一致は同じ fail-closed
  終端 (KIO-E-STORE-CORRUPT-001 / exit 4)・拒否時 cleanup (dir key と照合キーは image_hash)』
- 前提: image object `Y` (image_hash=`sha256:h`) を初めて `kio open` する。展開 cache は未作成。
- 操作: `kio open kio://<scope>/object/image/sha256:h` を実行する。
- 期待: §B (PA08-PA10) が raw について定める耐久 publish (private temp → fsync → no-replace publish) と
  EEXIST 時の再照合規約が、image の materialize にも同一に適用される — 照合キーは `image_hash`
  (raw_hash ではない)。§B の各契約は raw/image 双方を対象としたパラメタ化契約として扱ってよい
  (実装が別関数に分岐していても、期待される外部挙動は同一)。

### PA07 image object 不在は手順5と同じ not_found (exit 4) [P1]
- 正本: 06 §1.1 L131-132『image の purge 帰結は object の物理削除 (live 参照 0 —
  05-runtime.md §3.5) そのものが表し、object 不在は手順 5 と同じ not_found / exit 4』
- 前提: image object `Y` (image_hash=`sha256:h`) が purge closure により物理削除済み (live 参照 0 の
  ため CAS から除去されている) だが、当該 raw_hash 系の tombstone/erase receipt は (image には
  適用されないため) 何の関係もない。
- 操作: `kio open kio://<scope>/object/image/sha256:h` を実行する。
- 期待: `image_hash` 用の独自エラー種別ではなく、raw 系の手順 5 (not_found) と同じ終端
  (exit 4、`KIO-E-STORE-NOT-FOUND-001` 相当または `KIO-E-PURGE-NOT-FOUND-001` — 実装は raw の
  not_found 経路と統一されたコードを使うこと) で終端する。

---

## B. raw/image 一時展開の耐久 publish + 起動直前 3 点検査 (U23)

> 正本: 06 §1.1 L150 (一時展開の全文段落)、05 §3.5 (journal/epoch/lifecycle counter の 3 点検査は
> Phase 1 で契約済み — 本節はこれを **open コマンドの起動直前検査**として消費する側の契約)。

### PA08 cache 再利用は毎回 sha256 を再照合する (初回 materialize 限定ではない) [P0]
- 正本: 06 §1.1 L150『**publish が既存 cache と衝突 (EEXIST) した場合** — MVP では cache が自動掃除
  されないため**同一 raw の再 open で通常発生する** — は [04-pipeline.md §1.1] の no-replace 規則と
  同じく既存との内容一致を照合して自分の temp を破棄し、既存 cache を対象に起動直前の最終検査以降を
  続行する (**照合 = 既存 cache leaf の内容 sha256 が dir key の raw_hash と一致することの再計算** —
  展開 leaf は raw object の byte 列そのもの。**不一致は改変・破損の残骸として KIO-E-STORE-CORRUPT-001
  (exit 4) で fail-closed に終端する**...既存 cache には触れず自 temp も残さない)』
- 前提: raw_hash `X` を過去に一度 `kio open` しており、`~/.cache/kio/open/<X digest64>/<leaf>` が
  存在する。(a) その内容が正当 (sha256 が `X` に一致)。(b) その内容が (外部改変・旧世代の非 atomic
  書込の torn file 等により) 破損しており sha256 が一致しない。
- 操作: 同じ `X` を再度 `kio open` する。
- 期待: (a)(b) いずれの場合も、cache ファイルの存在チェックだけで即座に再利用してはならず、
  **毎回** 内容の sha256 を dir key (`X`) に対して再計算・照合する。(a) は照合成功し、そのまま
  起動直前検査 (PA09) へ進む。(b) は照合失敗により `KIO-E-STORE-CORRUPT-001` (exit 4) で
  fail-closed に終端し、既存 cache ファイルには一切触れない (削除・上書きしない — 回復はユーザーの
  cache 削除)。**現行実装との既知の不整合**: `open_cas_byte_object` (main.rs:6501-6515) は
  `if cache.is_file() { ... return Ok(Some((cache, true))); }` として、ファイルの**存在のみ**を
  条件に無条件で再利用する。コード自身のコメント (main.rs:6535-6536)
  「the M5 cache-hit path (which does NOT re-verify bytes)」がこれを明記しており、(b) のケースで
  破損内容がそのまま「正当な証拠」として返却されてしまう。

### PA09 起動直前の 3 点最終検査を経てから OS アプリを起動し、拒否時は publish 済み cache を除去する [P0]
- 正本: 06 §1.1 L150『展開は同じ `<raw_hash digest64>/` 配下の private temp に書き...cache path へ
  no-replace で publish してから、**起動直前の最終検査 ([05-runtime.md §3.5] の 3 点) を行い、通過した
  場合のみ起動する** — 検査で拒否した場合は publish 済み cache を **dev/inode 対照 (自らの publish と
  検証) の上で除去し**、temp も残さない』『起動直前検査で拒否した場合の終端は拒否理由の code に従う —
  tombstone 検出は手順 2 と同じ §7 規約どおり exit 4、active journal は
  KIO-E-PURGE-JOURNAL-ACTIVE-001 (exit 3 — 回復後に再試行可)』
- 前提: raw object `X` の cache publish (private temp → no-replace rename) が完了した直後。OS アプリの
  起動はまだ行われていない。(a) 起動直前検査時点で `X` の canonical final event が (publish 完了後に
  別プロセスの purge が割り込み) `purged` に変化している。(b) 起動直前検査時点で active な purge
  journal が (`X` を対象にせずとも) 存在する。(c) 何も変化がない (正常系)。
- 操作: 3 パターンで `kio open` の起動直前検査を観測する。
- 期待: (a) OS アプリは起動されず、publish 済み cache ファイルを **自らが直前に publish した実体との
  dev/inode 対照**の上で除去してから (対照なしの単純 unlink ではない — 第三者が cache path を
  差し替えていた場合に誤って別実体を消さないため)、exit 4 (`KIO-E-PURGE-TOMBSTONED-001`) で終端する。
  (b) 同様に cache を dev/inode 対照除去した上で `KIO-E-PURGE-JOURNAL-ACTIVE-001` (exit 3) で終端する。
  (c) 検査通過、OS アプリが起動される。**現行実装の確認事項**: `enforce_canonical_marker_barrier` +
  `ReadBarrierCheckpoint::recheck()` の 2 検査自体は Phase 1 で存在するが (main.rs:6328-6339)、
  この recheck が「cache publish 後・OS 起動**前**」というタイミングで、かつ拒否時に「publish 済み
  cache を dev/inode 対照除去」まで行っているかは、`open_raw_object` の呼び出し順序と失敗時クリーン
  アップ経路の実装時に併せて検証が必要 (現状コードは `if temporary { fs::remove_file(&path); }`
  (main.rs:6335-6336) で除去自体は行うが、dev/inode 対照を伴わない単純 `remove_file` であることに
  注意 — TOCTOU 窓で第三者が cache path を再利用していた場合に誤削除し得る)。

### PA10 一時展開は restore ではない (read-only・`--to`/`--force` 対象外) [P2]
- 正本: 06 §1.1 L150 (段落冒頭)『一時展開は **restore ではない**: working tree に書かず read-only で
  あるため、[§5](06-cli-spec.md) の安全要件 (`--to` 必須 / `--force`) の対象外』
- 前提: raw_hash `X` が working tree に存在せず (削除済み・過去版)、`kio open X` が一時展開経路を通る。
- 操作: 展開されたファイルの権限・呼び出し規約を確認する。
- 期待: 展開先ファイルは read-only (0400 相当) で作成され、`kio open` のコマンドラインに `--to` や
  `--force` は存在せず要求もされない。CLI は「原本は working tree に存在しない。永続コピーは
  `kio restore --to`」の注記を stderr に表示する (06 §1.1 末尾)。

---

## C. open cache の purge/prune-orphans 時冪等削除 (U24)

> 正本: 05 §3.5 L706-715 (purge closure が展開 cache を含む段落)、06 §1.1 L150 (「purge はこの展開
> cache を削除 closure に含める」)。

### PA11 purge closure は対象 raw_hash の展開 cache dir を冪等削除する [P1] [現状固定]
- 正本: 05 §3.5 L706『`~/.cache/kio/open/<raw_hash digest64>/` の一時展開 dir (存在すれば冪等削除 —
  [06-cli-spec.md §1.1])』
- 前提: raw_hash `X` を過去に `kio open` しており展開 cache が存在する。`X` を `kio purge` する。
- 操作: purge を実行後、cache dir の存在を確認する。
- 期待: `~/.cache/kio/open/<X digest64>/` が削除されている。cache が存在しなかった場合も purge は
  エラーにならない (冪等)。**現状確認**: `evict_open_cache` (kio-cli/purge.rs:1111-1125) は
  `cache_hashes` に対象 raw_hash 群を含め (purge.rs:710-714)、`root.join(hash.trim_start_matches(
  "sha256:"))` を `remove_tree_nofollow` で削除しており、この部分は新規則と一致する — 本契約は
  現状固定 (regression guard) として 1 本に圧縮する。

### PA12 物理削除対象の image cache dir も `image/` type segment で冪等削除される [P0]
- 正本: 05 §3.5 L707-710『**本 closure で物理削除対象となった image (live 参照 0)** の一時展開 dir
  `~/.cache/kio/open/image/<image_hash digest64>/` ([06-cli-spec.md §1.1] — **`image/` の type
  segment で raw 系 dir と分離**) も同様に冪等削除する (live 参照が残る共有 image の cache dir は
  削除しない — 当該 raw に帰属しない)』
- 前提: raw_hash `X` の purge により、image object `Y` (image_hash=`sha256:i`, live 参照 0 のため
  物理削除対象) の展開 cache が `~/.cache/kio/open/image/i/` に存在する。
- 操作: `X` を purge した後、cache dir の存在を確認する。
- 期待: `~/.cache/kio/open/image/i/` (raw 系の `~/.cache/kio/open/i/` とは別 path) が削除される。
  **現行実装との既知の不整合**: `delete_derived_surfaces` は `removable_images` (live 参照 0 と判定
  された image hash 群、purge.rs:681-685) を `cache_hashes` へ含め (purge.rs:715-716)、
  `evict_open_cache` (purge.rs:1111-1125) に渡すが、`evict_open_cache` は
  `root.join(hash.trim_start_matches("sha256:"))` という**型分離のない平坦 path**で削除を試みる
  (root = `cache_home().join("kio/open")`)。PA03 で確認した通り open 側の materialize も同じ平坦
  path (`open_cache_path`) を使うため、書込・削除の両面で `image/` segment が存在しない — 新規則の
  型分離要件を書込・削除いずれの側からも満たしていない。

### PA13 live 参照が残る共有 image の cache dir は削除しない [P1]
- 正本: 05 §3.5 L709-710『(live 参照が残る共有 image の cache dir は削除しない — 当該 raw に
  帰属しない)』
- 前提: raw_hash `X` (purge 対象) と raw_hash `Z` (purge 対象外) が同一 image object `Y`
  (image_hash=`sha256:i`) を共有しており、`Y` の live 参照は `Z` により 1 以上残る (`shared_images`
  に分類される、purge.rs:668-672)。`Y` の展開 cache `~/.cache/kio/open/image/i/` が存在する。
- 操作: `X` を purge する。
- 期待: `Y` は物理削除されず (live 参照が残るため)、その展開 cache dir も削除されない。**現状確認**:
  `cache_hashes` は `removable_images` (shared 側を除いた差集合、purge.rs:681-685) のみを含むため、
  この「共有 cache を消さない」判定ロジック自体は新規則と一致する — PA12 の型分離が修正された後も
  この除外条件はそのまま維持されるべきことを本契約で固定する。

### PA14 `kio repair --verify-objects --prune-orphans` は purge 済み raw/image の残存 cache を回収する [P1]
- 正本: 06 §1.1 L150『検査通過後の purge は並行 reader の既 open fd と同格。publish 後検査により
  purge 完遂後の平文 cache の**起動**を閉じる (publish と検査の間の crash による cache 残存は起動には
  至らず、`kio repair --verify-objects --prune-orphans` が purge 済み raw の cache 残骸として回収する
  — [10-operations.md §7.5.1])』/ 05 §3.5 L711-715 (`--prune-orphans` が orphan prepared/image の
  回収手段である旨)
- 前提: raw_hash `X` (canonical final event = `purged` または `erased`) の展開 cache が
  `~/.cache/kio/open/<X digest64>/` に残存している (publish 完了後・起動前 crash の残骸、または
  PA11/PA12 の purge closure 削除自体が中断した crash 残骸)。image についても同様のケースを用意する。
- 操作: `kio repair --verify-objects --prune-orphans` を実行する。
- 期待: raw・image 双方について、canonical final event が purged/erased の hash に対応する
  `~/.cache/kio/open/...` 残存 dir が削除される (raw 系は型分離なしの既存 path、image 系は PA12 の
  修正後は `image/` segment 付き path で照合すること)。

### PA15 `--prune-orphans` フラグは現状 `kio repair --verify-objects` に存在しない [P1]
- 正本: 06-cli-spec.md L52-57『`kio repair (--rebuild-db [...] | --verify-objects [--prune-orphans] |
  --registry-prune)`...`--prune-orphans` = どの manifest からも参照されない orphan prepared/image の
  削除 (確認プロンプト必須 — 10 §7.5.1。法務 purge の完結手段)』
- 前提: `kio repair --verify-objects --prune-orphans` を実行しようとする。
- 操作: CLI の引数パーサを検査する。
- 期待: `--prune-orphans` は `--verify-objects` のサブフラグとして受理される。**実装状態の確認**:
  `tasks/step4b-spec-gap.md` U24 の実装状態注記どおり、`--prune-orphans` フラグは crates 全体で
  grep 0 件であり (`verify_objects.rs` に同機能なし)、PA14 が要求する「purge 済み raw/image の cache
  残骸回収」を実行する CLI 経路自体が存在しない。本契約は F 領域 (fsck 拡大、別グループ) と隣接するが、
  `--prune-orphans` **の cache 回収機能**という限りで PA14 の実行可能性の前提として本書に含める。

---

## D. restore 宛先の安全検査 (U25)

> 正本: 05 §4.1 L968-1005 (Restore 安全要件全文)、06 §5 L263-292 (CLI 側の同要件)。

### PA16 `--to` の canonical 解決先が scope root 配下 (`.kio` 含む) の場合は `KIO-E-CONFIG-USAGE-001` (exit 2) で拒否する [P0]
- 正本: 05 §4.1 L971-974『working tree への直接書き戻しは禁止 (--to <dir> 必須。**--to の canonical
  解決先が当該 scope root 配下 (`.kio` 含む) の場合は KIO-E-CONFIG-USAGE-001 (exit 2) で拒否** —
  `--to .` による禁止の迂回を許さない』/ 06 §5 L266-267 (同旨、CLI 側)
- 前提: scope root が `/home/u/docs`、`.kio` が `/home/u/docs/.kio`。(a) `--to /home/u/docs` (scope
  root そのもの)。(b) `--to /home/u/docs/.kio`。(c) `--to /home/u/docs/.kio/sub`
  (`.kio` の子孫)。(d) `--to /home/u/docs/subdir` (scope root 配下だが `.kio` ではない通常の
  子ディレクトリ — これも「scope root 配下」に含まれるため拒否対象)。
- 操作: `kio restore <source> --to <各パターン>` を実行する。
- 期待: (a)(b)(c)(d) いずれも mutation 前に `KIO-E-CONFIG-USAGE-001` (exit 2) で拒否される。
  **現行実装との既知の不整合**: `validate_destination` (restore.rs:559-564) は (a)(b)(c) に相当する
  条件 (`destination == scope_root || destination == kio_dir || destination.starts_with(&kio_dir)`)
  を検出するが、`unsafe_restore_error` (restore.rs:970-977) を返す — これは
  `KIO-E-COMMIT-RESTORE-UNSAFE-001` + `ExitCode::Failure` (**exit 1**) であり、新規則の
  `KIO-E-CONFIG-USAGE-001` + `ExitCode::InvalidUsage` (**exit 2**) と一致しない。(d) (scope root
  配下だが `.kio` ではない通常ディレクトリ) は現状のチェック条件 (`starts_with(&kio_dir)` のみで
  `starts_with(&scope_root)` を見ていない) では**検出されず、素通りする** — 新規則の「scope root
  配下」全域拒否より狭い。

### PA17 canonical 解決規則は 05 §1.8 の root_path 算出規則と同一、`--to .` による迂回も拒否される [P0]
- 正本: 05 §4.1 L972-974『canonical 解決は §1.8 の canonical root_path 算出規則と同一 (絶対化 →
  lexical 解決 → 末尾 separator 除去 → realpath 含む) を --to と scope root の双方に適用する』
- 前提: カレントディレクトリが scope root (`/home/u/docs`) そのもの。
- 操作: `cd /home/u/docs && kio restore <source> --to .` を実行する。
- 期待: `--to .` は絶対化 (`/home/u/docs`) → lexical 解決 → realpath を経て scope root と同一の
  canonical path に解決され、PA16 と同じ `KIO-E-CONFIG-USAGE-001` (exit 2) で拒否される
  (相対 path・`.`・symlink 経由での迂回を許さない)。**現状確認**: `normalize_absolute` +
  `effective_destination` (restore.rs:620-646, 690-723) は絶対化・lexical 解決・realpath 相当の
  処理を行っており、この迂回防止の構造自体は存在する — エラーコード/exit のみが PA16 の対象。

### PA18 dirfd containment: `--to` の fstat を containment 判定時に取得した lstat と対照する [P1]
- 正本: 05 §4.1 L997-1002『**containment 判定と展開の同一実体束縛**: --to を O_DIRECTORY で open し、
  fstat (dev/inode) を canonical 解決先の lstat (**containment 判定時に取得した値** — 対照時の再取得は
  判定後の中間 component 差し替えで移動した実体を正当化するため用いない) と対照して同一実体を確認
  してから、以後の temp 作成・rename を全て同一 dirfd 配下に限定する...対照不一致は
  KIO-E-CONFIG-USAGE-001 (exit 2) で mutation 前に拒否する』
- 前提: `validate_destination` が `--to` を canonical 解決し、その時点の lstat (dev/inode) `L0` を
  取得する (PA16/PA17 の検査と同一パス)。その後、`--to` の中間 path component の 1 つが (TOCTOU 攻撃
  または偶発的な並行操作により) 別の実体へ差し替えられてから `open_destination_dir` が実行される。
- 操作: `kio restore <source> --to <差し替え後の path>` を実行する。
- 期待: `open_destination_dir` が O_DIRECTORY で open した実体の fstat (dev/inode) を、`L0`
  (containment 判定時に取得した値、再取得しない) と対照し、不一致を検出して
  `KIO-E-CONFIG-USAGE-001` (exit 2) で mutation 前に拒否する。**現行実装との既知の不整合**:
  `open_destination_dir` (restore.rs:725-812) は `cap_fs::open_ambient_dir` +
  `cap_fs::open_dir_nofollow` による component 単位の no-follow 再走査を行う (これ自体は TOCTOU に
  対して一定の安全性を持つ) が、`validate_destination` 側で取得した canonical 解決時の lstat 値を
  保持して `open_destination_dir` の結果と dev/inode 突き合わせる処理は見当たらない — 新規則が明示
  する「判定時に取得した値を保持し、対照時に再取得しない」という二重防御の構造そのものが確認できない。

### PA19 絶対 path・`..` を含む復元エントリの拒否 [P2] [現状固定]
- 正本: 05 §4.1 L1003-1004『絶対 path・「..」を含む復元エントリは拒否 (既存 symlink 経由で復元先の
  外部を上書きさせない)』
- 前提: restore source (evidence/commit/path のいずれか) の `path_at_commit` が (a) 絶対 path
  (`/etc/passwd` 等)、(b) `..` を含む相対 path (`../../etc/passwd`) であるような、通常は
  `kio snapshot` 側で拒否されているはずの異常な tree entry が (bypass や過去の緩い検証を経て)
  存在する。
- 操作: `kio restore <該当 source> --to <dir>` を実行する。
- 期待: (a)(b) いずれも展開前に拒否される。**現状確認**: `validate_restore_name`
  (restore.rs:529-544) は `TreeEntry::validate_materialization_path()` を再利用しており、これは
  tree entry の path 安全性検証で全社共通の既存 validator である — 本契約は新規実装を要求せず、
  この既存経路が restore でも呼ばれ続けることを回帰防止として固定する (現状固定)。

---

## E. restore の退避・隔離・no-replace publish protocol (U26)

> 正本: 05 §3.5 L830-891 (restore の barrier 検査位置・退避・隔離手順の全文)、05 §4.1 L975-1005、
> 06 §5 L271-292。**現状は grep 0 件 (`.kio-restore-bak`/`.kio-restore-quarantine` は
> `crates/kio-cli/src/restore.rs` に一切出現しない) — 本節は事実上まるごと未実装**であり、
> `atomic_replace_handle` (restore.rs:1373-1396) は単純な `cap_fs::rename` (POSIX 上、宛先を無条件に
> 置換する — no-replace ではない) で `--force` 上書きを行っている。

### PA20 予約名前空間: 出力名・上書き対象名が退避/隔離サフィックスの場合は展開前に明示拒否する [P1]
- 正本: 05 §4.1 L991-992『出力名・上書き対象名が `.kio-restore-bak` / `.kio-restore-quarantine` で
  終わる場合は展開前に明示拒否 (退避・隔離名前空間の予約 — 改名復元を案内)』
- 前提: restore source の `path_at_commit` が (a) `notes.md.kio-restore-bak`、(b)
  `notes.md.kio-restore-quarantine` のいずれかで終わる (歴史上そのようなファイル名で実際に
  snapshot された正当なケース)。
- 操作: `kio restore <該当 source> --to <dir>` を実行する。
- 期待: (a)(b) いずれも一切の展開 (temp 作成含む) を行わず、mutation 前に拒否される。エラーメッセージ
  は「予約名前空間のため、改名復元 (別名を指定した復元) を検討してください」という趣旨の案内を含む。

### PA21 退避名/隔離名の同名残存は `--force` の有無・宛先の存否に関わらず mutation 前に拒否する [P0]
- 正本: 05 §4.1 L975-977『**全出力 path について、退避 (`<basename>.kio-restore-bak`) / 隔離
  (`<basename>.kio-restore-quarantine`) の同名残存を --force の有無・宛先の存否に関わらず mutation
  前に検査し、残存 = 先行 restore の未完として拒否 + 回復案内する**』/ 05 §3.5 L852-857
  (bak/quarantine とも「--force 限定にすると先行 crash で宛先が消えた後の非 --force 再実行が stale
  退避を素通しする」ため --force 文脈に限定しない旨)
- 前提: 過去の restore 試行が crash し、`<dir>/notes.md.kio-restore-bak` が残存している。今回の
  restore は `notes.md` を同じ `<dir>` へ復元しようとするが、(a) `notes.md` は既に存在せず `--force`
  も指定しない (非 --force の新規復元)。(b) `notes.md` は存在し `--force` を指定する。
- 操作: (a)(b) いずれのパターンでも `kio restore <source> --to <dir>` を実行する。
- 期待: (a)(b) いずれも、`notes.md.kio-restore-bak` の残存を検出した時点で mutation 前に拒否される
  (「--force 限定にすると宛先消失後の非 --force 再実行が素通しする」ため、--force の有無に依存しない
  検査であることが必須)。エラーには回復手順 (内容確認の上での手動復帰または削除) を案内する。

### PA22 `--force` 上書きは旧ファイルを退避名へ no-replace で保全してから publish する [P0]
- 正本: 05 §4.1 L979-982『--force 上書きは旧ファイルを同 directory の退避名
  `<basename>.kio-restore-bak` へ no-replace で保全 (同名残存 = 先行未完として拒否 + 回復案内。
  退避名は stderr に表示・dev/inode を記録) してから publish し』
- 前提: `notes.md` が既存し、`kio restore <source> --to <dir> --force` を実行する。退避名の同名残存は
  ない (PA21 通過済み)。
- 操作: restore を実行する。
- 期待: publish (rename) の**前**に、既存の `notes.md` が同一 directory 内の `notes.md.kio-restore-bak`
  へ no-replace rename で退避される。退避完了時に退避名 (`notes.md.kio-restore-bak`) が stderr に
  表示され、退避した実体の dev/inode が (後続の巻き戻し/削除で使うため) 記録される。
  **現行実装との既知の不整合**: `publish_one` の overwrite 分岐 (restore.rs:1296-1319) は
  `atomic_replace_handle` (= 単純 `cap_fs::rename`、restore.rs:1373-1396) を直接呼び、旧ファイルの
  退避は一切行わない — 旧内容は rename 完了と同時に失われる。

### PA23 publish の rename は no-replace 相当で行い、競合検出時は無変更で失敗する [P0]
- 正本: 05 §3.5 L843-846『**publish の rename は非 --force・--force とも no-replace 相当
  (RENAME_NOREPLACE 等) で行い、競合検出時は無変更で失敗する** (非 --force = preflight の不存在
  判定後に現れた第三者ファイルを無断置換しない。--force = 下記の退避が destination を空けた直後に
  現れた第三者ファイルを置換しない — この競合時は退避を元 path へ復帰...して終端する。意図的置換は
  退避 rename だけが担う)』
- 前提: (a) 非 --force 復元で、preflight 時点では宛先が存在しなかったが、publish 直前に第三者
  プロセスが同名ファイルを作成した。(b) --force 復元で、PA22 の退避により destination が空いた
  直後、publish 直前に第三者プロセスが同名ファイルを作成した。
- 操作: (a)(b) いずれのケースでも restore の publish 段階を実行する。
- 期待: (a) publish の rename は RENAME_NOREPLACE 相当で失敗し、第三者ファイルは無変更のまま、
  `KIO-E-COMMIT-RESTORE-CONFLICT-001` (retryable exit 3、`conflict_kind=publish_race`) で終端する。
  (b) 同様に publish rename が第三者ファイルを検出して失敗し、**PA22 で退避した旧ファイルを元 path
  へ復帰**してから (意図的な置換は退避 rename のみが行う、という原則により) 同じ conflict エラーで
  終端する。**現状確認**: 非-overwrite 分岐 (restore.rs:1320-1360) は `cap_fs::hard_link` +
  `AlreadyExists` 検出で (a) 相当の no-replace 的挙動を部分的に持つが、(b) の overwrite 分岐は
  PA22 のとおり退避自体が存在しないため、この巻き戻しも成立しない。

### PA24 publish (rename) 完了後に journal/epoch/lifecycle counter の 3 点を再検査し、purge 完遂検出時は巻き戻す [P0]
- 正本: 05 §3.5 L859-864『**restore はさらに rename 完了後に同 3 点を再検査し**、変化を検出したら
  対象 raw の canonical 状態 (08 §3.1 手順 5) を再解決する — 対象が alive のまま (無関係な lifecycle
  変化) なら publish を維持して成功。対象 raw を closure に含む active journal を検出した場合は
  下記と同様に巻き戻して KIO-E-PURGE-JOURNAL-ACTIVE-001 (retryable exit 3) で終端する...対象の
  purge が完遂していた場合は巻き戻す』
- 前提: restore の publish (rename) が完了した直後 (ファイルは既に `<dir>/notes.md` として存在する)。
  この rename の**間**に、対象 raw_hash の `kio purge` が完了していた (canonical final event が
  `purged` に変化)。
- 操作: restore を実行し、publish 完了後の再検査を観測する。
- 期待: publish 完了後に (§I の checkpoint 2 とは別の) 対象 raw_hash 固有の再解決が走り、対象が
  `purged` (完遂) であることを検出して**巻き戻し** (PA25 参照) に入る。**現行実装との既知の不整合**:
  `publish_all` (restore.rs:1204-1283) は各ファイルの `publish_one` 呼び出しの**前**に
  `check_purge_state(...).and_then(|()| checkpoint.recheck())` (restore.rs:1217-1218) を実行するのみで、
  `publish_one` 成功後 (rename 完了後) に同種の再検査を行う経路が存在しない — 「publish 前検査」しか
  なく「publish 後再検査 + 巻き戻し」という新規則の要求する 2 段階検査になっていない。

### PA25 巻き戻しは publish 済みファイルを隔離名へ no-replace rename し、rename した実体を dev/inode 対照検証する [P0]
- 正本: 05 §3.5 L864-871『publish 済みファイルは **unlink せず**、同一 directory 内の決定的隔離名
  `<basename>.kio-restore-quarantine` への no-replace rename で隔離し (隔離名は stderr に表示)、
  **rename した実体を fstat の dev/inode 対照で自らの publish と検証する** (対照→削除の 2 操作では
  対照後の置換窓が残るため、rename した実体の上で検証する。一致 = 隔離分を削除...不一致 = 第三者
  ファイル — 元 path へ no-replace rename で復帰を試み、成功・失敗いずれも競合終端)』
- 前提: PA24 の巻き戻しが発動する。publish 済みファイルの dev/inode (`P0`、publish 完了直後に記録
  済みと仮定) が既知。(a) 隔離 rename 後、rename した実体の dev/inode が `P0` と一致する
  (正常系 — publish 後・隔離前の窓に第三者置換が無かった)。(b) 隔離 rename 後、rename した実体の
  dev/inode が `P0` と**不一致** (publish 完了〜隔離 rename の間に第三者が同 path を差し替えていた)。
- 操作: (a)(b) それぞれで巻き戻しの隔離 rename を実行する。
- 期待: (a) 隔離名 (`notes.md.kio-restore-quarantine`) が stderr に表示され、隔離された実体の削除
  (pathname に対する `unlink`) を行い、`KIO-E-PURGE-JOURNAL-ACTIVE-001` または
  `KIO-E-PURGE-NOT-FOUND-001`/tombstone (PA26 参照) で終端する。(b) 隔離された実体は削除せず、
  元 path (`notes.md`) へ no-replace rename での復帰を試みる — 成功・失敗いずれの場合も
  `KIO-E-COMMIT-RESTORE-CONFLICT-001` (`conflict_kind=quarantine_rename_race` または
  `quarantine_mismatch`) で終端する。

### PA26 退避の復帰・除去も同じ隔離検証方式で行い、復帰後は preflight と同一の応答で終端する [P1]
- 正本: 05 §3.5 L873-879『**退避の復帰・除去も同じ隔離検証方式で行う**...退避を隔離名へ no-replace
  rename → rename した実体を記録済み dev/inode と対照 → 一致 = 復帰なら元 path へ no-replace
  rename・除去なら削除。不一致 = 第三者による退避差し替え — 退避名へ no-replace で戻し (失敗 = 隔離名の
  まま)、それ以上触れずに競合終端。**復帰後は preflight と同一の応答で終端する: canonical =
  `purged` (tombstone) なら tombstone、`erased` なら KIO-E-PURGE-NOT-FOUND-001**』
- 前提: PA25 の巻き戻し (publish 側) が完了し、PA22 で退避した `notes.md.kio-restore-bak` を元の
  `notes.md` へ復帰する段階に入る。対象 raw_hash の canonical final event が (a) `purged`、
  (b) `erased`。
- 操作: (a)(b) それぞれで退避の復帰を実行する。
- 期待: 退避ファイルは PA25 と同型の「隔離名へ no-replace rename → dev/inode 対照 → 元 path へ
  no-replace rename」で復帰される。復帰完了後、restore コマンド全体の最終応答は (a) tombstone
  応答 (`status:"tombstoned"`, exit 4)、(b) `KIO-E-PURGE-NOT-FOUND-001` (exit 4) — **PA24 で最初に
  preflight (`check_purge_state` 相当) が返したであろう応答と同一の形** — で終端する
  (巻き戻し・退避復帰が「たまたま成功した」ことを理由に異なる応答を返さない)。

---

## F. restore 競合のエラー分類統一 (U27)

> 正本: 05 §3.5 L847-852、05 §4.1 L987-990、06 §5 L282-285。

### PA27 restore の全競合終端を `KIO-E-COMMIT-RESTORE-CONFLICT-001` (retryable exit 3) に統一する [P1]
- 正本: 05 §4.1 L987-990『競合処置は段階別...いずれも両所在を表示して
  KIO-E-COMMIT-RESTORE-CONFLICT-001 (retryable exit 3、context に conflict_kind・retry_disposition)
  で終端』
- 前提: PA20-PA26 で列挙した全ての競合シナリオ (publish 時の第三者ファイル出現・隔離 rename 競合・
  隔離実体の dev/inode 不一致・退避の dev/inode 不一致・退避/隔離 rename 自体の失敗) を横断的に
  列挙する。
- 操作: 各シナリオを個別に発生させる。
- 期待: 全シナリオが単一のエラーコード `KIO-E-COMMIT-RESTORE-CONFLICT-001` + `retryable exit 3`
  で終端する — シナリオごとに異なるエラーコードを使わない (`context.conflict_kind` で区別する、
  PA28)。**現行実装との既知の不整合**: `KIO-E-COMMIT-RESTORE-CONFLICT-001` 自体は既存
  (restore.rs:392, 1343) だが「宛先ファイル既存 + `--force` 無し」(preflight 時点、restore.rs:400)
  と「hard_link 時の `AlreadyExists`」(publish 時点、restore.rs:1343) の 2 ケースのみに限定され、
  §E (PA20-26) が新設する退避/隔離関連の競合ケースは実装自体が存在しないため当然このコードに
  統一されていない。

### PA28 `context.conflict_kind` は 7 値の閉 enum である (パラメタ化) [P1]
- 正本: 05 §3.5 L848-850『context に閉 enum `conflict_kind` (publish_race / quarantine_rename_race /
  quarantine_mismatch / backup_mismatch / restore_rename_race / stale_backup / stale_quarantine)』
- 前提: PA21 (stale_backup/stale_quarantine — 退避/隔離名の同名残存)・PA23 (publish_race)・PA25
  (quarantine_rename_race, quarantine_mismatch)・PA26 (backup_mismatch) の各シナリオを個別に発生
  させる。`restore_rename_race` (通常の非退避 rename 競合、PA23(a) 相当) も含める。
- 操作: 各シナリオで返る `KIO-E-COMMIT-RESTORE-CONFLICT-001` の `context.conflict_kind` を検査する。
- 期待: 7 値 (`publish_race`, `quarantine_rename_race`, `quarantine_mismatch`, `backup_mismatch`,
  `restore_rename_race`, `stale_backup`, `stale_quarantine`) のいずれか 1 つが、シナリオに応じて
  正確に設定される。7 値以外の値は現れない (閉 enum)。

### PA29 `context.retry_disposition` — transient は publish_race のみ、他は manual_action [P1]
- 正本: 05 §3.5 L850-852『`retry_disposition` (**transient = publish_race のみ** — transient は
  「次回 preflight を妨げる残存物を作らない競合」に限る。他は全て manual_action。自動再試行が
  安全なのは transient のみ)』
- 前提: PA28 の 7 パターンそれぞれについて `conflict_kind` が確定している。
- 操作: 各パターンの `context.retry_disposition` を検査する。
- 期待: `conflict_kind=publish_race` の場合のみ `retry_disposition="transient"`。他の 6 値
  (quarantine_rename_race, quarantine_mismatch, backup_mismatch, restore_rename_race,
  stale_backup, stale_quarantine) は全て `retry_disposition="manual_action"` — 自動リトライ
  ループを組む呼び出し側は `transient` の場合のみ機械的に再試行してよい。

---

## G. purge CLI 構文・保証範囲反転・削除対象拡大 (U28 / U29 / U30、圧縮)

> `tasks/step4b-spec-gap.md` はこの 3 項目を「適合済みの可能性」と評価している。現行実装を精査した
> 結果、3 項目とも規範文と実質的に一致することを確認したため、各 1〜2 本の「現状固定」契約へ圧縮する
> (指示書「真に適合なら契約 1 本 (現状固定) に圧縮してよい」に従う)。

### PA30 purge CLI 構文が新 spec と完全一致する (`path|--raw-hash` 排他・reason 5 値閉 enum・`--yes`) [P1] [現状固定]
- 正本: 06 §6 L300-303『`kio purge <path|--raw-hash <h>> --reason <legal|privacy|misingest|copyright|other>`』
  / 02 §2.4 引用の CLI 例、05 §3.1 L648-653 (同型)
- 前提: `kio purge` の引数パーサ。
- 操作: (a) `path` と `--raw-hash` の同時指定、(b) いずれも未指定、(c) `--reason` に 5 値以外の値、
  (d) `--yes` 単独指定 (confirm prompt スキップのみ) を試す。
- 期待: (a)(b) は usage error。(c) は `clap` の `value_parser` レベルで拒否。(d) は確認プロンプトを
  スキップして続行する (network opt-in 等の別ゲートには影響しない)。**現状確認**: `PurgeArgs`
  (purge.rs:45-71) の `ArgGroup` (`path`/`raw_hash` 排他必須)・`PURGE_REASONS`
  (purge.rs:41, 5 値)・`yes: bool` は新規則と完全一致 — 現状固定として 1 本に圧縮する。

### PA31 purge は commit/tree object を書き換えず、削除事実の記録 (tombstone) を物理削除より先に耐久化する [P0] [現状固定]
- 正本: 05 §3.5 L692-695『purge は **object の物理削除 + default tombstone または内部 erase
  receipt** であり、**履歴 DAG の書き換えではない**』/ 10-operations.md §7 相当・02 §2.4 引用
  『消す事実の記録 (tombstone) を先に耐久化したうえで...本文を全履歴にわたり物理削除します』
- 前提: raw_hash `X` を `kio purge --reason legal` する。
- 操作: purge の phase 遷移順序 (`Prepared → Tombstoned → Deleted → Committed`) と、各 phase での
  実際の副作用発生順序を観測する。commit/tree object の書き換えの有無を確認する。
- 期待: `Prepared` 相の後、`Tombstoned` 相でまず tombstone (`purged` event) が耐久 publish され、
  それより**後**の `Deleted` 相で初めて object/SQLite/chunks.jsonl の物理削除が行われる。既存の
  commit/tree object は一切書き換えられない (新しい `commit_type=purged` の commit が**追加**
  されるのみ)。**現状確認**: `execute_visible_phases` (purge.rs:333-375) は `Prepared` 相で
  `publish_terminal_records` (tombstone/erase receipt append) を実行してから `Tombstoned` へ進み、
  `delete_content_surfaces`/`delete_derived_surfaces` (物理削除) はその後の `Deleted` 相遷移時に
  実行される — 新規則と一致 (現状固定)。

### PA32 purge の物理削除対象は raw/prepared/image/normalized/chunk/embedding + manifest、共有派生は live 参照 0 限定 [P0] [現状固定]
- 正本: 05 §3.5 L701-705『派生 artifact: prepared / **image** / normalized / chunk / embedding
  (...**manifest object...を含む**。**共有されうる派生 (prepared / image / embedding) は、purge
  対象外の live 参照が 0 の場合のみ物理削除する**...)』
- 前提: raw_hash `X` を purge する。`X` の normalized instance が参照する prepared object `P1`
  (他 raw と非共有) と `P2` (他 raw `Y` と共有、`Y` は purge 対象外)。
- 操作: purge を実行する。
- 期待: `P1` は物理削除される。`P2` は live 参照 (`Y`) が残るため物理削除されない。当該
  `(raw_hash, tool_profile_hash)` の全 gen・全確定版の manifest object が削除対象に含まれる。
  **現状確認**: `delete_derived_surfaces`/`scan_derived_inventory` (purge.rs:604-788) は
  `shared_prepared`/`shared_images` (live 参照 > 0) を `target_prepared`/`target_images` から
  除外してから物理削除する構造を既に持つ — 新規則と一致 (現状固定。ただし本契約が固定するのは
  「対象範囲」のみであり、この判定を**いつ計算し、resume 時にどう扱うか**という別の論点は §N
  (PA42-46) が扱う — 混同しない)。

---

## H. SQLite / chunks.jsonl の purge 範囲の具体化 (U31)

### PA33 `chunk_vec` は対象 chunk_id 限定、`embeddings` は live 参照 0 限定、`query_cache` は除外される (パラメタ化) [P1] [現状固定]
- 正本: 05 §3.5 L716『`chunk_vec` は対象 chunk_id の行に限定し、**embeddings 行は object 側と同じく
  live 参照 0 の場合のみ削除する** (共有 text_hash の行を無条件に消すと、非対象文書の vector 検索が
  rebuild まで欠ける)。`target_type='query_cache'` の embeddings 行は候補に含めない (文書 lifecycle
  と無関係)』
- 前提: raw_hash `X` の purge において、(a) `X` 由来の chunk が持つ `chunk_vec` 行、(b) `X` の
  chunk とテキストを共有する (同一 `text_hash`) が **別の** 生存 chunk からも参照される
  `embeddings` 行、(c) `X` とは無関係な `target_type='query_cache'` の `embeddings` 行。
- 操作: purge を実行する。
- 期待: (a) は削除される。(b) は他 chunk からの参照が残るため削除されない。(c) は最初から候補に
  含まれず削除されない。**現状確認**: `tasks/step4b-spec-gap.md` U31 の実装状態注記
  (`fts.rs:245-306` の `purge_raw`) によれば、この 3 条件は既に実装されている — 現状固定として
  1 本に圧縮する。

### PA34 `chunk_publications` テーブルが存在しない (purge 対象を規定できない) [P1]
- 正本: 05 §3.5 L716『SQLite の chunks / chunk_config_generations / **chunk_publications** 行と
  FTS エントリ』
- 前提: purge が SQLite から削除すべき表の一覧を列挙する。
- 操作: `sqlite_master` から `chunk_publications` テーブルの存在を確認する。
- 期待: `chunk_publications` テーブルが存在し、対象 chunk_id に対応する行が purge で削除される。
  **実装状態の確認**: `chunk_publications` は crates 全体で grep 0 件であり、テーブル自体が
  存在しない (この論点は A 領域/Phase 1 の DDL 契約と隣接するが、purge 側の削除対象として本書に
  含める — テーブルが新設された時点で purge の削除経路にも追加される必要がある)。

---

## I. staging の purge 範囲拡大と帰属列挙方式 (U32)

### PA35 staging の帰属列挙は `.kio/staging/` の耐久 descriptor 全走査が正本であり、tasks.jsonl に依存しない [P1]
- 正本: 05 §3.5 L718『対象 raw_hash に帰属する task の **staging**...**task の状態を問わず** (retryable
  failed の保全 staging を含む...)。**帰属列挙の正本 = `.kio/staging/` の耐久 descriptor 全走査**
  ([03-data-model.md §2] — tasks.jsonl 非依存。task 記録の喪失後も削除対象を列挙できる)』
- 前提: raw_hash `X` に帰属する staging descriptor が `.kio/staging/` に存在するが、対応する
  `tasks.jsonl` の行が (過去の compaction や別の障害で) 既に失われている。
- 操作: `X` を purge する。
- 期待: `tasks.jsonl` に対応行が無くても、`.kio/staging/` の descriptor 全走査によって `X` に帰属する
  staging が発見され削除される。**現行実装との既知の不整合**: `delete_target_tasks`
  (purge.rs:939-1030) は `TaskStore::new(repo.kio_dir()).all()` (= tasks.jsonl 全件読取) を正本
  として動作しており、「task 状態を問わず対象化する」点は新規則と一致するが (tasks.jsonl 内の
  状態フィルタは既に外れている)、**正本が tasks.jsonl のままである**点が新規則の
  「`.kio/staging/` descriptor 全走査へ移行」と一致しない。`.kio/staging/` という耐久 descriptor
  directory 自体の実装有無は本書のスコープ外 (07-adapter-spec.md §8.3 側) だが、存在する前提で
  purge 側がそれを列挙元にする必要がある。

---

## J. purge のログ scrub 範囲を scope_id 単位に限定 (U33)

### PA36 ログ scrub は当該 scope の scope_id を持つ行のみを対象とし、他 scope の同一 raw_hash 行には触れない [P0]
- 正本: 10-operations.md §7/§12.6 相当 (`tasks/step4b-spec-gap.md` U33 統合要約)『purge のログ scrub
  対象を旧 spec の「対象の raw_hash/path/query を含む行」から新 spec の「**当該 scope の scope_id を
  持ち**対象の raw_hash/path/query を含む行」に変更する。device-global log の別 scope の同一 raw_hash
  行には触れないようにし、scope 由来の行は scope_id を必須 field とする規約を追加する』
- 前提: device-global ログ (`$XDG_DATA_HOME/kio/logs/{events,errors,metrics}*`) に、(a) 現在 purge を
  実行している scope (`scope_id=S1`) の raw_hash `X` を含む行、(b) **別の** scope (`scope_id=S2`,
  `S1` とは無関係) が偶然同一の raw_hash `X` を持ち、それを含む行 (別ユーザーが同一ファイルを別の
  `.kio` へ独立に取り込んだ結果、raw_hash が衝突するケース — 05 §3.4 の「purge スコープは `.kio`
  単位」規約から、この `S2` 側の行は `S1` の purge が触れてはならない)。
- 操作: `S1` の scope で `X` を `kio purge --raw-hash X --reason legal` する。
- 期待: (a) の行は削除/マスクされる。(b) の行は `scope_id` が `S1` と一致しないため一切変更されない
  (削除もマスクもされない)。**現行実装との既知の不整合**: `scrub_logs` (purge.rs:1127-1174) の
  `identifiers` (purge.rs:1138-1143) は `plan.target_raw_hashes` と `plan.historical_paths` のみで
  構成され `scope_id` を含まない。`scrub_one_log`/`value_contains_identifier`
  (purge.rs:1216-1258) は raw_hash/path の**文字列一致のみ**で行を削除するため、(b) のような
  他 scope 由来の同一 raw_hash 行も無差別に削除されてしまう。

---

## K. working tree 残存原本の警告義務化 (U34)

### PA37 purge の preview/完了表示は working tree に同一 bytes の原本が残存する場合に必ず警告する [P1]
- 正本: 05 §3.5 L741-745『**working tree の原本には触れない**...したがって purge の preview と完了
  表示は、対象 raw_hash と同一 bytes の原本が working tree に残存する場合に**必ず警告する**:
  残存原本は次回 `kio index` の自動 scan で再取り込みされ、既存 pointer は再び alive になる...
  恒久的に除外するには原本の削除または `.kioignore` への追加が必要である』
- 前提: raw_hash `X` (`.../report-v1.pdf` に紐づく) を purge する。working tree には `X` と同一
  bytes を持つ**別名**のファイル (`.../backup-copy.pdf`、purge 対象の path とは異なる) が残存する。
- 操作: `kio purge --raw-hash X --reason legal` の preview と完了表示 (`--json` を含む) を検査する。
- 期待: preview 表示と完了表示の双方に、working tree 上の残存原本 (`backup-copy.pdf`) を検出した旨の
  警告が含まれる。警告文言は「次回 `kio index` で再取り込みされ pointer が再び alive になる」ことと
  「恒久的除外には原本削除または `.kioignore` 追加が必要」であることを案内する。

### PA38 [解釈割れ] working tree 残存原本は警告対象か、それとも purge 自体を拒否する対象か [P1]
- 正本: 05 §3.5 L741-745 (PA37 と同一引用)。文言は「必ず警告する」であり、purge 自体を止めるとは
  述べていない — 「working tree の原本には触れない」という原則の帰結として、warning-only であるべき
  ことを文脈上示唆する。
- 前提: PA37 と同一の残存シナリオだが、残存原本の path が purge 対象の **同一 path** である
  ケース (`report-v1.pdf` を purge した直後に working tree を見ると `report-v1.pdf` 自体が
  同一 bytes のまま残っている — リネームではなく素朴な「まだ存在する」ケース)。
- 操作: このケースで purge を実行する。
- 期待: **[解釈割れ]** 新 spec の字面 (PA37 の引用) だけからは、この場合も purge は「警告を出しつつ
  成功する」べきなのか、それとも `KIO-E-PURGE-WORKING-COPY-001` で purge そのものを拒否すべきなのか
  一意に決まらない。**現行実装との対比**: `refuse_live_working_copy`/`refuse_live_working_copy_for_phase`
  (purge.rs:1925-1943, 1537-1554) は working tree に同一 raw_hash を持つ tree entry が 1 件でも
  あれば `KIO-E-PURGE-WORKING-COPY-001` (`ExitCode::PermanentFailure`) で purge**そのものを完全に
  拒否**しており、PA37 が要求する「警告のみで purge は進む」という読みとは異なる。しかし
  `tasks/step4b-spec-gap.md` の U34 実装状態注記はこの `refuse_live_working_copy` の存在に一切
  触れておらず ([未実装] とだけ記す)、既存の hard block を「PA37 の適用対象外 (別の独立した安全機構)」
  と見るか「PA37 と矛盾する過剰実装」と見るかは spec 側の記述だけでは判定できない。本書はどちらか
  一方を規範として断定せず、実装時に発注側の裁定を要すると注記するにとどめる (現状の hard block を
  維持しつつ、PA37 の「同一 path ではないが同一 bytes」という別名残存ケースに限って警告表示を新設する、
  という折衷解も spec と非矛盾に見える)。

### PA39 現状の `KIO-E-PURGE-WORKING-COPY-001` hard block は working tree 直接削除をしない Kio の原則と両立する形で残置してよい [P2]
- 正本: 02 §2.4 引用『Kio はユーザーのファイルを削除しない』/ 05 §3.5 L741『working tree の原本には
  触れない』
- 前提: PA38 の解釈割れを受け、`refuse_live_working_copy` を維持する裁定が下されたと仮定する。
- 操作: raw_hash `X` が現在の HEAD tree に同一 path・同一 raw_hash で存在する状態 (working tree
  ファイルがそのまま生きている、リネームなし) で purge を試みる。
- 期待: `KIO-E-PURGE-WORKING-COPY-001` (exit 4) で拒否され、working tree のファイルには一切触れない
  (削除・リネームしない) — この場合の hard block は「Kio はユーザーファイルを削除しない」原則と
  矛盾しない (むしろ purge が完了したのに原本が生き残ることの防止として機能する)。本契約は PA38 の
  解釈割れとは独立に、hard block を採用する場合でも working tree 自体には不干渉であることを固定する。

---

## L. purge 時の in-flight 外部実行タスクとの整合 (U37)

> 本節は A 領域 (cost-ledger / Online Batch 2 相プロトコル、Phase 1・CL1-71) の内部規則を再契約しない
> — `batch_requests` の状態機械・`recovery_settle_unknown` 等は Phase 1 の正本に従う。本節が契約する
> のは「purge がいつ・どの範囲でこの機構を呼び出すか」という E 領域側の境界のみ。

### PA40 prepared 相で、当該 scope の対象 raw_hash を入力とする pending/running 外部実行タスクを abandon 相当で terminal 化する (タイミングのギャップを含む) [P0]
- 正本: 05 §3.5 L893-897『**in-flight 外部実行との整合**: prepared 相で、**当該 scope (purge を
  実行する `.kio` の scope_id) の**対象 raw_hash を入力とする pending / running の外部実行タスク
  (batch_requests state 0/1 — `request_kind` = batch / sync の両方...scope_id 条件が無いと同一 raw
  を持つ**別 scope** の実行中 request まで terminal 化・掃除してしまう) を abandon 相当で terminal 化
  し (estimated 記帳)、provider 上の対応 upload (batch 行のみ) を掃除する』
- 前提: raw_hash `X` (scope_id=`S1`) を入力とする batch_requests 行が state=0 (pending) で存在する。
  `X` を `kio purge --raw-hash X --reason legal` する。
- 操作: purge を実行する。
- 期待: **`prepared` 相のうちに** (tombstone 耐久化・削除・commit publish のいずれよりも前に)、
  当該行が abandon 相当で terminal 化され (estimated 記帳)、provider 上の upload が掃除される。
  **現行実装との既知の不整合**: `delete_target_tasks` (purge.rs:939-1030) が in-flight 予約を
  settle する唯一の経路だが、これは `execute_visible_phases` の `Tombstoned → Deleted` 遷移
  (`delete_derived_surfaces` 内、purge.rs:353,705) から呼ばれており、`Prepared` 相ではなく
  **`Deleted` 相**で実行される — 新規則の「prepared 相で完遂する」というタイミング要件と一致しない。

### PA41 scope_id 条件を欠くと別 scope の同一 raw_hash の実行中 request まで巻き込む (パラメタ化: batch/sync 両方 + 孤立 intent_token 行) [P0]
- 正本: 05 §3.5 L893-900『(表はデバイスグローバルのため、scope_id 条件が無いと同一 raw を持つ
  **別 scope** の実行中 request まで terminal 化・掃除してしまう — purge は `.kio` 単位)。**加えて、
  対象 raw_hash の terminal だが `intent_token IS NOT NULL` の行 (残骸掃除未完) の provider 残骸
  掃除も同じ prepared 相で完遂する** (これが無いと terminal 化直後の crash が残した機密 upload が
  次の batch 系実行まで provider 上に残る)』
- 前提: (a) scope `S1` で raw_hash `X` を purge するが、**別 scope** `S2` (無関係、同一 raw_hash `X`
  を偶然持つ) の batch_requests 行が state=1 (running, request_kind=batch) で存在する。(b) `S1` 自身の
  raw_hash `X` に帰属する batch_requests 行が既に terminal (state=2 または 3) だが
  `intent_token IS NOT NULL` (残骸掃除未完) であり、**対応する tasks.jsonl の行は既に存在しない**
  (孤立行)。(c) 同様のケースを `request_kind=sync` でも用意する。
- 操作: (a)(b)(c) それぞれで `S1` の purge を実行する。
- 期待: (a) `S2` の行は一切変更されない (別 scope は不可侵)。(b) `tasks.jsonl` に対応行が無くても、
  `S1` かつ `X` に帰属する残骸掃除未完の terminal 行が発見され、provider 残骸 (upload) が掃除完了後に
  `intent_token` が NULL 化される。(c) batch と sync の両 `request_kind` が同様に扱われる。
  **現行実装との既知の不整合**: `delete_target_tasks` は `tasks.jsonl` の行を起点に
  `task.reservation_id` から ledger 行を辿る構造 (purge.rs:986-1017) のため、(b) のように
  tasks.jsonl 側の行が既に失われている「孤立した intent_token 残存行」は発見できない — scope_id
  かつ raw_hash を条件に `batch_requests` テーブル自体を直接走査する経路が存在しない。

---

## M. 二重 purge (再 purge) の挙動確定 (U38) — Phase 1 で充足済み、参照のみ

### PA42 再 purge は既存 tombstone/erase receipt へ新規 purged/erased event を追加 append する (Phase 1 LC58-60 準拠、参照のみ) [P2] [現状固定]
- 正本: 09-mvp-scope.md §5.3 相当 (`tasks/step4b-spec-gap.md` U38 統合要約)『既に purge 済みの
  raw_hash を再度 purge すると、同一 raw_hash の lifecycle `events[]` へ新たな `purged` event を
  追加 append する』
- 前提: raw_hash `X` の tombstone が既に active (`purged`) または retired 状態。`X` を再度
  `kio purge --raw-hash X --reason <任意>` する。
- 操作: 再 purge を実行する。
- 期待: Phase 1 の `tasks/step4b-contract-tests-lifecycle.md` **LC58 (再 purge は events[] へ新規
  purged/erased event を追加 append)**・**LC59 (「既存 active marker」判定は当該 marker 自身の末尾
  event で行う)**・**§M 裁定 #2 (reason 一致要件なし)** が既にこの挙動を契約・実装済み
  (`kio-core/src/purge.rs` の `state.begin()` — 再 purge 時に retired 状態の marker へは新規
  `purged` event を append し、既に active な marker への再 purge 要求は `AlreadyComplete` として
  素通りする、いずれも reason 不一致で拒否しない)。本書は U38 を独立に再契約せず、この Phase 1
  契約を参照するのみとし、現状固定として 1 本のみ記載する (U38 は E 領域の担当割当てに含まれるが、
  実体は B 領域 Phase 1 の成果物と同一であることを確認した記録)。

---

## N. purge closure 完全化 (LC46 の継続 — Phase 1 引き継ぎ)

> Phase 1 (`tasks/step4b-contract-tests-lifecycle.md`) は **LC46-LC51** で purge journal の
> 機構自体 (record の必須 field 一式・phase の名称と厳密順序・`closure`/`planned_commit` が
> `prepared` 相で一度確定され、以後のフィールド値としては再計算されず resume 時にそのまま journal
> から読み戻される、という**構造**) を契約・実装済みであり、既存のユニットテスト
> `lc48_closure_and_planned_commit_are_fixed_at_prepared_and_unchanged_on_resume`
> (`crates/kio-core/src/purge.rs:2239-2260`) がこれを検証している。しかし LC46 の実装コメント自身が
> 明記する通り、`ClosureItem`/`PurgeJournal::new` (kio-core/purge.rs:596-651) は
> **`object_type: "raw"` の対象 raw_hash 一覧のみ**を `closure` に記録する簡略実装であり、
> 「削除対象の全 object type × hash — 共有派生の live 参照判定の結果を含む」という 05 §3.5 の
> 完全な定義を満たしていない。かつ、実際の物理削除 (`delete_content_surfaces`/
> `delete_derived_surfaces`, kio-cli/purge.rs:487-788) は **`journal.closure` を一度も参照せず**、
> `deleted` 相に入るたびに (fresh-start でも resume でも) `scan_derived_inventory` でライブ再走査して
> shared/removable を再計算している。本節はこの「closure の内容的完全性」と「closure が実際の削除
> 決定の唯一の正本として機能しているか」を契約する — E 領域 (U29/U30/U31) の削除対象範囲そのもの
> と直接接続する、Phase 2 側の宿題。

### PA43 closure は削除対象の全 object type × hash を記録する (raw だけでなく prepared/image/normalized/chunk/embedding + manifest) [P0]
- 正本: 05 §3.5 L796『closure (**削除対象の全 object type × hash** — 共有派生の live 参照判定の
  結果を含む)』
- 前提: raw_hash `X` の purge が `prepared` 相を完了する。`X` の normalized instance は prepared
  object `P1` (非共有)・image object `I1` (非共有)・chunk object 群・embedding 行・manifest object
  を参照する。
- 操作: `prepared` 相完了直後の journal の `closure` フィールドを検査する。
- 期待: `closure` には `{object_type:"raw", hash:X}` に加えて `{object_type:"prepared", hash:P1}`、
  `{object_type:"image", hash:I1}`、対象 chunk_id 群、対象 manifest object hash が全て列挙されて
  いる。**現行実装との既知の不整合**: `PurgeJournal::new` (kio-core/purge.rs:658-696) は
  `target_raw_hashes` のみから `object_type:"raw"` の `ClosureItem` を生成し、`ClosureItem`
  struct 自身のコメント (kio-core/purge.rs:596-601)「The full "every object type × hash destined
  for deletion..." enumeration...is out of this module's scope」がこの限定を明記している。

### PA44 closure は共有派生の live 参照判定の**結果**を保持し、prepared 相で一度確定した後は再計算しない — resume 時も同一決定を再利用する [P0]
- 正本: 05 §3.5 L796, L798-799『closure (...共有派生の live 参照判定の結果を含む)』/
  10-operations.md §7.5.3 系の in-place migration 原則と同型の「一度確定した計算結果は再現するのみで
  再計算しない」原則 (LC48 の `planned_commit`/`closure` 固定要件の直接の帰結)
- 前提: raw_hash `X` の purge が `prepared` 相で、prepared object `P1` を「live 参照 0 → 削除対象」と
  判定して closure に記録する (この時点で `P1` を共有する他の raw は存在しない)。`tombstoned` 相まで
  進んだところで crash する。crash 後、`deleted` 相へ進む**前**に、**別の** purge 操作 (または
  `kio index` による新規取り込み) が完了し、`P1` を新たに共有する raw `Z` が追加された結果、
  もし今この瞬間に live 参照を再計算すれば `P1` は「共有 → 保持」と判定が変わるはずの状況を作る。
- 操作: 元の purge (`X` 対象) を resume する (`kio purge --raw-hash X --reason legal` を再実行し、
  既存 journal を検出させる)。
- 期待: resume された `deleted` 相は、`prepared` 相で確定・journal に記録済みの closure
  (`P1` を削除対象に含む決定) を**そのまま再利用**し、`P1` を物理削除する — crash-resume の間に
  発生した新しい共有関係を理由に判定を覆さない (LC48「以降の phase でこれらの値が再計算されたり
  変化したりしない」の直接適用)。これにより、同一の論理的な purge 操作は「中断されずに一気に完走した
  場合」と「crash-resume を経た場合」とで**同一の削除結果**になる (再実行安全性の強い意味 — 単なる
  idempotent だけでなく決定論的)。**現行実装との既知の不整合**: `delete_derived_surfaces`
  (kio-cli/purge.rs:604-719) は `deleted` 相に入るたび (fresh-start か resume かを問わず) 常に
  `scan_derived_inventory` (purge.rs:721-788) を呼び出してライブ走査から shared/removable を
  再計算しており、`journal.closure` の値は一度も参照されない。したがって上記シナリオでは、resume 後
  `P1` は (再計算の結果) 「共有 → 保持」と**判定が変わり得る** — closure に記録された当初の決定と
  実際の削除結果が食い違う可能性がある。

### PA45 closure に記載されなかった object は削除されず、記載された object は必ず削除される (監査可能性) [P1]
- 前提: PA43 が満たされ closure が完全な object type × hash 列挙を持つと仮定する。
- 操作: `deleted` 相の実行結果 (実際に削除された object 一覧) を、`prepared` 相で確定した
  `journal.closure` と突き合わせる。
- 期待: 実際に物理削除された object の集合と `journal.closure` に列挙された object の集合が
  完全に一致する (closure ⊆ 実削除 かつ 実削除 ⊆ closure)。`kio status` 等で active journal を
  検査すれば、purge が「何を消すつもりか」を closure から監査でき、実際の結果と乖離しないことが
  保証される。

### PA46 SQLite 行 (chunk_vec/embeddings の live 参照判定含む)・chunks.jsonl 該当行・staging descriptor も prepared 相で closure の一部として確定すべきである (§H/§I との接続) [P1]
- 正本: 05 §3.5 L716 (SQLite 範囲、§H)・L718 (staging 帰属列挙、§I) の各規範文 (再掲は避け、§H/§I の
  引用を参照する)。closure の「全 object type × hash」という定義文言 (L796) 自体は object-store
  対象 (raw/prepared/image/normalized/chunk/embedding) を念頭に置いた記述だが、purge が単一の
  crash-safe な操作として設計されている以上、SQLite 行・chunks.jsonl 該当行・staging descriptor の
  対象範囲決定も同じ「prepared で確定・以後不変」という設計原則に服するべきという要求は
  05 §3.5 の journal 全体の趣旨 (「crash 安全の正本」) から導かれる。
- 前提: PA33/PA34 (§H) の SQLite 対象・PA35 (§I) の staging 対象決定が、`prepared` 相以前の
  ライブクエリ (SQLite の `SELECT` や `.kio/staging/` の readdir) で行われている。
- 操作: `prepared` 相完了後にこれらの決定が journal (or 同格の耐久記録) に固定されているかを確認する。
- 期待: SQLite の対象 chunk_id 群・embeddings 行の live 参照判定結果・staging descriptor の対象一覧
  が、`prepared` 相の耐久記録に含まれ、`deleted` 相 (resume 含む) はこの記録を消費するのみで
  再クエリしない。**現状確認**: PA44 と同型の不整合が SQLite 側 (`delete_derived_surfaces` 内の
  `SqliteFtsIndex::open`+`purge_raw` 呼び出し) にも staging 側 (§I, PA35) にも同様に存在する
  可能性が高いが、SQLite クエリ結果を journal に埋め込むこと自体のコスト (chunk_id 集合が大きい
  scope での journal サイズ膨張) とのトレードオフは spec が明示的に扱っておらず、実装時の裁定を
  要する — 本契約は「確定すべき」という要求のみを固定し、具体的な記録形式 (journal 本体か別
  sidecar か) は指定しない。

---

## O. restore canonical dispatch の分岐 ii〜iv (Phase 1 引き継ぎ)

> Phase 1 (`tasks/step4b-contract-tests-lifecycle.md` LC8-LC14) は canonical final event の 4 分岐
> ((i) purged→tombstone、(ii) erased かつ raw 不在→not_found、(iii) retired かつ raw 不在→
> STORE-CORRUPT、(iv) marker 無しかつ raw 不在→STORE-CORRUPT) を**アルゴリズムとして**契約し、
> `crates/kio-cli/src/main.rs` の `enforce_canonical_marker_barrier` (main.rs:7055-7086) として実装
> した上で `resolve_pointer_for_cli` (open/view/evidence verify の共有経路) に配線済みである。
> しかし restore は**この共有関数を一度も呼ばず**、独自の `check_purge_state`
> (`crates/kio-cli/src/restore.rs:1037-1078`) を使う。この関数自身の doc comment
> (restore.rs:1024-1036) が「Only the `purged` branch (LC11) is handled here...the raw-presence-
> dependent LC12/13/14 branches...are not replicated here」と明記しており、`main.rs` 側の
> `enforce_canonical_marker_barrier` の doc comment (main.rs:7049-7054) もまた「Known residual scope
> gap...the task instructions scoped LC12-14's replacement to open/view/**restore** only」と
> 述べていて、restore への配線が (意図されていたにもかかわらず) 未完了であることを両側から
> 裏付けている。本節はこの配線ギャップを契約する。

### PA47 現状: restore は分岐 (i) のみ独自実装し、(ii)(iii)(iv) は raw 存在検査へ委譲されている [P1]
- 正本: 08 §3.1 手順 5 (Phase 1 LC11-14 が引用・契約済み。本契約は新たな規範文引用ではなく、現状の
  実装ギャップそのものを固定観測する契約)
- 前提: restore の呼び出し経路 (`resolve_evidence_source`・`preflight`・`preflight_in_dir`・
  `publish_all`) が全て `check_purge_state(target, raw_hash)` を経由した後、別途
  `store.inspect_object(ObjectKind::Raw, raw_hash)` の成否で `missing_live_raw_error`
  (`KIO-E-PURGE-NOT-FOUND-001` 固定) を返す、という 2 段構成になっていることを確認する。
- 操作: `check_purge_state` のソースコードとその呼び出し元 4 箇所を横断的に検査する。
- 期待: `check_purge_state` (restore.rs:1053-1064) は `canonical_final_event(...)` を計算し、
  `event.kind == EventKind::Purged` の場合のみ `tombstone_error` を返す (分岐 (i) のみ)。canonical
  が `Erased`/`Retired`/`None` のいずれであっても `check_purge_state` は `Ok(())` を返して素通りし、
  その後の raw 存在検査が失敗した場合は呼び出し元が一律に `missing_live_raw_error`
  (`KIO-E-PURGE-NOT-FOUND-001`) を返す — canonical の種別 (erased/retired/none) を一切区別しない。

### PA48 分岐 (ii)/(iii)/(iv) はそれぞれ異なるエラーコードで終端すべきである (パラメタ化) [P0]
- 正本: 08 §3.1 手順 5 (main.rs:7036-7044 の Phase 1 実装コメントが LC12/LC13/LC14 の対応を正確に
  要約している)『(ii) canonical = `erased` and `!raw_present` -> `KIO-E-PURGE-NOT-FOUND-001`
  (LC12)』『(iii) canonical = `retired` and `!raw_present` -> `KIO-E-STORE-CORRUPT-001` (LC13 —
  retired marker の raw は必ず存在するはずで、その不在は corruption)』『(iv) no marker at all and
  `!raw_present` -> `KIO-E-STORE-CORRUPT-001` (LC14(a))』
- 前提: raw_hash `X` について 3 パターンを用意する。(a) canonical final event = `erased`、raw object
  `X` が CAS に不在 (正常な erase 済み欠落)。(b) canonical final event = `retired`
  (resurrection 済みのはずだが)、raw object `X` が (異常系として) CAS に不在。(c) tombstone/erase
  receipt のいずれも存在せず、raw object `X` が CAS に不在 (無印の異常な欠落)。
- 操作: (a)(b)(c) それぞれについて `kio restore <X を指す evidence pointer> --to <dir>` を実行する。
- 期待: (a) `KIO-E-PURGE-NOT-FOUND-001` (exit 4)。(b) `KIO-E-STORE-CORRUPT-001` (exit 4 —
  (a) とは異なるコード。「retired なのに raw が無い」は resurrection の完遂に失敗した corruption で
  あり、正当な purge 起因の欠落と区別する)。(c) `KIO-E-STORE-CORRUPT-001` (exit 4 — marker 無しの
  欠落は corruption 疑い、`kio repair --verify-objects` を案内)。**現行実装との既知の不整合**:
  (a) は現状のコードでも `missing_live_raw_error` = `KIO-E-PURGE-NOT-FOUND-001` を返すため
  **偶然一致**するが、(b)(c) は現状のコードが同じ `missing_live_raw_error` =
  `KIO-E-PURGE-NOT-FOUND-001` を一律に返してしまい、期待される `KIO-E-STORE-CORRUPT-001` と
  **一致しない** — スクリプトや自動化が exit code/error_code を見て「正当な purge 起因の欠落」と
  「store の破損」を区別しようとした場合、restore 経由では常に前者に見えてしまい、破損検出が
  隠蔽される。

### PA49 分岐 (iv) の非該当ケース: canonical = `erased` でも raw が存在すれば restore は拒否しない [P1]
- 正本: 08 §3.1 手順 5 (main.rs:7045-7047 の実装コメント)『every other combination (canonical =
  `erased`/`retired`/none with `raw_present` true) -> `Ok(())`, the normal continue-resolving path
  (LC14(b)/(c))』
- 前提: raw_hash `X` の canonical final event が `erased` (erase receipt が active) だが、
  何らかの理由 (再 ingest 等) で raw object `X` は CAS に**存在する**。
- 操作: `kio restore <X を指す evidence pointer> --to <dir>` を実行する。
- 期待: restore は拒否されず、通常どおり `X` の内容が展開・publish される (erase receipt は
  re-ingest barrier ではなく、raw が物理的に存在すればそれを alive として扱ってよい —
  05 §3.5/08 §3.1 の一貫した設計)。**現状確認の要点**: 現行の `check_purge_state` は canonical が
  `Erased` の場合に何もしない (分岐しない) ため、この非該当ケース自体は現状でも正しく通過している
  可能性が高い — PA48 の修正実装がこの「raw 存在時は素通り」という正しい挙動を壊さないことを
  回帰契約として固定する。

### PA50 restore の 3 呼び出し箇所 (`preflight`/`preflight_in_dir`/`publish_all`) は全て同一の canonical dispatch 関数を共有する [P0]
- 正本: 05 §3.5 L907『検証失敗の marker は入口を問わず (fsck・resolver・再 purge) 説明能力を持たない
  corruption とする』の一般原則、および main.rs 側の実装コメント (main.rs:7049-7054) が明記する
  「open/view/restore で同一の canonical dispatch を共有する」という設計意図
- 前提: PA48 の修正 (分岐 (ii)/(iii)/(iv) を正しく区別する canonical dispatch) を restore に導入する。
  restore には purge 状態を検査する呼び出し箇所が 3 つある: `preflight` (restore.rs:358)、
  `preflight_in_dir` (restore.rs:440)、`publish_all` の per-file ループ内 (restore.rs:1217)。
- 操作: raw_hash `X` について PA48 の (b) (retired かつ raw 不在の corruption ケース) を、
  3 呼び出し箇所それぞれが最初に遭遇するシナリオ (通常の restore フロー・`--to` 未作成ディレクトリへの
  restore・publish 直前の recheck タイミング) で個別に発生させる。
- 期待: 3 箇所いずれで検出されても、同一の `KIO-E-STORE-CORRUPT-001` が返る — 呼び出し箇所によって
  緩い/厳しい判定基準が生じない (`open`/`view` が使う `enforce_canonical_marker_barrier` と実装を
  共有するか、少なくとも同一の判定表を持つ独立実装であることを要求する。3 箇所が個別に
  `missing_live_raw_error` 相当のショートカットへ fallback する現状の構造を、単一の
  canonical-dispatch 呼び出しへ統一する)。

---

## P. 解釈割れ注記一覧 (§L)

1. **PA38 (working tree 残存原本 = 警告 or 拒否)**: 05 §3.5 L741-745 (PA37) は purge の
   preview/完了表示が working tree 残存原本を「必ず警告する」と述べるのみで、purge 自体を止めるとは
   書いていない。一方、現行実装 `refuse_live_working_copy` (purge.rs:1925-1943) は working tree に
   同一 raw_hash の tree entry が 1 件でもあれば purge 全体を `KIO-E-PURGE-WORKING-COPY-001` で
   完全に拒否しており、`tasks/step4b-spec-gap.md` の U34 実装状態評価はこの既存機構に一切言及して
   いない。新規則の「警告のみで purge は進む」という読みと、既存の「hard block」という読みのどちらを
   正本とするか、あるいは「同一 path での残存 (現行の hard block 対象)」と「別名での残存 (PA37 の
   警告対象)」とでケースを分けるべきかは、spec の文言だけからは一意に決まらない。発注側の裁定を要する。

2. **PA46 (SQLite/staging を closure 本体に埋め込むか sidecar にするか)**: 05 §3.5 L796 の
   「closure (削除対象の全 object type × hash)」という定義は object-store 系 (raw/prepared/image/
   normalized/chunk/embedding) を主眼にした記述であり、chunk_id が数万件規模になり得る scope での
   SQLite/staging 対象一覧を journal 本体 (`.kio/purge/journal`、上限 `MAX_PURGE_JOURNAL_BYTES` =
   8 MiB) にそのまま埋め込むべきか、別の耐久 sidecar ファイルに切り出すべきかは spec が明示的に
   規定していない (LC46 の journal record 定義自体もこの規模のケースを想定した記述になっていない)。
   「prepared で確定し以後再計算しない」という原則の適用対象であることは確実だが、具体的な永続化
   形式は実装時の裁定を要する。

3. **PA34 (`chunk_publications` の purge 削除規則の詳細)**: テーブル自体が現状存在しないため
   (A 領域/Phase 1 の DDL 契約の管轄)、purge が具体的にどの列条件で行を削除すべきか
   (対象 chunk_id 一致のみか、対象 raw_hash 経由の間接一致も含むか) は、テーブルの DDL が確定して
   いない現時点では規範文からの一意な導出ができない。テーブル新設時に本契約 (PA34) を具体化する
   必要がある。

## R. 裁定 (§P の解釈割れ — 実装用、2026-07-22 オーケストレータ裁定)

1. **PA38**: **spec どおり警告のみ — purge は進む。現行の hard block (KIO-E-PURGE-WORKING-COPY-001) は廃止**。spec 規範文は「必ず警告する + 恒久的除外には原本削除または .kioignore 追加を案内」という「進めて案内する」設計を明記しており、同一 path/別名の区別もしない (同一 bytes 残存の全ケースで警告)。
2. **PA46**: **sidecar 方式** — journal 本体には closure の導出済み参照 (sidecar パス + 内容 hash) を置き、実体は `.kio/purge/journal-closure` (単一 JSON・同じ temp+rename+fsync 規律) に確定保存する。MAX_PURGE_JOURNAL_BYTES (8 MiB) は torn/DoS 防御として維持。「prepared で確定・以後再計算しない」原則は sidecar 内容に適用。
3. **PA34**: **対象 chunk_id 一致の行削除** (raw_hash 間接は chunks 表経由で chunk_id 集合に落ちるため同値)。chunk_publications テーブルの DDL 新設は P2-C (PC38-39 の時点条件実装) と同時に行い、その時点で本契約を具体化する。

---

## Q. 集計

| 領域 | 契約数 | P0 | P1 | P2 |
|---|---|---|---|---|
| §A (U22, PA01-07) | 7 | 4 (01,03,04,06) | 3 (02,05,07) | 0 |
| §B (U23, PA08-10) | 3 | 2 (08,09) | 0 | 1 (10) |
| §C (U24, PA11-15) | 5 | 1 (12) | 4 (11,13,14,15) | 0 |
| §D (U25, PA16-19) | 4 | 2 (16,17) | 1 (18) | 1 (19) |
| §E (U26, PA20-26) | 7 | 5 (21,22,23,24,25) | 2 (20,26) | 0 |
| §F (U27, PA27-29) | 3 | 0 | 3 (27,28,29) | 0 |
| §G (U28/29/30, PA30-32) | 3 | 2 (31,32) | 1 (30) | 0 |
| §H (U31, PA33-34) | 2 | 0 | 2 (33,34) | 0 |
| §I (U32, PA35) | 1 | 0 | 1 (35) | 0 |
| §J (U33, PA36) | 1 | 1 (36) | 0 | 0 |
| §K (U34, PA37-39) | 3 | 0 | 2 (37,38) | 1 (39) |
| §L (U37, PA40-41) | 2 | 2 (40,41) | 0 | 0 |
| §M (U38, PA42) | 1 | 0 | 0 | 1 (42) |
| §N (LC46 継続, PA43-46) | 4 | 2 (43,44) | 2 (45,46) | 0 |
| §O (restore ii〜iv, PA47-50) | 4 | 2 (48,50) | 2 (47,49) | 0 |
| **合計** | **50** | **23** | **23** | **4** |

**契約数**: 50 件 (P0=23 / P1=23 / P2=4、目安 45-65 に適合)。**解釈割れ注記**: 3 件 (§P)。
