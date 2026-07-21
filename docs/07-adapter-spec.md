# 07 Adapter Spec

Adapter (Prepare / Markdownize / Embedding / Summary / Classification / Rerank) の trait 契約 + 実行形態 + Markdown incremental プロンプト規約。

> 関連: [03-data-model.md §5](03-data-model.md) (`tool_profile_hash` 計算規約) / [04-pipeline.md §3](04-pipeline.md) (incremental Markdownize) / [06-cli-spec.md §9](06-cli-spec.md) (Agent/Adapter API)

---

# 1. 基本方針

Prepare / Markdownize / Embedding / Summary / Classification / Rerank は KCS core に含めず、**Adapter に委譲** する。OCR は Markdownize Adapter の **内部能力 (capability)** として扱う。Embedding は Text / Image を分離せず、**単一マルチモーダル Embedding Adapter** に統合する。

```
KCS core:                 Adapter:
  object store              Prepare
  snapshot                  Markdownize (OCR は内部能力)
  restore                   Embedding (multimodal)
  search                    Summary       optional
  task state                Classification optional
  common KCS API            Rerank        optional
```

Adapter の実行設定 (cmd / args / url / 認証情報) は **`.kcs/` の共有対象に含めない**。各デバイスの `~/.config/kcs/tools.toml` や OS keychain に保存する。`.kcs/` は生成済み artifact の provenance と互換性判定に必要な `profile_hash` だけを保持する。

R23 の同梱 runtime が実行できる online target は `mistral_ocr_markdownize` と
`gemini_embedding_2` の built-in 実装に限定する。これらの role では `cmd` / `args` /
`url` による実行先の差し替えを受理せず、宣言された model と built-in target の一致を
起動時と実行直前に検証する。上記の実行設定フィールドは将来の外部 Adapter 契約用であり、
現在の built-in role の設定方法ではない。

認証情報の保存規約:

```text
推奨 (優先順):
1. OS keychain 参照:   auth = "keychain:<service_name>"
2. 環境変数参照:       auth = "env:GEMINI_API_KEY"

許容 (非推奨):
3. tools.toml 直書き:  auth = "plain:<api_key>"
   - tools.toml の permission が 0600 (owner read/write のみ) でない場合、
     KCS は起動時に warn を出す (errors.jsonl に level=warn で記録)

禁止 (既定どおり):
   .kcs/ 配下・tool-lock.json・tool_profile_hash の入力への認証情報の混入
```

`tools.schema.json` は `auth` フィールドを `^(keychain|env|plain):` にマッチする文字列
として規定する ([06-cli-spec.md §11](06-cli-spec.md))。

---

# 2. 実行形態

Adapter は **提供主体ではなく実行形態と決定性** で分類する。

```
online_api               LLM 等のネットワーク越し API (frontier AI が中心)
                         明示的な network opt-in が必要
offline_api              ローカル LLM / ローカル embedding server
                         ネット送信なし。非決定的出力はあり得る
deterministic_library    決定論的ライブラリ (PDF text extraction, parser)
                         同じ入力 + 同じ profile なら同じ出力
```

KCS API の契約は実行形態に依らず同じ。

```
KCS core
  → task descriptor (task_id, adapter_kind, input_hash, allowed scope, network permission)
  → device-local Adapter
  → artifact descriptor (output_hash, status, error_code / error_category)
  → KCS core
```

## 2.1 同梱 deterministic Adapter (ベースライン index)

KCS は `deterministic_library` の Prepare / Markdownize Adapter を同梱する。対象: plain text / Markdown / コード、PDF text layer 抽出。OCR・レイアウト解析・画像理解は行わない。**出力は単純な passthrough ではなく、Normalized Markdown v1 (§5.2.1) への決定的正規化**である — 少なくとも Setext 見出し → ATX 変換・生 HTML block の fenced text 化・改行 / 空白 / fence の正規化を行う (§5.2.1 準拠が受け入れ検査 V5 の通過条件のため、passthrough では通常の Markdown (Setext 等) がオフライン基線 index で全滅する)。

- online Adapter が未設定または network 未承認のとき、Markdownize タスクは同梱 deterministic Adapter で実行する (タスクを止めない)。Embedding タスクは生成しない (検索は text fallback、[05-runtime.md §1](05-runtime.md))
- この状態を **ベースライン index** と呼ぶ。`init → index --approve → search → open <pointer>` の最低体験ライン ([01-positioning.md §3](01-positioning.md)) はベースライン index のみで成立しなければならない
- online Adapter を承認した後の AI 強化は、別 `tool_profile_hash` の artifact として通常の Markdownize / Embedding タスクで生成する (identity 規約 [03-data-model.md §5](03-data-model.md) のとおり。ベースライン artifact とその Evidence Pointer は不変のまま残る)

---

# 3. ネットワーク送信原則と opt-in (正本)

KCS core は、**明示オプトインなしにネットワーク越し API へファイル内容を送信してはならない**。
本節を network opt-in の正本とし、[06-cli-spec.md §2](06-cli-spec.md) / [10-operations.md §1](10-operations.md) / [01-positioning.md §1.1](01-positioning.md)
は本節を参照する。

```text
default: no network transmission (opt-in 未成立の scope からはオンライン送信しない)
```

opt-in の単位・成立・寿命:

```text
単位:   scope × adapter
        (どの .kcs のファイルを、どの online_api Adapter (tool_id) に送るか)

成立:   (a) 初回スキャン承認フローで network transmission policy を承認
            (対話承認 または --approve。--yes では成立しない: 06-cli-spec.md §2)。
            **承認の成立 = approvals[] 行の materialize と、同一承認操作での scope config
            `allow_network = true` の設定の両方** (送信 gate は boolean と行の AND —
            行だけでは送信が有効にならない)
        (b) 明示設定: .kcs/config.toml の adapter.policy.allow_network = true —
            **boolean 単独では送信 gate (boolean × 行の AND) を満たさない**。行の materialize は
            承認操作 (対話 / --approve) のみで、config の手編集は kill switch の解除・意思表示に
            留まる (**例外 = 下記の初回 materialize**: `approvals_initialized` marker が無く
            approvals[] が空の**初回に限り**、最初の 1 tool を自動 materialize する — それ以外は
            crash 中間 (true × 行なし) との区別のため自動 materialize をせず、送信可能化には
            (a) の承認操作を要する)

寿命:   永続 (revoke まで)。ただし対象 Adapter の tool_id・execution_mode・tool_profile_hash の
        いずれかが変わった場合は失効し、再承認を要する (profile に畳み込まれる設定 —
        `[markdownize].bbox_annotation` 等 — の変更も含む。照合の実体は下記「記録」の送信 gate)。

revoke: adapter.policy.allow_network = false に設定する (これは **scope 全体の kill switch** —
`--online` の一時 opt-in でも上書きされない。下記「優先関係」の例外)。
単一 Adapter だけの revoke は approvals[] 当該行の **status=revoked + revoked_at への更新**で行う
(opt-in 単位 = scope × adapter に対応する既存機構 — 下記)。**効果は当該 Adapter の新規送信停止に
限り、他 Adapter の active 承認と `allow_network` boolean は変えない**。**revoke は単一 Adapter では同一
(scope_id, tool_id) の `approval_pending` を execution_mode / tool_profile_hash 不問で同一 atomic write
除去し、`--all` は tool を
問わず存在する全ての `approval_pending` を除去する** — 未 publish の
pending intent を残さない (行 publish 前に revoke した場合に、次回実行の self-heal が承認を
復活させる経路の封鎖 — 別 tool の crash 残存 pending も `--all` で残さない。**4 組一致に限ると**、
profile 変更後の revoke が旧 profile の pending を取り逃し、config を戻した後の self-heal が
revoke 直後の承認を復活させる — pending は未 publish の intent であり、広めの除去は再承認要求に
なるだけで安全側)。**加えて、revoke が
pending の除去または行の revoked 化を実際に実行した場合、`approvals_initialized` marker が無ければ
同一 atomic write で `approvals_initialized: true` を記録する** (初回 materialize 例外の消費 —
pending が唯一の区別子である crash 中間 (true × 行ゼロ × marker 無し) で revoke 後の次回実行の
(b) 初回 materialize が、直前に revoke した承認を復活させない)。対象なし (行なし・
pending なし・既 revoked) は冪等成功 (exit 0 + 「対象なし」表示 — **marker も書かない**: 未使用
scope の初回 materialize 経路を revoke の空振りで消費しない)。**単一 Adapter revoke の実行主体 = `kcs adapter revoke <tool_id>`**
([06-cli-spec.md §1](06-cli-spec.md) — `.kcs/.lock` 下の locked mutation、[05-runtime.md §6](05-runtime.md))。
承認側の行 publish・self-heal も同じ lock 下で行い、**publish の直前に `approval_pending` の存在を
再検証する** (CAS — 並行する revoke が除去した pending を publish しない)。明示承認コマンド
(対話 / --approve) はこの再検証の不一致を**明示エラー (KCS-E-ADAPTER-APPROVAL-CONFLICT-001 / exit 5 —
並行 revoke との競合・再承認が必要) で終端する** (無音の no-op
成功にしない。self-heal は発火条件不成立として非発火のままでよい)。
        新規オンライン送信 task の発行停止は、kill switch では scope 全体・単一 Adapter revoke では
        当該 Adapter 分のみ (送信済みデータの取り消しは、どちらの revoke でも保証しない。**発行停止の
        境界 = 相 1 claim Tx 内 (`BEGIN IMMEDIATE` 保持下) の最終再読 ([05-runtime.md §1.1](05-runtime.md)) — 再読後に完了した
        revoke の当該送信は in-flight として許容**)。

記録:   承認記録に scope_id / tool_id / **execution_mode / tool_profile_hash (承認時点)** /
        approved_at / approval_method を残す。送信前に現在の execution_mode / profile と照合し、
        不一致 = 失効 (再承認要求) — 保存しないと「変わった場合は失効」を永続状態から判定できない。
        **保存先 = `.kcs/scope.json` の `approvals[]` 配列** (schema 検証対象
        [10-operations.md §12.3](10-operations.md)、truth [03-data-model.md §4.1](03-data-model.md))。
        `(scope_id, tool_id)` 単位の行で、失効・revoke は当該行の **status=revoked + revoked_at への
        更新** (atomic rename) で行う (行は削除しない — 監査保全)。送信 gate は
        「`allow_network` の実効設定が true であり (**未設定・設定 key の喪失は gate 不成立** —
        active 行が現存する場合は config へ true を再設定するだけで回復し、再承認は不要)、**かつ**
        行の scope_id が当該 scope.json の scope_id と
        一致し、現在の execution_mode / tool_profile_hash に一致する `status=active` 行が存在する」の
        両立とする (**scope_id 不一致の行は gate に使わない** — fork 複製由来の旧 scope 行の残存で
        再承認を迂回させない。[06-cli-spec.md §10](06-cli-spec.md))。**`--online` の一時 opt-in は
        この gate の唯一の例外** — 「優先関係」のとおり opt-in 未成立の既定閉鎖のみを上書きし
        (approvals[] 行は作らない)、consent 由来 `cli_online` として §7 の log に記録する。明示
        revoke (`allow_network = false`・行の revoked) は上書きしない。
        `approvals[]` 要素の required field = scope_id / tool_id / execution_mode /
        tool_profile_hash / approved_at / approval_method / **status (`active` | `revoked`)** —
        status=revoked の行は **revoked_at** も必須 ([10-operations.md §12.3](10-operations.md) の
        schema 定義と一致)。status を持たない legacy 行は `active` として読む (10 §12.3 の
        要素単位後方互換 — schema error にしない)。
        初回スキャン承認 (10-operations.md §1) の記録とは別物 — あちらは scope 単位の
        取り込み承認、こちらは adapter 単位の network opt-in。
        (b) の config boolean は scope 内の全 online_api Adapter の**送信 gate 条件** (false で全停止)
        であると同時に、**scope で最初に実行される 1 Adapter に限り approvals[] 行を materialize する
        意思表示**として扱う —
        行 materialize 後は (a) と同じ照合・失効規則に従う (tool_id 個別の可否は approvals[] が
        単位。boolean だけでは profile 変化の失効を判定できないため、行なしでの送信は不可)。
        **materialize が発火するのは当該 scope の approvals[] に行が (tool_id を問わず) 一つも
        存在せず、かつ scope.json に `approvals_initialized` marker が無い初回、その最初の 1 tool に
        対してのみ**。初回承認 (materialize / --approve のいずれも) は行 publish と**同一 atomic
        write** で `approvals_initialized: true` を記録する ([10-operations.md §12.3](10-operations.md) の
        optional key) — 以後 approvals[] が空になっても (手動編集・不整合 backup 復元等)、行ゼロ ×
        marker あり は真正初回と区別して **fail-closed (明示承認要求)** とする (行ゼロだけでは台帳
        喪失と初回を区別できない)。marker は行と同時に書かれるため、承認途中の crash 中間 (true ×
        行なし × marker なし) では self-heal が成立する — ただし**完遂できるのは下記
        `approval_pending` (pending intent) と 4 組完全一致の tool のみ** (crash 後に config /
        Adapter 構成が変わって「最初の 1 tool」が別 identity になっても、承認したのと別の
        Adapter を materialize しない)。2 個目以降の tool_id や tool_id が
        変わった Adapter は、boolean が true のままでも自動生成せず明示承認 (対話 / --approve) を
        要する (新 identity への blanket 波及を許すと、上記寿命規則の「tool_id が変わった場合は
        失効し、再承認」を『新規行の初回 materialize』として迂回できてしまう)。profile 変更で
        失効した行や revoked 行が存在する場合も同様に再承認を要する (残存 boolean による失効迂回の禁止)。
        承認操作の書込順は **(0) pending intent = 承認対象の 4 組 (scope_id / tool_id /
        execution_mode / tool_profile_hash) + 公開行の監査値 (`approved_at` / `approval_method`) を
        scope.json の `approval_pending` key へ atomic に
        耐久化 → (1) config.toml (`allow_network = true`) を耐久化 → (2) approvals[] 行 + marker を
        publish し、同一 atomic write で `approval_pending` を除去** (self-heal は pending の payload
        をそのまま publish する — 監査値を補完・捏造しない) — 途中で crash した中間
        (true × 行なし) は、次回実行の self-heal が **`approval_pending` と完全一致する場合に限り**
        行 publish を完遂する (pending 記録が無い・一致しない中間は自動生成せず明示承認 (対話 /
        --approve) を要求する)。`approval_pending` の schema は
        [10-operations.md §12.3](10-operations.md) — **approved_at / approval_method を欠く legacy
        pending は schema error にしない**: 完全一致不成立として self-heal の対象外であり、次回
        locked mutation で除去して明示承認を要求する (10 §12.3 の要素単位後方互換)。**この除去も
        `approvals_initialized` marker が無ければ同一 atomic write で true 化する** (revoke の pending
        除去と同型の初回 materialize 例外の消費 — 除去だけで marker を残さないと「true × 行ゼロ ×
        marker 無し」= 真正初回条件が復活し、次回実行の (b) 初回 materialize が「明示承認を要求する」
        を無音で迂回する。対象なしでは書かない)。**scope 全体の revoke** は逆順 (全行の revoked 化 → boolean false) — 中間
        (revoked × true) は gate の AND で送信不能 (安全側) のまま恒久に安全であり、**boolean の
        false 化は kill switch 操作 (config 編集) 側の責務 — 自動整合はしない** (`kcs adapter revoke
        --all` の終状態 (全行 revoked × true、[06-cli-spec.md §1](06-cli-spec.md) の「boolean は
        変えない」) と scope 全体 revoke の crash 中間を状態だけでは区別できないため。
        **単一 Adapter revoke は当該行の更新のみ**)。
```

CLI フラグ `--online` は **その 1 回の実行に限る一時 opt-in** で、**永続的な承認状態
(`approvals[]` 行) を作らない** (実行の送信記録は §7 の log に残り、consent の由来 —
approvals / cli_online — を含める)。`--offline` は逆向きの一時上書きで、当該実行の新規送信を
禁止する (未送信の online タスクは **pending のまま**当該実行では送信しない — 永続状態・
hold_reason は変更しない ([04-pipeline.md §5.2/§5.4](04-pipeline.md) — enqueue のみ + index_status に
pending 可視化)。`--override-budget` と併用した場合も budget pause の解除のみ行い、送信はしない)。
適用対象は online 作業を駆動し得る全コマンド
(`kcs index` / `kcs batch resume` / `kcs batch retry` / `kcs reindex` — `--force` / `--at <commit>`
のいずれも online embedding を駆動し得る — / `kcs repair --rebuild-db` (rebuild 後の enrichment —
[04-pipeline.md §5.4](04-pipeline.md)) / **`kcs search` — vector|hybrid の page 1 の query embedding**
([05-runtime.md §1.1](05-runtime.md) の consent gate: payload は query 文字列のみ。送信可否 = 参加
scope の 1 つ以上に当該 embedding Adapter の active 承認 — 承認ゼロは text fallback / `--vector` は
error。課金は `scope_id='device'` — [04-pipeline.md §5.4](04-pipeline.md))。[06-cli-spec.md §1](06-cli-spec.md))。**既存 in-flight
request の照会・出力取得・upload 掃除 ([04-pipeline.md §5.8](04-pipeline.md) 回復) は新規送信に
当たらず、opt-in / `--online` なしで実行できる** (opt-in が制御するのは新規 upload・job 作成・
sync 呼出のみ)。
優先関係は次のとおり:

```text
CLI (--online / --offline)  >  .kcs/config.toml (scope)  >  ~/.config/kcs/config.toml (user)
```

この優先で `--online` が上書きできるのは **opt-in 未成立 (`allow_network` 未設定) の既定閉鎖**である。
**明示 revoke (`allow_network = false` の明示設定) は `--online` より優先する** (kill switch の趣旨 —
解除は config の再変更のみ。`--offline` 側は常に最優先で当該実行の新規送信を禁止する)。

**01-positioning.md との整合**: デフォルト同梱 Adapter は online_api (frontier AI) だが、
初回スキャン承認で network transmission policy に同意するまで送信は始まらない。
"frontier AI default" は同梱・推奨構成を指し、"default: no network transmission" は
opt-in 未成立状態の既定値を指す。両者は矛盾せず、初回スキャン承認フローが接続する。

オンライン API Adapter を使う場合、ユーザーがどの scope / file / task を送信対象にしたかを
記録する。オフライン API / 決定論的ライブラリの場合も `execution_mode` と `profile_hash` は
記録する。

---

# 4. 共通メタデータ

すべての Adapter は次を返す:

```
AdapterProfile:
  adapter_kind          "prepare" | "markdownize" | "embedding" | ...
  adapter_id
  execution_mode        "online_api" | "offline_api" | "deterministic_library"
  tool_profile_hash     計算規約は 03-data-model.md §5.1
  version
  capability_flags      ["ocr", "layout_detection", "incremental_update", ...]
  billable_kinds        billable を宣言する Adapter (§5.7 条件 6) は必須 — 報告し得る
                        `billable_units.kind` の閉集合 (拒否課金の有無の宣言 = 下記 `reject_billing`)。
                        **実行時 usage の kind が宣言集合外の場合は課金 field の不良として
                        estimated 縮退 + warning ([04-pipeline.md §5.4](04-pipeline.md) — 応答の
                        受否・outcome・`contract_violation_count` は変えない)**。宣言集合の執行面は
                        送信前の pricing 被覆検査の入力 ([10-operations.md §12.3](10-operations.md))
  reject_billing        billable を宣言する Adapter (§5.7 条件 6) は必須 — "billable" | "nonbillable"
                        の閉 enum (投入拒否 (permanent 4xx) に課金する provider か否かの機械可読宣言。
                        billable_kinds と同じく出力非影響 = tool_profile_hash 非対象。legacy / 未知値
                        は fail-closed = "billable" として扱う)。usage 欠落の permanent 4xx を
                        「正当な非課金 reject (確定額 0)」と「billable provider の欠落 (estimated
                        縮退)」に分離する判定源 ([04-pipeline.md §5.4](04-pipeline.md))
  allow_network

AdapterRun:
  task_id
  input_hashes
  output_hashes
  status                "pending" | "running" | "done" | "partial" | "failed"
                        (partial = unit 単位の部分失敗, 04-pipeline.md §5.2。正常な制御応答
                         (fallback_to_full) は request として成功 = "done" — outcome の区別は
                         cost_ledger 側 ([04-pipeline.md §3.2](04-pipeline.md)))
  error_code            機械判定用 (06-cli-spec.md §8)
  error_category        transient | permanent | rate_limit — 04 §5.3 の retry 分類の入力
                        (集計用の粗分類 — auth / quota / invalid_input 等の細分は error_code が
                         担い、retry 対応は 04 §5.3 の表が error_code 基準で優先する)
  retry_after_ms        optional — provider の Retry-After を透過 (rate_limit 時)
  usage                 one-of { usd } | { billable_units } — request 単位の課金報告 (§5.7)。
                        usd = 有限・非負の実測額 (billable reject では provider が宣言する請求額を
                        これに充てる — §5.7 条件 6。第三の field は設けない)。billable_units =
                        **unique-kind の配列** `[{ kind, count }, ...]` (1 要素以上。kind = "pages" |
                        "tokens_in" | "tokens_out" の閉 enum — 拡張は spec 改訂。count = 非負整数。
                        **kind の重複は課金 field の不良 (estimated 縮退 + warning —
                        [04-pipeline.md §5.4](04-pipeline.md))**。USD 換算は要素ごとの単価 × count の**合算** —
                        input/output token 両課金の provider を単一報告で表現する)。単価解決元 = tools.toml の
                        `[pricing]` 単価表 (kind → USD 単価 — [03-data-model.md §11](03-data-model.md)、
                        **単価の正本は tools.toml** — tool-lock ではない。schema 型と billable Adapter の
                        kind 被覆必須は [10-operations.md §12.3](10-operations.md)、kind の単価が解決
                        不能な場合の終端は estimated 縮退 — [04-pipeline.md §5.4](04-pipeline.md))。**換算は終端 Tx
                        時点の表で確定し、以後の単価変更で再計算しない** (台帳 UPDATE 禁止と整合)。
                        **billable な terminal 応答 (成功・billable reject・fetch_output・sync 応答・
                        正常な制御応答 (fallback_to_full — [04-pipeline.md §3.2](04-pipeline.md)))
                        で必須** — 欠落・不正値は estimated 記帳へ縮退する ([04-pipeline.md §5.4](04-pipeline.md)
                        の記帳値事前検証と同一規範 — **応答の受否・outcome・violation 予算は変えない**)
```

---

# 5. 各 Adapter の trait

## 5.1 Prepare

```
input:
  raw_hash, media_type
output:
  prepared_object_hashes
  prepared_unit_hashes        (page / slide / sheet / image 単位)
  image_object_hashes         (画像抽出があれば)
metadata:
  unit_kind, page_number, mime, fingerprint (semantic_fingerprint)
```

PDF page image、Office intermediate、抽出済み image など、後続 Markdownize / Embedding が扱いやすい単位を作る。

## 5.2 Markdownize

OCR は独立 Adapter ではなく **本 Adapter の capability** として表現する。

```
input:
  raw_hash, media_type
  prepared_unit_hint          (optional)
  mode                        "full" | "incremental"
  previous (incremental 時のみ): { raw, normalized_units, tool_profile_hash }
  hints (incremental 時のみ):   { changed_unit_keys, added_unit_keys, removed_unit_keys, page_fingerprints }
  tool_profile_hash
  spec_version
output:
  mode_used                    "full" | "incremental"
  updated_units / added_units / removed_unit_keys / unchanged_unit_keys
  failed_units                 [{ unit_key, error_kind }] — 部分失敗の unit (error_kind は
                               [04-pipeline.md §5.3](04-pipeline.md) の閉 enum。04 §3.2 V1 の被覆に
                               含める (full は V6 の被覆)。persist されず manifest 側で failed へ遷移
                               — partial の表現手段)
  fallback_to_full             bool
  reason
  # Evidence Pointer は Adapter output に含めない — 必須フィールド (chunk_hash / commit) は
  # chunking と snapshot の後にしか存在しないため、発行は KCS core が行う (08 §2.1)
capability_flags:
  ocr, layout_detection, table_extraction, speech_to_text, incremental_update
```

incremental の詳細プロンプト規約は §8 (生成 LLM 系のみ。§8 冒頭の適用範囲を参照)。

**標準 Adapter (非 text-native)**: PDF / DOCX / PPTX / 画像の Markdownize 第一候補は Mistral OCR 系文書処理 API (`mistral_ocr_markdownize`) とする (経緯: 旧 `research/markdown.md` — git 履歴)。規約:

- 表は Markdown 本文に inline で保持する (`table_format=null` 相当)。独立 table object は作らない。
- 文書内 embedded image は抽出して image object ([03-data-model.md §2](03-data-model.md)) として保存し、Markdown 内の参照は `kcs://<scope_id>/object/image/<image_hash>` に置換する ([08-evidence-pointer-spec.md §2.3](08-evidence-pointer-spec.md))。実装は Step 2 ([09-mvp-scope.md §3.1](09-mvp-scope.md))。
- bbox / page / confidence score は unit metadata に記録する。**Evidence Pointer の必須 schema には含めない** (optional フィールドとしての露出は Phase 4+ 判断。forward compatibility は [08-evidence-pointer-spec.md §8](08-evidence-pointer-spec.md))。
- **図中テキストの検索可能性 — bbox_annotation を採用 (2026-07-04 実 API 境界調査で確定)**: 実測
  (`experiments/ocr-verification`、段階 fixture C0-C5 + 曖昧画像 15 枚) により、表は複雑・ラスタ化でも
  100% textize される一方、**チャート/グラフ内テキスト (軸ラベル・凡例・値) は 100% images[] へ消失**
  し (C3 が境界)、ホワイトボード写真風は ~55%、フロー図入りスライドは ~41% を失うことを確認。
  対策として Mistral の **bbox_annotation (+25% コスト) を既定 ON** とし、images[] として返る領域の
  説明+書き起こしを取得して unit metadata に記録し、chunk 化時に image 参照近傍へ検索可能テキスト
  として取り込む (`.kcs/config.toml` の `[markdownize] bbox_annotation = true` (既定) で制御 — folder-config schema の正式 key ([10-operations.md §12.3](10-operations.md))。**値は出力に影響するため tool_profile_hash に畳み込む** = 切替は世代判定に乗る)。Markdownize は文書 1 版につき 1 回のコストであり
  incremental 再利用でさらに希釈されるため +25% は budget 内。生成 LLM (Gemini Vision) による二次
  Markdownize fallback は annotation で不足する場合の Phase 4+ 保留のまま。実装は Step 4 (契約は
  step4a で確定)。
  - wire は次の exact `bbox_annotation_format` JSON Schema 1 個を使い、説明/書き起こし指示は schema
    field description に固定する (bbox 専用 prompt parameter は使わない)。各 `pages[].images[]` の
    `image_annotation` は `short_description` / `transcribed_text` の厳密 JSON とする。JCS byte 列の
    sha256 `sha256:9404f8ffe2983113f082d255a61817ad0798e74aeb82cb5063a391fbcbea9ca8`
    を enabled profile の `prompt_template_hash` とする

    ```json
    {
      "type": "json_schema",
      "json_schema": {
        "name": "kcs_bbox_annotation_v1",
        "strict": true,
        "schema": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "short_description": {
              "type": "string",
              "description": "Describe the figure briefly in plain text. Do not use Markdown or HTML."
            },
            "transcribed_text": {
              "type": "string",
              "description": "Transcribe all visible text verbatim in plain text. Do not use Markdown or HTML."
            }
          },
          "required": ["short_description", "transcribed_text"]
        }
      }
    }
    ```

  - annotation text は newline→LF / NFC / non-newline-control 除去後、provider 由来の各行を次の exact
    CommonMark source escape に通す: original `&`→`&amp;`、`<`→`&lt;`、`>`→`&gt;`、それ以外の
    ASCII punctuation (`U+0021..002F`, `U+003A..0040`, `U+005B..0060`, `U+007B..007E`) は文字の前に
    `\` を 1 個付け、その他は変更しない。変換後の各行を trusted prefix
    `> KCS figure description: ` / `> KCS figure text: ` の後へ置き、対応 image URI 直後の persisted
    unit Markdown に入れる。unit metadata にも同じ post-escape strings を保持し、検索 bytes と Evidence
    span の元を一致させる。この変換後の CommonMark AST は provider 由来の link / image / raw HTML /
    autolink node を 1 件も含んではならない
  - 上限は image 256/page・4,096/response、description 4 KiB、transcription 64 KiB、aggregate
    16 MiB、bbox coordinate 0..=1e9 かつ positive area。string/aggregate byte 上限は untrusted response
    decode 時と上記 canonical escape 後の両方で検査し、膨張後も超過を許さない。annotation
    policy/profile は task identity に含め、既存 annotation 無し Done task を default-on の完了扱いにしない
- 生成 LLM (Gemini / Claude / GPT 等) は Markdownize の主処理ではなく、OCR 後の品質検証・図表解釈・summary (§5.4) に使う。

> **実地検証済み (2026-07-03、設計宿題 #6 解消 [09-mvp-scope.md §5.5](09-mvp-scope.md))**: 合成 fixture (複雑表・日本語・数式・埋め込み画像、4 ページ) を sync / Batch 両モードで検証: 表セル一致率 1.0 (17/17)、日本語 CER 0.0、画像抽出 1/1 (placeholder 形式も §5.2 想定どおり)、数式は LaTeX でテキスト化。単価は公称一致 (API $4 / Batch $2 per 1,000 pages)、Batch のジョブ往復は 4 ページで約 24 秒。ハーネスと実測ログは `experiments/ocr-verification`。検証が崩れた場合の fallback (生成 LLM 系 §8.2 へ戻す) の設計は維持する。Batch trait の `list_uploads` / `provider_scope_id` / pagination の契約試験は未実施 — Step 3 実測に含める。

## 5.2.1 Normalized Markdown 形式 (最小凍結 — 2026-07-18)

全 Markdownize Adapter の出力 (normalized unit の Markdown) は次の最小形式に従う。chunk span と
Evidence Pointer のバイト位置は保存された bytes に対して定義されるため、**この形式は実装後に
変えると互換性コストが高い** ([10-operations.md §11](10-operations.md)) — 以下を v1 として凍結する:

- **エンコーディング**: UTF-8 (BOM 禁止)、Unicode 正規化 NFC、改行 LF のみ、行末 trailing space 禁止、
  ファイル終端は LF 1 個
- **見出し**: ATX (`#`〜`######`) のみ (Setext 禁止)。chunk 境界規則 ([04-pipeline.md §4.1](04-pipeline.md))
  の入力
- **表**: GFM table 記法で inline 保持 (§5.2 規約と同じ — 独立 table object は作らない)
- **画像参照**: `![...](kcs://<scope_id>/object/image/<image_hash>)` のみ
  ([08-evidence-pointer-spec.md §2.3](08-evidence-pointer-spec.md))
- **生 HTML / autolink**: 禁止。**provider 由来の生テキストを Markdown 本文へ埋め込む場合は、由来を
  問わず §5.2 bbox_annotation と同じ CommonMark source escape を適用する** (`&` `<` `>` の実体参照化 +
  ASCII punctuation の `\` 前置 — bbox 専用の手順ではなく全 Markdownize 出力共通の規約)
- **code fence**: CommonMark の ``` fence (チルダ不可)。**fence 内の「無変換」は構文的変換 (escape /
  参照置換) の禁止のみを意味する — エンコーディング (UTF-8/NFC)・改行 (LF)・trailing space 禁止は
  fence 内にも適用する** (適用しないと CRLF/NFD を含むコードで v1 の byte 決定性が壊れる)
- 上記の準拠は KCS 側受け入れ検査 ([04-pipeline.md §3.2](04-pipeline.md)) の構造検証に含める

media 別の変換規約 (何を見出しにするか等) は Adapter 実装の裁量 (tool_profile_hash が識別する)。
本節が固定するのは**バイト表現の規約のみ**である。

## 5.3 Embedding (multimodal)

```
input_type:           "text" | "image" | "markdown_chunk" | "image_object" | "query"
input:
  items: [{ id, text|path, mime? }]
output:
  vectors: [{ id, vector }]
  dimensions, distance, modality
metadata:
  adapter_id, model_family, version, embedding_profile_hash
```

**Embedding 応答の受入検査** (markdownize の V1〜V6 に相当する): (1) `vectors[].id` は入力 id 集合と**全単射** (欠落・過剰・重複は違反)、(2) `dimensions` は profile と一致し全 vector が同次元、(3) 全要素が**有限値** (NaN/Inf 拒否) かつ**非ゼロ vector**、(4) float32 への決定的変換と **L2 正規化は core 側で実施**する (Adapter の正規化有無に依存しない)。**変換・正規化後の最終 vector にも (3) と同じ有限・非ゼロ (かつ単位ノルム — 許容誤差内) を再検査する** (underflow の零 vector / overflow の Inf を index に入れない — 違反は同じ contract violation)、(5) 応答 metadata の `embedding_profile_hash`・`modality`・`distance` が期待 profile と一致する (同次元の別 vector space の混入を契約で拒否する — 不一致は同じ contract violation)。違反応答は全体 reject — contract violation として課金・再試行は §5.8 相 3 と同じ規則に従う ([04-pipeline.md §5.8](04-pipeline.md)。再試行分類は [04-pipeline.md §5.3](04-pipeline.md))。`failed_units` 相当の部分失敗 field を持たない **all-or-nothing 契約は意図的**である (MVP は text chunk のみを embed し、失敗の粒度は request 再投入で足りる — Phase 4+ の multimodal 拡張で再検討)。

Text Embedding Adapter / Image Embedding Adapter は**採用しない**。同一 Embedding Adapter が同一 profile で多モダリティを単一 vector space へ写像する。

> **実地検証済み — 単一 multimodal profile を採用 (2026-07-03 再検証で確定)**: 初回調査は「Gemini Embedding 2 multimodal は preview で pin 不可」を根拠に text-only 緩和を適用したが、事実誤認 (`gemini-embedding-2` は 2026-04-22 に GA、pinned stable 版あり) が判明し**撤回**。再検証 (`tasks/step3-embedding-verify.md` の再検証節) により本節冒頭の本来の契約どおり **単一マルチモーダル Embedding Adapter** を採用する。確定 profile: **`gemini-embedding-2` (GA 版を Adapter が起動時解決して pin、§6) / 768 次元 (MRL 切り詰め — 切り詰め後次元も profile に固定) / cosine / `modality="multimodal"` / `mode="online"`** (Vertex はバッチ推論非対応のため sync 呼出 — client 側の並列は**タスク間** (別 batch_requests 行) で行い、単一タスク内の複数 request は直列 ([04-pipeline.md §5.4](04-pipeline.md) の縮退 2 相)。429 は rate_limit 分類で backoff — §5.7)。MVP で実際に embed するのは text chunk のみだが、profile を multimodal にしておくことで Phase 4+ の image/audio embedding を [03-data-model.md §7](03-data-model.md) の全 re-index なしに追加できる。text 品質は MTEB で前世代 text 専用モデルを上回り日本語も同格 (再検証節)。コスト: 10 万 chunk 初回 ≈ $10 (単月 budget 内)。**非 multimodal の embedding profile (`modality="text"` 等、別ベクトル空間への埋め込み) は採用不可** — tool-lock materialize / adapter 登録時に `KCS-E-EMBED-MODALITY-001` (exit 2) で拒否する ([03-data-model.md §7](03-data-model.md))。

embedding の SQLite schema (`embeddings` / `chunk_vec`) の正本は [04-pipeline.md §4.3](04-pipeline.md)
とする (本節は profile — モデル / 次元 / 距離 / modality — の正本。SQL 定義の重複記載は 2026-07-14 に
解消し、本節から参照する)。

sqlite-vec の制約で vector table を物理分割してもよいが、概念上は単一の Embedding Adapter / 単一の `profile_hash`。profile が一致しない場合、KCS は vector 検索を強行せず再生成または text fallback。

## 5.4 Summary (optional)

```
input:   normalized_refs | chunk_hashes | search_result_ids
output:  summary_hash
metadata: profile_hash, source_hashes, summary_kind
```

`normalized_refs` は normalized instance への参照 `(raw_hash, tool_profile_hash, gen)` ([03-data-model.md §2.1](03-data-model.md))。normalized の content hash は存在しない ([03-data-model.md §5](03-data-model.md))。

## 5.5 Classification (optional)

```
input:   raw_hashes | normalized_refs | chunk_hashes | image_object_hashes
output:  labels, categories, confidence, routing_metadata
metadata: profile_hash, label_schema_hash
```

## 5.6 Rerank (optional)

```
input:   query, candidate_result_ids, candidate_features
output:  reranked_result_ids, scores
metadata: profile_hash, searched_scopes, fallback_reason
```

Rerank Adapter は KCS の検索結果を再順位付けするだけで、**searched_scopes / fallback_reason を隠蔽してはならない**。

## 5.7 Batch 実行契約とプロバイダ採用条件

Batch モードを持つ online Adapter (Markdownize / Embedding) は、[04-pipeline.md §5.8](04-pipeline.md) の
2 相プロトコルが要求する次の操作を trait として公開する:

```
upload(bytes, filename)        client 指定の filename を受理する (intent_token 埋込のため)
create_job(inputs, metadata)   client 任意の metadata (intent_token + タスクキー 4 組) を job に付与できる
get_job(job_id) / list_jobs()  list は account/workspace scope 内の全件を pagination 走査でき、
                               どちらも create_job で付与した metadata を完全・不変に返却する
                               (帰属・orphan 報告の前提 — [04-pipeline.md §5.8](04-pipeline.md))
list_uploads()                 scope 内の upload を pagination 走査でき、filename (intent_token 埋込) で
                               照合できる — upload_id 記録前クラッシュの残骸発見の唯一の経路
delete_upload(upload_id)       404 (不存在) は削除成功として報告する
fetch_output(job_id)           出力 JSONL は入力ごとの custom_id (= unit_key) を保存して返却する
                               ([04-pipeline.md §5.8](04-pipeline.md) の unit 復元の前提)
provider_scope_id()            下記の不変識別子を返す
```

- **エラー分類の契約**: Adapter は失敗を transient (5xx / ネットワーク断)・rate_limit (429 —
  `Retry-After` があれば `retry_after_ms` で透過する)・permanent (内容起因の 4xx) の 3 分類で
  報告する (§4 の error_category と同一 enum)。分類と retry 予算の対応は
  [04-pipeline.md §5.3](04-pipeline.md) (rate_limit は Retry-After を解除条件とする retryable)
- **課金報告**: **request (job / sync 呼出) 単位** — 各 request の応答 / fetch_output に実測コスト
  (または単価計算に足る unit 数) を含めて報告する ([04-pipeline.md §5.4](04-pipeline.md) / §5.8 の
  request 単位記帳の前提 — 直列多 request task では各 request の終端 Tx が自身の実測 usage を持つ)。
  **機械契約は §4 AdapterRun の `usage` field (one-of: `usd` | `billable_units`) — billable な
  terminal 応答で必須**。報告値が cost ledger の記録源である
- **provider_scope_id**: `adapter 名前空間 + account 不変 ID (+ workspace 不変 ID)` の連結。表示名・
  alias 等の可変値は使わない。値は「これから呼び出す client instance」から取得する

**Batch プロバイダ採用条件** (満たさない provider は sync 呼出のみで採用するか、採用しない):

1. job 一覧照会 (または token による job 発見) と **upload 一覧照会**が可能であること — これが無いと
   未記録 in-flight・未記録 upload 残骸の回復が構造的に不可能になる
2. job 作成 → 一覧可視化の遅延に上限があること (KCS の可視化猶予 既定 10 分以内)。**upload →
   一覧可視化にも同じ上限を適用する** ([04-pipeline.md §5.8](04-pipeline.md) の upload 照合が前提とする)。
   upload() は upload_id を返し (返却型必須)、list_uploads は pagination を提供すること
3. job / 一覧情報の保持期間が KCS の回復期限 (既定 48h) 以上であること
4. job metadata / filename に client 任意の識別子 (intent_token) を埋め込めること
5. account / workspace の**安定した**識別子を取得できること (取得不能なら reservation の照合が恒久
   unknown になり、`kcs batch abandon` 頼みの運用になる)
6. 投入拒否 (permanent 4xx) にも課金するか否かを宣言すること。**課金する provider の Adapter は、
   拒否応答時に usage (`usd` = 宣言請求額 | `billable_units` — §4 の one-of と同形、第三の field は
   設けない) を機械可読で返却する** (この返却義務は Batch 限定で
   なく **sync online Adapter にも共通** — [04-pipeline.md §5.4](04-pipeline.md) の sync 記帳規律が参照する) — KCS は submit_rejected の
   terminal 化と同一 Tx で記帳する (**報告値が有効なら provider 値 (`estimated=0`)、無効・欠落は
   estimated 縮退** — [04-pipeline.md §5.4](04-pipeline.md) の事前検証と DDL 注記)

7. job id / provider request id が、同一 adapter_kind 内で account / workspace を跨いで KCS の
   回復期限 (既定 48h) 内に再利用されないこと (実質一意 — [04-pipeline.md §5.8](04-pipeline.md) の
   記帳済み判別が task key × job id を突合キーとする前提)

`mistral_ocr_markdownize` の Batch モードは 2026-07-03 の実地検証 (§5.2 末尾) の範囲でこの条件下で
採用済み。

---

# 6. tool-lock.json

`.kcs/tool-lock.json` は使用 Adapter の identity を記録する。実行可能情報 (`cmd`, `args`, `url`, 認証情報) は **絶対に含めない**:

```json
{
  "spec_version": 1,
  "prepare": {
    "tool_id": "prepare_default",
    "kind": "deterministic_library",
    "profile_hash": "sha256:..."
  },
  "markdown": {
    "tool_id": "mistral_ocr_markdownize",
    "kind": "online_api",
    "profile_hash": "sha256:...",
    "capabilities": ["ocr", "layout_detection", "table_extraction"]
  },
  "embedding": {
    "tool_id": "gemini_embedding_2",
    "kind": "online_api",
    "mode": "online",
    "dimensions": 768,
    "distance": "cosine",
    "modality": "multimodal",
    "profile_hash": "sha256:..."
  }
}
```

`tool_lock_hash` は **[03-data-model.md §5.2](03-data-model.md) の canonical 入力** (spec_version + 各 role の tool_id / profile_hash — embedding のみ + dimensions / distance / modality) を JCS 畳み込みした identity — **tool-lock.json 全体ではない**。`kind` / `capabilities` / `mode` は作業コピーの表示・検証用 field であり identity に含めない (toollock object へ保存されるのも §5.2 の canonical bytes)。

config (`~/.config/kcs/tools.toml`) では `mistral-ocr-latest` のような可変 alias を指定してよい。ただし **OCR API は応答内で alias を実バージョンに解決しない** (2026-07-03 実測: 応答の `model` フィールドは `mistral-ocr-latest` のまま返る。`experiments/ocr-verification`)。したがって Adapter は **API 呼び出し自体を版付きモデル名で行う**: alias が設定されている場合は、Adapter が実行開始時に提供元のモデル一覧 API から現行の版付き名を解決してから呼び出し、その版を `tool_profile_hash` の `model_version_pin` に記録する ([03-data-model.md §5.1](03-data-model.md) — 可変 alias の pin は禁止)。モデル更新は `tool_changed` として扱われ、再 Markdownize は first-instance-wins / gen の既存機構 (§9) に乗る。

---

# 7. Adapter 実行制約 (policy)

```toml
[adapter.policy]
allow_network = false
allowed_scope = "."
max_input_bytes = 104857600        # 100 MiB (= 100 * 1024 * 1024)
timeout_seconds = 300
redact_logs = true
store_request_body = false
store_response_body = false
require_command_confirmation = true
```

任意コマンド/任意 URL を使う外部 Adapter dispatcher は将来仕様とする。実装する場合は
**初回実行時** に command / URL / scope / network policy を preview し、ユーザー承認を
得るほか、command allowlist、secret redaction、ログ本文禁止を前提にする。R23 の
Markdownize / Embedding runtime にはこの dispatcher と承認経路はなく、`cmd` / `args` /
`url` を設定しても実行せず schema error とする。

ログに残してよいもの:

```
task_id, adapter_id, tool_profile_hash, execution_mode, scope_id
input_raw_hash, output_hash
status, error_code, error_category, retry_after_ms
network_consent (approvals | cli_online — 送信を伴った実行のみ)
started_at, finished_at
adapter_kind, input_hash, intent_token, submission_seq
usage_validation (missing | invalid), billing_source (estimated)
                             (非機微 — 課金 field 縮退の warning ([04-pipeline.md §5.4](04-pipeline.md)
                              の記帳値事前検証)。event code は KCS-EV-ADAPTER-USAGE-001)
                             (非機微。**cost_ledger / batch_requests への到達は 4 組 key
                              (scope_id, adapter_kind, input_hash, tool_profile_hash) +
                              submission_seq が正** — intent_token は補助 (成功行の batch_job_id は
                              provider request id を優先し token を保持しない)。input_raw_hash は
                              raw 由来 task 用で、device 行 (query embedding) の input identity は
                              input_hash 側。CAS で敗れた送信 ([04-pipeline.md §5.4](04-pipeline.md))
                              は回収側の unknown_settled 行に対応づく — 送信 log 件数と cost_ledger
                              行数が一致しないのは二重課金防止のための意図的挙動)
```

`adapter_id` は tools.toml の `tool_id` と同一値である (別 namespace を作らない — approvals[] (§3) の照合キーと一致し、実行 Adapter を承認行へ一意に対応付ける)。

残してはならないもの:

```
原文本文 / normalized 本文 / API request body / API response body / 秘密情報
```

## 7.1 強制モデルと信頼境界 (MVP)

MVP における Adapter の脅威モデルを次のとおり確定する。

```text
1. R23 で実行される Adapter は KCS 同梱の built-in target のみで、trusted code として
   扱う。将来の外部 dispatcher を実装する場合も、ユーザーが明示的にインストールし
   ~/.config/kcs/tools.toml に設定した Adapter だけを trusted code として扱う。

2. [adapter.policy] は「KCS 側の入力制御 + 事後監査」の規約であり、
   sandbox による強制保証ではない。
   - `max_input_bytes` は **AdapterRun 1 回の入力 (prepared input の canonical bytes 合計)** に
     適用する (**AdapterRun = 1 回の Adapter 呼出 = 1 request / job** — §4・§5.7 の課金報告と同一
     単位。task 全体の総量上限ではない — 総量は budget cap 側が律する) — 超過は送信前に当該 task を
     terminal failed (invalid_input・非再試行) とし、送信しない (課金なし)
   - KCS は allowed_scope 外のファイルを Adapter に渡さない (入力制御)
   - KCS は allow_network=false の Adapter にオンライン送信前提の task を発行しない
   - AdapterRun (task_id / input_hashes / output_hashes / status) を監査ログとして残す

3. 将来の外部 dispatcher における、悪意ある・侵害された Adapter プロセス自体の挙動 (allowed_scope 外の読み取り、
   allow_network=false 下での無断送信) は MVP では防御しない。
   OS レベルのサンドボックス強制は Phase 4+ の再設計論点とする。

4. 第三者 Adapter の配布・署名・検証 (サプライチェーン) は v2 以降のスコープ外。
   MVP で同梱・文書化するのは KCS 公式 Adapter のみ。
```

将来の外部 dispatcher に初回実行時の承認 UI を追加する場合は、この前提を反映した
文言にする (例: 「この Adapter はあなたの権限で実行されます。信頼できる提供元のもの
だけをインストールしてください」)。

---

# 8. Incremental Markdownize プロンプト規約

[04-pipeline.md §3.1](04-pipeline.md) で発動条件と入出力 schema を定義した。本節は **Adapter 内部のプロンプト規約** を固定する (Adapter ごとの揺れを防ぐため)。

**適用範囲**: 本節のプロンプト規約は**生成 LLM 系 Markdownize Adapter** に適用する。文書処理 API 系 (Mistral OCR 等、§5.2) は unit (page) fingerprint の再利用により変更 unit のみを再処理する経路 ([04-pipeline.md §2.2](04-pipeline.md)) で incremental を実現するため、プロンプト規約は適用されない。ただし §8.1 の 6 (受け入れ検査) と入出力 schema は**全 Markdownize Adapter 共通**。

## 8.1 Adapter が守るべき規約

```
1. "unchanged" と判断した unit は出力に含めない (旧 unit を再利用)
2. 変更 unit は完全に書き直す (部分編集ではなく full unit replacement)
   → Markdown の局所一貫性を保つ
3. heading 構造の変更は KCS には影響しない (chunk side で対応)
4. Adapter が「軽微とは言えない」と判断したら fallback_to_full=true で短絡
   (受理側は unit 検査に先立つ制御応答として扱い、同一 task を mode=full で再発行する —
   [04-pipeline.md §3.2](04-pipeline.md) の制御応答規則。full 応答での本 flag は contract violation)
   閾値の Adapter 側 hint は KCS 側 hint と衝突したら **KCS 側を優先**
5. spec_version 不一致なら、Adapter は invalid_input として失敗 (`KCS-E-ADAPTER-SPECVER-001` — 汎用 `KCS-E-ADAPTER-CONTRACT-001` (retryable 1 回) と区別し、[04-pipeline.md §5.3](04-pipeline.md) の invalid_input 分類 = max_attempts 0 に一意に対応させる)
6. 出力は KCS 側の受け入れ検査 (04-pipeline.md §3.2) を通過しなければ persist されない。
   違反は KCS-E-ADAPTER-CONTRACT-001 として reject され、**incremental capability 非互換の場合に
   限り** full に fallback する (spec_version 非互換は下記のとおり fallback しない)
```

`spec_version` の bump 規約は [10-operations.md §12.5](10-operations.md) を正とする。**full fallback (§8.4) が有効なのは incremental capability だけが非互換な場合に限る** — full request も同じ `spec_version` を含むため、spec_version 自体の非互換は full で呼び直しても同じ invalid_input を再生するだけである。この場合は `KCS-E-ADAPTER-SPECVER-001` (§8.1 手順 5 — invalid_input / 非再試行) として当該 online Adapter のタスクを failed permanent (Adapter 更新が必要) にし、同梱 deterministic Adapter のベースライン (§2.1) は影響を受けず継続する。

## 8.2 推奨プロンプト構造 (frontier AI 系)

```
SYSTEM:
  You are a markdownization adapter for KCS.
  Given the previous markdown of <unit_key> and the new raw input,
  produce updated markdown for changed units only.
  Keep unchanged units out of the output.

USER:
  Mode: incremental
  Tool profile: <hash>
  Previous markdown for changed units:
    <unit_key_1>: <markdown_1>
    <unit_key_2>: <markdown_2>
  New raw content (relevant pages only):
    <raw_excerpt>
  Hints:
    changed_unit_keys: [...]
    page_fingerprints: {...}

  If you judge the change as non-minor, return fallback_to_full=true
  with a brief reason. Otherwise return updated_units.
```

具体的な system prompt は Adapter 実装で固定し、`prompt_template_hash` (`tool_profile_hash` 入力フィールド) で identity に含める。

## 8.3 ストリーミング応答

大型 PDF (100+ pages) では TTFB を抑えるためストリーミング出力を許容する。KCS は Adapter からの SSE / chunked JSON を受け取り、unit 完了ごとに persist する。

ストリーミング中の unit は staging 領域に persist し (**配置と耐久 descriptor は
[03-data-model.md §2](03-data-model.md) の `.kcs/staging/` — purge / status / prune-orphans の
帰属列挙の正本**)、応答完了後に**全体集合が受け入れ検査
([04-pipeline.md §3.2](04-pipeline.md)) を通過した時点で manifest へ一括確定する** (検査前の unit は
公開しない — §3.2 の「違反応答は 1 unit も persist しない」と整合)。ストリーミング失敗時は staging を
破棄せず、**完了済み unit は保全したまま task を failed (retryable) にする。task が done (受け入れ検査
通過 → manifest 一括確定)・failed permanent・abandon・settled partial (全 unit が terminal —
[04-pipeline.md §5.2](04-pipeline.md)) のいずれかで terminal 化したときは、当該 task の
staging を同一遷移で冪等に cleanup する (**遷移内の順序は terminal 状態の耐久化 (done は manifest
一括確定の耐久化) が先、cleanup が後** — 逆順だと crash 時に公開元 bytes を失う。crash 時は遷移の
回復 replay で cleanup も再実行される。
非 terminal task の staging は `kcs status` に表示し、prune-orphans の blocker として可視化する一方、
terminal 化済み task の残存 root は cleanup 失敗の残骸として prune-orphans の削除対象 —
[10-operations.md §7.5.1](10-operations.md))** — manifest には `pending`
という unit 状態は存在しない ([03-data-model.md §2.1](03-data-model.md) の遷移は failed → done のみ)。
**同一 root 名の残存時の前置回復**: 同一 `(raw64, tool64, adapter_kind)` の staging root が既に
存在する状態で新しい task を開始する場合、root 公開 (atomic rename) の**前**に旧 root の回復を、
**呼び出し元コマンドが既に保持する `.kcs/.lock` の同一 critical section 内で**完了する
(04 §5.8 と同水準 — 別 lock の再取得はしない) — 対応 task が terminal なら cleanup を完遂してから公開し、非 terminal なら
新 task を開始せず当該 task を再開する。root 公開の rename は**既存 root 名への上書きをしない**
(no-replace — 新旧世代の bytes 混在を防ぐ。世代識別は path に載せない — [03-data-model.md §2](03-data-model.md) の配置は不変)。

**retry の合成規則**: staging の完了済み bytes は凍結する。retry 応答は**全 unit を含んでよい**
(未完了 unit のみへの絞り込みは任意の転送最適化 — Adapter は staging の内容を知り得ないため
KCS は要求しない)。**凍結保全と合成が適用されるのは transport 中断 (stream 失敗) からの resume に
限る** — 受け入れ検査 reject (contract violation — [04-pipeline.md §3.2](04-pipeline.md)) 起因の
再投入では staging を破棄して開始する (違反 unit を含み得る staging を first-instance-wins で
勝たせると、修正済み retry 応答が破棄され再違反が確定するため)。KCS が staging + retry 応答を合成する際、**まず生の retry 応答の各配列に V1 / V6 の配列内 unit_key 重複検査と配列間の排他検査
(pairwise disjoint — V1 の 4 集合 / V6 の 3 集合) を適用し** (staged-key の
再出現で重複・非排他が消える前に契約違反を検出する)、その後 **staging に確定済みの unit_key と
重複する応答 unit は黙って破棄する** (staging 側が first instance — first-instance-wins
([03-data-model.md §5](03-data-model.md)) と同型)。合成後の**完成集合に対して**受け入れ検査
(incremental は V1〜V6、full は full 契約) を適用してから一括公開する。

**staging の物理喪失** (プロセスクラッシュ・task cache 消失) 時は staging 全体を破棄し、未確定 unit
全体を再取得する — 完了済み bytes の凍結は転送量の最適化であり、正しさは全再取得で常に回復できる
(tasks.jsonl と同じ喪失許容 — [04-pipeline.md §5.7](04-pipeline.md))。

## 8.4 Capability 宣言なしの Adapter

`capabilities` に `incremental_update` を含まない Adapter は、KCS が **常に full モード** で呼ぶ。これにより既存 Adapter との後方互換が保たれる。

---

# 9. 再現性ポリシー

Adapter の完全な再実行決定性は要求しない。KCS が保証するのは:

```
raw_hash 不変                既存 artifact を尊重 (first-instance-wins)
raw_hash 変化                 新 artifact 候補を作る
explicit re-normalize         同 (raw_hash, tool_profile_hash) に対して gen+1 の新 normalized
                              instance を作る (kcs reindex --force、または prepared_hash 変化起因の
                              自動 gen+1 — 03-data-model.md §2.1 の例外)。旧 instance は
                              保全され、既存 commit / Evidence Pointer は旧 gen を参照し続ける
                              (03-data-model.md §2.1)
```

Markdown の content hash は持たない ([03-data-model.md §5](03-data-model.md))。同一 `(raw_hash, tool_profile_hash)` から複数回生成した結果が異なっても、**最初に確定したインスタンスを永続化** し、以後は再生成しない (first-instance-wins — 上記 explicit re-normalize の gen+1 は新 instance の追加であり、確定済み instance の置換・再生成ではない)。
