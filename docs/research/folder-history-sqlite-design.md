# フォルダ単位バージョン管理 + AI 検索 — SQLite 正本方式 設計書 (改訂版)

> **位置づけ (2026-07-14)**: 本書は KCS 本体の spec **ではない**。「SQLite を正本とし Content Object だけを
> Hash 保存する」フォルダ単位バージョン管理の元設計に、AI 検索 (Mistral OCR 4 / チャンク / マルチモーダル
> embedding / 横断検索) を統合した独立の設計検討である。KCS の実装知見 (kcs-index / 04-pipeline.md 等) を
> 移植しているが、要件が異なるため意図的に異なる技術選択を採る。KCS spec と矛盾しても本書は KCS を拘束しない。
> 元設計 (レビュー会話で提示された文書) は独立ファイルとしては存在せず、その規範は**すべて本書に収録済み**
> である — 本文中の「元設計」への言及は出自の説明であり、本書の外に参照解決を要しない。
>
> **要件上の前提 (KCS との分岐点)**: 原本ファイルが Evidence の正本であり、Markdown は再生成可能 (99% 一致で可 —
> 受容前提の表明で、実装は一致率を測定・保証しない。再生成時の再利用は §5.6 の text_hash 一致のみ)
> な検索用派生物。引用の無人機械検証は要件外。履歴メタデータは使い捨て可 (失われても原本ファイルは残る)。
> この前提を変える場合の再検討条件は §19。

---

# 1. 設計目的と要件

各フォルダ直下の Word・PDF などのファイルについて、変更時だけファイル実体を保存し、フォルダ単位の
コミット履歴を SQLite で管理する。さらに原本を LLM (OCR) で Markdown 化し、テキスト・画像の両方を
対象とするハイブリッド検索 (全文検索 + ベクトル検索) を提供する。

バージョン管理の要件 (元設計から変更なし):

- 各フォルダが独立して履歴を管理する。管理対象はフォルダ直下のファイルのみ (サブフォルダは対象外、必要なら独自履歴)
- ファイル本体は SQLite に保存しない。内容が変化したファイルだけ新しい実体を保存する
- 同一内容のファイル実体は Content Hash で重複排除する
- 複数ファイルの変更を 1 つのコミットにまとめられる。変更されていないファイルの履歴行は作成しない
- 並行して作成されたコミットをすべて保存し、現在版はファイル単位の Last Write Wins で決定する
- 端末 ID やランダムな nonce には依存しない。同一の正規化されたコミットは同一の Commit Hash になる

AI 検索の要件 (本改訂で追加):

- OCR は **Mistral OCR 4** (bbox annotation 付き) とし、**すべて Mistral Batch API で実行する** (50% 割引)。
  Embedding も同じ非同期ジョブ機構 (§9.1) で処理する — server-side batch のあるプロバイダなら利用し、
  無ければ client 側キューで代替する (割引の有無はプロバイダ依存であり、50% は OCR にのみ確定)
- Markdown は見出し (`#`) でチャンク分割し、画像はそれぞれ独立チャンクとする
- **Embedding は必須**。画像は分離保存し、**単一のマルチモーダルベクトル空間**に入れて画像込みの検索を可能にする
- テキストチャンクと画像チャンクは**同一テーブル**で管理し、FTS とベクトルのハイブリッド検索を両立する
- バッチ処理情報とデバイス横断の検索集約は**アプリ配下の DB** で管理する (フォルダの可搬性を汚さない)

# 2. 全体構成 — 三層

```text
┌─ 層 1: 各対象フォルダ (truth) ──────────────────────────────────────┐
│ .folder-history/                                                     │
│   repository-id           固定 Repository ID                          │
│   metadata.sqlite         履歴の正本 + 派生物台帳 + 単独検索インデックス │
│   objects/sha256/         原本 / 派生 Markdown / 抽出画像 (内容アドレス) │
│   tmp/                                                                │
│ フォルダ単体で自己完結。コピー・共有すれば履歴と検索がそのまま渡る       │
│ (静止状態のコピーに限る。複数デバイスでのライブ同時編集 + 汎用同期は     │
│  §19 の条件 1 の理由により非対応 — conflicted copy の履歴は黙って失われる)│
└──────────────────────────────────────────────────────────────────────┘
┌─ 層 2: アプリ配下・運用層 (デバイスローカルの運用データ) ─────────────┐
│ ~/.local/share/<app>/app.sqlite                                       │
│   folders / batch_requests / cost_ledger  Batch ジョブのガード + 課金台帳│
│   app_config                          現行 profile 設定 (§8 の実体)     │
│   watch_roots / scan_cache / fp_cache / pending_deletes                │
│                                       変更検知のキャッシュ (§20)        │
│ 喪失しても層 1 との差集合から再構築可能 (損失の内訳は §15 規約 7)        │
└──────────────────────────────────────────────────────────────────────┘
┌─ 層 3: アプリ配下・集約層 (横断検索キャッシュ) ───────────────────────┐
│ 同じ app.sqlite 内の agg_* テーブル群 + sync_state                     │
│ 各フォルダから追記型レプリケーションで集約。全フォルダ横断のハイブリッド │
│ 検索が 1 DB で完結する。丸ごと失われても全フォルダから再構築可能         │
└──────────────────────────────────────────────────────────────────────┘
```

原則: **真実は常に層 1**。層 2 はガードとログ、層 3 は検索キャッシュであり、どちらも真実を持たない。
層 2 の喪失で失われるものは**規約 7 の (a)〜(f) を正**として列挙する (a: 未回収 job の再投入 /
b: 課金履歴 cost_ledger / c: terminal failed の抑制 — 恒常失敗対象は再び attempts 上限まで
再投入される / d: 未完了の明示再生成 intent §5.3 / e: in-flight の upload_id・intent_token /
f: **app_config の現行設定 (tool・embedding profile・画像フィルタ)・unregister の退役事実・
watch_roots 外の登録フォルダの個別パス — bootstrap で再入力・再確認 §21.5**)。いずれも層 1 の
真実には触れないが、**「有界」の内訳は 2 種** (規約 7): (a)(c)(d)(f) = 対象・操作ごとに有界な
再実行コスト / (b)(e) = 運用量に比例する不可逆な記録喪失 (「層 1 に波及しない」の意味での有界)。
なお app 全損は **in-flight の upload_id / intent_token も失う**ため、プロバイダ側に upload 済みの
入力ファイルを識別・削除できなくなる — 保持期限 (約 30 日) までの機密残留が生じる (回復不能な
真実喪失ではないが、規約 7 の損失に含めて認識する。プロバイダ側の TTL 失効に委ねる)。

# 3. ディレクトリ構成

```text
対象フォルダ/
├── .folder-history/
│   ├── repository-id            # UUIDv7。履歴系列の識別 (コピーで保持、履歴を捨てて再開なら再生成)
│   ├── metadata.sqlite          # §5 の 8 テーブル
│   ├── objects/
│   │   └── sha256/
│   │       ├── ab/abcdef...     # 原本 (Content Hash)
│   │       ├── 9f/9fce12...     # 派生 Markdown (markdown_hash)
│   │       └── 3c/3c77aa...     # 抽出画像 (image_hash)
│   └── tmp/                     # 書き込みは tmp → fsync → rename → ディレクトリ fsync (§20.5)
├── report.pdf
├── proposal.docx
└── subfolder/                   # 親フォルダからは管理しない
```

原本・派生 Markdown・画像はすべて同一の内容アドレス置き場を共用する。種別はテーブル側が持つ。

# 4. Hash / 識別子の一覧

| 識別子 | 入力 | 役割 | 同一性判定に使うか |
| --- | --- | --- | --- |
| `content_hash` | **SHA-256** (原本ファイルの bytes) | 原本の identity・実体アドレス・dedup | **使う** (原本) |
| `commit_hash` | **SHA-256** (正規化コミットレコード — 直列化規約は §4.1) | コミットの identity | **使う** (コミット) |
| `tool_profile_hash` | 解決済み版付きモデル名 + annotation スキーマ + 呼び出しオプション | OCR ツール構成の identity | **使う** (派生の世代軸) |
| `markdown_hash` | 派生 Markdown の bytes | **保存アドレスと破損検出のみ** | **使わない** (LLM 非決定のため) |
| `text_hash` | **SHA-256** (chunk text の UTF-8 bytes — 追加正規化なし) | embedding 共有キー・FTS 対象判定 | 内容共有にのみ使う |
| `image_hash` | **SHA-256** (抽出画像の bytes) | 画像実体アドレス・embedding 共有キー | 内容共有にのみ使う |
| `embed_hash` | = COALESCE(image_hash, text_hash) | embedding 対象の統一キー (生成列) | — |
| `embedding_profile_hash` | embedding モデル/次元/距離の正規化 | ベクトル空間の identity | **使う** (全行一致必須) |

中核規範: **「生成済みか」の判定は `(content_hash, tool_profile_hash)` の行の存在で行い、派生バイト列の
hash では行わない**。LLM は非決定的であり、bytes の hash を同一性判定に使うと再生成のたびに「変更あり」に
なって増殖する。

## 4.1 Commit Hash の正規化直列化 (規範 — hash_format_version 1 として確定)

直列化形式は **RFC 8785 (JCS: JSON Canonicalization Scheme)** とする。独自バイナリ直列化は
採用しない — framing・長さ prefix・整数幅・endian の決定をすべて JCS が吸収し、独立実装が
同一 bytes を再現できる。

```text
commit_hash = SHA-256( JCS( commit_record ) )

commit_record = {
  "v": 1,                               // hash_format_version。直列化規約の変更で bump
  "repository_id": "<uuid 文字列>",     // 小文字・8-4-4-4-12 ハイフン区切り・brace / urn: なしに固定
                                        // (表記が揺れると同じ 16 bytes から別 commit_hash が生まれる)
  "parent_hash": "<hex64>",             // 親なし (初回コミット) はフィールドごと省略
  "created_at": <整数>,                  // UTC Unix 時間ミリ秒
  "message": "<文字列>",                // 無ければフィールドごと省略
  "changes": [                          // 正規化済み file_name の UTF-8 バイト列昇順
    { "file_name": "<文字列>",
      "event_type": 1,                  // 1=create, 2=update, 3=delete
      "content_hash": "<hex64>",        // event_type=3 では省略
      "size_bytes": "<10 進文字列>",     // event_type=3 では省略。文字列化の理由は固定規則を参照
      "previous_commit_hash": "<hex64>" // 同名ファイルの前バージョンが無ければ省略
    }, ...
  ]
}
```

固定規則:

```text
- hash 値は小文字 hex 64 文字の JSON 文字列として直列化する (DB 上の BLOB 32 bytes とは
  表現が異なる — 直列化専用表現)
- 文字列 (file_name / message) は NFC 正規化してから直列化する
- NULL リテラルは使用しない。値が無いフィールドはフィールドごと省略する (省略 = 無)
- changes は同名 file_name を同一コミット内に 1 件のみ許す
- キー順・数値表現・文字列エスケープは JCS の規定に従う (実装は JCS ライブラリを使う)
- 端末 ID・nonce・乱数は一切含めない (同一の正規化コミット → 同一の commit_hash)
- created_at (UTC ミリ秒) は 2^53 未満で JCS の数値表現域 (IEEE-754 double の安全整数) に
  収まる。**ナノ秒を JCS の数値として使ってはならない** (現在の epoch ns は 2^53 超で
  1 ns 差が同値に丸められる — §20.3 の fingerprint は文字列化で回避する)
- **size_bytes は 10 進文字列として直列化する** — ファイルサイズは 2^53 を超え得る (疎ファイル等)
  ため、数値のままだと実装が「拒否」と「丸め」に分岐して同一コミットから別 commit_hash が生まれる。
  統一規則: **2^53 超があり得る整数は JCS では 10 進文字列にする** (created_at は上記の規範で
  上限を保証できるため数値のまま。profile_record の options 内の整数にも同じ規則を適用する)。
  **文字列の字句形も固定する — 先頭ゼロなしの最短 10 進表記** ("01" 等の同値別表記は JCS では
  別 bytes = 別 hash になり、同一コミットから別 commit_hash が生まれる)
- 実装の最初の作業として test vector (固定 commit_record → 期待 commit_hash) を作成し、
  リグレッションテストとして固定する
```

**tool_profile_hash / embedding_profile_hash の直列化も同じ JCS 方式で確定する** — record の形は
**kind 別に排他** (§5.7 の shape 検証と対。共通形は存在しない):
- tool 用      = `{"v": 1, "model": "<解決済み版付き名>", "annotation_schema": {...}, "options": {...}}`
- embedding 用 = `{"v": 1, "model": "<解決済み版付き名>", "options": {...}}` (**annotation_schema を
  持たない** — tool 専用フィールド。持たせると §5.7 の shape 検証が拒否し、省略の揺れは
  profile_hash を分裂させる)
(いずれも既定値も省略せず明示、キー順は JCS 準拠) を SHA-256 する。
embedding profile の options には少なくとも **dimensions / distance_metric / L2 正規化の有無**を
含める (hash だけでは不可逆なため、record そのものは profiles 表 §5.7 へ永続化する — フォルダ
単体からクエリ embedding の作り方を復元するため)。
実装間・バージョン間で直列化が揺れると、同一構成が別 profile と判定されて全派生の
再生成 (= 再課金) が走るため、commit_hash と同様に test vector を固定する。

# 5. metadata.sqlite (フォルダ側・8 テーブル)

## 5.1 commits

```sql
CREATE TABLE commits (
    commit_hash BLOB PRIMARY KEY
        CHECK (length(commit_hash) = 32),
    parent_hash BLOB
        CHECK (parent_hash IS NULL OR length(parent_hash) = 32),
    created_at INTEGER NOT NULL,
    message TEXT,
    FOREIGN KEY (parent_hash) REFERENCES commits(commit_hash)
) WITHOUT ROWID;

CREATE INDEX idx_commits_order ON commits (created_at DESC, commit_hash DESC);
```

## 5.2 file_versions

```sql
CREATE TABLE file_versions (
    file_name TEXT NOT NULL,
    commit_hash BLOB NOT NULL
        CHECK (length(commit_hash) = 32),
    previous_commit_hash BLOB
        CHECK (previous_commit_hash IS NULL OR length(previous_commit_hash) = 32),
    event_type INTEGER NOT NULL
        CHECK (event_type IN (1, 2, 3)),          -- 1=create, 2=update, 3=delete
    content_hash BLOB
        CHECK (content_hash IS NULL OR length(content_hash) = 32),
    size_bytes INTEGER,
    PRIMARY KEY (file_name, commit_hash),
    FOREIGN KEY (commit_hash) REFERENCES commits(commit_hash) ON DELETE CASCADE,
    FOREIGN KEY (file_name, previous_commit_hash)
        REFERENCES file_versions(file_name, commit_hash),
    CHECK (
        (event_type = 3 AND content_hash IS NULL AND size_bytes IS NULL)
        OR
        (event_type IN (1, 2) AND content_hash IS NOT NULL
            AND size_bytes IS NOT NULL AND size_bytes >= 0)
    )
) WITHOUT ROWID;

CREATE INDEX idx_file_versions_commit ON file_versions (commit_hash);
CREATE INDEX idx_file_versions_previous
    ON file_versions (file_name, previous_commit_hash)
    WHERE previous_commit_hash IS NOT NULL;
```

現在版はファイル単位 LWW (`created_at DESC, commit_hash DESC` で最大のバージョン。event_type=3 なら
現在存在しない) で決定し、並行して作成されたコミットはすべて保存する。Commit Hash の正規化直列化は
§4.1 を正本とする。この 2 テーブルの DDL と意味論は元設計から不変である。

## 5.3 markdown_documents — 派生物の台帳

```sql
CREATE TABLE markdown_documents (
    content_hash BLOB NOT NULL
        CHECK (typeof(content_hash) = 'blob' AND length(content_hash) = 32),
    tool_profile_hash BLOB NOT NULL
        CHECK (typeof(tool_profile_hash) = 'blob' AND length(tool_profile_hash) = 32),
    markdown_hash BLOB NOT NULL                  -- objects/ のアドレス。identity ではない (§4)
        CHECK (typeof(markdown_hash) = 'blob' AND length(markdown_hash) = 32),
    generated_at INTEGER NOT NULL,
    PRIMARY KEY (content_hash, tool_profile_hash)
) WITHOUT ROWID;
```

- **行の存在 = 生成完了 (done)**。pending は「行が無い」、submitted / failed は app.sqlite (§9.1) が持つ
- 派生はファイル名・コミットに紐付けない。同一内容のファイルが複数版・複数名で現れても Markdownize は
  1 回で済み、版との対応は `file_versions.content_hash` との join で導出する (§12)
- 同一 tool での再生成 (破損時等) の置き換えは、同一 Tx で旧行を **DELETE してから INSERT** する。
  ON CONFLICT による UPSERT は**禁止** — 親行の UPDATE では `ON DELETE CASCADE` が発火せず、
  旧 chunks が残って `seq` UNIQUE 衝突または新 Markdown と旧 chunks の混在を招く。
  旧派生は保持しない (99% 要件 — **同一 (content, tool) の置換の話**。tool 変更で残る旧 tool の
  派生は明示 drop (§21.6) までの保持が別規範 — §11.2)
- **明示再生成の経路** (行の存在 = done の成果短絡の唯一の迂回。操作カタログの所在は §21.7):
  **先に rotation ガード (§9.1 — 旧 token の照合・記帳・intent_token NULL 化) を完了してから**
  (逆順だと、ガードの found 記帳 (attempts +1) が reset 後に落ち、旧世代の消費が新世代の
  再試行予算を食う)、**app.sqlite の 1 Tx だけ**で、対象ペアの batch_requests 行に
  **floor_generated_at = 現在の generated_at** を設定し、attempts = 0 にリセット (terminal 解除)
  する。行が無ければ (app 再構築後等) **state=2, attempts=0, batch_job_id / intent_token /
  upload_id = NULL で INSERT** し、floor / attempts のリセットは同じ INSERT に含める。
  **markdown_documents 行も無い場合 (drop-derivation §21.6 後の過去版のみ等) は
  floor_generated_at = 0 (sentinel — 派生不在・任意の新結果が成果)** — 「現在の generated_at」の
  参照先が無くても floor は設定でき、「floor 設定済み = backfill 設定に関わらず候補」(§10) により
  backfill OFF でも明示再生成が機能する (未設定だと過去版のみの content に再投入経路が無い)。
  **submission_seq の初期値は 0 ではなく、cost_ledger の同キー最大値から継承する**:
  `COALESCE((SELECT MAX(submission_seq) FROM cost_ledger WHERE repository_id=… AND kind=…
  AND target_key=…), 0)` — batch_requests は削除される (unregister / 退役) が cost_ledger は
  永続のため、0 起点だと「行削除 → 再登録 → 再投入」で seq が 1 から再採番され、close Tx
  (state=2 + ledger 追記が同一 Tx) が旧 ledger 行と UNIQUE 衝突して恒久失敗する (この継承規則は
  **batch_requests 行を新規 INSERT する全経路** — §9.1 相 1・client 前計上・本節の明示再生成
  INSERT・**§6 preflight の terminal marker INSERT** — に適用する。register 自体は行を作らず、
  再登録後の初回投入 = 相 1 がここに含まれる。preflight marker は課金を持たないため実害は無いが、
  規則を無例外にして実装判断を残さない。seq の high-watermark の正本は ledger 側)。
  state=2 は「成果なし・state=2 → 投入対象」の遷移 (§9.1) により次 tick の submit を駆動する
  初期値として機能する。metadata.sqlite へは書き込まない — kind=1 の「フォルダ成果あり」(§9.1) は
  「markdown_documents 行が存在し、**かつ generated_at > floor_generated_at**」と定義されるため、
  floor 設定だけで旧派生は成果なしと扱われ、**backfill 設定 (§10) に関わらず**次 tick の submit が
  再投入する (過去版だけが持つ content は backfill OFF では他に再投入経路が無い)。
  旧派生は新結果の collect (DELETE → INSERT 置換) まで検索に残り続け、collect の INSERT は
  generated_at = max(now, floor_generated_at + 1) を適用してから floor を NULL へ戻す。
  単一 Tx で完結するため、多段手順の途中クラッシュで「旧値だけ消えた」「要求だけ消えた」中間
  状態が構造的に生じない。app 全損時は未完了の明示再生成 intent も消える — 再度明示操作する (§2)。
  なお明示再生成は同一ペアの再 OCR であり**再課金が発生する** (§16 の課金単位の明示的な例外)
- **generated_at はすべての置き換え経路で `max(now, 旧値 + 1)` として単調増加を保証する**
  (再 OCR 置換・再チャンク §7 の双方に適用)。集約層の置換検出 (§9.3-b) は generated_at 比較で
  行うため、同値を許すと置換が横断検索へ伝播しない

## 5.4 chunks — text / image 統一チャンク

```sql
CREATE TABLE chunks (
    chunk_id INTEGER PRIMARY KEY,                -- rowid (chunk_fts の content_rowid)
    content_hash BLOB NOT NULL
        CHECK (typeof(content_hash) = 'blob' AND length(content_hash) = 32),
    tool_profile_hash BLOB NOT NULL
        CHECK (typeof(tool_profile_hash) = 'blob' AND length(tool_profile_hash) = 32),
    seq INTEGER NOT NULL,                        -- Markdown 内の出現順 (text / image 通し採番)
    chunk_type INTEGER NOT NULL
        CHECK (chunk_type IN (1, 2)),            -- 1 = text, 2 = image
    heading_path TEXT NOT NULL DEFAULT '[]',     -- ATX 見出しスタック (JSON 配列 — **直列化は raw
                                                 --  UTF-8 固定・非 ASCII を \uXXXX に escape しない**
                                                 --  (escape 表記は FTS trigram に別文字列として載り、
                                                 --  同一見出しの検索が直列化実装で分岐する))
    char_start INTEGER NOT NULL,                 -- 保存済み Markdown 全文内の文字 span。単位は
    char_end INTEGER NOT NULL,                   -- Unicode スカラー値 (コードポイント)、end は排他。
                                                 --  (image チャンクは参照記法の出現範囲)

    text TEXT,                                   -- type=1: セクション本文 (必須)
                                                 -- type=2: annotation 由来テキスト (NULLABLE、§7 規則 3)
    text_hash BLOB
        CHECK (text_hash IS NULL
               OR (typeof(text_hash) = 'blob' AND length(text_hash) = 32)),
    image_hash BLOB                              -- type=2: 画像 bytes の SHA-256
        CHECK (image_hash IS NULL
               OR (typeof(image_hash) = 'blob' AND length(image_hash) = 32)),
    media_type TEXT,
    image_meta TEXT,                             -- JSON: { "page": 12, "bbox": [x0,y0,x1,y1],
                                                 --   "source_id": "img-0.jpeg", "image_type": "chart" }
                                                 -- 供給源は canonical block の meta 行 (§6)。
                                                 -- Markdown から常に再構築可能 (sidecar なし)

    embed_hash BLOB GENERATED ALWAYS AS (COALESCE(image_hash, text_hash)) VIRTUAL,

    CHECK (
        (chunk_type = 1 AND text IS NOT NULL AND text_hash IS NOT NULL
            AND image_hash IS NULL AND media_type IS NULL AND image_meta IS NULL)
        OR
        (chunk_type = 2 AND image_hash IS NOT NULL AND media_type IS NOT NULL
            AND image_meta IS NOT NULL
            AND (text IS NULL) = (text_hash IS NULL))
    ),
    CHECK (typeof(seq) = 'integer' AND seq >= 0),
    CHECK (typeof(char_start) = 'integer' AND typeof(char_end) = 'integer'
           AND char_start >= 0 AND char_end >= char_start),   -- INTEGER affinity だけでは
                                                 --  seq=0.5 / span=[7,3) 等の不正値を弾けず
                                                 --  §12 の preview 解決キーが壊れる
    UNIQUE (content_hash, tool_profile_hash, seq),
    FOREIGN KEY (content_hash, tool_profile_hash)
        REFERENCES markdown_documents(content_hash, tool_profile_hash)
        ON DELETE CASCADE
);
CREATE INDEX idx_chunks_source ON chunks (content_hash, tool_profile_hash);
CREATE INDEX idx_chunks_embed  ON chunks (embed_hash);
```

- text と image を 1 テーブルに統一し、`text` を NULLABLE にすることで、FTS・ベクトル両経路が同じ行 =
  同じ `chunk_id` に着地する (§11 のハイブリッドの前提)
- image チャンクの `text` には canonical block (§6) の **description + transcription のみ**が入る
  (§7 規則 3)。文書由来キャプションは取り込まず、通常本文として text チャンク側に残る。
  これにより annotation 付き画像はテキスト検索でもヒットする
- **commit_hash 列は持たない** (§18.1)。**vector 列も持たない** (§18.2)

## 5.5 chunk_fts — 全文検索 (text を持つ行のみ索引)

```sql
-- FTS の content には「text を持つ行だけ」を返す view を指定する。
-- content='chunks' の直接指定は誤り — text=NULL の image 行が content 側に存在するのに
-- FTS 側に無い状態となり、FTS5 の integrity-check / rebuild と整合しなくなる
CREATE VIEW chunks_fts_src AS
    SELECT chunk_id, text, heading_path FROM chunks WHERE text IS NOT NULL;

CREATE VIRTUAL TABLE chunk_fts USING fts5(
    text, heading_path,
    content='chunks_fts_src', content_rowid='chunk_id',
    tokenize='trigram'                           -- CJK 対応。英文中心なら 'unicode61 remove_diacritics 2'
);                                               -- ただし trigram は 3 文字未満のクエリに 0 件を返す
                                                 -- (短語クエリの fallback は §11.2)

CREATE TRIGGER chunks_ai AFTER INSERT ON chunks
WHEN new.text IS NOT NULL BEGIN
    INSERT INTO chunk_fts(rowid, text, heading_path)
    VALUES (new.chunk_id, new.text, new.heading_path);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks
WHEN old.text IS NOT NULL BEGIN
    INSERT INTO chunk_fts(chunk_fts, rowid, text, heading_path)
    VALUES ('delete', old.chunk_id, old.text, old.heading_path);
END;
-- UPDATE trigger は張らない。chunks の変更は「DELETE → INSERT (置き換え)」のみ許可 (§15 規約 4)
```

## 5.6 embeddings / embedding_vec — マルチモーダル (必須)

```sql
CREATE TABLE embeddings (
    target_type INTEGER NOT NULL
        CHECK (target_type IN (1, 2)),           -- 1 = text, 2 = image (chunks.chunk_type と対応)
    target_hash BLOB NOT NULL                    -- = chunks.embed_hash
        CHECK (typeof(target_hash) = 'blob' AND length(target_hash) = 32),
    vector BLOB NOT NULL                         -- L2 正規化済み float32 × dimensions。**byte order は
                                                 --  IEEE-754 little-endian に固定** (sqlite-vec と同一 —
                                                 --  異 endian 機へフォルダをコピーしても順位が壊れない。
                                                 --  §2「検索がそのまま渡る」の前提。length 検査だけでは
                                                 --  endian 差を弾けず同次元で黙った誤順位になる)
        CHECK (typeof(vector) = 'blob' AND length(vector) = 4 * dimensions),
    dimensions INTEGER NOT NULL
        CHECK (typeof(dimensions) = 'integer' AND dimensions > 0),
    embedding_profile_hash BLOB NOT NULL         -- 単一 multimodal profile (§15 規約 3)
        CHECK (typeof(embedding_profile_hash) = 'blob'
               AND length(embedding_profile_hash) = 32),
    PRIMARY KEY (target_type, target_hash)
) WITHOUT ROWID;

-- embedding_vec は profile 確定時に <dim> を実数へ展開して作成する DDL テンプレート。
-- <dim> は採用 profile の次元 (= embeddings.dimensions) に一致させる。
-- 本文中の 768 という数値は参考値 (KCS の採用例) であり本書の規範ではない (§8)
CREATE VIRTUAL TABLE embedding_vec USING vec0(   -- sqlite-vec。embeddings からの導出物 (再構築可能)
    target_key TEXT PRIMARY KEY,                 -- target_type || ':' || lower(hex(target_hash))
                                                 --  hex は小文字固定 (§11.2 の契約と同一。
                                                 --  SQL の hex() は大文字を返すため必ず lower() を通す)
    embedding float[<dim>] distance_metric=<metric>  -- <dim> と同様 <metric> も profile record の
                                                     --  distance_metric から展開する (参考採用値 cosine)。
                                                     --  §8-c は次元と距離の両方を照合し、いずれか不一致で
                                                     --  DROP→CREATE する — 距離だけの変更は次元一致で
                                                     --  すり抜け旧 metric のまま黙った誤順位になる
);
```

- キーは chunk 行ではなく**内容 (embed_hash)**。同一段落・同一画像 (全ページ共通ロゴ等) が複数文書・
  複数版に現れても vector は 1 本。再生成でも text_hash が変わらなかった chunk はそのまま再利用される
  (OCR の非決定性次第で再利用率は変わる — 効果はこの上限内)ため、
  **再課金は変わった分だけ**になる
- `embeddings` が正、`embedding_vec` は KNN 加速用の導出物。不整合時・rebuild 時は
  embeddings → embedding_vec の順に再構築する

## 5.7 profiles — profile record の永続化

```sql
CREATE TABLE profiles (
    profile_hash BLOB PRIMARY KEY
        CHECK (typeof(profile_hash) = 'blob' AND length(profile_hash) = 32),
    kind INTEGER NOT NULL CHECK (kind IN (1, 2)),    -- 1 = tool (OCR), 2 = embedding
    record_json TEXT NOT NULL                        -- §4.1 の profile_record (JCS 直列化 bytes そのもの)
) WITHOUT ROWID;
```

- markdown_documents / embeddings へ行を書く同一 Tx で、参照する profile_hash の行を
  INSERT OR IGNORE する。書込境界で `SHA-256(record_json) = profile_hash` を検証する。
  **PK が profile_hash 単独で足りる (kind を含まない) のは、tool と embedding の record が構造的に
  交わらない (必須フィールドが互いに排他) ため** — この排他は adapter が書込前の shape 検証で強制
  する: **kind=tool の record は annotation_schema を必須、kind=embedding の record は options 内の
  dimensions / distance_metric を必須**とし (フィールド名は §4.1 / §5.6 と同一の
  **distance_metric** — 「metric」等の別名は不可)、他 kind の必須フィールドを持つ record は拒否する。また **model は
  provider / adapter 名前空間を含む解決済み完全修飾名**とする (別 provider の同名モデル・同次元への
  切替が同一 hash に落ちると、旧空間の vector が現行として照合される)。record 仕様を変更する場合はこの前提を維持する
  か、record に kind 判別フィールドを含めて hash レベルで分離する (同一 record が両 kind に載ると
  INSERT OR IGNORE が後着の kind を黙って落とし、fsck の参照整合 (kind 一致) が恒久不一致になる)
- 目的: hash は不可逆なので、この表が無いと**フォルダ単体 (コピー先・app 全損後) から
  「どのモデル・次元・距離でクエリ embedding を作ればよいか」を復元できない** — 層 1 の
  自己完結 (§2「検索がそのまま渡る」) はこの表を含めて成立する。**フォルダ単独 (app 不在) の
  検索・検査が「現行」を導く規則は §11.2 のフォルダ単独決定規則** (embeddings /
  markdown_documents から導出)。**app 管理下の §8 起動時検査・embedding_vec の次元照合の
  参照元は app_config の embedding_profile record であり、この表ではない** (§8 冒頭 /
  §10 step 3 — この表は履歴の保管庫で、新規フォルダでは空)

# 6. OCR パイプライン (Mistral OCR 4 + bbox annotation, Batch)

呼び出し規約:

```text
model                  : 解決済みの版付き名 (例 "mistral-ocr-4-0")。
                         "mistral-ocr-latest" 等の可変 alias での呼び出しは禁止 —
                         OCR API は応答内で alias を実バージョンに解決しないため、
                         Adapter がモデル一覧 API から版付き名を解決してから呼び、
                         その版を tool_profile_hash の入力に含める (KCS 2026-07-03 実測の移植)
include_image_base64   : true  (画像分離に必須)
bbox_annotation_format : 有効 (既定 ON)。スキーマ例:
                           image_type        : 図の種類 (chart/diagram/photo/table/logo など)
                           short_description : 一文説明 (alt テキストに使用)
                           transcription     : 図中の文字・ラベル・数値の書き起こし
include_blocks         : 使用しない (チャンク分割は保存済み Markdown の解析で行う。§7)
実行                    : すべて Batch API (endpoint=/v1/ocr, JSONL の custom_id に target_key,
                         timeout_hours=24)
```

**投入前検査 (preflight) と投入後の後始末**:

- **対象形式**: OCR へ投入するのは PDF と画像 (Mistral OCR の対応形式) のみ。判定は拡張子ではなく
  マジックバイトで行う。**Word 等のオフィス文書は版付き決定論的コンバータ (固定版) で PDF へ
  変換してから投入し、コンバータの識別子と版を tool_profile_hash の入力 (options) に含める**。
  **変換 PDF は一時生成物であり objects/ へ保存しない** — content_hash・保存・照合の対象は常に
  **原本 bytes** (§4)。投入直前の原本再照合 (下記) も原本に対して行い、照合後に同一コンバータで
  再変換して upload する (決定論的なので再実行は同一 bytes)。**upload_id 列・filename への
  intent_token 埋込は「実際に upload した bytes」(変換物) に適用する** — 原本は upload しない。
  実測 pages 等の課金入力は job 応答から取る。
  **変換の失敗分岐**: 同一入力で再現する決定論的失敗 (破損 DOCX・パスワード保護・非対応内部形式) は
  state=3 (error='convert_failed', attempts = 上限) の行を **1 回だけ**作って terminal に固定する
  (unsupported_format と同族 — 毎 tick の再変換ループを作らない。復帰は明示 retry)。コンバータ
  不在・リソース不足等の環境起因の一時失敗は行を作らず (作成済みなら据置き) 次 tick 再試行 +
  共通 backoff (§9.1) + status。**サイズ上限 (512MB) は変換後の bytes にも適用する** — 検査は
  変換してから行う (原本が上限内でも変換物が超過し得る — preflight を通過した upload の 4xx を防ぐ)。
  対象外のファイル (動画・アーカイブ・実行ファイル等) は **upload せず**、batch_requests に
  state=3 (error='unsupported_format', attempts = 上限) の行を **1 回だけ**作って terminal に
  固定する — status はこの error 値で「非対象」に分類表示でき、submit 候補の差集合からも以後
  除外される (マジックバイト判定を毎 tick 繰り返す無駄ループを作らない。無条件 upload が
  帯域・プロバイダ保存・機密の各面で有害である点は従来どおり)。対象形式の判定を変える場合
  (コンバータ追加等) は tool_profile の変更として現れるため target_key が変わり、自然に再判定される
- **サイズ上限**: 1 ファイル 512MB (プロバイダ上限)。超過は submit せず、非対象と同様に
  error='oversize' の terminal 行を 1 回だけ作って status 表示する (毎 tick の再判定を避ける)。
  Batch の JSONL 自体にも上限があるため、行数・バイト数で複数 job へ分割してよい
  (§10 の「1 job = 1 repository」の規則は維持)
- **Batch 入力の形式**: JSONL の各行は upload 済み**入力** (原本 — **Office 文書は変換 PDF** (下記
  変換規範)。「原本の file id」ではない — 変換を伴う場合の原本は upload されない) の file id を
  参照する (**base64 内嵌は
  用いない** — JSONL が入力の約 4/3 倍に膨張し、上の 512MB 判定が入力サイズと乖離する)。**JSONL
  自身も upload されるため、その file id も相 2a と同じ「filename への intent_token 埋込」(§9.1) の
  対象とする** — JSONL の id は upload_id 列に持たず (列は**実際に upload した入力** (原本 — Office
  文書は変換 PDF) 用)、掃除 (upload 後始末・token sweep
  の残骸掃除) は token 埋込の filename 一覧で発見・削除する
- **投入直前の原本再照合**: 投入対象の**原本** objects/<content_hash> の bytes を読み SHA-256 を再計算して
  名前と照合する — 不一致は投入せず fsck (§13) の破損報告へ誘導する (bit-rot した bytes から派生を
  作らない。restore (§21.4) の読出し時再計算と同じ規律 — 週次 fsck の検出を待つ間の窓を塞ぐ)
- **upload 入力の削除**: upload した入力 (原本 — Office 文書は変換 PDF) の file id は batch_requests の
  upload_id 列に記録し (§9.1)、
  tick 末尾の掃除が「その upload に紐付く全行が終端 (state 2/3) かつ upload_cleaned = 0」の
  ものをプロバイダから削除して upload_cleaned = 1 を記録する。**削除の失敗・クラッシュは
  次 tick の同じ掃除が再試行する** — state を先に閉じても後始末が失われない (放置すると
  プロバイダ側に 30 日程度残留する — 機密・ストレージの両面)
- **結果の失効**: Batch 結果には保持期限 (約 24 時間) がある。collect は期限内の実行を推奨し、
  失効した item は state=3 (error='result_expired') として閉じる。再投入は**通常の遷移表
  (§9.1) に従う** — attempts < 上限なら次 tick の submit が再投入し (**再課金が発生する** —
  長期停止していた端末の再開時に起こり得る)、上限到達なら terminal (明示 retry のみ。
  失効 → 再課金の無限ループにはしない)

応答の保存時変換 (§10 tick の OCR collect):

```text
1. images[] の image_base64 を decode → SHA-256 → objects/ へ保存 (image_hash)
2. pages[].markdown を **page index の昇順**に、**各ページ末尾の改行を 1 つの LF に正規化して
   join** して結合し (末尾 LF 無しページの直結で次ページ先頭の ATX 見出しが行中に埋もれるのを
   防ぐ — 結合規則も決定論的に固定する)、画像参照 ![img-0.jpeg](img-0.jpeg) を下記の
   canonical img block へ置換して「保存する Markdown」を確定する
3. Markdown bytes → SHA-256 → objects/ へ保存 (markdown_hash)
```

**保存済み Markdown は完全自己記述である** — 画像のメタ (page / bbox / source_id) も annotation も
img block に materialize されるため、解析 (§7)・検索・再チャンク・集約のすべてが Markdown だけで
完結する。**sidecar の持ち回りは存在しない**。

**canonical img block grammar** (materialize の正規形。§7 の解析器はこの形だけを認識する):

```text
![<alt>](obj:<image_hash64>)        ← 画像参照 (単独行。image_hash64 = 小文字 hex 64 文字)
<!-- img:<image_hash64>             ← img block 開始 (単独行。参照行の直後に必須)
v: 1                                 ← grammar version (ここから 5 行は meta、常に出力)
page: <整数>
bbox: [x0,y0,x1,y1]
source_id: <元応答の画像 id (例 img-0.jpeg)>
media_type: <MIME (例 image/png)>
image_type: <図の種類>               ← ここから 3 行は annotation ON のときのみ出力
description: <short_description>
transcription: <図中文字・ラベル・数値の書き起こし>
-->                                 ← img block 終了 (単独行)
```

- `<alt>` = annotation ON なら short_description、**OFF なら source_id をそのまま使う** (固定規則)。
  alt には下記の field 値と同一の **1 行正規化のみ**を適用し、その上で**値中の `\` `[` `]` を
  それぞれ `\\` `\[` `\]` へ一度だけ置換する** (field 値エスケープと label 置換を重ねない — 二重適用は
  `\` を `\\\\` に膨らませ、保存 Markdown 上の表示値が原値と乖離する) — 参照行は `![<alt>](obj:…)` であり、`](` だけの置換では
  先行する裸の `]` (例 `foo]bar`) が image label `![…]` を早期に閉じて参照が壊れる。
  `[` `]` を両方エスケープすれば `](obj:` の早期閉じも含めてラベル終端の破壊を塞げる
  (解析器 §7 はこの canonical 形だけを認識し、un-escape は逆順で行う)
- 改行は LF に統一。field は上記の順で固定。meta 5 行 (v / page / bbox / source_id / media_type)
  は annotation の有無に関わらず常に出力する
- `v` は **grammar version** (現行 1)。§7 の解析器は v を見て版別に dispatch する。grammar を
  将来変更する場合は v を +1 し、既存の保存済み Markdown を**一括再 materialize** する移行手順を
  取る (画像 bytes と旧 block の値から復元できるため OCR 再課金なし)。
  **旧版行の特定は追跡列を持たず、markdown_documents を全走査して保存済み Markdown の先頭
  img block の `v:` 行を読んで判定する** (版は Markdown 自身に埋まっているため専用列は不要 —
  内容から導出できるものを二重化しない)。**img block を 1 つも含まない (画像 0 件の) 文書は
  grammar version の対象外として常にスキップする** — grammar の版は img block の encoding にのみ
  関わる (「v 不明 = 旧版」と誤って扱うと無意味な再構築 + generated_at 更新が agg へ伝播する)。
  **文書内の img block 間で v が一致しない場合 (混在) も未知の v と同様に fail-closed とする** —
  「最初の block の v を正とする」前提で残りを解釈すると、先頭 block の改変・別版の手書き混入が
  後続 block の誤解釈になる (判定の入口は先頭 block の v、確定は全 block の一致検査)。
  **未知の v (自装置の解析器より新しい版) の block を含む Markdown の再解析は fail-closed で
  スキップ + status とする** — テキスト扱い・推測 dispatch は chunks / text_hash を実装依存に
  分岐させる (新しい版のアプリが再 materialize した派生を、旧アプリは読み取り専用として扱う)。移行はフォルダ単位で再開可能: 各派生の再 materialize は
  §5.3 の DELETE → INSERT 置換 (generated_at 単調更新) と同じ Tx 規律に従い、中断しても未処理の
  v=旧 行が次回も検出される。同様に**チャンク規則・画像フィルタのグローバル変更 (§7 / §8) の
  一括再チャンクも、markdown_documents 全走査で対象を列挙**する (再解析はローカル操作で
  再課金なし。大規模時は §16 のフォルダ単位分散実行を推奨)
- `media_type` は保存時に画像 bytes のマジックバイトから**決定論的に判定**して書く
  (image/png・image/jpeg・image/gif・image/webp・image/tiff・image/bmp。判定不能は
  application/octet-stream) — chunks.media_type (NOT NULL) を Markdown だけから充填するため
- 各 field 値は 1 行に正規化する (値内の改行は空白 1 個へ置換)。エスケープは**可逆**に行う —
  まず `\` を `\\` へ、次に `-->` を `--\>` へ置換する。解析時の un-escape は逆順
  (`--\>` → `-->` → `\\` → `\`)。元値に `--\>` が含まれていても `--\\>` として保存されるため
  往復で変質しない
- **既存本文のエスケープ (phantom block の防止)**: materialize 時、OCR が返した本文テキスト側の行が
  **「0 個以上の `\` に続いて canonical grammar 形 (行頭パターン `![` + `](obj:`、または
  `<!-- img:`) が現れる形」である場合、その行頭へ `\` を 1 個前置する** (G→`\G`、`\G`→`\\G`、
  `\\G`→`\\\G`) — 裸の grammar 形だけを対象にすると、元から `\` + grammar 形だった本文行が
  素通りし、§7 の un-escape (1 個除去) が原文を変質させる。この規則で §7 との往復が全段で可逆に
  なる (**test vector に 3 段 — G / `\G` / `\\G` — の往復例を含める**)。本文が偶然・意図的に
  grammar を偽装して phantom image チャンクを生む経路を塞ぐ (§7 の実在検証と併せた二層防御)。
  **エスケープは OCR 応答由来の本文への保存時 1 回限りの変換** — grammar 再 materialize (v 移行の
  一括再生成) は本文を保存済み Markdown (既にエスケープ済み) から引き継ぐため、**本文エスケープを
  再適用しない** (再適用は「0 個以上の `\` + grammar 形」に再一致して `\` を版ごとに累積させる)。
  **エスケープは保存時変換 2 のページ結合後の全文に対して行う** — ページ単位に先へ掛けると、
  結合 (LF join) が新たに作る行頭 (前ページ末尾が改行なしで grammar 断片が次ページ先頭と連結する
  ケース) を取り逃がす

コスト (確定値): OCR 4 標準 $4 / annotation 付き $5 (+25%) / **Batch で 50% 割引 → 実効 $2.5 per 1,000 ページ**。
課金は**同一 `(content_hash, tool_profile_hash)` につき 1 回きり** — 内容が変わらない限り再課金されず、
tool profile の変更 (モデル版・annotation スキーマ等) 時は同じ内容でも再 OCR される (§4 の identity)。

# 7. チャンク分割規則

入力は **objects/ に保存済みの Markdown 全文** (API 応答ではない)。この設計により分割規則が OCR ベンダーの
応答形式に依存しない。

```text
1. ATX 見出し (行頭 1〜6 個の # + 空白) をチャンク境界とする。
   コードフェンス内の # は見出しと見なさない。setext 見出しは対象外。
   **コードフェンスの認識は CommonMark の fenced code block 規則に固定する**: ` ``` ` または
   `~~~` の 3 個以上 (行頭 0〜3 空白のインデント許容)、閉じは開始と同種の文字で開始以上の長さ、
   EOF まで閉じが無ければ残り全文をフェンス内として扱う。**4 空白インデントのコードブロックも
   同様に見出し抑制の対象**とする — 規則を固定しないと同一 Markdown から実装ごとに異なる
   チャンク境界・text_hash が生まれ、embedding の内容共有が実装間で崩れる
2. heading_path = チャンク開始位置で有効な見出しスタック。最初の見出しより前は []
3. §6 canonical img block grammar の画像参照行は 1 行 = 1 つの独立した image チャンク。
   seq は本文中の出現位置で採番 (text と image の通し順)。
   - image チャンクの text = 直後の img block の **description と transcription の値のみ**
     (field ラベル・コメントマーカーは含めない) を LF で連結。両 field が無ければ text = NULL
   - image チャンクの image_meta = img block の **page / bbox / source_id / image_type の値**から、
     chunks.media_type = img block の **media_type 行**から充填する (いずれも Markdown から
     常に再構築可能)。**annotation OFF で image_type 行が無い場合は image_meta の image_type
     キーを省略する** (JSON に null を入れない — §4.1 の「値が無いフィールドは省略」と同じ規則)
   - 文書由来のキャプション行は image チャンクへ取り込まない (通常本文として text チャンク側に
     残り、FTS でヒットする)
   - **実在検証**: image_hash が objects/ に実在することを確認し、実在しない参照は image チャンクを
     生成せず規則 4 の除去のみ行う (phantom チャンクの防止 — §6 の本文エスケープと併せた二層防御。
     本文由来の grammar 偽装は §6 でエスケープ済みのため、非エスケープの img block は
     materialize 由来のはずであり、実在しない hash は破損か偽装のどちらか)
4. 画像参照行と、その直後に続く img block (開始行から `-->` 行まで) は
   text チャンクの本文から除去する
   → text_hash が画像・annotation の変化に影響されず、embedding 再利用率が上がる。
   **除去の単位は「行全体 + その行末の LF」** (参照行から `-->` 行の LF まで) とし、除去に伴う
   空行の圧縮・追加はしない — LF の扱いを固定しないと同一 Markdown から実装ごとに異なる
   text_hash が生まれる (実装の最初の作業とする test vector に本規則の例を含める)。
   **参照行・img block の認識は「行全体が grammar に一致」する場合のみ** (値の途中に現れる
   類似文字列への部分一致は禁止)。**un-escape (可逆性)**: §6 の phantom 防止で行頭 `\` を前置
   された行は、text チャンクの本文へ含める際に **`\` を 1 つ除去**する。**un-escape の対象判定は
   §6 のエスケープ条件と同一のパターン** — 「1 個以上の `\` に続いて grammar 形 (行頭パターン
   `![` + `](obj:`、または `<!-- img:`) が現れる行」であり、**行全体の厳密 grammar 一致
   (hash64 の妥当性) は要求しない** (encoder (§6) はパターンで広くエスケープするため、decoder を
   厳密一致に限ると `\![diagram](obj:see appendix)` のような「§6 一致・厳密 grammar 不一致」の
   行の `\` が残留し往復可逆が破れる。**画像チャンクとしての認識は上記の行全体厳密一致 +
   実在検証のままで不変** — un-escape の条件を encoder に揃えても phantom 防止は弱まらない)。
   除去しないと原文と異なる text が FTS・プレビューに恒久残留する (元から `\` + grammar 形
   だった行は §6 で `\\` になっており、1 つ除去で原文へ戻る — 往復可逆)。char span は
   保存済み Markdown (エスケープ済み) 上の位置のまま。**除去・un-escape 後の本文が空白のみになる
   文書 (画像のみの文書・フィルタで全画像が除外された文書) は text チャンクを生成しない** —
   空 text チャンクの有無が実装で分岐すると seq / FTS / embed 対象が分岐する。
   **image はチャンク境界ではない** (境界は規則 1 の ATX
   見出しのみ) — セクション途中に画像がある場合、text チャンクは除去後の前後本文を 1 つに
   連結した単一チャンクとし、char span は除去前の Markdown 上の位置で表す
5. (補助) 1 見出しセクションが max_chars (**既定 2,000。単位は Unicode スカラー値**) を超える
   場合のみ、段落境界 (空行) で貪欲分割する。**空行が無いまま 2 × max_chars を超える場合は
   文字位置で hard split する (overlap なし)**。分割片は heading_path を共有する
6. opt-in 画像フィルタ (§8) が ON の場合、除外条件 (objects/ の画像 bytes の最小サイズ閾値、
   または img block の image_type が除外リストに合致) に該当する画像参照は **image チャンクを
   生成しない** (規則 4 の本文からの除去は行う)。フィルタ設定の変更は下記の再チャンク経路で
   全派生に反映する
7. OCR 結果の Markdown が空 (0 bytes または空白のみ) の場合、チャンクは 1 つも生成しない
   (markdown_documents の行 = done は通常どおり作る)。空文字 text チャンクは FTS にトークンを
   持たず embedding も無意味なベクトルになるため、行だけ増やさない
```

分割規則の変更は OCR 再課金なしのローカル操作: 同一 Tx で対象派生の chunks を DELETE →
保存済み Markdown から再解析して INSERT し、**markdown_documents.generated_at を現在時刻へ
単調更新する**。generated_at の更新は必須である — 集約層の置換検出 (§9.3-b) は generated_at
比較で行うため、更新しないと再チャンク結果が横断検索へ永久に反映されない。
text_hash 不変の chunk は embedding が自動再利用される。

**floor の同時引き上げ (必須)**: generated_at を進める**すべてのローカル変換** (本節の再チャンク・
§8 フィルタ変更・§6 grammar 再 materialize) は、対象ペアの batch_requests 行に
floor_generated_at が設定されている (NULL でない) 場合、**floor を新しい generated_at 以上へ
引き上げる**。順序は **app (floor 引き上げ) → metadata (generated_at 更新)** とする —
floor の先行引き上げは「成果なし」範囲を広げるだけで再 OCR 方向に倒れる fail-safe だが、
逆順はクラッシュ窓で generated_at > floor が成立し、**明示再生成 (§5.3) が黙って取り消される** —
未投入なら再 OCR 不発、in-flight なら collect 冒頭スキップが課金済みの新 OCR 結果を破棄して
成功報告する (課金事故)。

一括再チャンク (規則・フィルタのグローバル変更) は、行に規則版を持たないため**中断後は全派生を
対象にやり直す** (差分再開しない — ローカル操作で再課金ゼロのため全量再実行を許容する。冪等。
フォルダ単位の完了管理は §16 の分散実行の範囲で実装裁量)。**中断 (クラッシュ) の再開駆動は
明示操作の再実行**とする — 途中状態 (新旧規則のチャンク混在) は無害で、再実行が全派生を現行
規則で置換して収束する。**実行中・未完了の表示のため、一括変換の開始時に app_config へ operation
record (**key = `'bulk_operation'`** — §9.1 の許可 key 集合に含まれる。値 = JSON {変換の種別,
目標規則 / フィルタの record または hash, 開始時刻}) を書き、全量完了時に消す** — 行に規則版を持たない (§18) ため、この record が無いとクラッシュ後に「未完了の一括変換が
ある」ことを status が判定できない (record が残っていれば「一括変換が未完の可能性 — 明示再実行で
解消」を表示する。record は表示と再実行誘導のためだけの hint — 収束の正しさは再実行の全量置換が
担い、record を失っても壊れない)。自動再開の常駐機構は持たない。
**チャンク規則・フィルタは device-local (app 側)** — 他 device 由来のフォルダをコピー・再登録した
場合、旧規則で作られた chunk が残り得る (行に規則版を持たないため自動検知しない)。収束経路は本節の
一括再チャンク (ローカル・無課金) の明示実行 — register を自動再チャンクで重くしない。

# 8. Embedding

- **単一マルチモーダル profile に固定する**。text 用と image 用に別モデル (別ベクトル空間) を使う構成は
  禁止 — 別空間ではテキストクエリで画像を引くクロスモーダル検索が成立しない。起動時に
  `embeddings.embedding_profile_hash / dimensions` の全行一致に加えて **embedding_vec 表の存在と
  次元 (現行 profile の dimensions — **app_config の embedding_profile record から読む**。§5.7 は
  履歴の保管庫で新規フォルダでは空 — §10 step 3 と同一の参照元。フォルダ単独 (app 不在) の検査は
  §11.2 の一意 profile 規則) の一致**を検査する
- **profile (モデル・次元・距離) の変更 = 「現行 profile 設定の更新」1 操作のみ**。以降は全経路が
  宣言的に収束する — 多段の手動手順・行の一括削除は行わない (手順の途中クラッシュで壊れた中間
  状態が残る設計を排除する)。**設定の適用前に vec0 の受理検証を行う**: 新 record の `<dim>` /
  `<metric>` で一時 vec 表の CREATE を試行し、拒否 (非対応 metric・次元上限超) されたら設定を
  commit せず status で報告する — 無検証で commit すると §8-c / §8-e の DROP → CREATE が毎 tick
  失敗して KNN が恒久停止する (設定の妥当性はこの 1 点で fail-fast にする):
  a. **成果判定が profile を含む**: kind=2 の「フォルダ成果あり」(§9.1) は (target_type,
     target_hash) 行の存在**かつ embedding_profile_hash = 現行**。旧 profile 行は成果なしと
     扱われ、次 tick の Embed submit が全対象を再投入する。kind=2 の batch_requests 行は
     **削除しない** — INSERT 初回のみ規範のまま UPDATE で再投入され、in-flight の旧 job は
     collect の profile 照合 (§9.1) が破棄して行を閉じる。**再課金ガード (attempts) は「同一
     profile 内」で数える**: profile_hash が現行と異なる行の再投入では、**state を問わず**
     attempts = 0 にリセットしてから数え直す (§9.1 相 1。terminal 行に限定すると state=2 の
     旧 profile 行が旧 attempts を引き継ぎ、新 profile の初回失敗で即 terminal になる)。
     submission_seq はリセットしない (課金記帳の通算連番 — §9.1)。
     (これが旧設計で「全行削除」していた理由の正しい置き換え — 課金ガードは profile ごとに
     独立して効き、job handle と履歴は失われない)
  b. **collect の INSERT は置換**: 同一 (target_type, target_hash) に旧 profile の行が残って
     いれば、同一 Tx で embedding_vec → embeddings の順に DELETE してから INSERT する
  c. **embedding_vec は完全導出物**: tick の Embed submit 冒頭で vec 表の**次元と距離 (distance_metric)**
     を現行 profile (**app_config の embedding_profile record** — §8 冒頭 / §10 step 3 と同一の
     参照元。§5.7 は履歴の保管庫で新規フォルダでは空のため参照元にならない) と照合し、
     **いずれか不一致なら DROP → CREATE する** — 距離だけの
     変更は次元一致で見逃され旧 metric の順位が黙って残るため、次元と距離の両方を照合する。
     **profile hash 自体は照合しない (§8-e と意図的に非対称)**: フォルダ層は「vec を構築した
     profile」の耐久記録を持たないため hash 照合を構成できないが、次元・距離が同一の profile
     切替は b の行単位置換が漸進的に入れ替え、移行中の混在は §11.2 の一意 profile gate が KNN を
     FTS へ縮退させて覆う (実害の残らない意図された非対称)。
     さらに (**次元・距離一致の場合も毎回**) embeddings の
     現行 profile 行のうち **embedding_vec に target_key が無いものを冪等 INSERT で再充填する**
     — 差集合ベースにするのは、次元照合だけでは「CREATE 済み・再充填の途中でクラッシュ」した
     半端な vec 表 (次元は正しいが行が一部欠落) を検出できず、欠落分の KNN が永久に 0 件に
     なるため。差集合なら DROP → CREATE → 再充填のどの位置でクラッシュしても次 tick が残りを埋める
  d. **旧 profile 行の掃除**: 同じく Embed submit 冒頭で、embeddings の profile 不一致行を
     embedding_vec → embeddings の順に一括削除してよい (b の置換だけでも収束するが、
     全 re-embed の完了を待たずにストレージを回収できる)
  e. **集約側 (フォルダ側 c と同型の宣言的検査)**: tick の Replicate (§10 step 5) 冒頭で、
     agg_vec の**次元と距離**と app_config (§9.1) の agg 構築 profile を現行 profile と照合し、
     いずれか不一致なら agg_embeddings / agg_vec を破棄 (**agg_embeddings は行 DELETE、
     agg_vec のみ DROP → CREATE** — agg_embeddings は通常表なので schema ごと消さない) して
     再レプリケーションする。**破棄 (building 書込 + agg wipe) と同一 app Tx で、sync_state の
     synced_profile_hash を全行 NULL へ戻す** — 破棄前の完了値を残すと、profile を旧値へ戻した
     再訪 (P2→P3→P2) で全フォルダの synced=P2 が building=P2 と即・全一致し、**wipe 直後の空の
     agg のまま ready が立つ** (空 index の KNN 0 件が正常扱いされる)。
     **app_config の agg 構築 profile は building / ready の 2 key に分ける**:
     破棄時に `agg_building_profile_hash` = 現行を書き ready を消す → **接続フォルダすべてが
     building profile で §9.3-c を完了した時点で `agg_ready_profile_hash` = 現行へ更新する**。
     **ready 判定の母数 (接続フォルダ) = 「当該 tick に metadata を開けて §9.3 を実行できた
     フォルダ」** — folders 行があっても **missing / fork 中 / damaged / 一時読取不能のものは
     除外する** (missing だけの除外では不足 — damaged は root_path 現存で missing にならず、
     §9.3-c を永久に完了できないため、1 フォルダの破損が横断 KNN を恒久停止させる)。
     **接続フォルダが 0 件の間は ready を更新しない** (全称条件の空虚な真で空 index が ready を
     騙るのを防ぐ — status に「集約対象フォルダなし」を表示)。
     **「§9.3-c 完了」の判定は宣言的に行う**: 各フォルダに
     ついて (i) 現行 profile の eligible chunk のうち embeddings 未生成のものが無い (フォルダ側
     re-embed 完了) かつ (ii) その現行 profile embeddings が agg_embeddings / agg_vec に全て複製済み
     (差集合が空) を満たしたら **sync_state.synced_profile_hash を building へ UPDATE** し、ready 更新は
     「接続フォルダの synced_profile_hash がすべて building と一致」で判定する (per-folder の完了列が
     無いと「どのフォルダが新 profile を複製し終えたか」を追跡できず、0 行コピーの空 index が
     ready を騙る)。検索 (§11.2) が照合するのは ready — 単一 key だと「破棄直後・1 フォルダだけ
     同期済み」の部分 index が照合を通過して正常扱いされる。**ready は「設定時点の被覆」の宣言**
     であり、設定後に追加された新規 content の embed 遅延による部分性は通常状態 (非同期の宿命 —
     未 embed 残数は status。除外フォルダの復帰分も同様)。
     agg の意味論は「接続フォルダの和」であり、復帰したフォルダの分は次 Replicate の §9.3-c 差集合が埋める。
     (hash の app_config 表現は **lower hex64 に固定** — writer/reader の大小文字差で毎 tick
     再構築や恒久 KNN 停止を起こさない。)**命令的な「profile 変更イベント時に一度だけ破棄」ではなく毎 tick の
     冪等検査にする** — イベント時の一回破棄はクラッシュで飛ぶと agg_vec が旧次元のまま残り、
     §9.3-c の新次元 INSERT が vec0 に拒否されて replicate が毎 tick 落ちる。未 re-embed の
     フォルダが後から接続されても §9.3-c が現行 profile の行だけを扱うため旧空間の vector は
     混入しない。**same-profile での agg_vec の silent な欠落 (破損・部分喪失) は、フォルダ側 c と
     同型の差集合再充填で埋める**: Replicate 冒頭で agg_embeddings の現行 profile 行のうち agg_vec に
     target_key が無いものを冪等 INSERT で再充填する — 集約は cache だが、profile 変更を伴わない
     行喪失を「規約 9 の破棄・再構築」まで放置すると当該 target が KNN から永久欠落するため、
     ローカル c と同じ理由で毎 tick 差集合を検査する (fsck §13 も同じ差集合を検査する)
- 参考実採用値 (KCS): gemini-embedding-2 / 768 次元 (MRL 切り詰め) / cosine / L2 正規化。
  保存・クエリ両ベクトルを L2 正規化するため cosine 距離の順位は厳密
- 対象: chunk_type=1 → `text` を embed / chunk_type=2 → objects/ の画像 bytes を embed。
  **既定は全 chunk が対象**。embeddings の行は必ず `(chunks.chunk_type, chunks.embed_hash)` を
  キーとして作る — それ以外のキーの行は検索 join (§11.2) から到達できない死に行になるため
  **禁止**する (annotation テキストの検索は FTS 経路 §5.5 が担う)
- **プロバイダに server-side batch が無い場合** (例: Vertex はバッチ推論非対応 — KCS 実測) も、
  §9.1 の batch_requests を client 側キューとして同じ状態機械で回す (§1 のとおり「Batch」の
  確定範囲は OCR = Mistral Batch API。embedding は「非同期ジョブ」の意)。ただし**この構成では
  intent 回復が依拠する「job 一覧照会」も、呼出中クラッシュを識別する手段も存在しない**ため、
  写像を次のように固定する:
  (i) **実行前計上**: 同期 API を呼ぶ**前に** app Tx で attempts+1・submission_seq+1・
      batch_job_id = intent_token (client 実行 id として流用 — cost_ledger の batch_job_id にも
      これを記帳する)・submitted_at・**投入時 profile の snapshot (kind=2 は profile_hash = 現行、
      kind=1/2 とも profile_record = 現行 record — 相 1 と同じ書込)** を永続化する (相 1 と相 3 の
      統合に相当)。**profile_hash / profile_record を欠くと、kind=2 の DDL CHECK (profile_hash 非 NULL
      を state 非依存で課す) 違反で前計上 INSERT 自体が始められず、collect の §5.7 保存
      (record_json 非 NULL) も成立しない**
  (ii) 呼出成功 → 同 tick 内で即 collect (metadata Tx + cost_ledger + state=2) まで進める。
      **呼出失敗は相 2b と同じ 2 分岐**: 一時 (429 / 断 / 5xx) = 行は前計上のまま次 tick の回復
      対象 (Retry-After は retry_not_before へ) / **恒久拒否 (内容起因の 4xx) = state=3
      (error='submit_rejected') + 同 Tx で attempts=上限、かつ batch_job_id を NULL へ戻す** —
      恒久 4xx は「未実行の確定」なので ledger 記帳はしない — **「内容起因 4xx = 課金なし」は
      プロバイダ前提であり、拒否にも課金する provider を採用する場合はこの分岐にも記帳を足す** (§9.1 の
      同規範と同じく **submission_seq を +1 へ行 UPDATE し、その新値で冪等記帳** — seq 現値のままは
      明示 retry 後の 2 度目の課金される拒否と UNIQUE 衝突し実課金が吸収される)
      (server 相 2b と非対称にすると
      client だけ attempts を浪費して無駄な再呼出を繰り返す)。batch_job_id (= intent_token) を
      残すと、後日この target が成果あり化した際に reconcile close の付随処理 (b) — batch_job_id
      非 NULL なら記帳 — が**未実行と確定した attempt を誤記帳**する
  (iii) クラッシュ回復: 前計上済み (batch_job_id 非 NULL・state=0) の行は「**実行された可能性が
      ある**」として扱い、遷移表の再投入判定 (attempts 上限) に従って再実行する。
      **再実行の前計上 Tx では、まず直前 attempt の submission_seq を NULL + estimated で冪等
      terminal 記帳 (ON CONFLICT DO NOTHING) してから attempts+1・submission_seq+1 を行う** —
      呼出中クラッシュ (プロバイダは処理・課金済みであり得る) の attempt を上限到達時の 1 件
      しか記帳しないと、中間 attempt の課金が台帳から永久に欠落する (client_exhausted の記帳を
      毎回の再実行に一般化 — §9.1「実行された可能性のある課金を取りこぼさない」)。
      **再実行は相 1 の規則一式を含む**: profile_hash が現行と異なる行は attempts=0 に数え直し、
      profile snapshot (profile_hash / profile_record) を現行で書き直してから前計上する (§8-a —
      dispatch 経由で相 1 を迂回すると旧 profile の attempts を新 profile が引き継ぐ)。
      **attempts >= 上限に達した state=0 行は state=3 (error='client_exhausted') へ閉じ、同 Tx で
      旧 seq を terminal 記帳 (NULL + estimated) する** (§9.1 intent 回復の dispatch が実行点 —
      この分岐が無いと上限到達の state=0 は submit / reconcile / collect / 明示 retry / 滞留監視の
      すべての対象外で永久滞留する)。正常完了の close (state=2 + cost_ledger) は同一 app Tx
  **「重複課金は最悪 job 1 回分」の主張は server-side batch 経路限定**である — client 経路では
  呼出中クラッシュ (プロバイダは処理・課金済み・応答未受信) を区別できないため重複課金は
  原理的に排除できず、**attempts 上限 (既定 3) による有界化**に留まる。実行前計上が無いと
  attempts が永続化されず (相 3 でのみ +1 だと呼出後クラッシュで 0 のまま)、この有界化すら
  成立しない — 「未実行として無条件再実行」の記述は誤り
- **opt-in の画像フィルタ** (既定 OFF): 設定で最小バイト閾値や img block の image_type
  除外リスト (logo / decoration 等) を有効化した場合、該当する画像参照から **image チャンク自体を
  生成しない** (§7 規則 6)。chunks に行が無いため、FTS・KNN・embed submit のすべてから一貫して
  消え、検索側 (§11.2 eligible) に特別な分岐は不要。**フィルタ設定は app_config に canonical record
  (JCS bytes) で永続化する (専用の hash key は持たない — 比較は record bytes の一致で行い、hash が
  必要な文脈では読み手が SHA-256 を計算する)** — tool / embedding profile と同格の「現行設定」であり、
  app 全損後の bootstrap で再入力しないと「既存 chunks がどのフィルタ設定で作られたか」を復元できず
  (規約 7-f の損失に含む)、既定との差分検出も不能になる (§21.5 で再入力)。**設定の変更 (ON/OFF・
  条件変更) は §7 の再チャンク経路で全派生に反映する** (chunks DELETE → 再解析 → generated_at 単調
  更新 → §9.3-b で集約へ伝播)。切替前に投入済みの embed job が後から回収されても、対応する chunks
  行が無い embeddings 行はフォルダ側の孤児掃除 (§13) が回収する。既定動作は冒頭のとおり全対象

# 9. app.sqlite (アプリ配下)

## 9.1 運用層 — folders / batch_requests / cost_ledger

```sql
CREATE TABLE folders (
    repository_id BLOB PRIMARY KEY               -- .folder-history/repository-id
        CHECK (typeof(repository_id) = 'blob' AND length(repository_id) = 16),
    root_path TEXT NOT NULL,                     -- 現在の場所 (repository_id による再発見のたびに更新
                                                 --  — 起動時・定期 walk の両方。§20.4)
    last_seen_at INTEGER NOT NULL,               -- 書込規則: folders 行の INSERT (register / fork 手順 3)
                                                 --  と再発見・rebind (§20.4 / §21.1) で now へ更新
    missing_since INTEGER                        -- root_path 不在を最初に観測した時刻 (UTC ms)。
                                                 --  再発見で NULL へ戻す。§20.4 の猶予 30 日は
                                                 --  この列を起点に判定する — last_seen_at 起算だと
                                                 --  初回不在で即満了 / 毎 tick 更新だと永久に
                                                 --  満了しない、のどちらかに壊れる
) WITHOUT ROWID;

CREATE TABLE batch_requests (                    -- 可変のガード行 (真実・課金履歴を持たない)
    repository_id BLOB NOT NULL
        CHECK (typeof(repository_id) = 'blob' AND length(repository_id) = 16),
    kind INTEGER NOT NULL CHECK (kind IN (1, 2)),  -- 1 = OCR, 2 = embedding
    target_key TEXT NOT NULL,                    -- kind=1: hex(content_hash) || ':' || hex(tool_profile_hash)
                                                 -- kind=2: chunk_type       || ':' || hex(embed_hash)
                                                 -- (SQL で構築するなら lower(hex(...)) — hex() は大文字を
                                                 --  返す。小文字固定は §5.6 / §11.2 の契約と同一)
    state INTEGER NOT NULL
        CHECK (state IN (0, 1, 2, 3)),           -- 0 = submit intent (2 相 submit の相 1)
                                                 -- 1 = submitted, 2 = done, 3 = failed
    batch_job_id TEXT,                           -- server-side batch の job id / client 側キューの実行 id。
                                                 --  server 経路の state=0 では NULL (**行上は未記録 —
                                                 --  job は存在し得る** (相 2b 完了・相 3 前クラッシュ)。
                                                 --  未作成の断定は §9.1 intent 回復の照合・期限判定・
                                                 --  job_create_started_at が行う — この NULL を「job
                                                 --  不存在」の根拠にしない)。
                                                 --  client 経路は実行前計上 (§8) で state=0 でも
                                                 --  実行 id (= intent_token) を持つ
    intent_token TEXT,                           -- 2 相 submit の突合キー (job の metadata に埋める。
                                                 --  同一 job に積む行は同じ値を共有)
    upload_id TEXT,                              -- プロバイダへ upload した入力ファイル id (§6 の後始末)
    scope_id TEXT,                               -- 相 2b 直前に job_create_started_at と同じ小 Tx で
                                                 --  記録する provider account / workspace の canonical
                                                 --  識別子 (§9.1 照合の「同一 scope」判定の基準。
                                                 --  NULL = 相 2b 未着手 or 旧版由来 — 照合は unknown)
    job_create_started_at INTEGER,               -- 相 2b (job 作成呼出) 開始直前に単独の小 Tx で記録
                                                 --  (伝播猶予の起点 — §9.1。NULL = 相 2b 未着手 =
                                                 --  job は存在し得ない。再試行では上書き。**相 1 の
                                                 --  token rotation で NULL へ戻す**。**「NULL = 未着手
                                                 --  の証明」は列導入後の lifecycle 限定 — 列追加
                                                 --  migration では state=0 かつ intent_token 非 NULL
                                                 --  の既存行へ token の時刻成分を backfill (§14)**)
    upload_cleaned INTEGER NOT NULL DEFAULT 0,   -- upload 削除済みフラグ (掃除は state と独立に再試行)
    attempts INTEGER NOT NULL DEFAULT 0,         -- リセット可能な再試行ガード (照会失敗は数えない)。
                                                 --  上限は app 設定 (既定 3)。上限超の failed は
                                                 --  明示操作でのみ再試行 (再課金ガード。kind=2 は
                                                 --  profile 内で計数 — §8-a)。**課金記帳のキーには
                                                 --  使わない** (リセットで番号が再利用されるため)
    submission_seq INTEGER NOT NULL DEFAULT 0,   -- **リセットしない通算投入連番** (job 作成 / client
                                                 --  実行のたびに +1。明示再生成・profile 数え直しでも
                                                 --  戻さない)。cost_ledger の一意キーはこちら。
                                                 --  **行の新規 INSERT 時の初期値は 0 ではなく
                                                 --  cost_ledger の同キー MAX から継承する** (§5.3 —
                                                 --  行は削除される・ledger は永続のため、0 起点は
                                                 --  再登録後の再投入で旧 ledger と UNIQUE 衝突する)
    error TEXT,
    submitted_at INTEGER,                        -- 最新 attempt の投入時刻 (attempt 履歴は cost_ledger)
    completed_at INTEGER,                        -- state が 2/3 へ確定した時刻 (**確定する全ての
                                                 --  UPDATE で同時に書く** — collect に限らず
                                                 --  reconcile / submit_rejected / client_exhausted /
                                                 --  expired / cancelled / detached / abandoned も。
                                                 --  §9.1 の共通規範)。未終端は NULL
                                                 --  (未終端 NULL は status の滞留検知に使う)
    profile_hash BLOB,                           -- kind=2: 投入時の embedding_profile_hash
                                                 --  (collect 時に現行 profile と照合 — 不一致は破棄)
    profile_record TEXT,                         -- **投入時 profile record の snapshot** (JCS bytes —
                                                 --  kind=1 は tool profile / kind=2 は embedding
                                                 --  profile)。collect はこれを §5.7 profiles へ
                                                 --  INSERT する — current 参照だと tool / profile
                                                 --  切替中の in-flight job の record を復元できない
    floor_generated_at INTEGER,                  -- kind=1: 明示再生成 (§5.3) の単調性 floor +
                                                 --  成果判定の入力。通常投入は NULL
    PRIMARY KEY (repository_id, kind, target_key),
    CHECK (                                      -- profile_hash は kind と連動させて強制する:
        (kind = 1 AND profile_hash IS NULL)      --  kind=2 で NULL を許すと「投入時 profile 不明」の
        OR                                       --  行が生まれ、collect の profile 不一致破棄 (§9.1
                                                 --  collect 規則) をスキーマで保証できない
        (kind = 2 AND typeof(profile_hash) = 'blob' AND length(profile_hash) = 32)
    ),
    CHECK (state <> 1 OR batch_job_id IS NOT NULL),
    CHECK (state NOT IN (0, 1) OR profile_record IS NOT NULL),  -- 相 1 / client 前計上の必須 snapshot を
                                                 --  スキーマでも強制 (terminal marker 等は対象外)
    CHECK (floor_generated_at IS NULL OR kind = 1),  -- floor は kind=1 (OCR) 専用 (§5.3)
    CHECK (upload_cleaned IN (0, 1))
) WITHOUT ROWID;
CREATE INDEX idx_batch_open   ON batch_requests (batch_job_id) WHERE state = 1;
CREATE INDEX idx_batch_active ON batch_requests (repository_id, kind) WHERE state IN (0, 1, 3);

CREATE TABLE cost_ledger (                       -- 課金履歴 (追記専用 — UPDATE / DELETE 禁止)
    ledger_id INTEGER PRIMARY KEY,               -- rowid
    ts INTEGER NOT NULL,                         -- 課金の確定 (collect / close 記帳) 時刻 UTC ミリ秒。
                                                 --  月次コスト = GROUP BY strftime('%Y-%m', ...) は
                                                 --  この列で行う (attempt 単位。**確定月への配賦**で
                                                 --  あり、provider 側の請求発生時刻とは長期停止で
                                                 --  数か月ずれ得る — 正はプロバイダ側 §16)
    repository_id BLOB NOT NULL
        CHECK (typeof(repository_id) = 'blob' AND length(repository_id) = 16),
    kind INTEGER NOT NULL CHECK (kind IN (1, 2)),
    target_key TEXT NOT NULL,
    batch_job_id TEXT NOT NULL,                  -- 値の規則: server job id / client 実行 id
                                                 --  (= intent_token 流用 §8) / **無 id 記帳
                                                 --  (期限超 confirmed-absent — intent 回復・
                                                 --  detached・(b')/token sweep 前段の期限超分岐)
                                                 --  は intent_token** / **job 発見記帳 ((b')・
                                                 --  token sweep 前段の found) は照合で発見した
                                                 --  実 job id** —
                                                 --  job id 不明の記帳に入れる値が無いと INSERT が
                                                 --  NOT NULL 違反で intent 回復ごと恒久停止する。
                                                 --  この列は「記帳済み判別」の突合キーを兼ねる (§9.1)
    submission_seq INTEGER NOT NULL,             -- その時点の batch_requests.submission_seq
                                                 --  (**attempts は使わない** — リセットで番号が
                                                 --  再利用され、正当な再課金の記帳が UNIQUE 衝突で
                                                 --  恒久失敗する。seq はリセットしない通算値)
    pages INTEGER,                               -- kind=1: 実測ページ数
    cost_usd REAL,                               -- 単価非公開プロバイダ・client 側キューでは取得不能
                                                 --  = NULL 可 (「無料」ではなく「未取得」)
    cost_estimated INTEGER NOT NULL DEFAULT 0,   -- 1 = cost_usd は推定値。月次集計は実額と推定を
                                                 --  分けて表示し「未確定」を「$0」に埋没させない
    UNIQUE (repository_id, kind, target_key, submission_seq)  -- 同一 seq は 1 行のみ。**writer は必ず
                                                 --  INSERT … ON CONFLICT DO NOTHING (§9.1 close 規範)**
                                                 --  — 衝突は「同一課金の再観測」の吸収でありエラー
                                                 --  ではない。素朴 INSERT は close Tx を abort させる
);
CREATE INDEX idx_cost_month ON cost_ledger (ts);

CREATE TABLE app_config (                        -- デバイスの現行設定 (単一行相当の key-value)。
    key   TEXT PRIMARY KEY,                       -- 現行の key 契約 (**許可 key 集合 — 存在条件は
                                                 --  key 別**: profile 系 = bootstrap 再入力後は必須 /
                                                 --  retry_not_before = 抑止中のみ / agg 2 key = 構築
                                                 --  開始後 / fork_in_progress = fork 中のみ /
                                                 --  bulk_operation = 一括変換 (§7) 実行中のみ。
                                                 --  「すべて必須」ではない — bootstrap 直後・非 fork 時
                                                 --  の不在は正常。DDL コメントだけ見て
                                                 --  旧単一 key を実装すると §11.2 の ready 照合が永久
                                                 --  不一致で KNN が恒久停止する):
                                                 --   'tool_profile'              = 現行 OCR profile_record
                                                 --   'embedding_profile'         = 現行 embedding profile_record
                                                 --   'image_filter'              = 現行フィルタ record (§8。既定 OFF)
                                                 --   'retry_not_before'          = provider・kind 別の submit /
                                                 --                                 collect 抑止期限 (§9.1。JSON)
                                                 --   'agg_building_profile_hash' = agg 破棄・再構築中の目標
                                                 --   'agg_ready_profile_hash'    = agg_vec が全接続フォルダで
                                                 --                                 複製完了した profile (§8-e —
                                                 --                                 §11.2 が照合するのはこちら)
                                                 --   'fork_in_progress'          = fork 中のみ存在 (§21.3 —
                                                 --                                 JSON {old_id, new_id, realpath,
                                                 --                                 started_at}。tick.lock 直列化 +
                                                 --                                 毎 tick 冒頭回復により高々 1 件)
                                                 --   'bulk_operation'            = 一括変換 (§7) の operation record
                                                 --                                 (JSON {種別, 目標規則 / フィルタ,
                                                 --                                 開始時刻}。実行中のみ存在 —
                                                 --                                 全量完了時に消す)
                                                 --  hash 値はすべて lower hex64 に固定する (§8-e)
    value TEXT NOT NULL                           -- profile_record (§4.1 JCS bytes) / hex(hash) / JSON
) WITHOUT ROWID;
```

**cost_ledger は追記専用**である。batch_requests は可変のガード (UPDATE で遷移・フォルダ退役で
DELETE) だが、発生済み課金は物理事実なので **profile 変更 (§8) でもフォルダ退役 (§9.3-d) でも
削除しない**。課金・ページ数を batch_requests の行に持たせない理由: 可変行の 1 行では attempt
単位の発生時刻を表現できず (月跨ぎ retry の誤配賦)、ガード行の削除が課金履歴を道連れにする。

**app_config は §8 の「現行 profile 設定」の実体**である。profile 変更 (§8) はこの 1 行の UPDATE =
単一の宣言的操作であり、成果判定 (§9.1)・vec 再作成 (§8-c)・agg 破棄 (§8-e) はすべてこの現行値を
参照して収束する。**横断検索 (§11.2) の `:query_vector` はこの `embedding_profile` record から
生成する** — フォルダ側の profiles 表 (§5.7) は各フォルダに閉じており、app.sqlite だけで完結する
横断検索には app 側に現行 profile record が必要になる (これが無いとクエリを embed できず横断検索が
実行不能になる)。フォルダ単独検索は §5.7 の profiles から、横断検索は app_config から読む。
hash ではなく record を保持するのは、hash が不可逆でモデル/次元/距離を復元できないため。

**状態遷移 (規範)**。行の INSERT は初回のみで、以降は UPDATE で遷移する (PK 衝突を構造的に排除)。
**「フォルダ成果あり」の定義 (submit / reconcile / collect のすべてが同じ定義を使う)**:

```text
kind=1: markdown_documents に該当行が存在し、かつ batch_requests 行の floor_generated_at が
        NULL または「行の generated_at > floor_generated_at」。明示再生成 (§5.3) の floor 以下は
        旧派生が残っていても「成果なし」— これが再投入の駆動力になる
kind=2: embeddings に (target_type, target_hash) の行が存在し、かつその
        embedding_profile_hash = 現行 profile (§8-a。旧 profile の行は「成果なし」)
```

```text
submit 時の判定 (対象キーごと。**フォルダ成果の存在が常に最優先**):
  フォルダ成果あり                                → 投入しない。行が state IN (0, 3) なら state=2 へ
                                                    閉じる (成果がある以上 failed は過去の話)。
                                                    **state=1 は閉じない** — collect が課金記録と
                                                    同時に閉じる (下記)
  成果なし・行なし                                → 投入対象 (下記 2 相 — INSERT は state=0 から)
  成果なし・state=0                               → 前回 submit の中断。下記「intent 回復」へ
  成果なし・state=1                               → 何もしない (回収待ち)
  成果なし・state=2                               → 投入対象 (app は真実でない — フォルダ DB の
                                                    再構築等で成果が消えたケースの再投入)
  成果なし・state=3・attempts < 上限               → 投入対象 (再投入)
  成果なし・state=3・attempts >= 上限              → 投入しない (terminal failed。復帰は明示操作
                                                    = attempts を 0 にリセットする操作のみ。
                                                    kind=2 で profile_hash が現行と異なる場合は
                                                    §8-a により attempts を数え直して投入対象)

profile 未設定 (bootstrap 直後 — app_config に当該 kind の現行 record が無い) の間は、その kind の
submit / client 前計上に加えて、**reconcile / collect の成果判定・§8-c の vec 検査 (kind=2)・
§8-e / Replicate の agg 構築 profile 検査も skip** し status「profile 未設定」を表示する — 現行
record が無いと成果判定 (現行 profile との一致) と `<dim>` / `<metric>` の展開が構成できない。
**state=1 の行は不変で保留** (再入力後の collect が回収・記帳する)。DDL の CHECK
(profile_record 必須) が fail-closed に拒否するが、期待挙動は skip であって tick 中断・エラー連発
ではない — §21.5 bootstrap の再入力で解除

submit の 2 相実行 (外部副作用と app 行の dual-write を「先に意図を永続化」で塞ぐ):
  相 1 (app Tx)  : 投入対象の行を state=0 へ INSERT / UPDATE し、job 単位の intent_token
                   (**新規 UUIDv7 — 時刻成分 = 相 1 の実行時刻を intent 回復の期限判定に使う**
                   (下記)。同一 job に積む行は同じ値。**JSONL を複数 job へ分割する場合は job ごとに
                   別 token — 分割の決定は相 1 の採番より前** (token は job 単位が規範 — 1 token に
                   複数 job を対応させると found 採用の job 特定が非一意になる)) を書く。batch_job_id は NULL へ戻し、
                   **error / completed_at / job_create_started_at / scope_id も NULL へ戻す** (旧 attempt の残骸が
                   滞留監視・伝播猶予の起点を汚さない — job_create_started_at を残すと時計後退と
                   重なった場合に旧 attempt の開始時刻を max() が拾い、未呼出の新 attempt が未来 skew /
                   期限超判定へ誤って入り attempts 消費・estimated 記帳を反復する。**scope_id を残すと
                   旧世代の scope が相 2b 未着手の行に残り**、資格情報切替後の照合が scope 不一致の
                   恒久 unknown へ誤誘導される — 実 job が存在しないのに stalled 化し、明示 abandon の
                   偽 estimated 記帳まで誘発する。scope_id は job_create_started_at と対で相 2b 直前に
                   記録され、相 1 で対で NULL へ戻る — 対の不変条件)。
                   **rotation ガード — state IN (2, 3) かつ intent_token 非 NULL の行を再投入
                   (明示 retry・遷移表再投入・floor 明示再生成 (§5.3 — state=2 も投入対象になる)) する場合は、先に当該 token の「照合・記帳・intent_token
                   NULL 化」を完了してから相 1 を行う** (floor 明示再生成では **§5.3 の floor /
                   attempts リセット Tx よりも前** — reset 後にガードの found 記帳 (attempts +1) が
                   落ちると、旧世代の消費が新世代の再試行予算を食う) — 先に rotation すると旧 token の照合キーが
                   消え、作成済み job の発見・記帳経路 ((b')/sweep) が恒久に失われる。**適用は
                   state IN (2, 3) の再投入に限る** (sweep の終端定義 (state 2/3) と同一 — state=2 でも
                   token 残存 = sweep 未完で、floor 再生成の相 1 が同じ上書きを起こす) — state=0 の
                   載せ直し (intent 回復の confirmed-absent) と
                   client 前計上の再実行 dispatch は、自身の照合・期限判定・記帳経路が旧 token を
                   処理済みのため対象外 (ここにもガードを課すと「sweep は全行終端のみ対象」と
                   自己循環し requeue が恒久不能になる)。**残骸掃除 (upload 削除) はガードの完了
                   条件に含めない** — best-effort 続行 (「削除失敗は続行 = 既知の残余」と整合。
                   ガードの本体は課金の照合・記帳・キーの引き継ぎ)。**照合が恒久 unknown (資格情報
                   喪失等) の行は保持のまま stalled として可視化し、明示 abandon (ユーザー確認で
                   estimated 記帳 + terminal 化 — token の NULL 化は残骸掃除完了時 (下記)) を脱出路とする** — 脱出路が無いと明示
                   retry・profile 変更が永久に拒否される。**abandon の操作実体 (§21 のカタログに
                   準ずる): 対象 = intent_token 非 NULL の行 (state 不問 — state=0 の照合が恒久
                   unknown の行も対象)。単一 app Tx で (i) 記帳済み判別 (同キー × batch_job_id IN
                   (行の batch_job_id (非 NULL の場合), 当該 token) の ledger 行) → (ii) 未記帳なら submission_seq +1 行
                   UPDATE + 新値で batch_job_id = token・NULL + estimated 記帳 → (iii) state=3
                   (error='abandoned') + attempts = 上限 + completed_at。**intent_token はこの Tx では
                   NULL 化しない — JSONL 残骸の唯一の発見キー (§6 の filename 埋込) で、先に消すと
                   掃除が JSONL を発見できず機密が provider TTL まで残留する**。残骸掃除と NULL 化は
                   token sweep の abandoned 例外 (下記 — 照合・記帳なしで掃除 → 全削除成功で NULL 化)
                   が引き継ぐ。後日 job が可視化されても sweep found
                   の IN 判別が token キーの記帳を「記帳済み」と判定し、二重計上しない。**
                   **投入時 profile の snapshot を書く**: kind=2 は profile_hash = :current_profile、
                   kind=1 / kind=2 とも profile_record = 現行 record (app_config §9.1) — DDL の
                   CHECK は kind=2 に profile_hash 非 NULL を state 非依存で課すため、初回 INSERT で
                   設定しないと投入が制約違反で開始できない。record も snapshot するのは、
                   tool / profile 切替中に完了する in-flight job の record を collect 時に current
                   から復元できないため (§5.7 への保存材料)。
                   **profile_hash が現行と異なる行を再投入する場合は state を問わず同 Tx で
                   attempts=0 にリセットする** (§8-a の「profile 内で数え直す」の実体 — terminal
                   限定にすると state=2 の旧 profile 行が attempts を引き継ぎ、新 profile 初回の
                   失敗で即 terminal になる)。
                   **この行の upload_cleaned を 0 に戻す** (この後 relaunch する新 upload を
                   step 4.5 の掃除対象に含めるため)。旧 attempt の upload_id が未清掃なら削除を
                   試みるが、**削除は同 upload を共有する全行が終端 (2/3) している場合のみ** (4.5 の
                   掃除と同条件 — 相 1 だけ無条件だと、再投入する行が state=1 の同輩と共有する
                   upload を先に消して回収不能 = 再投入の二重課金を作る)。**旧 intent_token が
                   非 NULL のまま再投入する場合 (sweep 未完の terminal 行への明示 retry・profile
                   変更経由の再投入) は、その token の未記録 upload 残骸 (filename の token 埋込で
                   発見) の削除も先に試みる** — rotation で旧 token を上書きすると残骸の探索キーを
                   失う (期限超 (iv) と同じ規則)。**外部 upload 削除は app Tx の外で行う**。削除は
                   失敗しても続行する
                   (残骸はプロバイダ保持期限で自然消滅する既知の残余)
  相 2a (外部+app): 入力 upload (原本 — Office 文書は変換 PDF、§6。**filename に intent_token を埋め込む** — 記録前クラッシュの
                   残骸を token で発見・掃除可能にする)。**upload 成功直後に小さな app Tx で
                   upload_id を行へ記録する** — 相 3 まで遅らせると「upload 成功 → job 作成 4xx」で
                   残骸の handle を失い、TTL まで機密入力 (原本 — Office 文書は変換 PDF、§6) が追跡不能で残る。
                   **upload の失敗も相 2b と同じ 2 分岐**: 一時 (429 / 断 / 5xx) = state=0 のまま
                   次 tick へ (Retry-After は retry_not_before へ永続化) / 恒久拒否 (内容起因の
                   4xx) = state=3 (error='submit_rejected') + 同 Tx で attempts=上限 (分類しないと
                   恒久 4xx が attempts 不消費のまま毎 tick 再 upload する無限ループになる)
  相 2b (外部)   : Batch job 作成 (job の metadata に intent_token を埋める)。**呼出の直前に、対象行へ
                   job_create_started_at = now と scope_id (provider の account / workspace の
                   canonical 識別子 — 照合の「同一 scope」判定の基準値。**構成 = adapter 名前空間 +
                   account 不変 ID + workspace 不変 ID (無い階層は省略) の連結** — 表示名・alias 等の
                   可変値は使わない。stable な識別子を提供できない provider は server-side intent
                   回復の採用条件を満たさない — 取得不能時は NULL = fail-closed (恒久 unknown →
                   明示 abandon が脱出路)。**値は「これから呼び出す client instance」から取得し、
                   job 作成も同一 instance で行う** — 記録後に現行設定を再読みすると、記録と呼出の
                   間の資格情報切替で行の scope と job の実在 scope が分裂する) を単独の小 Tx で記録する** (伝播猶予の起点 — 下記
                   intent 回復。呼出後の記録では「作成成功・記録前クラッシュ」で残らず意味がない。
                   再試行時は上書きしてよい — 最新の作成試行の開始が起点)。**失敗は 2 分岐**:
                   一時的失敗 (429 / ネットワーク断 / 5xx) → 行は state=0 のまま次 tick の
                   intent 回復が載せ直す (attempts 不消費。**Retry-After は app_config の
                   retry_not_before として永続化し、submit は期限まで当該 provider への投入を
                   見送る** — 非常駐 tick を跨ぐ抑制) /
                   **恒久拒否 (内容起因の 4xx — アカウント制限・内容検査等) → 即 terminal**:
                   state=3 (error='submit_rejected') **かつ同 Tx で attempts = 上限を設定する** —
                   terminal の実体は遷移表の「attempts >= 上限」なので、attempts 据え置きだと
                   「state=3・attempts < 上限 → 投入対象」が次 tick に自動再投入して宣言と逆に
                   無限ループする (preflight の非対象 marker と同じ手法)。復帰は明示 retry のみ。
                   記録済み upload_id は通常の後始末 (4.5) が掃除する。
                   分類不能な失敗は一時扱いとし、恒久滞留は completed_at NULL の status 監視で拾う
  相 3 (app Tx)  : 該当行を state=1, batch_job_id, upload_id, **attempts+1, submission_seq+1**,
                   submitted_at=now へ UPDATE。**profile_hash / profile_record には触れない** —
                   相 1 の投入時 snapshot を上書きすると、相 2 とこの相の間に profile が変更された
                   場合に旧 profile の job が「現行」を騙る (upload_cleaned も相 1 で 0 済みのため
                   触れない)
  intent 回復 (submit 冒頭で state=0 の行を処理):
    **dispatch**: batch_job_id 非 NULL の state=0 は **client 前計上済み** — job 一覧照合ではなく
    §8 (iii) の再実行経路へ送る (attempts >= 上限なら **state=3 (error='client_exhausted') +
    旧 seq の terminal 記帳 (NULL + estimated)** — client の上限到達行は submit / reconcile /
    collect のどの対象にもならず脱出不能になるため、この分岐が唯一の出口)。
    batch_job_id NULL の state=0 (server 経路) はプロバイダの job 一覧から metadata の
    intent_token 一致を探す。**照合の結果は三値** (found / confirmed-absent / unknown — detached
    (b) と同一規範):
    **found = 採用** — 相 3 と同じ UPDATE (state=1 + batch_job_id +
    attempts+1 + submission_seq+1 + **submitted_at=now** — 時刻基準 job_missing の入力) だが、
    **profile_hash / profile_record は相 1 の snapshot の
    まま触れない** (採用時点の current で上書きすると、クラッシュと回復の間に profile が変更
    された場合、旧 profile で作られた job の結果が collect の照合を素通りして旧空間の vector が
    現行として混入する)。
    **unknown = 照会自体の失敗 (429 / ネットワーク断 / 5xx) は「不存在」と解釈しない** — 行を
    state=0 のまま保持して次 tick 再試行する (Retry-After は retry_not_before へ。**Retry-After が
    無い 429 / 5xx にも既定の抑止 (例: 60 秒 × 連続失敗回数、上限 15 分) を retry_not_before へ
    入れる** — dirty 早回し tick が無抑止の hot retry を繰り返さない。**この既定抑止は一時失敗を
    扱う全分岐 — 相 2a upload 失敗・相 2b job 作成失敗・client 呼出の一時失敗・collect の照会失敗
    (state=1)・本 intent 回復の unknown — に共通で適用する** (各分岐の「Retry-After は
    retry_not_before へ」はこの共通則の再掲であり、ヘッダ無しの場合も同じ既定抑止に倒す)。
    不存在扱いで
    載せ直すと実在 job と二重になり「最悪 1 job」の有界化が破れる)。
    **confirmed-absent = 一覧の正常応答に無い**場合のみ載せ直しへ進むが、**期限判定を先に行う**:
    intent_token (UUIDv7) の時刻成分から (timeout_hours + 結果保持期限 + 猶予 1 日) を超えて
    いる場合、「未作成」とは断定できない (作成済み job が保持期限で一覧から消えた可能性 —
    相 2b 完了・相 3 前クラッシュ後の長期停止)。**時刻成分が now + 許容 skew (既定 5 分) より
    未来、または解釈不能な場合も期限超と同様に扱う** (安全側 — 未来時計で発行された token は
    時計修正後に恒久「期限内」となり、課金済み job を無記帳で載せ直してしまう。過剰側の誤判定は
    下記の記帳済み判別と estimated 区分が吸収する)。**逆側の伝播猶予**: **起点 = max(intent_token の時刻成分, 行の
    job_create_started_at (非 NULL の場合))** — token 時刻だけを起点にすると、相 2a の upload が
    猶予より長い場合に「作成された直後の job」が起点超過で保護から漏れる (job 作成は upload 完了後に
    しか始まらない)。**job_create_started_at が NULL の行の confirmed-absent は、期限判定 (上記) のみで
    「未作成」と扱ってよい** (相 2b 未着手 = job は存在し得ない)。起点が**過去側で** now から数分以内
    (**0 ≤ now − 起点 ≤ 猶予 (既定 10 分)**) の confirmed-absent は unknown と同様に扱い保持する。
    **未来側も now < 起点 ≤ now + 許容 skew (5 分) の帯域は同様に保持する** — 「5 分超の未来 =
    期限超扱い (常に優先)・過去側のみ猶予」の 2 規則だけでは (now, now + 5 分] が両保護から漏れ、
    NTP 補正直後の confirmed-absent が素通しで載せ直される — job 一覧 API の
    read-after-write 整合を仮定しない (作成直後の job が一覧へ未反映のまま dirty 早回しの次 tick が
    照合すると、実在 job を「未作成」と誤認して載せ直し = 追跡不能の二重 job になる)。
    **プロバイダ採用条件**: この猶予による有界化は「**job 一覧の可視化遅延の上限 ≤ 伝播猶予**」を
    provider が満たす場合にのみ成立する — 猶予は provider 別に設定可 (既定 10 分)。遅延上限を
    保証・確認できない provider では、猶予を超える stale な正常一覧が「作成済み job を未作成と
    誤認する載せ直し」を attempts / seq / 記帳の消費なしに反復させ、未追跡・課金済み job を累積
    させ得る — その場合「未追跡 job は最悪 1 個」の有界化は成立しない (採用条件として扱う)。**採用条件は
    もう 1 つある**: 「terminal 後も job が一覧に残る保持期間 ≥ timeout_hours + 結果保持期限 +
    猶予 1 日」— 期限判定 (上記) はこの期間内の一覧残存を前提にしており、早期完了した job が一覧
    から先に消える provider では、期限内の confirmed-absent が課金済み job を無記帳のまま載せ直す
    (可視化の**遅延**上限と一覧の**保持**下限は独立の契約要件で、採用時に両方を確認する)。
    **この期限
    判定・伝播猶予は intent_token を job 一覧と照合する全照合点 (本 intent 回復・detached (b)・
    close 付随 (b')・token sweep 前段) に共通で適用する**。**「一覧の正常応答」は該当範囲の全ページ
    走査を完了した応答に限る** — pagination を持つ一覧 API で先頭ページのみの「不在」は
    confirmed-absent ではなく unknown として扱う (部分応答は不在の証明にならない — 後続ページの
    実在 job を「未作成」と誤認して二重投入する)。**かつ job 作成時と同一の account / workspace
    scope での照会に限る** — 資格情報・tenant の変更後に得た一覧は (空でも全ページ走査済みでも)
    不在の証明にならず unknown として扱う (別 scope の正常な空応答が「未作成」誤認 → 二重投入に
    なる。scope の安定はプロバイダ採用条件と同列の運用前提)。**job_create_started_at IS NULL の
    行 (相 2b 未着手 — scope_id も相 1 で対で NULL) は一覧照合の対象にしない** — job 不存在が行の
    状態から確定しており、intent 回復の期限判定 (token 時刻起点) が載せ直しを処理する。**同一性の判定は行の scope_id
    (相 2b 直前に記録 — DDL) と現照会 scope の比較で行う** — scope_id が NULL の行 (相 2b 未着手・
    旧版由来) は同一性を判定できないため、job_create_started_at が非 NULL なら常に unknown 扱い
    (恒久なら stalled + 明示 abandon)。期限超の処理は**すべて同一 app Tx**:
    (i) **記帳済み判別** — 同 (repository_id, kind, target_key) で batch_job_id = 当該 intent_token の
    cost_ledger 行が既に存在すれば記帳を省略 (seq+1 もしない — 前回の同 Tx がクラッシュで
    完走しなかった再試行。この述語が無いと再試行のたびに別 seq の推定行が増殖する)、
    (ii) 未記帳なら **同一 Tx で batch_requests.submission_seq を +1 へ UPDATE し (相 3 / found
    採用と同じ行更新 — 怠ると次の正規 close が旧値から同じ +1 を計算し、この推定行と UNIQUE
    衝突して実課金の記帳が ON CONFLICT DO NOTHING に黙って吸収される)、その新値で NULL +
    estimated を冪等記帳する (batch_job_id = 当該 intent_token — job id 不明の記帳の突合キー。
    cost_ledger の NOT NULL を満たす)**、
    (iii) **attempts+1** (作成済みであり得た attempt を消費 — 数えないと相 2b/相 3 境界の
    クラッシュ反復が attempts 上限を素通りして外部 job を増やし続ける)、
    (iii') **attempts >= 上限なら載せ直さない**: state=3 (error='expired') で terminal 化し (iv) を
    行わない — (iii) で数えた上限が (iv) の無条件 rotation で素通りしては (iii) の目的が成立しない
    (client_exhausted の server 対応物。この出口が無いと相 2b/相 3 境界クラッシュ + 長期停止の
    反復が上限を超えて外部 job と estimated 記帳を増やし続ける)。token は (ii) で記帳済みのため、
    upload / job 残骸の掃除と intent_token の NULL 化は 4.5 の token sweep が引き継ぐ。復帰は
    明示 retry (attempts リセット) のみ、
    (iv) 載せ直しの相 1 (新 intent_token 書込。**期限内分岐と同じく、旧 token の upload 残骸 —
    filename の token 埋込で発見できる未記録 upload を含む — の削除を app Tx の外で先に試みる**。
    失敗は続行 = 既知の残余) — **以上 (i)〜(iv) の DB 書込 (載せ直し相 1 の行更新を含む) を
    1 Tx で確定する** ((iv) の外部 upload 削除の呼出だけが Tx 外 — 相 1 の規則と同じ。記帳と
    rotation を分けると間のクラッシュで (i) の述語が効かない別 token 世代が生まれ、また記帳・
    attempts 確定後・rotation 前のクラッシュ反復が、載せ直しゼロ回のまま attempts だけを再消費して
    偽 expired に到達する)。
    期限内の不一致は未作成として、同 token の
    upload 残骸を削除してから行を今回の投入対象へ載せ直す (新 intent_token で相 1 から)。
    **kind=1 の載せ直しガード**: target_key に埋まる tool_profile_hash が現行 tool と一致する
    場合のみ載せ直す。**不一致 (載せ直しまでに tool が変更された) は state=3
    (error='tool_changed', attempts=上限) で閉じる** — 現行 record で snapshot を書き直すと
    key の tool と snapshot が食い違い、collect の §5.7 保存 (SHA-256(record)=key の hash 検証)
    が必ず失敗する。新 tool の生成は新しい target_key が別行として通常投入される。
    これにより「job 作成成功・記録前クラッシュ」の未追跡 job が最悪 1 個に有界化される
    (§10 の損失上限の根拠 — **server-side batch 経路限定**。client 側キューの有界化は
    attempts 上限による — §8)

collect 時 (state=1 の batch_job_id を照会):
  照会自体の失敗 (HTTP 429 / ネットワーク断) → 行は変更しない (state=1 のまま次 tick 再照会。
              attempts は「job の投入回数」であり照会失敗では消費しない。**Retry-After が返る場合は
              同 tick 内の後続照会を打ち切り、かつ submit と同様に app_config の retry_not_before
              (provider・kind 別) へ永続化して次 tick 以降も期限まで照会を見送る** — 同 tick 打ち切り
              だけだと非常駐 tick が期限前に再照会し provider 指定に反する)
  item 成功 → **フォルダ側に成果が既に存在するなら metadata 処理をスキップ**し、無ければ
              **kind=1 は §10 ステップ 2 の b〜c を、kind=2 は §10 ステップ 4 の処理を**実行
              (kind で分岐する — kind=2 の成果を OCR の保存・解析処理へ送らない)
              → いずれの場合も app 行を state=2 に UPDATE (**completed_at = now を同時に書く** —
              **state を 2/3 へ確定する全ての UPDATE に共通の規範** (DDL の定義どおり。detached
              経路に限らない — 滞留監視 (§13 の completed_at 長期 NULL) と削除条件の入力)。
              **kind=1 は floor_generated_at を NULL へ戻す** — 明示再生成の完了) + **cost_ledger へ attempt 単位の課金行を冪等追記**
              (kind=1: 実測 pages と実効単価。単価不明プロバイダは cost_usd=NULL +
              cost_estimated。**冪等クローズ = `INSERT … ON CONFLICT (repository_id, kind, target_key,
              submission_seq) DO NOTHING`** — 前回 tick が metadata Tx 後・app 更新前に落ちて同一 seq が
              既に記帳済みでも、UNIQUE 衝突を「同一課金の再観測」として黙って吸収する。素朴 INSERT だと
              衝突が close Tx を abort させて恒久ループになる)
  item 成功・kind=2 で行の profile_hash が現行 embedding_profile_hash と不一致
            → vector は**破棄**して state=3 (error='profile_changed') — 投入後の profile 変更で
              旧空間の vector が新 profile の embeddings に混入する経路を塞ぐ。ただし
              **その job は実際に課金済みなので cost_ledger には attempt 単位で記帳する**
              (vector を捨てても課金は物理事実 — §9.1 の台帳一貫性。破棄と記帳は同一 app Tx)
  item 失敗 → UPDATE state=3 + error (attempts は submit 側でのみ増やす) + **batch_job_id 非 NULL なら
              下記「terminal 化時の課金記帳」と同じ冪等記帳を行う** (失敗 item にも課金する provider で
              台帳が欠落しないように。**失敗 item が非課金と契約上確定している provider では記帳を
              省略してよい — ON CONFLICT が吸収するのは同一 seq の再観測だけで、非課金の判定は
              しない** (初回 INSERT は衝突せず成立する — 「非課金なら ON CONFLICT が skip する」は誤り))
  job TIMEOUT / FAILED → その job の未回収 item を UPDATE state=3 (error='job_timeout' 等)
  **job 資源が不在 (404 — 保持期限超過・アカウント変更・provider 移行で job が消滅) → その行を
              UPDATE state=3 (error='job_missing')**。これは一時的な照会失敗 (429 / ネットワーク
              断) とは区別する**恒久シグナル**であり、行不変に倒すと state=1 が永久滞留する
              (reconcile は state IN (0,3) のみで state=1 を触れず、submit は「成果なし・
              state=1 = 回収待ち」で何もしないため、成果あり・成果なしのいずれでも脱出路が無い)。
              state=3 化により、成果ありなら次 reconcile が閉じ、成果なしなら遷移表が上限内で
              再投入する。**「404 か一時失敗か」を判別できないプロバイダでは時刻基準で判定する:
              submitted_at から (timeout_hours + 結果保持期限 + 猶予 1 日) を超えて state=1 の
              行を job_missing とみなす** (「照会失敗が N 回続いたら」の回数基準は不可 — tick は
              非常駐で連続失敗回数を保持する場所が無い。時刻基準なら列追加なしで決定論的。
              誤判定しても再投入は attempts 上限内に有界)
  結果失効 → UPDATE state=3 (error='result_expired')。再投入は上の遷移表に従う (§6 — 上限内のみ)
  **job 終端・出力欠落**: 終端した job の出力を処理し終えた後、**provider の出力 JSONL に
              custom_id が実際に存在しない item だけ**を state=3 (error='output_missing') へ
              閉じる — 永久回収待ちにしない。**出力には存在するがローカル処理が一時失敗した item
              (SQLITE_BUSY・一時 I/O 等) は state=1 のまま残し、次 tick が再取得・再処理する**
              (これも output_missing に倒すと、成果が取得可能なのに再投入 = 不要な再課金になる)。
              **出力は存在するが内容が決定論的に不正な item (base64 / JSON 破損・次元不一致・非有限
              vector 等、再取得しても必ず同じ失敗) は state=3 (error='invalid_output') + 下記の課金記帳で
              閉じる** — 一時失敗と同一視すると state=1 が毎 tick 同じ失敗で永久滞留し upload も残る
  **terminal 化時の課金記帳**: job が provider 側で作成された attempt (batch_job_id 非 NULL) が
              成果なしの terminal (result_expired / job_timeout / output_missing / job_missing /
              profile_changed / invalid_output / item 失敗) へ倒れる場合も、**cost_ledger へ記帳する**
              (cost_usd は取得できれば実額、不能なら NULL + estimated) — 実行された可能性のある課金を
              「成功時のみ記帳」で取りこぼさない (失効した初回 attempt の課金が台帳から消える穴を塞ぐ)。
              **この記帳、および collect 成功 / reconcile・submit の close / client_exhausted / detached の
              cost_ledger 追記はすべて冪等に行う** — `INSERT … ON CONFLICT (repository_id, kind,
              target_key, submission_seq) DO NOTHING`。同一 seq への 2 回目は「同一課金事実の再観測」で
              あり、素朴 INSERT だと UNIQUE が Tx を abort させ、記帳と state 更新を同一 Tx で行う close が
              毎 tick 落ちて行が脱出不能になる (例: profile を A→B→A と戻すと、collect の profile_changed
              記帳 (seq=n) と次 tick reconcile の close 記帳 (同 seq=n) が衝突する)
  upload 後始末 (tick 末尾, state と独立): upload_cleaned=0 の DISTINCT upload_id のうち
              「同 upload の全行が state IN (2,3)」のものをプロバイダから削除し、成功した行に
              upload_cleaned=1 を記録する (§6 — 失敗・クラッシュは次 tick が再試行。**不在応答
              (404 — 既に存在しない) は削除成功として扱う** — 失敗扱いにすると毎 tick の恒久
              再試行・detached 行の恒久残留になる)。
              **token sweep (同じく state と独立)**: intent_token 非 NULL かつ同 token 全行終端の
              token について、**まず (b') と同一の前段を実行する** — **ただし error IN
              ('submit_rejected', 'abandoned') の行は照合・記帳とも行わず、残骸掃除 → 全削除成功
              (404 含む) で NULL 化だけを行う** (submit_rejected = 未作成 / 未実行の確定 — 相 2a/2b・
              client 呼出の恒久 4xx。abandoned = ユーザーが照合断念を宣言済みで、記帳は abandon Tx が
              実施済み (§9.1) — 掃除が恒久に失敗する間は token 残存 = 削除ガード対象のまま「既知の
              残余」として可視化される。client provider には job 一覧が無く照合が恒久 unknown と
              なって token が永久残留し、削除ガード (intent_token IS NULL) と組み合うと行が削除不能に
              なる。server 側も未作成確定の行への期限超 phantom 記帳を防ぐ。**拒否にも課金する
              provider を採用する場合は、§8 の注記どおり submit_rejected へ倒す分岐自体で同一 Tx の
              冪等記帳を足す — **submission_seq を +1 へ行 UPDATE し、その新値で batch_job_id =
              当該 intent_token・NULL + estimated を記帳する** (期限超 (ii) と同型。seq 現値のままだと
              明示 retry 後の 2 度目の課金される拒否が同一 seq で UNIQUE 衝突し、ON CONFLICT が
              実課金を「再観測」として黙って吸収する)** — この sweep 除外は「課金があるならその分岐で
              記帳済み」を前提にできる)。それ以外の
              batch_job_id NULL の行は
              token 照合し、**found (job 実在)** かつ未記帳 (**同キー × batch_job_id IN (発見 job id,
              当該 intent_token) の ledger 行なし** — 発見 job id だけを見ると「期限超記帳 (token
              キー) → 掃除・NULL 化前のクラッシュ → 再訪時に job が遅延可視化」の順で同一 job が
              token キーと job id キーの 2 行に二重計上される) なら小 Tx で batch_requests.submission_seq を +1・**attempts を +1** (実在した
              job = 消費された attempt — 期限超 (iii) と同じ原則) へ UPDATE + その
              新値で NULL + estimated を冪等記帳し、**同じ小 Tx で行の batch_job_id へ発見 job id を
              書く** (行の自己記述化 — 以後の sweep 再訪はこの行を「batch_job_id NULL」の照合対象に
              しない。found 記帳 (job id) → 一覧からの消滅 → 期限超記帳 (token) の時間差で、同一 job が
              述語分裂により 2 行計上される穴を構造的に塞ぐ。**照合から外れるだけで、batch_job_id
              非 NULL の行 — 自己記述化済み・client 前計上・detached (a) の terminal 行 — も同 token の
              残骸掃除と intent_token NULL 化の対象には含まれ続ける** — 外すと記帳済み・掃除未完の行の
              token が永久残留し、削除ガード (intent_token IS NULL) と恒久矛盾する)。**照合が
              unknown なら掃除も NULL 化もせず保持** (次 tick 再試行)。**confirmed-absent には
              intent 回復と同一の期限判定・伝播猶予を適用する**: 期限超 (未来 skew・解釈不能を
              含む) は「未作成」と断定せず、記帳済み判別 → submission_seq+1 (行 UPDATE) + NULL +
              estimated (batch_job_id = 当該 intent_token) で**記帳してから**掃除へ進む (期限判定を
              欠く sweep は、保持期限で一覧から消えた課金済み job を無記帳のまま NULL 化して
              再駆動キーごと痕跡を消す — detached (b) と同型の穴が sweep 自身に開く)。期限内の
              confirmed-absent は未作成として記帳なしで掃除へ進む。その後 upload / job 残骸の
              掃除を試み (**404 = 成功** — 上と同じ)、**成功した行の intent_token を NULL へ戻す**
              — reconcile close 付随処理
              (b')(c) の失敗・クラッシュの再駆動 (close 後の行は submit / reconcile / collect の
              どれにも再訪されないため、この sweep が前段なしの「掃除 + NULL 化」だけだと、
              (b') が飛んだ課金済み job を無記帳のまま掃除して痕跡を消す)
```

**detached 行の処理規範** (unregister §21.2 / フォルダ消失 §9.3-d で folders 行が無くなった
repository の batch_requests 残置行): detached は**課金追跡専用**であり、フォルダへの書込は
一切行わない — folders.root_path が無い時点で成果の書込先は存在しない。処理は次に限る:

```text
- state=1 の detached: collect が job を照会し、終端したら**結果 payload は破棄**して
  state=2/3 + cost_ledger 記帳 + completed_at のみ記録する (profile_changed の破棄と同型 —
  metadata 書込をしないことを明示する。素朴な実装が未解決パスへ書き込んで落ちる分岐を残さない)
- state=0 の detached: **「job 未作成 = 課金なし」を前提にしてはならない** — 相 2b 完了・相 3 前
  クラッシュの state=0 は job 作成済みであり得るし、client 前計上済み (batch_job_id 非 NULL) は
  実行済みであり得る。処理は: (a) batch_job_id 非 NULL (client) → 実行された可能性ありとして
  terminal 記帳 (NULL + estimated) し、**同一 Tx で state=3 (error='detached') + completed_at を
  確定する** — 「記帳して即削除」ではなく terminal 化し、行の削除は下記の削除条件の段階遷移に
  委ねる (即削除は削除ガード (intent_token IS NULL) と矛盾し、ガード遵守なら state=0 のまま sweep の
  「全行終端」条件に入れず token を NULL 化する経路が無い — 規範を同時に満たす実装が無くなる) /
  (b) NULL (server) → intent_token で job 一覧を
  照合し、**実在すれば通常の intent 採用と同一の UPDATE (state=1 + batch_job_id + attempts+1 +
  submission_seq+1 + submitted_at。profile snapshot は相 1 のまま不変) で state=1 の detached へ採用**
  (submission_seq を増やさないと、以後の close (state=1 detached 規則) の記帳が旧 lifecycle の同一 seq と
  UNIQUE 衝突し、冪等追記が黙って吸収した結果この別 attempt の課金が台帳に載らない。以後は上の
  state=1 規則で回収・記帳)、**不存在の確認にも attached と同一の期限判定を適用する** —
  intent_token (UUIDv7) の時刻成分から (timeout_hours + 結果保持期限 + 猶予 1 日) を超えている
  (または未来 skew で解釈不能な) confirmed-absent は「未作成」と断定せず、attached の期限超と
  同じ規則 (記帳済み判別 → submission_seq+1 + **attempts+1** + NULL + estimated、batch_job_id =
  intent_token — attached (iii) と同じく「作成済みであり得た attempt」を数える。数えないと再登録後の
  遷移表が物理 job より多い再投入を許す) で
  **記帳し、同一 Tx で state=3 (error='expired') + completed_at を確定する** (detached は載せ直さ
  ない — 課金追跡専用。期限判定なしの削除は、
  保持期限で一覧から消えた課金済み job を無記帳で消す)。期限内の不存在確認も **state=3
  (error='detached') で terminal 化する** (**ただし伝播猶予内 (起点から猶予以内) の confirmed-absent
  は共通則どおり unknown として保持し、即 terminal 化しない** — 期限判定・伝播猶予の共通適用は
  detached (b) も照合点に含む)。いずれも行の削除自体は下記の削除条件 (全行終端 +
  upload 掃除完了 + intent_token NULL) の段階遷移に委ねる — terminal 化した行の残骸掃除と token の
  NULL 化は 4.5 の upload 掃除 / token sweep が通常どおり行う。**照合不能なら terminal 化せず
  保持**して次 tick が再試行
- 全行が終端し upload 掃除 (4.5) が完了した detached 行は削除する。ただし
  **upload_cleaned=0 かつ upload_id 非 NULL の行は掃除完了まで削除しない** (行を消すと upload の
  handle を失い TTL まで機密残留する)。**intent_token 非 NULL の行も削除しない** — token 残存 =
  (b')/token sweep の前段 (未記帳 job の照合・記帳) と残骸掃除が未完了で、行を消すと課金の
  再駆動キーごと追跡を失う (sweep が記帳・掃除・NULL 化を完了した後に削除する)。cost_ledger は残る。
  **注記 (意図されたコスト — fork §21.3 の課金注記と同族)**: detached が payload 破棄で終端した後、
  行の削除前に同 repository が再登録されると、行は attached に戻り「成果なし・state=2 → 投入対象」で
  同一 target が自動再投入・再課金される — detached = 課金追跡専用 (成果を書かない) の帰結であり、
  有界 (該当 target 分のみ)・ledger 追跡済みの意図されたコスト
- detached は submit / reconcile / scan の対象外 (成果判定にフォルダ DB が必要なため)。
  detached の処理 (上記) は **tick の collect (step 2 / 4) の冒頭で実行する** (実行点の明示)
```

「成果あり」行の遷移の実行点は state で分担する: **state=0|3 → 2 は §10 tick の reconciliation**
(submit の前。submit の対象選定は「成果なし」だけを見るため、この照合が無いと「成果あり・
state=3」が永久に failed のまま残る)、**state=1 → 2 は collect の冒頭スキップのみ** — state=1 の
成果ありは「metadata Tx 後・app 更新前クラッシュ」の窓であり、collect だけが結果から課金情報
(pages / cost) を読めるため、reconcile / submit で先に閉じると cost_ledger の行が欠落する。
**reconcile / submit が state=0|3 を成果ありで閉じる際の付随処理 (同一 app Tx)**:
(a) **kind=1 は floor_generated_at を NULL へ戻す** — collect 経由と同じ完了処理。残すと後日の
ローカル変換 (§7) が floor を引き上げて「成果なし」化し、完了済みの明示再生成が不要な再 OCR を
点火する。(b) **batch_job_id 非 NULL (job 作成済み / client 実行済み) なら cost_ledger へ
NULL + estimated で冪等記帳する (ON CONFLICT DO NOTHING)** — client 経路の「metadata Tx 後・
app Tx 前クラッシュ」は state=0 のまま成果ありになり、reconcile が唯一の close 点のため、ここで
記帳しないと実課金が台帳から永久に欠落する。同一 seq が既に terminal 記帳済み (profile_changed 等)
でも冪等追記が衝突を吸収する。(b') **state=0 (server — batch_job_id NULL) で intent_token が残る行の
close では、(c) の掃除の際に token 照合で job の実在を先に確認し、実在すれば掃除の前に小 Tx で
batch_requests.submission_seq を +1 へ UPDATE + その新値で NULL + estimated を冪等記帳し、**同じ
小 Tx で行の batch_job_id へ発見 job id を書く** (行の自己記述化 — 以後の token sweep 前段はこの行を
照合対象にしない。found 記帳 (job id) → 掃除前クラッシュ → 長期停止で job が一覧から消滅 → sweep の
期限超記帳 (token) が「未記帳」と誤認して同一 job を 2 行計上する述語分裂を塞ぐ)**
(**ledger の batch_job_id = 照合で発見した実 job id**。行の UPDATE を怠ると次の正規記帳が旧値から
同じ +1 を計算して UNIQUE 衝突し、ON CONFLICT が実課金の行を黙って吸収する — 相 3 / found 採用と
同じ行更新。記帳の前に「同キー × batch_job_id = 発見 job id」の既存 ledger 行を確認し、既存なら
省略する — **記帳済み判別**: seq+1 は非冪等のため、この述語が無いと close 後クラッシュからの
再駆動が別 seq の推定行を重ねる。**照合が unknown (429/断) の場合は記帳も掃除もせず保持** — 次 tick の
token sweep が再試行する。**confirmed-absent には intent 回復と同一の期限判定・伝播猶予を適用
する**: 期限超 (未来 skew・解釈不能を含む) は記帳済み判別 → submission_seq+1 (行 UPDATE) +
NULL + estimated (batch_job_id = 当該 intent_token) で**記帳してから** (c) へ進み、期限内の
confirmed-absent は未作成として記帳なしで (c) へ進む — 期限判定を欠くと、保持期限で一覧から
消えた課金済み job (相 2b 完了・相 3 前クラッシュ + 長期停止) を無記帳のまま掃除する)。相 2b 完了・相 3 前クラッシュの行は job
実在でも batch_job_id NULL のため (b) の条件から漏れる (kind=2 の profile 往復 A→B→A は
この行を単一デバイスの正規操作だけで成果あり化する — 課金済み job を無記帳のまま破棄しない。
detached (b) と同型)。(c) **intent_token が残る行の upload / job 残骸の掃除は、この app Tx
の外で試みる** (外部 API 呼び出しであり、相 1 の旧 upload 掃除と同じく Tx 内に置くと 429 等が close Tx を
巻き添えにする。失敗は次 tick が再試行 — 再駆動は 4.5 の token sweep (下記)。閉じるだけだと token 残骸が
誰にも掃除されず TTL まで機密残留する)。**掃除の実行条件は「同 token を共有する全行が終端 (2/3)」**
(4.5 の upload 条件と同型) — 1 job に複数 target を積んだ場合、先に閉じた行が共有 job を掃除すると
残りの行の回収が不能になり再投入 = 二重課金する。
この規則により旧「既知の残余 (失効窓の課金行は記録できない)」は解消される — batch_job_id を
保持済みの attempt は結果が失効しても NULL + estimated で記帳できる (terminal 化時の課金記帳と
同じ規範)。cost_ledger の金額は「記録できた課金 (推定含む)」であり、請求の最終的な正は
プロバイダ側 — 突合には batch_job_id を使う。

バッチ処理情報を file_versions / chunks に織り込まない理由と、フォルダ側 metadata.sqlite にも置かない
理由は §18.3-18.4。

**変更検知のキャッシュ (§20)** — stat 情報はデバイス固有 (コピーで mtime / inode が変わる) なので
フォルダ側ではなく app.sqlite に置く。すべてヒントであり、喪失しても全再計算に落ちるだけ:

```sql
CREATE TABLE watch_roots (                   -- 検知層が walk する監視対象 Root (明示登録)
    root_path TEXT PRIMARY KEY,
    added_at INTEGER NOT NULL
) WITHOUT ROWID;

CREATE TABLE scan_cache (                    -- 段 1: ファイル単位の stat キャッシュ (§20.3)
    repository_id BLOB NOT NULL
        CHECK (typeof(repository_id) = 'blob' AND length(repository_id) = 16),
    file_name TEXT NOT NULL,
    mtime_ns INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    inode INTEGER,                           -- 取れるプラットフォームのみ (FAT 等は NULL)
    content_hash BLOB NOT NULL               -- この stat 状態で最後に計算した内容 hash
        CHECK (typeof(content_hash) = 'blob' AND length(content_hash) = 32),
    verified_at INTEGER NOT NULL,            -- この行の content_hash を検証 (計算) した時刻
                                             -- (UTC ミリ秒)。racy 判定の基準 — §20.3 の比較式は
                                             -- 双方を秒へ切り捨てる (mtime_ns/1e9 >= verified_at/1e3)
    syntax_fail_count INTEGER NOT NULL       -- §20.5 有界スキップ: この stat tuple での連続構文検証
        DEFAULT 0                            --  失敗回数。stat tuple の変化・検証成功・bytes コミット
        CHECK (syntax_fail_count >= 0),      --  確定で 0 へ。一時 EIO・安定確認失敗は数えない (§20.5)。
                                             --  既存 DB は ADD COLUMN (DEFAULT 0 / NULL) — backfill 不要
    first_failure_at INTEGER,                -- 上記カウントの初回失敗時刻 (UTC ミリ秒) — 24 時間判定の
                                             --  起点 (§20.5)。count = 0 のとき NULL (下の CHECK)
    CHECK ((syntax_fail_count = 0) = (first_failure_at IS NULL)),
    PRIMARY KEY (repository_id, file_name)
) WITHOUT ROWID;

CREATE TABLE pending_deletes (               -- delete 判定「連続 2 回 absent」の継続の永続化 (§20.5)。
    repository_id BLOB NOT NULL              -- tick は常駐しないため、メモリの連続カウントでは
        CHECK (typeof(repository_id) = 'blob' AND length(repository_id) = 16),
    file_name TEXT NOT NULL,                 --  「2 回目」を判定できない。喪失してもカウントの
    first_absent_at INTEGER NOT NULL,        --  やり直し (削除確定が遅れる) になるだけで見逃さない
    PRIMARY KEY (repository_id, file_name)
) WITHOUT ROWID;

CREATE TABLE fp_cache (                      -- 段 0: 階層 fingerprint (§20.3。任意の最適化)
    path TEXT PRIMARY KEY,                   -- 絶対パス (watch_roots 配下の各ディレクトリ)
    files_fp BLOB
        CHECK (files_fp IS NULL OR (typeof(files_fp) = 'blob' AND length(files_fp) = 32)),
    dirs_fp BLOB
        CHECK (dirs_fp IS NULL OR (typeof(dirs_fp) = 'blob' AND length(dirs_fp) = 32)),
    dir_fp BLOB NOT NULL
        CHECK (typeof(dir_fp) = 'blob' AND length(dir_fp) = 32),
    scanned_at INTEGER NOT NULL
) WITHOUT ROWID;
```

## 9.2 集約層 — 横断検索キャッシュ (agg_*)

全フォルダの検索対象を app.sqlite に集約し、デバイス横断のハイブリッド検索を 1 DB で完結させる。
**集約層は検索キャッシュであり真実を持たない** (§15 規約 9)。

repository_id は BLOB 16 bytes (UUIDv7)。hash 列の CHECK は規約 10 に従い全列へ展開する
(以下の DDL が省略なしの実定義):

```sql
CREATE TABLE agg_commits (                       -- append-only ミラー
    repository_id BLOB NOT NULL
        CHECK (typeof(repository_id) = 'blob' AND length(repository_id) = 16),
    commit_hash BLOB NOT NULL
        CHECK (typeof(commit_hash) = 'blob' AND length(commit_hash) = 32),
    parent_hash BLOB
        CHECK (parent_hash IS NULL
               OR (typeof(parent_hash) = 'blob' AND length(parent_hash) = 32)),
    created_at INTEGER NOT NULL,
    message TEXT,
    PRIMARY KEY (repository_id, commit_hash)
) WITHOUT ROWID;

CREATE TABLE agg_file_versions (                 -- append-only ミラー (横断の版フィルタ計算用)
    repository_id BLOB NOT NULL
        CHECK (typeof(repository_id) = 'blob' AND length(repository_id) = 16),
    file_name TEXT NOT NULL,
    commit_hash BLOB NOT NULL
        CHECK (typeof(commit_hash) = 'blob' AND length(commit_hash) = 32),
    previous_commit_hash BLOB
        CHECK (previous_commit_hash IS NULL
               OR (typeof(previous_commit_hash) = 'blob' AND length(previous_commit_hash) = 32)),
    event_type INTEGER NOT NULL CHECK (event_type IN (1, 2, 3)),
    content_hash BLOB
        CHECK (content_hash IS NULL
               OR (typeof(content_hash) = 'blob' AND length(content_hash) = 32)),
    size_bytes INTEGER,
    CHECK (                                      -- §5.2 file_versions と同一の複合 CHECK。無いと
        (event_type = 3 AND content_hash IS NULL AND size_bytes IS NULL)   -- 削除版が content_hash 付きで
        OR                                       --  受理され §11.1(B) の過去版検索に削除版が露出する
        (event_type IN (1, 2) AND content_hash IS NOT NULL
            AND size_bytes IS NOT NULL AND size_bytes >= 0)
    ),
    PRIMARY KEY (repository_id, file_name, commit_hash)
) WITHOUT ROWID;

CREATE TABLE agg_markdown_documents (            -- 同期の単位 (generated_at 比較で置換検出)
    repository_id BLOB NOT NULL
        CHECK (typeof(repository_id) = 'blob' AND length(repository_id) = 16),
    content_hash BLOB NOT NULL
        CHECK (typeof(content_hash) = 'blob' AND length(content_hash) = 32),
    tool_profile_hash BLOB NOT NULL
        CHECK (typeof(tool_profile_hash) = 'blob' AND length(tool_profile_hash) = 32),
    markdown_hash BLOB NOT NULL
        CHECK (typeof(markdown_hash) = 'blob' AND length(markdown_hash) = 32),
    generated_at INTEGER NOT NULL,
    PRIMARY KEY (repository_id, content_hash, tool_profile_hash)
) WITHOUT ROWID;

CREATE TABLE agg_chunks (
    chunk_uid INTEGER PRIMARY KEY,               -- app 側で採番 (agg_chunk_fts の content_rowid)
    repository_id BLOB NOT NULL
        CHECK (typeof(repository_id) = 'blob' AND length(repository_id) = 16),
    content_hash BLOB NOT NULL
        CHECK (typeof(content_hash) = 'blob' AND length(content_hash) = 32),
    tool_profile_hash BLOB NOT NULL
        CHECK (typeof(tool_profile_hash) = 'blob' AND length(tool_profile_hash) = 32),
    seq INTEGER NOT NULL,
    chunk_type INTEGER NOT NULL CHECK (chunk_type IN (1, 2)),
    heading_path TEXT NOT NULL DEFAULT '[]',
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    text TEXT,
    text_hash BLOB
        CHECK (text_hash IS NULL
               OR (typeof(text_hash) = 'blob' AND length(text_hash) = 32)),
    image_hash BLOB
        CHECK (image_hash IS NULL
               OR (typeof(image_hash) = 'blob' AND length(image_hash) = 32)),
    media_type TEXT,
    image_meta TEXT,
    embed_hash BLOB GENERATED ALWAYS AS (COALESCE(image_hash, text_hash)) VIRTUAL,
    CHECK (                                      -- §5.4 と同一の行 CHECK。embed_hash の非 NULL も
        (chunk_type = 1 AND text IS NOT NULL AND text_hash IS NOT NULL
            AND image_hash IS NULL AND media_type IS NULL AND image_meta IS NULL)
        OR
        (chunk_type = 2 AND image_hash IS NOT NULL AND media_type IS NOT NULL
            AND image_meta IS NOT NULL
            AND (text IS NULL) = (text_hash IS NULL))
    ),                                           --  この制約から構造的に保証される
    CHECK (typeof(seq) = 'integer' AND seq >= 0),    -- §5.4 と同一 (横断検索の §12 preview キーは
    CHECK (typeof(char_start) = 'integer' AND typeof(char_end) = 'integer'
           AND char_start >= 0 AND char_end >= char_start),  --  agg 側から読むため層 3 でも弾く)
    UNIQUE (repository_id, content_hash, tool_profile_hash, seq)
);
CREATE INDEX idx_agg_chunks_embed ON agg_chunks (embed_hash);

-- agg_chunk_fts: §5.5 と同一定義 — content には view agg_chunks_fts_src
-- (SELECT chunk_uid, text, heading_path FROM agg_chunks WHERE text IS NOT NULL) を指定し
-- (content_rowid='chunk_uid')、trigger は §5.5 の 2 本を表名・rowid 名の読み替えで適用。
-- 読み替えは機械的に一意: chunks→agg_chunks / chunk_id→chunk_uid / chunk_fts→agg_chunk_fts /
-- view 名→agg_chunks_fts_src / trigger 名に agg_ 接頭辞。列・WHERE 条件・INSERT/DELETE の
-- 対は §5.5 と同一 (これ以外の読み替えは無い)

CREATE TABLE agg_embeddings (
    target_type INTEGER NOT NULL
        CHECK (target_type IN (1, 2)),
    target_hash BLOB NOT NULL                    -- repository_id を持たない: 内容アドレスなので
        CHECK (typeof(target_hash) = 'blob' AND length(target_hash) = 32),
    vector BLOB NOT NULL                         -- デバイス全体で dedup が効く (同一文書が複数
        CHECK (typeof(vector) = 'blob' AND length(vector) = 4 * dimensions),
    dimensions INTEGER NOT NULL                  --  フォルダにあっても vector は 1 本)
        CHECK (typeof(dimensions) = 'integer' AND dimensions > 0),
    embedding_profile_hash BLOB NOT NULL
        CHECK (typeof(embedding_profile_hash) = 'blob'
               AND length(embedding_profile_hash) = 32),
    PRIMARY KEY (target_type, target_hash)
) WITHOUT ROWID;

CREATE VIRTUAL TABLE agg_vec USING vec0(         -- §5.6 embedding_vec と同じ DDL テンプレート
    target_key TEXT PRIMARY KEY,                 -- (<dim> / <metric> は profile 確定時に §5.6 と同じ値へ展開)
    embedding float[<dim>] distance_metric=<metric>
);

CREATE TABLE sync_state (                        -- フォルダごとの同期カーソル
    repository_id BLOB PRIMARY KEY
        CHECK (typeof(repository_id) = 'blob' AND length(repository_id) = 16),
    last_commit_created_at INTEGER,              -- commits / file_versions の追記カーソル
    last_commit_hash BLOB                        --  (初回同期前はともに NULL)
        CHECK (last_commit_hash IS NULL
               OR (typeof(last_commit_hash) = 'blob' AND length(last_commit_hash) = 32)),
    synced_profile_hash BLOB                     -- このフォルダの現行 embedding を agg へ複製し終えた
        CHECK (synced_profile_hash IS NULL       --  embedding profile の hash (§8-e — ready 更新の
               OR (typeof(synced_profile_hash) = 'blob'  --  宣言的判定に使う。未複製・移行中は NULL)。
                   AND length(synced_profile_hash) = 32)),  -- **§8-e の building (app_config は
                                                 --  lower hex64 TEXT) との比較は hex を BLOB へ復号して
                                                 --  行う** (§11.2 の BLOB bind 契約と同一 — TEXT 直書きは
                                                 --  CHECK 違反、TEXT 比較は無音不一致)
    synced_at INTEGER NOT NULL                   -- 行の作成 = フォルダの**初回 Replicate** で INSERT
                                                 --  (カーソル・synced_profile_hash は NULL、
                                                 --   synced_at = now)。以後はカーソル前進で UPSERT
) WITHOUT ROWID;
```

## 9.3 レプリケーション規則

commits / file_versions は append-only であるため、差分同期は「カーソル以降の行をコピーするだけ」で済む。

```text
Replicate (フォルダごと。§10 tick のステップ 5。同一フォルダ分は 1 つの app Tx で適用する):
z. 後退検出。**判定の実行点は tick の冒頭 (step 0 の前) — フォルダごとに max(created_at,
   commit_hash) とカーソルを照合する安価な読取のみ**で行い、検出したフォルダは**同 tick の
   step 0〜4 の対象から除外**して (**ただし step 2 / 4 の既存 in-flight job の collect と detached
   処理は除外しない — §10 step -1 と同一の例外**。除外対象は巻き戻った状態を入力にする scan /
   reconcile / submit / replicate — 課金済み結果の回収は巻き戻りと無関係)、本ステップ (5) が
   wipe + full resync を行う — step 5 まで
   判定を遅らせると、バックアップ復元 (§13 の正規手順) 直後の最初の tick が「巻き戻った LWW」を
   対象に step 1 の OCR submit (課金) を先に実行してしまう (z はそれを事後にしか止められない)。
   次の**いずれか**でフォルダは過去状態へ巻き戻されている
   (バックアップ復元等) と判定する:
   (1) フォルダ側 commits の最大 (created_at, commit_hash) がカーソルより**小さい**
   (2) カーソルが NULL でないのに、その (created_at, commit_hash) の commit が
       **フォルダ側 commits に実在しない** — max 比較だけでは「空 DB へ復元 → 新規コミットで
       max がカーソルを超えた」ケースがすり抜け、復元前の幽霊 commit が agg に残留する
   判定したら、この repository の集約行を §9.3-d と同様に wipe (agg 4 表 + sync_state) してから
   カーソル NULL で full resync する — 検出しないと、フォルダに存在しない幽霊 commit / chunk が
   agg に残留し、横断検索が解決先の無い結果を返し続ける。**同時に当該 repository の scan_cache と
   配下 fp_cache を無効化し、次 tick に強制 hash scan を課す** — metadata だけを旧版へ復元した場合
   working ツリーは新しいまま (fp / scan_cache も新状態を指す) のため、無効化しないと段 0/1 が
   「変更なし」でスキップして working が deep-scan まで metadata に追いつかず、検索結果 (agg=旧) と
   実ファイル (新) が最大 1 週間乖離する。
   **後退検出は status に "regressed" として通知する** (conflict / damaged / missing と同格) —
   metadata.sqlite のみを古い版へ復元した場合、フォルダ内部は完全整合で fsck を通過するため、
   この通知が無いとユーザーはコミット履歴の巻き戻り (= データ喪失相当) を検索結果の変化以外で
   知り得ない。wipe + resync は無言で進めない
a. commits / file_versions (append-only 差分。フォルダ側 DB を folder としてATTACH した完全形。
   初回同期はカーソルが NULL — 行値比較は NULL で UNKNOWN になるため明示的に扱う):
     INSERT INTO agg_commits (repository_id, commit_hash, parent_hash, created_at, message)
     SELECT :repo, c.commit_hash, c.parent_hash, c.created_at, c.message
     FROM folder.commits c
     WHERE :cursor_at IS NULL
        OR (c.created_at, c.commit_hash) > (:cursor_at, :cursor_hash);

     INSERT INTO agg_file_versions (repository_id, file_name, commit_hash,
                                    previous_commit_hash, event_type, content_hash, size_bytes)
     SELECT :repo, fv.file_name, fv.commit_hash, fv.previous_commit_hash,
            fv.event_type, fv.content_hash, fv.size_bytes
     FROM folder.file_versions fv
     JOIN folder.commits c USING (commit_hash)      -- file_versions に created_at は無い
     WHERE :cursor_at IS NULL
        OR (c.created_at, c.commit_hash) > (:cursor_at, :cursor_hash);
   → sync_state をコピー済み最大の (created_at, commit_hash) へ UPSERT (カーソル前進)
b. markdown_documents (派生単位の全置換 + 逆差集合):
   フォルダ側と agg_markdown_documents を (content_hash, tool_profile_hash) で突き合わせ:
   - agg に無い、または generated_at が異なる派生
     → 同 Tx で agg_chunks の該当派生行を DELETE → フォルダ側 chunks を INSERT
       (trigger が agg_chunk_fts を追随) → agg_markdown_documents を UPSERT
       (この UPSERT を怠ると同じ派生が毎 tick 再検出される)
   - 逆差集合: agg にあるがフォルダ側に無い (content_hash, tool_profile_hash)
     → agg_markdown_documents と agg_chunks の該当行を DELETE
       (tool 切替後の旧派生削除など、フォルダ内で消えた派生が集約へ伝播する唯一の経路)
   ← chunk の置き換え・再 OCR・派生破棄の伝播はすべてこの b で完結する (tombstone 不要)
c. embeddings: **フォルダ側の行のうち embedding_profile_hash が現行 profile と一致するものだけ**
   を同期対象とする (不一致 = 未 re-embed の旧空間 vector は skip — 移行期間中に後から接続された
   フォルダが集約を旧空間で汚染する経路、および次元不一致 blob の agg_vec INSERT 失敗で
   replicate Tx 全体が毎 tick 落ちる経路を塞ぐ)。対象行について agg に無い
   (target_type, target_hash) をコピーし、同一キーで agg 側の **embedding_profile_hash** が
   異なる行は置換する。
   **コピー・置換のいずれも agg_embeddings と agg_vec への投入を同一 Tx で行う** —
   新規コピー時に agg_vec を書き忘れると、その vector は KNN に永久に現れない。
   **agg_vec への投入は常に DELETE → INSERT** (新規コピーも置換も同形) — agg_embeddings 行を
   欠いた agg_vec 孤児 (破損・規範外の掃除順) が残っていると、素朴 INSERT が target_key PK 衝突で
   replicate Tx を毎 tick abort させる (DELETE → INSERT は孤児を無害に上書きする。fsck §13 は
   逆方向 (vec にあるが embeddings に無い) の差集合も検査する)。profile 変更後の agg 全破棄は
   §8-e の**毎 tick 冪等検査** (Replicate 冒頭で agg_vec の次元・距離と app_config の agg 構築 profile を
   現行と照合) が担う — イベント時の一度きり破棄はクラッシュで飛ぶと agg_vec が旧次元のまま残る。
   **同期の完了追跡 (§8-e の ready 更新の入力)**: このフォルダの現行 profile eligible chunk がすべて
   embeddings を持ち (§8 の re-embed 完了) かつその全 embeddings が agg へ複製済み (差集合が空) に
   なったら、同一 Tx で sync_state.synced_profile_hash を現行 (building) profile へ UPDATE する —
   まだ欠落があれば NULL のまま。§8-e はこの列が接続フォルダすべてで building と一致した時点で
   agg_ready_profile_hash を更新する (0 行コピーの空 index が ready を騙るのを防ぐ)
d. フォルダ削除: folders から消えた repository_id について、repository-scoped な表
   (agg_commits / agg_file_versions / agg_markdown_documents / agg_chunks) の行と
   **sync_state・batch_requests・scan_cache・pending_deletes の該当 repository 行**
   (および旧 root_path 配下の fp_cache 行) を一括 DELETE する (sync_state を残すと
   同じ repository_id の再発見時に旧カーソル以前の履歴が永久に再同期されず、batch_requests を
   残すと消えた成果を前提にした古い state が再発見後の submit / reconcile を誤らせる)。
   **batch_requests の削除規則は §21.2 unregister と同一**: 「(cancel 確定 or terminal (2/3))
   かつ (upload_id IS NULL or upload_cleaned=1) かつ intent_token IS NULL」の行のみ削除し、
   **それ以外 (cancel 未確定の in-flight・upload 未清掃・token 残存) は detached として残す**
   (要約でガード 2 条件を落とすと、局所記述に従う実装が (b')/sweep の課金・掃除の再駆動キーを
   道連れに削除する) (§9.1 の
   detached 処理規範 — 削除すると課金され得る job を追跡できず、同 repository の再登録 / fork 後の
   新 id が同一対象を再投入して二重課金になり、旧 job の課金も台帳から消える。「失敗しても
   timeout で自然終端するから削除してよい」は誤り — 終端しても記帳する行が無い)。
   **cost_ledger は削除しない** (§9.1 — 発生済み課金は物理事実)。
   agg_embeddings / agg_vec は repository_id を持たないため一括削除の対象外 —
   b / d の削除後に「agg_chunks のどの **(chunk_type, embed_hash) ペア**からも参照されない
   (target_type, target_hash) 行」を孤児として削除する (§13 と同型の逆参照掃除。
   **型を含むペアで一致させる** — hash 単独の比較は type 違いの同 hash で孤児を残す)
```

# 10. パイプライン全体 (tick — 常駐なし・差集合駆動・冪等)

```text
tick (cron / 手動 / dirty 起因の早回し。tick 全体を単一実行ロックで直列化する — 下記の並行性規約):
-1. 後退検出 (z)  §9.3-z の判定をフォルダごとに実行する (安価な読取のみ)。**判定は三値**:
                 verified (後退なし — step 0〜4 へ進む) / regressed (検出 — **同 tick の
                 step 0〜4 の対象から除外** (**ただし step 2 / 4 の既存 in-flight job の collect と
                 detached 処理は除外しない** — 下記注記のとおり課金済み結果の回収は巻き戻りと
                 無関係。除外するのは巻き戻った状態を入力にする処理 = scan / reconcile / submit /
                 replicate) し step 5 が wipe + full resync + cache 無効化) /
                 **unreadable (metadata を開けない — 一時 EIO 等) = 未検証として regressed と
                 同様に step 0〜4 から除外・保留** (in-flight collect の非除外例外は、metadata を
                 開けない unreadable では実行不能なので実質 regressed 側にのみ効く — unreadable の
                 in-flight は次 tick 持越し) (「開けなかったから進む」に倒すと、復元直後 +
                 一時 EIO の組合せで巻き戻った LWW のまま step 1 の submit = 課金へ進む)。
                 判定を step 5 まで遅らせない理由: バックアップ復元直後の
                 最初の tick が巻き戻った LWW で step 1 の submit = 課金を先に実行してしまう。
                 **注記**: z 検出時も既存の in-flight job の collect は通常どおり実行してよい —
                 巻き戻り後の履歴に無い content の派生は eligible (§11 版フィルタ) に現れず
                 検索を汚さない (残骸が不要なら §21.6 drop-derivation で破棄できる。課金済みの
                 結果を fence で破棄する機構は設けない)
0. Scan & Commit スキャン (§20.3 の 3 段) を実行し、変更のあった管理フォルダについて
                 コミットを作成する (§20.5)。以降のステップが読む「現在版」は本ステップの
                 結果である (鮮度保証 — tick 内でスキャンより古い現在版を読むことはない)。
                 消費した dirty 集合は本ステップ完了時にクリアする (スキャン中に届いた
                 新規 dirty は次回 tick へ持ち越す)
0.5 Reconcile    batch_requests の **state IN (0, 3)** のうち **folders 行が実在する行**
                 (detached は対象外 — §9.1「detached は submit / reconcile / scan の対象外」。
                 成果照合にフォルダ DB が必要なため) についてフォルダ成果 (§9.1 の
                 「成果あり」定義 — kind=1 は floor、kind=2 は profile を含む) を照合し、
                 成果ありを state=2 へ閉じる (§9.1「成果あり」遷移の実行点。submit は成果なし
                 だけを見るため、この照合が無いと成果あり・state=3 が永久に残る)。
                 **state=1 は閉じない** — collect の冒頭スキップが課金記録 (cost_ledger) と
                 同時に閉じる (§9.1 — reconcile で閉じると課金行が欠落する)
1. OCR submit    冒頭で state=0 (kind=1) の intent 回復 (§9.1) を行う。
                 対象 = 各フォルダの現在版 content_hash (selected_files CTE = §11.1 の
                 現在版モード) の **DISTINCT 集合** (同一 content_hash を複数 file_name が
                 参照しても target は 1 つ。JSONL にも同一 custom_id を 1 行だけ積む) を
                 identity ペア (content_hash, :current_tool) で判定:
                   §9.1 の「フォルダ成果なし」(markdown_documents 行の存在 + floor_generated_at
                   を考慮 — 明示再生成 §5.3 で floor が設定された対象は旧行が残っていても候補)
                     ← ペアで引く。旧 tool の行が新 tool の生成を抑止してはならない
                   AND batch_requests (kind=1, 同ペアの target_key) が §9.1 遷移表で「投入可」
                 → preflight (§6。非対象は terminal 行を 1 回だけ作って以後除外) を通過した
                 入力 (原本 — Office 文書は変換 PDF、§6) を §9.1 の 2 相 submit で投入する。JSONL (custom_id = target_key。
                 **1 つの Batch job には 1 repository の分だけを積む** — custom_id は job 内で
                 unique が要求されるため、repo を跨ぐと同一 target_key が衝突する)
                 (backfill — 既定 ON、設定で無効化可): 上記に加えて all_versions (§11.1 B) の
                 DISTINCT content_hash のうち現在版に無いものを**低優先**で同様に投入する。
                 過去版込み検索 (§11.1 B/C) の本文はこれで成立する — 導入前からの既存履歴・
                 tick 間に通過した中間版・tool 変更後の旧版が対象になる。
                 **floor が設定された対象は backfill 設定に関わらず常に候補**とする (§5.3 —
                 過去版のみの content の明示再生成は backfill OFF では他に経路が無い)
2. OCR collect   **冒頭で §9.1 の detached 処理 (kind=1 分) を実行する** (実行点の再掲 — §9.1)。
                 次に state=1 の job (**folders に現存する repository の行に限る** — detached の
                 state=1 は冒頭の detached 規範だけが扱う。無限定の照会に含めると存在しない
                 フォルダの metadata へ書き込もうとして落ちる) を照会し (照会失敗 = 429 等は
                 行を変えず次 tick — §9.1)、
                 完了 job の出力を custom_id ごとに §9.1 collect 遷移で処理:
                 a. フォルダ側成果が既に存在すれば b〜c をスキップ (冪等。前回 tick が
                    d の前で落ちたケース) して d へ
                 b. §6 の保存時変換 (画像 → objects, Markdown 確定 → objects)
                 c. §7 の解析 → metadata.sqlite 1 Tx: 同一 (content_hash, tool_profile_hash) の
                    旧 markdown_documents 行を DELETE (CASCADE で旧 chunks / FTS 掃除)
                    → markdown_documents INSERT → chunks INSERT → profiles INSERT OR IGNORE
                    (**record は batch_requests 行の profile_record snapshot から** — current 参照
                    だと tool 切替中に完了した旧 tool job の record を復元できない。§5.7 / §9.1)
                                                                    ← フォルダ側を先に確定
                    (UPSERT は禁止 — 理由は §5.3。generated_at は §5.3 の単調規則で採番)
                 d. app.sqlite 1 Tx: state=2 へ UPDATE + floor_generated_at を NULL へ戻す +
                    cost_ledger へ attempt 単位の課金行を追記      ← アプリ側は後 (冪等クローズ)
                 失敗 item → state=3 + error / job TIMEOUT・FAILED / **job_missing (404 — 恒久
                 消滅)** → 未回収 item を state=3 (再投入の可否は次 tick の submit が §9.1 遷移表で
                 判定 — 無条件の再キューはしない。404 と一時的照会失敗の区別は §9.1)
                 e. job 終端後、その job で state=1 のまま残った行を state=3
                    (error='output_missing') へ閉じる (§9.1 — 出力から custom_id が欠けた item)
3. Embed submit  冒頭で (i) embedding_vec の**次元と距離**を現行 profile と照合し、いずれか
                 不一致なら DROP → CREATE (§8-c。**「現行 profile」の参照元は app_config の
                 embedding_profile record** — §5.7 は履歴の保管庫であり、新規フォルダでは
                 profiles が空のため <dim>/<metric> の展開元にならない。§21.1 手順 2 で遅延
                 された vec の初回作成もここで行う)。**次元一致の場合も含め毎回、embeddings の現行 profile 行のうち
                 vec に target_key が無いものを差集合で冪等再充填する** (§8-c — CREATE 済み・
                 充填途中クラッシュの半端な vec の欠落を埋める)、(ii) embeddings の
                 profile 不一致行を embedding_vec → embeddings の順に掃除、(iii) state=0
                 (kind=2) の intent 回復 (いずれも冪等 — §8-c/d, §9.1)。
                 対象 = chunks の DISTINCT (chunk_type, embed_hash) ペア (§8 opt-in フィルタの
                 除外分を除く) を (target_type, target_hash) と比較:
                   NOT EXISTS (SELECT 1 FROM embeddings e
                               WHERE e.target_type = c.chunk_type
                                 AND e.target_hash = c.embed_hash
                                 AND e.embedding_profile_hash = :current_profile)
                     ← profile を含めて引く (§8-a。旧 profile の行は成果ではない)
                   AND batch_requests (kind=2) が §9.1 遷移表で「投入可」
                 → §9.1 の 2 相 submit で投入する
4. Embed collect **冒頭で §9.1 の detached 処理 (kind=2 分) を実行する** (実行点の再掲 — §9.1)。
                 **照会する state=1 は folders に現存する repository の行に限る** (step 2 と同じ —
                 detached の state=1 は冒頭の detached 規範のみが扱う。無限定だと存在しないフォルダの
                 metadata へ書き込もうとして落ちる)。
                 → 各 item: **まず行の profile_hash を現行 embedding_profile_hash と照合し、
                 不一致なら vector を破棄して state=3 (error='profile_changed') — INSERT しない
                 (§9.1 の遷移。ここが state=2 と書かれていたら誤り)。ただし課金済みなので
                 cost_ledger には記帳する (§9.1)**。一致なら:
                 フォルダ側 embeddings の (target_type, target_hash) 行が**現行 profile で**
                 存在すればスキップ (冪等 — OCR collect の 2-a と同じ吸収)。旧 profile の行が
                 あれば同一 Tx で embedding_vec → embeddings の順に DELETE してから INSERT
                 (§8-b)。無ければ metadata.sqlite 1 Tx: embeddings INSERT + **embedding_vec は
                 DELETE → INSERT** (agg §9.3-c と同形 — 破損起源の vec 孤児 (embeddings 行なし・
                 vec 行あり) が残ると素朴 INSERT が target_key PK 衝突で毎 tick 同一失敗する) +
                 profiles INSERT (record は行の profile_record snapshot から — §9.1)。
                 いずれの場合も app 側 state=2 へ UPDATE + cost_ledger 追記
4.5 Upload 掃除 + token sweep
                 upload_cleaned=0 で全行終端の upload をプロバイダから削除する (§6 / §9.1 —
                 state と独立の再試行。404 = 成功)。**続けて §9.1 の token sweep** — (b') 前段
                 (未記帳 job の冪等記帳 + 期限超 confirmed-absent の記帳 — §9.1 の期限判定・
                 伝播猶予を適用) → 残骸掃除 → 成功で intent_token NULL 化 (close 後の記帳・掃除
                 失敗の唯一の再駆動点)
5. Replicate     冒頭で agg_vec の**次元・距離** × app_config の agg 構築 profile を現行と照合し、
                 いずれか不一致なら agg_embeddings (行 DELETE) / agg_vec (DROP → CREATE —
                 §8-e の区別どおり、通常表は schema ごと消さない) を破棄→再作成 + sync_state の
                 synced_profile_hash 全行 NULL 化 (§8-e の毎 tick 冪等検査) → §9.3 (a〜d。z の判定は
                 step -1 で実行済み — 検出フォルダはここで wipe + full resync)
```

**並行性規約**: tick は app.sqlite と同ディレクトリの `tick.lock` (flock、取得失敗 = 即終了) で
**プロセスとして単一実行に直列化する**。**スキャンとコミット作成 (ステップ 0 = §20.3 / §20.5) も
tick の一部であり、同じ tick.lock の下で実行する** — スキャンを独立プロセスにすると、コミット作成
(§20.5 の Tx) と tick の現在版読取りが並行し得る。§14 の busy_timeout は SQLite のロック待ち
設定であって tick の直列化ではない — 並行 tick を許すと、両者が同じ差集合を読んでから外部
Batch job を二重作成し得る (DB の一意制約では外部 API 呼び出しの重複を防げない)。

**層 A の dirty 集合はプロセス内メモリで持ち、永続化しない** (専用テーブルは作らない)。
イベントスレッドが dirty に repository_id を積み、次の tick のステップ 0 が消費して
「dirty フォルダは即時、それ以外は定期間隔で」スキャン対象を決める。dirty があるときは
tick を早回しで起動してよい (tick.lock が直列化するため安全)。プロセス再起動で dirty が
失われても起動時フルスキャンが吸収する — イベントは正しさに寄与しないため喪失は無害 (規約 11)。

- 全ステップが差集合クエリ駆動なので tick は何度実行しても安全。submit 側の判定も collect 側の
  処理も「フォルダ側に成果が存在するか」を先に見るため、クラッシュで app 側の state 更新が漏れても
  再投入・再処理されず行を閉じるだけで済む (§9.1 遷移表)
- クラッシュ時に残るのは「objects/ の未参照ファイル」「app 側の閉じ忘れ submitted 行」
  「state=0 の submit intent」のみで、次の tick が収束させる (intent はプロバイダ照合で採用
  または作り直し — §9.1)。**重複課金は intent 回復により最悪でも job 1 回分に有界 —
  server-side batch 経路限定、かつ §9.1 のプロバイダ採用条件 (一覧の可視化遅延上限・保持期間) を
  満たす provider に限る主張** (client 側キューは呼出中クラッシュを識別できず、
  attempts 上限による有界化に留まる — §8/§9.1 と同一の限定)。
  「job 作成成功・記録前クラッシュ」を繰り返しても、次 tick が intent_token で既存 job を
  採用するため未追跡 job は累積しない。app.sqlite 全損はこの有界化の外 (損失は §2 / 規約 7)
- 検索可能になるまでのラグ: FTS はステップ 2 完了時点から有効 (最大 ~24h — **単独フォルダ検索の
  chunk_fts の話。横断検索の agg_chunk_fts はステップ 5 の Replicate 後** — 層で有効時期が異なる)、
  ベクトルはさらに
  embedding の 1 周回遅れ。embeddings が無い chunk は KNN に出ないだけで FTS が先に効く。
  「OCR 待ち n 件 / embed 待ち m 件」は差集合 + batch_requests で status 表示できる。
  objects/ の総容量・cost_ledger の月次額・恒久滞留 (completed_at が長期 NULL の state=1) も
  status に出す (§14 の busy_timeout で tick の書込 Tx が SQLITE_BUSY になった対象はスキップして
  次 tick が再試行する — 全体の正しさは差集合駆動で保たれる)

# 11. 検索

## 11.1 版フィルタ (3 モード)

3 モードはいずれも**同じ公開名 `selected_files(repository_id, file_name, content_hash)`** を返す
完全 SQL とする。§11.2 は選んだモードの WITH 節 (末尾の `SELECT * ...` を除く) を自身の WITH 句の
先頭へ前置して使う。以下は横断 (agg_*) 版:

```sql
-- (A) 現在版のみ (ファイル単位 LWW)
WITH ranked AS (
    SELECT fv.repository_id, fv.file_name, fv.content_hash, fv.event_type,
           ROW_NUMBER() OVER (
               PARTITION BY fv.repository_id, fv.file_name
               ORDER BY c.created_at DESC, c.commit_hash DESC
           ) AS pos
    FROM agg_file_versions fv
    JOIN agg_commits c
      ON c.repository_id = fv.repository_id AND c.commit_hash = fv.commit_hash
),
selected_files AS (
    SELECT repository_id, file_name, content_hash
    FROM ranked WHERE pos = 1 AND event_type <> 3
)
SELECT * FROM selected_files;

-- (B) 過去版込み
WITH selected_files AS (
    SELECT DISTINCT repository_id, file_name, content_hash
    FROM agg_file_versions
    WHERE content_hash IS NOT NULL
)
SELECT * FROM selected_files;

-- (C) 時点指定 — (A) と同形で、ranked の JOIN の直後に行値比較を 1 行足す
WITH ranked AS (
    SELECT fv.repository_id, fv.file_name, fv.content_hash, fv.event_type,
           ROW_NUMBER() OVER (
               PARTITION BY fv.repository_id, fv.file_name
               ORDER BY c.created_at DESC, c.commit_hash DESC
           ) AS pos
    FROM agg_file_versions fv
    JOIN agg_commits c
      ON c.repository_id = fv.repository_id AND c.commit_hash = fv.commit_hash
    WHERE (c.created_at, c.commit_hash) <= (:at_time, :at_hash)
),
selected_files AS (
    SELECT repository_id, file_name, content_hash
    FROM ranked WHERE pos = 1 AND event_type <> 3
)
SELECT * FROM selected_files;
```

フォルダ単独検索は次の**機械的 mapping** で同形 SQL になる (repository_id 列と、それを使う
PARTITION / 述語を除去する):

| 横断 (app.sqlite) | フォルダ単独 (metadata.sqlite) |
| --- | --- |
| agg_commits / agg_file_versions | commits / file_versions |
| agg_chunks / `chunk_uid` | chunks / `chunk_id` |
| agg_chunk_fts | chunk_fts |
| agg_embeddings / agg_vec | embeddings / embedding_vec |
| bind 給源: app_config (`:current_tool` / `:current_profile` / `:query_vector` の embed 元) | `:current_profile` = §5.7 profiles + embeddings の一意 profile 規則 / `:current_tool` = markdown_documents の最新 generated_at 規則 (いずれも §11.2 の「フォルダ単独の現行決定規則」— app_config は横断専用で単独検索の給源ではない) |

過去版の Markdown / chunk / embedding は保持済みなので、過去版込み検索に再生成・再課金は発生しない。
**ただし tool profile 変更後の過去版本文は backfill (§10 — 既定 ON) が成立させる** — backfill OFF は
「tool 変更を跨ぐ過去版検索の完全性を放棄する」設定であり (旧 tool 派生は §9.3-b の逆差集合で
agg から消え、現行 tool の派生は過去版に対して生成されない)、OFF 時はその旨を status に明示する。

## 11.2 ハイブリッド (FTS + マルチモーダル KNN → RRF 融合)

両経路とも join で chunks の行 (chunk_id / chunk_uid) に着地するため、テーブル分離のまま融合できる。
**版・tool の絞り込み (eligible) は rank 計算より先に適用する** — 後段で絞ると、旧版・旧 tool の
chunk が KNN の top-k や FTS の順位を占有し、対象チャンクのヒットが 0 件になり得る:

```sql
WITH ranked AS (                    -- §11.1 (A) 現在版モードを組み込んだ実行可能な完全形。
    SELECT fv.repository_id, fv.file_name, fv.content_hash, fv.event_type,
           ROW_NUMBER() OVER (
               PARTITION BY fv.repository_id, fv.file_name
               ORDER BY c.created_at DESC, c.commit_hash DESC
           ) AS pos
    FROM agg_file_versions fv
    JOIN agg_commits c
      ON c.repository_id = fv.repository_id AND c.commit_hash = fv.commit_hash
),
selected_files AS (
    SELECT repository_id, file_name, content_hash
    FROM ranked WHERE pos = 1 AND event_type <> 3
),
-- 過去版込み / 時点指定は、上記 2 CTE を §11.1 (B) / (C) の同名 CTE に差し替えるだけ
-- (公開名 selected_files と列が同一のため機械的に置換できる)
eligible AS (                       -- 版 + 現行 tool で先に絞った検索対象チャンク
    SELECT c.chunk_uid, c.chunk_type, c.embed_hash
    FROM agg_chunks c
    WHERE c.tool_profile_hash = :current_tool
      AND EXISTS (SELECT 1 FROM selected_files sf
                  WHERE sf.repository_id = c.repository_id
                    AND sf.content_hash = c.content_hash)
      -- EXISTS で引く: 同一 content_hash を複数 file_name が参照していても chunk_uid は
      -- 重複しない (JOIN だと重複行が ROW_NUMBER と RRF 加点を水増しする)
),
fts_hits AS (                       -- rank は eligible へ絞った後に計算する
    SELECT t.chunk_uid,
           ROW_NUMBER() OVER (ORDER BY t.bm25_rank, t.chunk_uid) AS r
    FROM (
        SELECT e.chunk_uid, bm25(agg_chunk_fts) AS bm25_rank
        FROM agg_chunk_fts                   -- エイリアスを付けない: FTS5 の MATCH / bm25() は
        JOIN eligible e                      -- 表名で参照するため、別名を付けると解決できない
          ON e.chunk_uid = agg_chunk_fts.rowid
        WHERE agg_chunk_fts MATCH :query
        ORDER BY bm25(agg_chunk_fts), e.chunk_uid
        LIMIT :fts_cap                       -- 中間候補の内部上限は**この内側段**で適用する (入力
                                             --  契約 §11.2 — rank 順の決定論的打切り)。window
                                             --  (ROW_NUMBER) と同じ段に LIMIT を書くと、window が
                                             --  全一致行を走査してから切るため一時領域・VM step が
                                             --  一致件数に比例して膨らむ。外側 :limit は fusion 後。
                                             --  KNN 側の対応物は k = :k_fetch
    ) t
),
vec_hits AS (
    SELECT e.chunk_uid,
           ROW_NUMBER() OVER (ORDER BY v.distance, e.chunk_uid) AS r
    FROM agg_vec v
    JOIN eligible e
      ON v.target_key = (e.chunk_type || ':' || lower(hex(e.embed_hash)))
      -- lower() は必須 — SQL の hex() は大文字を返し、格納側は小文字固定 (§5.6 / 下記契約)。
      -- 混在は join がエラーなく 0 件になり KNN 経路が沈黙する。
      -- ROW_NUMBER の第 2 キー chunk_uid は同スコア時の順位を決定論化する (FTS 側も同じ)
    WHERE v.embedding MATCH :query_vector AND k = :k_fetch    -- over-fetch (下記)
),
fused AS (
    SELECT chunk_uid, SUM(1.0 / (60 + r)) AS score        -- RRF (k=60)
    FROM (SELECT * FROM fts_hits UNION ALL SELECT * FROM vec_hits)
    GROUP BY chunk_uid
)
SELECT c.chunk_uid, c.repository_id, c.content_hash, c.tool_profile_hash,
       c.chunk_type, c.heading_path, c.char_start, c.char_end,
       c.text, c.image_hash, c.media_type, fu.score
FROM fused fu
JOIN agg_chunks c ON c.chunk_uid = fu.chunk_uid
ORDER BY fu.score DESC, c.chunk_uid LIMIT :limit;   -- 第 2 キーは必須 — RRF 同点 (FTS 単独 1 位と
                                                    -- KNN 単独 1 位は同スコア) が LIMIT 境界に並ぶと
                                                    -- 実行ごとに結果集合が揺れる
```

結果は **chunk 単位 1 行**で、§12 の解決チェーンを開始する解決キー (repository_id / content_hash /
tool_profile_hash / chunk_uid / char span) をすべて含む。file_name・commit・created_at への展開
(同一 content_hash が複数ファイル・複数版に属す場合の全列挙) は §12 のとおり表示段で行う —
検索 SELECT に file join を入れると同一チャンクが複数行へ膨れ、LIMIT を消費してしまう。

**vec0 の over-fetch / refill 規則**: vec0 の KNN は eligible 絞り込みの**前**に仮想テーブル側で
top-k を返すため、`:k_fetch` は要求件数より大きく取る — 初期値は
**`min(k_max, max(40, :limit × 4))`** (min クランプが無いと :limit=1025 で初期値が自らの上限
4,096 を超えて実行不能になる)。eligible join 後の vec_hits 件数が `:limit` に満たない場合は
`:k_fetch` を倍にして vec_hits を再クエリする (上限 = 設定値 k_max、**既定 4,096**。
到達後は不足のまま返す。refill 後は rank を再計算するため順位は一貫する)。
過去版込み検索 (all_versions) では eligible が広がるため refill はほぼ発生しない。

**検索入力の契約**:

- **`:query_vector` の生成源**: クエリテキストを現行 embedding profile で embed した L2 正規化
  ベクトル。**bind 形式は float32 (リトルエンディアン) の raw BLOB、長さ = dimensions × 4 バイト**
  (§5.6 の `float[<dim>]` 列・embeddings.vector と同形式 — 形式を固定しないとバインディング差で
  KNN が沈黙する)。横断検索 (agg_*) は **app_config の `embedding_profile` record (§9.1)** から生成する —
  これが無いと横断検索はクエリを embed できず KNN 経路が実行不能になる (§9.1 app_config の主目的)。
  **生成に使った profile の hash を `:query_profile_hash` として固定し、KNN 実行の直前に app_config の
  `agg_ready_profile_hash` (§8-e — 全接続フォルダの再レプリケーション完了時のみ更新) が
  `:query_profile_hash` と一致することを確認する** (「現行」との照合ではない — embed 中に profile が
  P1→P2 へ変わり ready も P2 へ進むと、P1 で作ったクエリベクトルが P2 index に当たる TOCTOU になる。
  生成時の hash に固定すれば変更中は必ず不一致になり FTS へ落ちる)。**照合と KNN 実行は同一の
  read Tx (同一接続のスナップショット) で行う** — 別 Tx だと照合通過と KNN の間に tick の再構築が
  挟まり、旧 profile のクエリベクトルが新空間へ当たる窓が残る (app.sqlite は WAL のため read Tx が
  スナップショットを固定する)。不一致 (profile 変更直後〜再構築
  完了前の窓) なら KNN を実行せず FTS のみで返して status に「index 再構築中」を示す — 新 profile の
  クエリを旧空間の agg_vec に当てると、次元違いは SQL エラー、同次元の model 違いは黙った誤順位に
  なる (building 単一 key では部分 index が照合を通過する)。**クエリの embed 呼び出し自体が失敗した
  場合 (429 / ネットワーク断 / 認証エラー) も KNN を実行せず FTS のみ + status で返す** — 必須 bind
  (`:query_vector`) を作れないため、ready 不一致時と同じ縮退にする (全失敗にも FTS 沈黙にもしない)。
  **フォルダ単独検索の「現行」の決定規則**: profiles 表 (§5.7) は hash キーの record 保管庫で
  current マーカーを持たない。**`:current_profile` は embeddings の全行一致検査 (§8) で得られる
  一意な embedding_profile_hash に対応する profiles 行を現行とする** (embeddings が空、または §8-d
  未実施の移行中で複数 profile が混在する間は KNN 経路を実行せず FTS のみ)。**`:current_tool` は
  markdown_documents の最新 generated_at を持つ行の tool_profile_hash を現行とする** — tool 切替後は
  旧 tool 派生が明示 drop (§21.6) まで残るため混在が定常であり、embedding と同じ「混在なら停止」を
  適用すると eligible の tool gate が FTS 経路まで恒久停止させ §2 (コピー先でそのまま検索できる) に
  反する。**この非対称は意図的**: embedding の混在は KNN の空間汚染 (黙った誤順位) を生むため停止で
  塞ぎ、tool の混在は「どの世代の本文を読むか」の選択にすぎないため最新世代を決定論的に採る。
  **generated_at が now + 許容 skew (5 分) を超える行は判定の候補から除外し status で警告する**
  (時計事故で未来値が書かれた行が MAX を恒久に占有し、以後の正常な世代が永久に選ばれなくなる —
  全行が未来の場合のみ最新を採用して機能を維持)。
  **同時刻 tie (異なる派生行の generated_at が同値) は tool_profile_hash のバイト昇順で決定する**
  (§5.3 の単調更新は同一派生の置換内の規則で、異なる派生行の間の同値を排除しない — tie-break が
  無いと bind が実装・走査順依存になる)。**近似であることの注記**: 一括ローカル変換 (再チャンク・
  grammar 再 materialize) は旧 tool 派生の generated_at も進めるため、変換直後は旧 tool が「最新」に
  なり得る — この規則は「最後に触れられた世代」の決定論的選択であり、「最後に OCR 生成が起きた
  tool」の厳密な復元は層 1 の目的外 (app 管理下の検索は app_config が正。次の新 tool 生成で復帰する)。
  **全行一致・最新 generated_at のいずれも chunks / 全 content への
  被覆を保証しない** — re-embed / 再 OCR 進行中の検索は部分的であり得る (FTS は tool gate 内で全量)。
  完全性は
  主張せず、未 embed 残数 (chunks 差集合) を status に示す
- **空クエリの拒否**: trim 後に空になるクエリは 0 件を返して**経路を実行しない** — 空 `:like_pattern`
  は `LIKE '%%'` で全 eligible 行に一致し、空 `:query_vector` も未定義。FTS / LIKE / KNN の
  いずれも走らせない
- `:query` は利用者の自然文を **FTS5 クエリ構文として解釈させない** — 全体を決定論的に
  エスケープしてフレーズ化する (内部の `"` を `""` に重ねた上で全体を `"..."` で括る)。
  エスケープ漏れは `"` 1 文字で SQL 全体が構文エラーになり、KNN 経路まで巻き添えで失われる
- **3 文字未満のクエリは trigram FTS が沈黙して 0 件を返す** (日本語の一般的な 2 文字語 —
  「検索」「会社」等 — が該当する実害の大きい制約)。この場合 FTS 経路を LIKE 走査
  (eligible に絞る) へ差し替え、RRF には通常の FTS 経路として参加させる。**FTS は text と
  heading_path の両列を索引する (§5.5) ため、LIKE fallback も両列を対象にする** —
  `(c.text IS NOT NULL AND (c.text LIKE :p ESCAPE '\' OR c.heading_path LIKE :p ESCAPE '\'))`。
  **`c.text IS NOT NULL` は必須** — FTS の対象 (view §5.5) は text 非 NULL 行のみで、fallback だけが
  annotation なし画像チャンク (text=NULL) を heading 経由で返すと、同じクエリの対象集合が 3 文字
  境界で変わる (fallback は FTS の代替経路であり対象集合を広げない)。片方だけだと「heading にのみ
  現れる短語」(例 heading_path=`["会計課"]`・本文に無し) が 3 文字以上 (FTS ヒット) と 2 文字以下
  (fallback 0 件) で挙動が変わる。**case 挙動の注記**: trigram FTS の折り畳み (Unicode simple case
  folding) と LIKE の既定 (ASCII のみ) は一致しない — fallback は **query・対象の両側に FTS と同一の
  折り畳みを適用して比較するのが正**。それが不能な実装では「短語 (≤2 文字) の一致は case 厳密の近似」
  であることを明記して選ぶ — 同じ語が 2 文字では出ず 3 文字で出る非対称を暗黙にしない。**bind は分離する** — フレーズ化済みの `:query` をそのまま LIKE へ
  渡すと引用符込みで検索されて 0 件になる。LIKE 用には**生のクエリ文字列**から `\` → `\\`、
  `%` → `\%`、`_` → `\_` の順でエスケープした `:like_pattern` (= `:p` は `'%'||:like_pattern||'%'`) を
  作る (エスケープしないと `%` / `_` 1 文字のクエリが全行ヒットになる)。rank は bm25 が使えない
  ため「最初の一致位置昇順 → chunk_uid 昇順」で決定論的に採番するが、位置は **text と heading_path の
  一致位置 (instr) の非 0 最小**を採り、**LIKE と同じ case 折り畳みで計算する**:
  `instr(lower(text), lower(生クエリ))` / `instr(lower(heading_path), lower(生クエリ))` — SQLite の
  既定 LIKE は ASCII を case-insensitive に照合する一方 instr は区別するため、揃えないと「LIKE は
  ヒットしたが instr = 0 (未一致)」の行が最上位に来る逆転が起きる (両列 0 の行は LIKE 条件を満たさず
  現れない)
- target_key の hex は**小文字に固定**する。SQL の hex() は大文字を返すため、SQL 内で構築する
  場合は lower(hex(...)) と書く (大文字小文字の混在は join がエラーなく 0 件になる)
- **hash 系 bind (:current_tool / :current_profile) は raw BLOB (32 bytes) で bind する** —
  app_config は record (JCS TEXT) を保持するため、読み手が SHA-256 を計算した**生バイト列**を
  bind する。lower hex の TEXT を bind すると BLOB 列 (tool_profile_hash 等) との比較が
  エラーなく 0 件になり FTS / KNN とも沈黙する (:at_hash の BLOB bind 規則と同じ穴)
- 時点指定 (§11.1 C) の `:at_hash` は **BLOB として bind** する (テキスト bind は行値比較の
  型不一致で境界がずれる)。**「時刻 t まで」の指定で commit を特定しない場合は :at_hash =
  X'FF…FF' (32 bytes) に固定する** — 同一 created_at の複数 commit を全て含める意味論。
  未規定だと同一 ms 帯の包含集合が実装依存に揺れる
- LIKE fallback の走査は **eligible が text / heading_path 列を公開しないため agg_chunks を chunk_uid で
  再 JOIN する** (`FROM eligible e JOIN agg_chunks c ON c.chunk_uid = e.chunk_uid
  WHERE c.text IS NOT NULL AND (c.text LIKE :p ESCAPE '\' OR c.heading_path LIKE :p ESCAPE '\')`) —
  掲載 SQL の fts_hits をこの形で差し替える (裸の `text` 参照は列不在エラー。**`c.text IS NOT NULL` は
  差し替え形にも必須のまま残す** — 上の規範 (fallback の対象は text 非 NULL 行のみ) の再掲で、
  欠くと text=NULL の画像 chunk が heading_path の短語一致だけで混入する)
- **`:limit` の契約**: 正整数として入力境界で検証する (上限 = 設定値)。SQLite の `LIMIT -1` は
  無制限を意味するため、負値・0・非整数・過大値は境界で拒否する — 検証しないと `:limit = -1` が
  100 万件規模の FTS ヒットを全件返してメモリを食い潰す
- **query の入力契約**: NUL (U+0000) を含む query は境界で拒否 (または除去) する — FTS5 の MATCH 式へ
  bind すると構文エラーで検索全体が abort する (`"` の二重化 (フレーズ化) では防げない — `:limit`
  検証と同じ入力境界の契約)
- **中間候補の上限**: fts_hits (および KNN の k) には**内部上限 (`LIMIT :fts_cap` — 設定値) を置く** —
  外側の `LIMIT :limit` は fusion・集約・sort の後にしか効かず、100 万件級の一致が rank 化・一時領域を
  先に食い潰す (`:limit` と同じ入力契約の一部。cap は RRF の再現率とのトレードオフとして設定で調整)

- テキストクエリの embedding で **text チャンクと画像が同列にヒット**する (multimodal 単一空間)
- annotation 付き画像は FTS 経路でもヒットする (両経路に出た chunk は RRF で自然にブースト)

# 12. 検索結果から原本への解決

chunks は commit を持たないが、content_hash join で原本・全文・版へ完全に解決できる:

```text
ヒットした chunk
  ├── text / heading_path / char_start..end     → プレビュー表示
  ├── (content_hash, tool_profile_hash)
  │     ├── markdown_documents → markdown_hash  → objects/ の Markdown 全文
  │     ├── objects/<content_hash>              → 原本ファイルそのもの (Evidence)
  │     └── file_versions を content_hash で逆引きし、commits を join
  │           (created_at は commits 側にある — file_versions JOIN commits USING (commit_hash))
  │           → (file_name, commit_hash, created_at) の全出現
  │             = どのファイルのどの版か / 現在版か過去版か / いつのコミットか
  └── chunk_type = 2 なら image_hash            → objects/ の画像実体
```

**提示前の hash 再照合**: 解決チェーンで objects/ から読んだ実体 (原本・Markdown 全文・画像) は
SHA-256 を再計算して名前 (content_hash / markdown_hash / image_hash) と照合してから提示する —
restore (§21.4 手順 1) と同じ規律。不一致 (silent bit-rot) は破損実体を「原本」として配らず
fsck (§13) へ誘導する (これが無いと週次 fsck までの最大 1 週間、破損が無検証のまま「原本」
として提示され得る)。

**解決可能性の限定**: この「完全に解決できる」は**接続中のフォルダに限る** — 横断検索は missing
(§20.4 猶予中 — 外付けドライブの一時切断等) のフォルダの agg 行にもヒットし得るが、その objects/ は
開けない。missing フォルダへのヒットは結果から除外せず、**解決段で「フォルダ接続なし (missing)」を
status 表示する** (どのオフラインドライブにあるかを示せること自体が検索の価値 — 再接続で解決可能に戻る)。

# 13. ガベージコレクション

objects/ の参照集合は **3 本の和集合** (**未知 grammar v の Markdown を持つ派生は fail-closed** —
参照を正しく列挙できない (自装置の解析器より新しい v・v 混在) 文書由来の参照は「全 objects 参照
あり」として保守的に GC 対象から外し status に報告する。§6/§7 の reparse fail-closed の鏡写し —
旧 regex での抽出は新形式の参照を 0 件と誤認し、参照中の原本を誤回収する):

```text
1. SELECT content_hash  FROM file_versions WHERE content_hash IS NOT NULL   -- 原本
2. SELECT markdown_hash FROM markdown_documents                             -- 派生 Markdown
3. 各 markdown_documents の保存済み Markdown (objects/<markdown_hash>) から抽出した
   obj:<image_hash64> 参照の集合                                             -- 抽出画像
```

3 本目は **SQL (chunks.image_hash) ではなく保存済み Markdown からの抽出を正とする** — §6 の
grammar が固定形のため正規表現で決定論的に抽出できる。chunks.image_hash はこの部分集合に
すぎない: opt-in フィルタ (§7 規則 6) で chunk 化されなかった画像は chunks に現れないが
Markdown からは参照されており、SQL 基準の GC は**フィルタ ON 中にその画像 object を誤回収する**
(フィルタを OFF に戻しても obj: 参照が宙に浮き、画像はローカル再解析では復元できず
再 OCR 課金になる)。

この集合に無い objects/sha256/ 配下を削除する。**GC は tick.lock を取得し、deep-scan と同一の
低頻度サイクル (既定 週 1) で実行する** — 本書の objects/ への writer はすべて tick 内
(ステップ 0 のコミット実体保存とステップ 2 の派生・画像保存) にあるため、これで
「objects 書込後・metadata 確定前」の中間状態を GC が観測することはない。保険として
作成から 24 時間以内の object は削除しない (grace)。

**GC は fail-closed**: 参照集合の構築中に markdown object の欠損・読取失敗、**または読み取れた
bytes の SHA-256 が markdown_hash と不一致 (silent bit-rot — 「読める」ことは「壊れていない」
ことを意味しない)** を検出したら、削除を行わず中断して status に報告する — 破損・欠損 Markdown
の obj: 参照は抽出できず (または壊れた値になり)、その派生の画像 object 群が「参照ゼロ」に見えて
誤回収される (部分喪失を追加喪失へ増幅する) ため。参照抽出の前提は「読めること」ではなく
**hash 一致**である。

**fsck (整合性検証)**: GC と同じ週次サイクルで実行し (**同一サイクル内では fsck → GC の順** —
fsck の修復・参照再構築が済んだ状態を GC の参照判定に見せる。**GC の実行点は tick の step 5 以降**
(§21.3 手順 5 の注記と同一 — scan 完了前は現在版原本も参照ゼロに見える))、検査は object 層と履歴層の両方に及ぶ:

- object 層: 参照集合に含まれる全 object の bytes を読み SHA-256 を再計算して名前と照合する。
  **読取の一時失敗 (AV/EDR の排他ロック・ネットワーク FS の一時 EIO 等) は「破損」と区別する** —
  GC の fail-closed と同じく「読めない」と「壊れている」を混同せず、一時失敗は status に retry
  対象として記録するに留め、明示再生成 (= 再課金) へは誘導しない。破損確定は「読めたが hash
  不一致」に限る
- 履歴層: `PRAGMA integrity_check` / `PRAGMA foreign_key_check` に加え、**全 commit の
  commit_record を §4.1 の直列化で再構築して commit_hash を再計算・照合**し、
  parent_hash / previous_commit_hash の鎖が解決可能であることを検査する (手動編集・部分破損で
  「object は正しいが履歴が偽」の状態を検出する — object 検証だけでは file_versions の
  content_hash を別の実在 object へ書き換えた改変が素通りする)。**FTS 整合も検査する**:
  chunk_fts へ external content 照合つきの integrity-check (`INSERT INTO chunk_fts(chunk_fts, rank)
  VALUES('integrity-check', 1)` — **第 2 引数 (rank 列への 1) が external content との照合を有効に
  する (SQLite 3.42+)。引数なしの形式は index 内部の整合しか検査せず、posting 単独欠損を成功の
  まま素通しする (偽陰性)**) を実行し、不一致は同 Tx で `'rebuild'` する — posting 単独の破損は
  `PRAGMA integrity_check` では検出されず、該当語の MATCH が恒久 0 件になる。agg_chunk_fts も
  同様に external content 照合つき (rank=1) で検査し、**不一致は同 Tx で `'rebuild'` する** —
  integrity-check は破損箇所 (どのフォルダ・どの親行か) を返さないため、旧規定の
  「synced_profile_hash NULL 化 + 該当親行 DELETE」はこの検査からは実行できない (posting の修復は
  index 全体の rebuild で完結する — external content (agg_chunks) は無傷が前提。agg_chunks 側の
  内容破損は下記の親子整合検査が per-folder の再同期を駆動する)。**folder 側の親子整合も
  同型で検査する**: markdown_documents の各行とその chunks 子行の対応 (**件数 + 全 field 照合 — text チャンクは
  SHA-256(text) = text_hash、image チャンクは image_hash / media_type / image_meta、共通で seq /
  chunk_type / heading_path / span (§7 再解析の出力との完全一致 — 再解析する以上、比較の追加コストは
  無い)** — §7 の解析は決定論的で、text_hash 列が内容整合の検証基盤を
  既に持つ。件数だけでは内容破損が素通りし、FTS の 'rebuild' が破損内容を正として再索引・固定化する)
  を照合し、不一致は該当 markdown_documents 行の §7 再解析 (ローカル・無課金) で再構築する
  (agg 側だけの検査だと、folder 正本側の子行欠落が「正しい正本」として agg へ複製される)
- profile 層: (a) **profiles 全行の SHA-256(record_json) = profile_hash を照合**し、(b) **参照
  整合を検査**する — markdown_documents.tool_profile_hash / embeddings.embedding_profile_hash が
  指す profile_hash の行が profiles に存在し kind が一致すること (LEFT JOIN の欠落検出。
  hash 照合だけでは「行ごと消えた」破損を見逃す)。**破損行の修復は fsck 自身が行う**: 破損した
  profile_hash が現行 profile (app_config §9.1、または batch_requests の profile_record snapshot)
  と一致するなら、検証済み record で **DELETE → INSERT** し置換する (**同一 Tx — BEGIN IMMEDIATE**。
  DELETE と INSERT を別 Tx にすると、間のクラッシュ + app.sqlite 喪失の二重障害で record の
  復元材料が両側から消える) — §5.7 の通常書込は
  INSERT OR IGNORE のため**破損行は何度書き込んでも直らない** (PK が既存で IGNORE される)。
  検証済み record を入手できない旧 profile の破損は報告に留める — 該当派生の修復誘導は **kind 別**
  (下記「profile 破損の誘導は kind 別」)。tool profile は §21.6 drop-derivation → 現行 tool で自動
  再投入、embedding profile は embeddings 行削除 → 現行 profile で自動 re-embed であり、「明示再生成
  (§5.3)」は kind=1 (OCR floor) 専用で embedding の修復には使えない (旧「§5.3 を誘導」の一律誘導は
  embedding に誤適用されるため kind で分岐する)
- 集約層 (cache): agg_embeddings と agg_vec の target_key 差集合を**双方向**に検査する —
  (i) embeddings にあるが vec に無い欠落は §8-e の毎 tick 差集合再充填が次 Replicate で埋める、
  (ii) **vec にあるが embeddings に無い孤児**は §9.3-c の DELETE→INSERT 投入が上書きで無害化する
  (素朴 INSERT 実装だと PK 衝突で replicate が毎 tick abort する — §9.3-c)。加えて **agg の
  親子整合** — agg_markdown_documents の各派生行とその agg_chunks 子行の対応 (件数) — を検査する:
  子行だけが部分喪失した派生は §9.3-b の generated_at 比較で再検出されない (親が一致したまま子が
  検索から恒久欠落する) ため、**不一致を検出したら当該派生の agg_markdown_documents 行を DELETE し、
  当該フォルダの sync_state.synced_profile_hash を NULL へ戻し、同一 Tx で agg_ready_profile_hash も
  削除する** (ready を残すと修復完了までの部分 index が ready を騙り KNN が欠落を正常として返す —
  全接続フォルダの synced 一致で再設定される) — 次 Replicate の §9.3-b が
  「agg に無い派生」として子ごと全置換する (cache の自己修復をこの検査が駆動する)。上記以外は
  いずれも件数を status に報告するに留める (agg は真実でないため、再同期の駆動以外の直接修復はしない)

破損・欠損は status に報告し、派生 (Markdown / 画像) は明示再生成 (§5.3) を誘導する。
**原本・派生の両方が同時喪失して GC が恒久 fail-closed に陥った場合の回復手段は §21.6 の
「派生破棄 (drop-derivation)」** — 参照の宙吊りを断ち切って GC を再開させる明示操作である。
**原本 object の欠損・破損は fsck 自身が修復できる**: working copy の bytes を hash して
一致すれば objects/ へ書き戻す (repair — 履歴行は不変のまま実体だけを復元する。通常スキャンは
LWW との hash 一致で「変更なし」と判定して再保存しないため、この書き戻しは fsck の明示経路で
しか起きない)。repair の読み取りは **§20.5 手順 1 と同じ 1 ストリーム規律** (hash 計算と tmp 書込を
同一 open で兼ね、前後 stat 一致を確認して rename + dir fsync) — hash 確認と保存で 2 回 open すると
その間の外部編集で「hash H の名前に別内容」を書く TOCTOU を fsck 自身が再導入する。
**「同一 content_hash の実体が既に存在すれば再保存しない」規則 (§20.5) の例外**: fsck が
hash 不一致 (破損) を検出した object は、既存実体があっても tmp からの原子置換で上書きする —
例外にしないと「壊れた実体が存在する」こと自体が修復を永久に妨げる。
一致する working copy が無ければ喪失として報告する (本設計はファイルシステム層の冗長性を
代替しない — 検出と誘導までが責務)。**profile 破損の誘導は kind 別**: tool profile record の
破損で該当派生を作り直す場合は §21.6 drop-derivation → 現行 tool での自動再投入、embedding
profile (旧) の破損は該当 embeddings 行の削除 (**同一 Tx で embedding_vec → embeddings の順** —
§8-b / 本節の孤児掃除と同じ規律。embeddings だけ消すと vec 孤児が残り、re-embed の collect INSERT が
target_key PK 衝突で恒久失敗する。fsck はローカル側も vec → embeddings の逆差集合 = vec 孤児を
検出対象に含め、**検出した孤児 vec 行は削除する (修復)** — 検出のみでは §10 step 4 の INSERT が
衝突し続ける。collect 側の DELETE → INSERT (§10 step 4) と二重の防御) → 現行 profile での自動 re-embed — 「明示再生成
(§5.3)」は OCR floor の操作であり embedding の修復には使えない。

**バックアップ規範**: フォルダコピーによるバックアップは **tick.lock を取得した静止状態で行い、
復元後は fsck を実行する** (稼働中コピーは「新しい metadata + 古い objects」のねじれを作り、
content-addressed の再保存スキップにより欠損が自己修復されない)。**復元 (書き戻し) も同様に
tick.lock 下で行う** — lock 外の外部復元 (metadata だけ古い版へ戻す等) も §9.3-z / §10 step -1 の
後退検出が次 tick に regressed として拾い、step 5 の wipe + full resync が回収する (working は
復元で変わらないため未取り込み内容は再コミットされる) が、これは検出前提の回収経路であって
静止復元が正。tick.lock の外で objects /
metadata を書き換える汎用同期ソフトとの併用は §19 の条件 1 のとおり非対応。
**app.sqlite のバックアップ (規約 7 の「課金履歴の保全が要件なら別途取る」の実体) は SQLite の
Online Backup API または `VACUUM INTO` で行う** — app.sqlite は WAL (§14) のため、**main ファイル
単独の raw コピーは WAL 未 checkpoint の commit 済みデータ (cost_ledger 行等) を失う**。禁止。

tool_profile_hash 切り替え後の旧派生は、markdown_documents の旧 tool 行を消せば同じ GC で
回収される (CASCADE で chunks も消える)。フォルダ側 embeddings の孤児行は chunks の
**(chunk_type, embed_hash) ペア**との差集合で掃除し、**同一 Tx で embedding_vec → embeddings の
順に削除する** (vec 側の行を残すと、同一内容の再出現時に target_key の PK 衝突を起こす)。
集約側への伝播は §9.3-b の逆差集合が、共有 vector の孤児掃除は §9.3-d が担う。

# 14. SQLite 設定

```sql
-- metadata.sqlite (元設計の設定を継承)
PRAGMA foreign_keys = ON;
PRAGMA synchronous = FULL;
PRAGMA journal_mode = DELETE;   -- 同期ソフト配下の WAL/SHM 分離同期問題の回避
PRAGMA busy_timeout = 5000;     -- 単独検索 (読み) と tick の書込 Tx の並行に備える
-- コミット処理中だけ短時間開く

-- app.sqlite (アプリ専有パスなので WAL で良い)
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;     -- SQLite ロック待ちの設定。tick の直列化は §10 の tick.lock が担う

-- 空きページの回収 (metadata / app 共通): 新規 DB 作成時に PRAGMA auto_vacuum = INCREMENTAL を
-- 設定し、fsck の週次サイクルで PRAGMA incremental_vacuum(N) を実行する (N = 有界ページ数の設定値
-- — 引数なしは全 freelist を一括回収し、大量 DELETE 後に長時間ロックとなり得る) — GC・派生置換・行削除の
-- DELETE で生じた空きページを回収しないと DB ファイルが単調肥大する (全量 VACUUM は長時間の
-- 排他ロックになるため規範にしない — 実行するなら fsck と同じ静止条件で任意)
```

**schema version (両 DB 必須)**: `PRAGMA user_version` を version 1 から採番し、schema 変更ごとに
+1 する。起動時に検査し、**DB の版がアプリの対応版より新しければ開かず fail-closed**
(新旧アプリ混在で旧アプリが新 DB を壊す経路を塞ぐ)、古ければ前方互換 migration
(ADD COLUMN / CREATE TABLE IF NOT EXISTS) を適用する。**migration は版ごとに単一 Tx で行う**:
`BEGIN IMMEDIATE` → user_version を再確認 (並行プロセスとの競合排除) → DDL / データ移行 →
`PRAGMA user_version = 新版` → `COMMIT`。SQLite では DDL も user_version も Tx に参加するため、
途中クラッシュは DDL ごと巻き戻り、再実行が常に安全になる — version 更新を別 Tx にすると
「ADD COLUMN 成功・version 未更新」で再起動時に duplicate column で恒久起動不能になる。
**意味論を持つ列の追加は backfill も同じ Tx で行う** — 例: batch_requests.job_create_started_at の
追加時は、state=0 かつ intent_token 非 NULL の既存行へ intent_token の時刻成分を backfill する
(「NULL = 相 2b 未着手の証明」(§9.1) は列導入後の lifecycle にのみ成立 — backfill しないと旧版で
作成済みの job が「未作成」誤認され、可視化遅延中の載せ直しで二重投入される)。
**migration は tick.lock 下で実行し、すべての writer (常駐スレッドの tick・明示操作) は
tick.lock 取得後・Tx 開始時に user_version を再確認する** — 起動時検査だけでは、migration 前から
生存する旧版 writer が新版 DB へ旧スキーマの意味論で書き込む窓が残る (常駐プロセス内の
バージョン更新を跨ぐ書込の遮断)。
**既存データを持つ表に FTS (external content) を後から追加する migration は、同じ Tx 内で
`INSERT INTO <fts>(<fts>) VALUES('rebuild')` を実行する** — trigger は以後の変更しか拾わないため、
rebuild なしでは既存行が索引に載らず MATCH が silent 0 件になる (local / agg 両方に適用)。
**PRAGMA の接続初期化規範**: `foreign_keys` は SQLite では **connection ごとの設定**であり
既定 OFF — 本書の全 PRAGMA (foreign_keys / busy_timeout 等) は「DB を開くすべての接続の
open initializer で適用し、適用を検証してから使う」ことを必須とする (適用漏れの接続で
DELETE を実行すると CASCADE が発火せず孤児行を作る — fork §21.3 の commits 全削除が典型)。

**権限と tmp 掃除**: `.folder-history/` 配下と app.sqlite の格納ディレクトリは 0700、
ファイルは 0600 で作成する (app.sqlite は全フォルダの root_path・エラー文言・コストを
1 ファイルに集約するため、漏洩時の影響がフォルダ単体より大きい)。**Windows では POSIX mode が
意味を持たない**ため、同じ対象に**継承を遮断した DACL (現在ユーザー + SYSTEM のみ)** を設定する —
親ディレクトリの Everyone 読取などの継承 ACL をそのまま受けると履歴・原本 objects が他ユーザー
可読になる。起動時と復元後に権限を検査し、**逸脱は status に報告して mode / DACL の修復を試み、
修復できるまで当該 repository を fail-closed** とする (既知の他ユーザー可読状態のまま原本・派生・
root_path を読み書きし続けない)。`tmp/` に残留した一時ファイル (rename 前クラッシュの残骸) は、
tick 開始時に 24 時間より古いものを削除する。

# 15. 設計規約 (不変条件)

```text
1. 識別: 原本 = content_hash / 派生の同一性 = (content_hash, tool_profile_hash) の行の存在。
   markdown_hash・派生バイト列の hash を同一性判定・再生成判定に使わない (LLM 非決定性)
2. tool_profile_hash の入力: 解決済み版付きモデル名 (alias 禁止) + annotation スキーマ +
   呼び出しオプション。変更 = 別派生として再生成キューに乗る
3. embedding profile は単一 multimodal 固定。起動時に全行一致 + embedding_vec の存在・次元を検査。
   変更 = 現行 profile 設定の更新のみ (§8 — 成果判定・置換・vec 再作成・掃除が宣言的に収束する。
   多段の手動手順・kind=2 行の一括削除は行わない)
4. chunks / embeddings の行は UPDATE しない。置き換えは DELETE → INSERT
   (FTS trigger と embedding 共有の整合を構造的に保証)。markdown_documents の置き換えも
   同一 Tx の DELETE → INSERT とする — 親行の UPSERT では ON DELETE CASCADE が発火しない
   (§5.3)。唯一の例外は再チャンク時の generated_at 単調更新 (§7)
5. チャンク分割規則の変更は OCR 再課金なしのローカル操作 (chunks DELETE → 保存済み Markdown から再解析)
6. 書き込み順序: objects/ → metadata.sqlite → app.sqlite。逆順の参照は常に存在が保証される —
   objects の「存在」は rename 後のディレクトリ fsync (§20.5) まで済んで初めて成立する。
   **例外 = §7 の floor 引き上げ (app (floor) → metadata (generated_at) の順が正)**: 本規約は
   「後の層が前の層を参照する」ための存在保証の順序であり、fence 系の意図書込 (floor) には
   適用しない — floor に本規約の順序を適用すると、metadata 先行更新後のクラッシュで明示再生成が
   silent cancel され、in-flight の課金済み新結果が破棄される (§7 の順序規範が優先)
7. app.sqlite の運用層は真実を持たない。喪失時は捨てて再構築。損失 = (a) 未回収 job の再投入
   (**全損時は喪失時点の in-flight 全 job が対象** — 「server = 未追跡 1 job」はアプリ健在時の
   クラッシュ窓の主張 (§9.1) であり、全損はその有界化の外 (§10)。client = attempts 上限内。
   無限定の「1 回分」ではない)、(b) cost_ledger の課金履歴、(c) terminal failed の抑制 (恒常失敗対象は再び attempts
   上限まで再投入される — 対象ごとに有界)、(d) 未完了の明示再生成 intent (§5.3 — 再操作で回復)、
   (e) in-flight の upload_id / intent_token — プロバイダ upload の識別・削除ができなくなり
   保持期限までの機密残留が生じる (§2)、(f) **app_config の現行設定 (tool / embedding profile・
   画像フィルタ設定 §8)・unregister の退役事実・watch_roots 外の登録フォルダの個別パス** —
   bootstrap でユーザーが再入力・再確認する
   (§21.5。退役済みフォルダも repository-id が層 1 に残る限り再発見されるため、不要なら再度
   unregister する)。いずれも層 1 の真実には触れない。**「有界」の内訳は 2 種**:
   (a)(c)(d)(f) は対象・操作ごとに有界な再実行コスト、(b)(e) は運用量 (累積課金件数・
   in-flight 数) に比例する不可逆な記録喪失 — 後者の「有界」は件数上限ではなく「層 1 の真実に
   波及しない」の意味 (課金履歴の保全が要件なら app.sqlite のバックアップを別途取る)
8. GC の参照集合は §13 の 3 本の和集合
9. 集約層 (agg_*) は検索キャッシュであり真実を持たない。真実は常に各フォルダの
   `.folder-history/` 全体 (metadata.sqlite + objects/ + repository-id — §2 の層 1)。
   **「真実」の語は履歴・派生・検索の正本を指す** — 内容 (Evidence) の正本は原本ファイル自身で
   あり (§1)、履歴メタデータは使い捨て可。この二層は矛盾しない (原本は working copy と層 1 の
   objects/ の双方に存在し、層 1 を失っても内容は原本から再構成できる — 失われるのは履歴)。
   app.sqlite は丸ごと失われても復元できる — ただし **watch_roots はユーザー設定であり、
   全損時はその再入力 (bootstrap) が復元の起点**になる。再入力後の walk が `.folder-history`
   (repository-id) を検出して folders を再構築し (登録済みリポジトリの**再発見**であって
   「新規管理フォルダの自動登録」ではない — 登録済みの証拠 = repository-id ファイルが
   フォルダ側に存在する)、全フォルダからの再レプリケーションで集約層が完全復元される
10. hash 値は BLOB (32 bytes) として書き込む。新規テーブルは CHECK (typeof(...) = 'blob' AND
    length(...) = 32) で強制する。DDL を元設計から変えない commits / file_versions への書き込みは、
    アプリの書込境界で同じ検証 (BLOB 型 + 32 bytes) を行う — SQLite の型親和性では 32 文字の TEXT
    も length() = 32 を満たすため、旧 DDL の CHECK だけでは SHA-256 bytes を保証できない
11. 変更検知の根拠は常にスキャンの content_hash (§20)。OS ファイル監視イベントは dirty
    マーキングにのみ使い、イベントの種別・パスからコミット内容を構成してはならない。
    fp_cache / scan_cache はヒントであり真実ではない — 喪失時は全再計算に落ちるだけで、
    低頻度 deep-scan が理論上の見逃し (mtime 保存コピー・racy) を有界時間で補正する
12. フォルダ DB を開いて書き込む・レプリケーションする全操作は、開いた `.folder-history/`
    の repository-id を folders 行と照合し、不一致なら中断して conflict を status 表示する
    (§20.4 — `.folder-history` の差し替えは可視ファイルの stat に現れず、段 0 の fp では
    検出できないため、この照合が管理 identity 差し替えの検出点になる)。
    **読み取り専用の操作 (フォルダ単独検索・履歴閲覧・§12 解決) も、対象パスが folders に
    登録済みならば同じ照合を行い、不一致は conflict として結果を返さない** — 書込限定だと
    差し替えられた別 repo の内容を当該フォルダの検索結果として黙って返す (provenance 偽装が
    唯一の検出点から漏れる)。**folders に行が無いパスの読み取り (未登録フォルダ・持ち込まれた
    コピーの standalone 検索) は層 1 自己完結 (§2) の正規の利用**であり照合先が存在しない —
    実行してよいが、**repository-id を結果の provenance として表示する**。**その repository-id が
    folders の別 root_path で登録済みなら「登録済み複製の重複コピー (conflict 中ならその旨)」を
    provenance / status に付す** — 黙って返すと conflict の非主流側を正本と誤認させる。
    **standalone 読み取りも対象の fork-journal (§21.3) を preflight で検査する** — 有効な journal は
    「fork 進行中」status で読み取りを保留し、破損 journal は damaged と同様に扱う (journal を層 1 に
    置く目的 = app 全損を挟んでも「fork 中断」と「空履歴の通常 repo」を区別する (§21.3 手順 0) は、
    app を持たない読み手にも適用される — 検査しないと未完 fork の空・部分履歴を通常として返す)。
    **照合の読取失敗の分類は §21.1 register と同一の 4 分類を全操作に適用する**: 一時読取不能
    (ロック / EIO) = 無変更で保留 + status / 読めるが構造不正 (UUID 形式外・metadata 破損) =
    damaged (§20.4) / 読めて不一致 = conflict / 不在 = damaged または missing (§20.4) —
    一時失敗を conflict / damaged へ倒すと破壊的解決 (fork・再初期化) へ誤誘導する。
    **fork_in_progress (§21.3) の対象 (old_id, realpath) は、呼出元を問わず (tick 内外・
    読み書きとも) 本規約の照合・conflict 判定の適用対象から除外する — 共有ガードとして実装する**
    (fork 手順 2〜3 の間は実体 id = new・folders = old が正常な中間状態であり、tick 経由の
    呼出だけ抑止すると tick 外の単独検索・履歴閲覧が fork 中に誤 conflict を返す)。
    fork 中の読取要求には conflict ではなく「fork 進行中」の status を返す
```

# 16. コスト

| 項目 | 単価 | 備考 |
| --- | --- | --- |
| OCR 4 + bbox annotation (Batch) | **$2.5 / 1,000 ページ** | $5/1k の 50% 割引。**同一 (content_hash, tool_profile_hash) につき 1 回きり** (§6。tool 変更時は同内容でも再 OCR) |
| 再 OCR (同一内容・同一 tool) | $0 | markdown_documents の行の存在で短絡 |
| 再生成時の embedding | 変わった chunk 分のみ | text_hash / image_hash の内容ベース共有 (§5.6) |
| チャンク分割規則の変更 | $0 (ローカル再解析) | §15 規約 5。ただし大規模一括変更は集約側の全置換 (§9.3-b) が 1 tick に集中するため、フォルダ単位の分散実行を推奨 |
| 明示再生成 (§5.3) | **再課金** | 同一ペアの再 OCR — 課金単位「1 回きり」の明示的な例外 |
| Batch 結果の失効後再投入 (§6) | **再課金** | 収集が結果保持期限 (約 24h) に間に合わなかった場合 |
| embedding 単価 | プロバイダ依存 | 参考: KCS 見積りで text 10 万 chunk ≈ $10 |

コストの記録は **cost_ledger (§9.1) が正**であり、attempt 単位の追記専用行として保存する —
retry の合算・月跨ぎの配賦・profile 変更やフォルダ退役後の履歴保全は、可変のガード行では
表現できないため ledger 側で成立させる。月次レポートは `GROUP BY strftime('%Y-%m', ts/1000,
'unixepoch')` で集計する。**単価を取得できないプロバイダ (embedding の従量非公開・client 側
キュー等) では cost_usd = NULL + cost_estimated=1 とし、月次集計は実額・推定・未取得を
区別して表示する** (「未取得」を「$0」に埋没させない)。請求の最終的な正はプロバイダ側であり、
ledger は「記録できた課金」— 突合には batch_job_id を使う (§9.1 — batch_job_id を保持済みの
attempt は結果が失効しても NULL + estimated で記帳されるため、失効窓の課金も台帳に残る)。

# 17. KCS 実装から移植した知見 (参照元)

| 本書の要素 | 移植元 |
| --- | --- |
| 派生物を content_hash に紐付け、path/commit に紐付けない | KCS chunk identity (docs/03-data-model.md §8.1、crates/kcs-index/src/chunking.rs) |
| 派生バイト列 hash を identity に使わない | KCS normalized_hash 不採用 (docs/03-data-model.md §5) |
| FTS5 external content + trigram + trigger 同期 | crates/kcs-index/src/fts.rs の本番実装 |
| チャンク境界の ATX 正準規則 | docs/04-pipeline.md §4.1 |
| 単一 multimodal profile 固定 / 非 multimodal 拒否 | docs/07-adapter-spec.md §5.3 / 03 §7 |
| embeddings 正 / vec0 導出の二層 | docs/04-pipeline.md §4.3 |
| text_hash ベースの embedding 内容共有 | docs/03-data-model.md §8.1 (embedding_hash) |
| bbox annotation 既定 ON (+25%) と markdown への materialize | docs/07-adapter-spec.md §5.2 / 03 §2.1 |
| モデル alias 禁止・版付き名 pin | docs/07-adapter-spec.md §6 (2026-07-03 実測) |
| 運用データ (job/課金) をフォルダ truth から分離 | docs/04-pipeline.md §5.1 (tasks) / §5.4 (cost-ledger) / docs/10-operations.md §3 (registry) |
| RRF (k=60) によるハイブリッド融合 | docs/05-runtime.md §1.3 |

# 18. 採用しない構成 (理由の記録)

元設計 §21 (**本書の現行 §21「明示操作」とは別番号** — files / file_heads / content_objects /
Next ポインタ / device テーブルの不採用) に加えて:

## 18.1 chunks への commit_hash 列 — 不採用

内容が変わらないコミットのたびに chunk 行の複製が必要になり、「同一内容は 1 回だけ処理・保存」という
内容アドレスの利点が壊れる。版との対応は file_versions の content_hash 逆引き (§12) で完全に解決できる。

## 18.2 chunks への vector 列 — 不採用

vector は内容単位 ((chunk_type, embed_hash) — §5.6 の正本キー) で N 個の chunk に共有される
(chunk N 行 : vector 1 本)。行に持つと
4 × dimensions bytes (768 次元の参考例で約 3KB) × 重複分の膨張と再利用の喪失を招く。また KNN を実行する vec0 は仮想テーブルであり、
どのみち別の物理テーブルが必須。ハイブリッドの両立は §11.2 の join で成立する。

## 18.3 file_versions / chunks へのバッチ状態の織り込み — 不採用

処理単位 (content_hash × tool / (chunk_type, embed_hash)) と行単位 (file×commit / 出現) のキーが一致せず、同じ処理の
状態が複数行に重複して矛盾する。また append-only の履歴正本に可変の運用列 (state/attempts/job_id) を
混ぜると commit_hash 検証の純度が下がる。「embed 済みか」の真実は embeddings の行の存在であり、
状態列は真実の二重化になる。

## 18.4 バッチ情報のフォルダ側 metadata.sqlite 管理 — 不採用

job_id はそのデバイスの API アカウントでしか意味を持たず、フォルダコピー先で回収不能なゴミになる
(可搬性の汚染)。**1 repository 内の複数対象を 1 job に積む**効率 (§10 — 1 job = 1 repository の
規則は維持)、コスト集計・レート制御がデバイス単位の関心事であることからも、アプリ配下 (§9.1) が
正しい置き場所。回収時の 2 DB 書き込みは §10 の順序規約 +
冪等クローズで実害を消す。

## 18.5 Mistral include_blocks によるチャンク分割 — 不採用

チャンク分割の正は保存済み Markdown (§7)。ベンダーの block 構造に依存すると、OCR 差し替え時に
分割器・テーブル・検索まで影響が波及する。bbox 座標は images[] から取得できる (image_meta)。

## 18.6 cross-repository の OCR 結果共有 (coalescing / fan-out) — 不採用

同一 content_hash のファイルが複数フォルダに存在しても、OCR・embedding は**各フォルダで独立に**
実行・保存する (batch_requests の PK が repository_id を含むのはこの帰結)。フォルダ自己完結
(層 1 = 真実、フォルダコピーだけで完結 — §2) を守るためで、フォルダ間に成果物の依存を
持ち込まない。per-folder の重複課金は意図的なトレードオフである。app 層で 1 回だけ OCR して
結果を各フォルダへ fan-out する最適化は将来可能だが、「app は真実を持たない」(規約 7 / 9) と
両立する設計が別途必要になるため MVP では採用しない。なお**同一フォルダ内**の重複は §10
ステップ 1 の DISTINCT と batch_requests の PK が防ぐ (こちらは採用済み)。
補足: agg_embeddings の device 横断 dedup (§9.2 — repository_id を持たない) は、同一原本が
複数フォルダにあっても各フォルダの OCR が独立かつ LLM 非決定であるため text_hash が一致する
とは限らず、実際に発火する頻度は限定的である (改善余地として記録 — 本節の不採用判断は不変)。

## 18.7 profiles 表の孤児掃除 — 意図的に行わない

profiles (§5.7) は (content_hash, tool_profile_hash) / embedding profile の record を保持するが、
参照する派生が全て消えた後の孤児行を能動的に削除する経路は**意図的に設けない**。profile record は
数十バイトで蓄積が無視でき、同一 profile の派生が再出現すれば再利用される (INSERT OR IGNORE)。
掃除機構を足すと「どの派生からも参照されない」判定のために全 markdown_documents / embeddings との
差集合を毎回計算する必要が生じ、得られるストレージ削減に見合わない。fsck の破損検出 (§13) は
孤児かどうかに関わらず全行を対象にするため、掃除の有無は正しさに影響しない。

# 19. 将来拡張と再検討の境界条件

- **中央集約 (元設計 §22)**: 層 3 の agg_* がそのまま同型拡張になる。(repository_id, commit_hash) キーと
  append-only レプリケーションは中央サーバへの集約でも同じ規則で動く
- **KCS 型の不変オブジェクト正本 (CAS) への移行を再検討すべき条件**: 次のいずれかが要件に入ったとき
  1. フォルダ丸ごとコピー / 汎用ファイル同期 (Dropbox 等) での履歴ごと共有を一級要件にする
     (可変 SQLite はコピー・同期中の破損リスクがある。immutable object は torn copy に強い)
  2. 履歴メタデータ自体の長期アーカイブ耐久 (数年単位で書き換えゼロのまま保全)
  3. AI Agent の引用の無人機械検証 (chunk 粒度の不変固定 = KCS の Evidence Pointer 相当)
  4. 複数端末の並行コミットを許した上で「その瞬間のフォルダ全体」の hash 固定が必要になる
     (LWW の時点再構築は後着の並行コミットで遡及変化するため、tree 相当の全体状態 hash が必要になる)
  その場合も本書の SQLite 群を検索インデックスとして残し、正本だけを不変オブジェクトに移す
  ハイブリッド移行が可能 (KCS がその構成の実装例)
- **規模の再考条件**: 本設計は個人〜小規模チーム規模 (数万ファイル・数十万 chunk / デバイス) を
  前提とする。batch_requests の累計行数や FTS 候補件数がこれを大きく超える運用が現れたら、
  reconcile の走査 (対象は state IN (0,3)。索引は collect と共用の部分 index
  `idx_batch_active` = state IN (0,1,3) — §9.1) の世代管理化、FTS 候補への
  上限 (**§11.2 で `:fts_cap` として導入済み** — 本節の旧称 `:k_fts` は同一物で bind 名は :fts_cap に
  統一)、集約置換のバックプレッシャ等を §16 の分散実行推奨と合わせて再設計する。
  また cost_ledger は追記専用で単調増加するため、大規模・長期運用では月次集計の
  マテリアライズや古い attempt 明細のアーカイブ (集計値は保持) を検討する

# 20. 変更検知 (スキャンと OS ファイル監視)

## 20.1 原則

- 検知は 3 層で構成する: **層 A = OS イベント** (稼働中の遅延短縮ヒント) / **層 B = スキャン**
  (正しさの基盤) / **層 C = 既存 tick** (§10 — 変更なし)
- **イベントが 1 個も届かなくても層 B だけで全機能が成立する** (検知が遅くなるだけ)。
  アプリ非稼働中の変更は起動時スキャンが吸収する
- OS イベントは「dirty な枝のマーキング」にのみ使う。**イベントの種別・パスからコミット内容を
  構成してはならない** (規約 11) — 全 API に「イベントが欠ける正規の条件」があるため
- 容量 (フォルダ合計サイズ) 等の集約値は検知手段として採用しない — ファイルシステムは集約値を
  保持せず (取得 = 結局全 stat walk)、同サイズ変更・増減の相殺・rename を見逃す。
  size は集約せず、段 0 / 段 1 の入力の一部として mtime と組で使う

## 20.2 OS 監視機能 (層 A)

| OS | API | 通知粒度 | 非稼働中の変更 | 主な弱点 |
| --- | --- | --- | --- | --- |
| macOS | FSEvents | ディレクトリ | sinceWhen で限定的に再生可 | イベント合体・型が曖昧 |
| Windows | ReadDirectoryChangesW | ファイル | 不可 | バッファ溢れで一括ロスト |
| Windows | USN Journal (NTFS) | ファイル | ジャーナル再生可 | ボリューム単位・wrap あり |
| Linux | inotify | ディレクトリ | 不可 | キュー溢れ・watch 数上限 |

- 実装は notify クレート (RecommendedWatcher が OS 別 backend を自動選択) +
  notify-debouncer-full を推奨。デバウンス後、対象フォルダを dirty 集合へ積む**だけ**にする
- FSEvents sinceWhen / USN 再生は「起動時スキャンの高速化オプション」であり、正しさを
  依存させない (必須にしない)
- 1 回の保存が 1 イベントではない (Office は一時ファイル + rename + ~$ロックファイル)。
  イベント列の解釈はせず、安定確認 (§20.5 手順 1) は層 B 側で行う

## 20.3 スキャン (層 B) — 3 段ドリルダウン

スキャンは **tick のステップ 0 として tick.lock の下で実行される** (§10 — 独立プロセスにしない)。
対象 = dirty フォルダ (即時。dirty 発生時は tick を早回し起動してよい) + 起動時全体 +
定期 (既定 1 時間)。**walk 対象 = watch_roots (§9.1) 配下 ∪ folders.root_path で、
重複排除する** — folders.root_path のうち**いずれかの watch_root 配下に既に含まれるものは
除外**し、watch_root 外へ移動された登録フォルダ (§20.4) だけを個別に足す。重複排除しないと
同一フォルダが 1 tick 内で 2 回 walk され、**§20.5 の「連続 2 回のスキャンで absent」= delete 確定
条件が同一 tick 内の数 ms に圧縮されて偽 delete を生む** (pending_deletes は 1 回目 absent で
UPSERT され、同 tick の 2 回目 walk が即 2 回目 absent と誤認する)。各対象を readdir + stat で
walk し、次の 3 段で絞り込む:

```text
段 0 (任意の最適化) — 階層 fingerprint (stat メタデータの再帰 Merkle):
  files_fp(D) = SHA-256(JCS([[name, mtime_ns, size_bytes], ...]))  -- 直下ファイル (ignore 後, name 昇順)
  dirs_fp(D)  = SHA-256(JCS([[name, dir_fp(child)], ...]))         -- 直下サブフォルダ (name 昇順)
  dir_fp(D)   = SHA-256(JCS([files_fp(D), dirs_fp(D)]))            -- bottom-up で計算
  (**`.folder-history/` は fp の入力から除外する** — 管理データの書込 (journal・metadata.sqlite・
   tmp) が毎 tick の偽変更検知にならないため。帰結として fork-journal の出現・変化は fp を変えない —
   下記スキップ例外の journal 検査がその検出を担う)
  (JCS 直列化での表現: 子の dir_fp / files_fp / dirs_fp は小文字 hex64 の JSON 文字列。
   **mtime_ns と size_bytes は 10 進文字列として直列化する** — RFC 8785 の数値は IEEE-754
   double であり、現在の epoch ナノ秒 (~1.7×10^18) は 2^53 を超えるため数値のままだと
   1 ns 差が同値に丸められ fingerprint が変更を区別できない。
   name はファイルシステムが返した名前をそのまま UTF-8 文字列として使い、Unicode 正規化は
   しない — デバイスローカルのヒントであり移植性は不要。昇順は UTF-8 バイト列比較。
   **非 UTF-8 のファイル名は fp の入力から除外する** — JCS string として表現できず、
   当該エントリは管理対象外 (§20.4 — status 表示のみ) のため fp が追跡する必要も無い)
  fp_cache との比較で:
    dir_fp 一致            → D 以下を丸ごとスキップ (DB 照会・後続処理ゼロ。**例外 — `.folder-history`
                             を持つフォルダ (登録有無不問 — 未完 fork の目標・conflict copy を含む) は
                             スキップ前に `.folder-history/fork-journal` の存在だけを検査する** —
                             journal は fp の入力外のため、これを怠ると §21.3 (b) の walk 検出が
                             fp 一致で恒久に殺され、PREPARED 直後・flag 記録前クラッシュの未完 fork が
                             検査されないまま残留する。fp 確定後にスキップ枝の**深部**へ journal が
                             出現する経路 (sync 伝播) は fp では観測できない — 検出上限 = deep-scan
                             周期 (下記補正、既定 週 1))
    files_fp のみ不一致    → 変更は D 直下ファイル → D が管理フォルダなら段 1 へ
    dirs_fp 不一致         → fp が不一致の子フォルダにのみ再帰 (両方不一致なら両方)
  fp_cache の更新は、**その枝の段 1〜2 の処理がすべて完了 (変更なしの確認、またはコミット確定)
  した後にのみ**行う。次のいずれかを含む枝は fp_cache を更新しない (= 確定させず、次回も
  段 1 へ落とす) — 先に更新すると次回 dir_fp 一致でスキップされ、保留した検証が永久に
  行われない:
    - 安定確認失敗・プレースホルダ skip・構文検証失敗の保留 (§20.5 — 有界スキップ確定前) 等で
      処理を持ち越したファイル
    - fork-journal を検出したが回復を完了できなかった枝 (一時読取不能の保留・damaged 表示中 —
      §21.3。fp を確定すると次回以降のスキップが journal 検査ごと回復を恒久に殺す)
    - racy 規則 (段 1) に該当した行 (stat 一致でも内容相違があり得る状態のまま fp を固定すると、
      同一秒内の上書きが weekly deep-scan まで見えなくなる)
    - pending_deletes (§20.5) に行が残るファイル (absent 2 回目の観測が skip で塞がれる)
    - name_collision / name_invalid (§20.5) の該当ファイルを含む枝 (恒久 status の再表示と
      衝突解消の検出が fp skip で塞がれる — 敗者の実体変化も観測し続ける)
  **`.folder-history` の存在チェック (管理フォルダの発見・規約 12 の repository-id 照合) は
  段 0 の fp スキップの対象外** — fp 一致で後続処理を省く場合も readdir 結果からこのチェックだけは
  常に行う (fp は ignore 規則で `.folder-history` を含まないため、cache 済みディレクトリへ
  `.folder-history` だけを持ち込む変化を fp では検出できない)
  fp_cache の孤児行 (消えたディレクトリ) は、watch_root / 登録フォルダの**完全 walk が成功した
  際に「今回観測しなかった配下 path の行」を DELETE** して掃除する (mark-and-sweep。
  ヒントなので削除は常に安全 — 放置すると絶対パス行が単調に蓄積する)

段 1 (必須) — scan_cache の行比較:
  (mtime_ns, size_bytes [, inode]) の**どれか 1 つでも**前回と違えば段 2 へ。
  **syntax_fail_count > 0 (§20.5 の有界スキップ未確定) の行も、stat 一致・非 racy に関わらず段 2 へ** —
  段 1 で止めると 2 回目以降の失敗観測が発生せず、3 回 / 24 時間の判定が恒久に進まない
  (bytes コミット確定でカウントは 0 へ戻り、この再入も終わる)。
  racy 規則: ファイルの mtime が **その行の verified_at (§9.1 — content_hash を検証した時刻)**
  と同一秒内またはそれ以降の行はキャッシュを信頼せず段 2 へ — 検証とファイル書き込みが
  同一タイムスタンプ粒度に入ると「stat 同一・内容相違」が起き得る (Git index と同じ罠)。
  比較は単位を揃えて秒へ切り捨てる: mtime_ns / 1e9 >= verified_at / 1e3 (verified_at は
  UTC ミリ秒 — §9.1)。racy に該当した枝は fp_cache を確定しない (段 0 の更新規則)。
  **例外 — mtime が現在時刻より未来の実体**: 時計修正まで恒久 racy となり毎 tick の段 2 (全量
  読取) が tick.lock を占有し続けるため、**段 2 の hash 照合が一致したら fp を確定してよい**
  (racy の趣旨は「stat 同一・内容相違」の見逃し防止 — hash 比較の一致はそれを包含する。以後の
  変更は mtime によらず size / inode / 次回 hash が拾う)

段 2 (真実) — content_hash:
  §20.5 の手順 (安定確認 → content_hash 計算 → 現在版 LWW と比較 → 差があればコミット) を
  実行し、scan_cache を更新する

補正 — deep-scan (低頻度、既定 週 1):
  fp_cache / scan_cache を無視して全ファイルの content_hash を再計算する。
  mtime 保存コピー (rsync -a 等)・FAT の 2 秒解像度・racy の見逃しを有界時間で補正する
```

**段 0 の物理制約 (誤解しやすい)**: walk (stat) 自体は毎回必要である。ファイルシステムは変更を
ツリー上方に伝播しない — ディレクトリの mtime は直下エントリの作成・削除・rename でのみ更新され、
**ファイル内容の上書きや孫の変更では変わらない**。したがって「Root の stat 1 回で変更の有無を知る」
手段は存在せず、walk を省けるのは層 A のイベントログだけ。fp が省くのは walk **後**の特定と
後続処理 (ファイル単位比較・DB 照会・hash 計算) である。

**実装順序**: 段 1 (scan_cache) を先に完成させる — 個人文書規模 (数万ファイル) なら SQLite の
全行比較で十分速い。段 0 (fp) は規模が問題になってから、層 A はさらにその後に足す。
どの段階でも正しさは変わらない (速さだけが変わる)。

## 20.4 監視 Root・フォルダ発見・除外

- **検知層だけがツリーを見る。履歴・チャンクの管理単位 (1 つの `.folder-history` = フォルダ直下のみ、
  サブフォルダは独立 — §1) は不変**。walk 中に `.folder-history` を持つフォルダ = 管理フォルダ
  (repository-id で folders と対応)。管理外フォルダの変更は無視する (新規管理フォルダの自動登録は
  しない — 登録は明示操作のみ)
- **watch_roots の正規化**: root_path は登録時に正規化 (realpath — symlink・`..`・FS の大文字
  小文字を解決した絶対パス) して保存する。正規化後に同一となる登録は no-op、既存 root と
  包含関係になる登録は拒否して status 表示する (同一実体の二重 walk と、大文字小文字違いの
  二重登録による偽 conflict を防ぐ)
- **walk の入力域**: エントリは lstat で判定し、**regular file のみ**を管理対象とする。
  symlink は辿らない (dir symlink の循環が段 0 の再帰を無限化する)。**加えて走査中の訪問済み
  (st_dev, st_ino) 集合でディレクトリの再訪を拒否する** — bind mount・junction・reparse point 等、
  symlink ではないディレクトリ別名による循環は symlink 非追跡だけでは防げない。**安定した
  (st_dev, st_ino) を提供しない FS (一部のネットワーク FS 等) では当該 watch_root を fail-closed
  (走査せず status 表示) とする** — 訪問済み判定の無効化は無限 walk、擬似値の同一視は別ディレクトリの
  取りこぼしになる。FIFO・ソケット・デバイス
  ファイルも読まない (read がブロックすると tick.lock を保持したまま停止する)。
  **対象外の型のエントリは、その論理名の観測としては absent と数える** (§20.5 の三値) —
  追跡中の regular file が同名の symlink 等へ置き換えられた場合、通常の delete 判定
  (連続 2 スキャン) で履歴に delete が記録される。skipped (存在扱い) は**読み取りの一時失敗**
  (安定確認失敗・権限エラー・プレースホルダ) に限る — 恒久的な型の不一致まで skipped にすると、
  旧内容が現在版として永久に検索に残る。対象外型の出現自体は status に表示する。
  **非 UTF-8 のファイル名**は論理名で表現できないため、どの論理名の観測にも数えず
  status 表示のみ (fail-closed — 追跡中の名前が非 UTF-8 名に rename された場合、旧論理名は
  absent になり通常の delete 判定に入る)
- **同一 repository-id の 2 箇所目を検出した場合** (フォルダの手動コピー等): folders の更新も
  スキャンも行わず **conflict として status 表示**し、ユーザーの明示解決 (片方を fork する —
  手順と意味論は §21.3。**fork = 履歴の再初期化**であり、旧 commits を新 ID で引き継ぐことは
  できない) を待つ。放置すると folders の 1 行を 2 つの物理フォルダが奪い合い、
  scan_cache が毎スキャン食い違って全 hash 再計算が続き、単一の sync_state カーソルの交互適用で
  片方のコミットが集約から永久に漏れる
- **repository-id の照合 (規約 12)**: コミット作成・replicate 等でフォルダ DB を開くたびに、
  `.folder-history/repository-id` を folders 行と照合する。不一致 (`.folder-history` ごとの
  差し替え等 — 可視ファイルの stat が不変なら段 0 の fp では検出できない) は conflict として
  中断・status 表示する
- **`.folder-history` だけが消失したフォルダ** (root と原本ファイルは現存): damaged として
  status 表示し、§9.3-d の削除処理へは進めない。復旧は「新 repository-id での明示再登録」
  (§21.1) のみを提示する (履歴は失われるが原本は無傷 — 位置づけ注記の「履歴使い捨て可」の範囲)
- フォルダの移動・削除: **起動時と定期 walk のたび**に folders の root_path を確認し、無ければ
  repository-id ファイルの内容一致で **watch_roots 配下**を再探索して root_path を更新する
  (更新契機は「再発見のたび」— 起動時限定ではない。§9.1 DDL コメントと同一規則)。
  **rebind の条件は「旧 root_path (パス) の不在」に限らない** — walk が folders の root_path と
  異なる位置で同一 repository-id を発見し、かつ**旧位置が当該 repo の実体でなくなっている**
  (パスごと不在 / marker 無し / 別 id — §21.1 の rebind 判定と同一) 場合も rebind する
  (旧パスが無関係のフォルダで再利用されたケースの自動化 — これが無いと健全な移動先が放置され、
  旧パス側の marker 不在が damaged 誤誘導になる)。**rebind の実体は §21.1 と共通** — root_path
  UPDATE + missing_since NULL 化 + **旧 root_path 配下の fp_cache 行の DELETE** (自動 rebind でも
  同じ。移動で walk の主体を失った旧領域は M&S が届かず、消さないと移動のたびに孤児 dir_fp が
  単調残留する)。**同一 id の実体が 2 箇所に現存する場合のみ**
  conflict (既存規則)。
  **fork_in_progress の old_id / new_id は再発見・root_path 更新の対象外**とする (§21.3) —
  fork 中断中にフォルダごと移動されると、除外が外れて未完 fork (履歴消去済み・id=old) が新パスで
  通常運用へ復帰し、空履歴に old_id で新規コミットを量産する。回復は §21.3 の journal 走査が担う。
  **再発見で root_path を新しいパスへ更新した場合、新 root_path 配下の fp_cache を無効化する**
  (§21.1 手順 3 と同じ理由 — cache 済みパスへ `.folder-history` ごと移動された場合、dir_fp 一致で
  初回スキャンが丸ごとスキップされ、以後の変更が deep-scan まで取り込まれない)。
  **watch_roots の外へ移動されたフォルダは再探索では見つからない** — root_path が有効なうちは
  §20.3 の walk 対象 (folders 起点) として検知が継続するが、旧 root_path が消えた場合は missing
  として status 表示し、ユーザーの再登録 (§21.1 — 現位置の指定) を待つ。いずれの場合も §9.3-d の
  削除処理へ即進まず**猶予期間** (既定 30 日) を置く (外付けドライブの一時切断を削除と誤検知
  しない)。**猶予の起点は folders.missing_since (§9.1 — 初回不在の観測で一度だけ設定し、再発見で
  NULL へ戻す)**。猶予満了 (now − missing_since >= 30 日) 後は **tick が §9.3-d を実行して退役し、
  status を missing → retired へ更新する** (実行者と契機を明示 — 満了後も status のまま残る
  宙吊りを作らない。満了前に再発見されれば猶予は解除される)
- ignore 規則 (fp・スキャン共通): `~$*` (Office ロック)、`.tmp` / `.crdownload` 等の一時拡張子、
  隠しファイル、`.folder-history` 自身
- クラウド同期フォルダ: プレースホルダ / オンデマンドファイル (Windows:
  FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS 属性 / macOS: dataless) は**既定でスキップし status に
  表示する** — content_hash 計算 = 全量ダウンロードの誘発を暗黙に行わない。
  ネットワークボリュームは stat 自体が高価なため、層 A と deep-scan 間隔の調整で補う

## 20.5 コミット作成処理 (元設計 §15 — 本書の現行 §15「設計規約」とは別番号 — を本書へ収録)

段 2 (§20.3) で変更が疑われたファイルは、次の手順でコミットになる:

```text
1. 安定確認: サイズと mtime を間隔を置いた 2 回の stat で一致確認する (書き込み途中を掴まない)。
   **open は symlink を辿らないフラグ (O_NOFOLLOW 相当) で行い、open 後に fstat で regular file で
   あることを再確認する** — lstat (§20.4 の型判定) と open の間に path が symlink へ差し替えられると
   フォルダ外のファイルを読んで履歴へ取り込む TOCTOU になる。**規約 12 の照合を通したフォルダに対する
   以降のファイル操作 (open / stat / rename) は、検証済み root の dirfd に相対して行う (openat /
   RESOLVE_BENEATH 相当)** — 照合と実操作の間に root の途中パス成分が別実体へ差し替えられる窓を塞ぐ
   (最終成分だけの O_NOFOLLOW では root 側の swap を防げない。restore §21.4・fsck §13 の書込・
   **fork §21.3 の書込 (手順 0 の journal・手順 2 の repository-id 書き換え)** にも適用 — fork も
   照合済み root を前提に書く操作であり同じ TOCTOU 窓に晒される)。
   **読み取りは 1 回のストリームで行い、SHA-256 の計算と tmp/ への書き込みを同時に行う**
   (手順 4 で保存する bytes と hash した bytes の同一性を構造的に保証する — hash 用と保存用に
   2 回 open すると、その間の書き換えで「hash A の名前に内容 B」が保存され得る)。
   読み取り前後の stat が同一であることを確認する。
   Word / PDF 等として構文的に開けるかの軽い検証を行い、壊れた中間状態はスキップして次回スキャンに回す。
   **ただしスキップは有界** — 同一 (size, mtime_ns, inode) のまま連続 3 回 (または 24 時間) 構文検証に
   失敗する実体は「書込途中の中間状態」ではなく安定した内容とみなし、**bytes のまま通常コミットする**
   (構文検証はスキップの根拠であって保存の条件ではない — 保存は bytes ベース (§1 の原則)。無期限スキップは
   安定して壊れた・暗号化された実体を恒久に保護外へ置き、その後の削除で内容が一度も守られない)。
   **カウントの実体は scan_cache に永続化する** — 対象の stat tuple ごとに syntax_fail_count /
   first_failure_at を記録し (§9.1 の DDL に定義 — 既存 DB は ADD COLUMN)、(a) stat tuple の変化・
   構文検証の成功・**bytes コミット確定 (有界スキップの発動)** で reset (発動後に段 1 の再入
   (§20.3) を終わらせる)、(b) **一時
   読取失敗 (EIO・AV ロック) と安定確認失敗はカウントしない** (構文検証を実施できた回だけ数える —
   混ぜると一時障害の混入で誤って bytes コミットに到達する)、(c) 24 時間の起点 = first_failure_at。
   tick は非常駐のためメモリ計数では再起動のたびに初回化し、有界化自体が実装不能になる
2. 変更判定: content_hash (手順 1 のストリームで計算済み) を、当該ファイルの現在版 (LWW) の
   content_hash と比較する。同一 → 実体も履歴行も作らない (tmp は破棄) / 異なる → create または update。
   **delete の判定は「現在版 LWW の生存ファイル名集合 − 今回 walk で観測した集合」を正本とする**
   (scan_cache は高速化ヒントであり削除判定の根拠にしない — cache 全損時に削除を見逃すため)。
   walk の観測は readable / skipped / absent の三値で扱い、**skipped (プレースホルダ・
   安定確認失敗・読み取りエラー) は「存在」として数えて delete にしない** (誤 tombstone の防止。
   skipped は次回スキャンで再処理される)。
   delete の**確定**にはさらに 2 条件を課す: (a) **その walk が完全に成功していること** —
   readdir / stat が 1 件でもエラーを返したフォルダは delete 判定・scan_cache 更新・fp_cache
   更新をすべて見送る (不完全な列挙は「絶対不在」を証明しない — ネットワーク FS の途中 EIO で
   存在ファイルへ偽 tombstone を打たない。**恒常的に stat が失敗するエントリが 1 つあると、
   そのフォルダの delete 確定は停止し続ける** — 偽 delete 防止を優先する意図されたトレードオフ。
   walk 不完全は status に表示し、解消はユーザーの対処に委ねる)、(b) **連続 2 回のスキャンで absent** であること
   (Office の保存は一時ファイル + rename の過程で正式名が瞬間的に消えるため、1 回の不在の
   即 delete は偽 delete / create の履歴を量産する)。
   **absent の継続は pending_deletes (§9.1) に永続化する** — 1 回目の absent を観測した完全
   walk で行を UPSERT し、readable / skipped の観測で行を DELETE する。delete の確定 =
   「pending_deletes に行が存在する状態で、後続の完全 walk が再び absent を観測し、**かつ
   now − first_absent_at >= 最小不在時間 (既定 30 秒)**」。回数条件だけでは dirty 早回し tick
   (§10 — 100ms 間隔もあり得る) が Office 保存の一時消失窓 (一時ファイル + rename の数百 ms) の
   中で 2 回 walk して偽 delete + 偽 create を作る — 「連続 2 回」は時間経過を含意しないため、
   時間条件を明示する。時間差は wall clock で測るため時計の急変 (NTP 前進等) で誤って満了し得る —
   **delete コミットの直前に対象名を最終確認し (§20.4 と同じ lstat + O_NOFOLLOW + regular 判定。
   対象は下記「論理名 → 物理名の解決」で得た raw エントリ)、readable な regular file なら確定を
   中止して pending をリセットする** (安価な最終防衛 — 時計急変下でも「実在ファイルへの偽 delete」
   を防ぐ。確認直後〜コミットの間の再作成という残余の窓は原子的に塞げないが、次 walk の create が
   是正する自己修復の範囲)。**「存在すれば中止」の素朴な stat は不可** —
   §20.4 は regular 以外の型 (directory / symlink / FIFO への置換) を absent と数えて delete 対象に
   するため、単純な存在チェックだと置換先の実体を「存在」と見て delete を永久に中止し、旧内容が
   現在版として残り続ける。skipped (一時読取失敗) は従来どおり保留、対象外型・不在は absent のまま確定する。
   tick は常駐せずスキャンはプロセスを跨ぐため、メモリ上の連続カウントでは
   「2 回目」を判定できない。pending_deletes はヒント側 (app) にあり、喪失してもカウントの
   やり直し (確定が遅れる) になるだけで削除を見逃さない。pending 中の枝は fp_cache を確定しない
   (§20.3)。**残留掃除**: 手順 5 (delete コミット) 成功後・手順 6 (cache 掃除) 前のクラッシュは、
   当該名が LWW 生存集合から消えているため以後 absent 候補にならず、pending 行が永久残留して
   fp 確定も塞ぎ続ける — **tick ステップ 0 の冒頭で「現在版 LWW が delete のファイルの
   pending_deletes / scan_cache 行」を冪等削除する** (手順 6 の取りこぼしの回収)。
   **file_name の正規化 (全層共通)**: ファイル名は **NFC 正規化した論理名**として扱い、
   file_versions への保存・LWW 比較・walk 観測集合との照合・scan_cache のキーのすべてで
   同じ論理名を使う (§4.1 の NFC は直列化専用ではなく、この論理名規則の一部)。macOS 等の
   readdir は NFD を返すため、正規化を怠ると同一ファイルの履歴が NFC / NFD の 2 系列に分断され
   偽 delete + 偽 create が量産される。
   **論理名 → 物理名の解決 (逆方向・全操作共通)**: 論理名を対象に**個別のファイル操作**を行う
   場合 (delete 確定直前の最終確認・restore の in-place 宛先 §21.4・fsck の working copy 読取
   §13)、論理名をそのまま path として open / stat / rename **してはならない** — NTFS / ext4 等は
   lookup を Unicode 正規化しないため、NFD 物理名の実体に対して NFC 名でアクセスすると「不在」に
   見え、書込は**別エントリを新規作成**して二重実体 (name_collision、restore 結果が採用規則で
   敗者になり得る) を作る (macOS APFS は API が正規化非依存 lookup を行うため顕在化しない)。
   解決規則: **検証済み root の readdir 列挙から、walk と同じ規則 (NFC 正規化 + case 折り畳み +
   衝突時の採用規則) で当該論理名に対応する raw エントリを求め、その raw 名を操作対象にする**
   (**採用規則は本節の case 規則 — 初出表記固定・BINARY 一致優先・UTF-8 バイト列昇順 tie-break —
   と同一の実装を共有する**。walk と resolver で独立に実装すると採用が食い違い、name_collision の
   収束結果が呼出点ごとに分かれる)。
   対応する raw エントリが無い場合 — delete 最終確認: absent として確定 / restore: 新規作成
   (NFC 表記で作成してよい — 既存実体が無い以上どれとも衝突しない) / fsck: working copy 喪失として報告。
   **残余の TOCTOU 窓 (3 呼出点共通)**: 解決 (readdir) と実操作の間に外部プロセスが競合する
   別正規化形の実体を作る狭い窓は原子的には塞げない — 生じた二重実体・変化は**次回 walk が
   name_collision / update として検出・収束させる** (delete 最終確認の「自己修復の範囲」と同じ
   許容を restore / fsck にも適用する)。restore は rename 直前に解決先を再 lstat して窓を
   狭める — **in-place restore ではこれを義務とする (§21.4: 保全時の (size, mtime_ns, inode) と
   不一致なら中止)。delete 最終確認・fsck では任意の強化**。
   **case 規則 (デバイスローカル)**: 走査ボリュームが case-insensitive (macOS APFS / Windows
   NTFS 既定) の場合、論理名の**同一性判定**は case-insensitive で行い、**保存する論理名は
   「その系列の初出時の表記」に固定する** — walk が readdir 表記と case 違いで一致する既存
   file_versions 系列を見つけたら、**新しい readdir 表記ではなく既存の保存済み論理名を
   そのまま使い続ける** (rename の表記変更は履歴に取り込まない。FS 自身が同一ファイルと
   みなす変更のため実害はない)。**ディレクトリ単位の case 感度 (NTFS の per-directory flag・ext4
   casefold 等) への備え**: 同一ディレクトリ内に case 違いのみで一致する raw エントリの併存を
   検出したら、ボリューム属性に関わらず**当該ディレクトリは case-sensitive として扱う** (併存の
   事実が最強の証拠 — ボリューム判定だけだと 2 実体を同一系列へ折り畳み、別ファイルの履歴を
   混線させる)。**この override は sensitive 方向のみ**に効く — 逆向き (case-sensitive ボリューム内の
   casefold ディレクトリ — ext4 casefold 等) は「併存できない」こと自体が性質のため、併存という証拠が
   原理的に発生しない。属性を照会できるプラットフォームでは dir 属性 (FS_CASEFOLD_FL 等) を判定に
   優先してよい。照会不能な環境では case-only rename が delete + create の 2 系列へ分裂するが、
   objects と履歴の喪失は無い (既知の近似挙動として許容)。**折り畳みで一致する既存系列が複数ある場合** (sensitive
   ボリューム上で分裂した系列 — 下記 — を insensitive ボリュームへ移動した場合) は、**readdir
   表記と BINARY 一致する系列があればそれを、無ければ保存論理名の UTF-8 バイト列昇順で最初の
   系列を採用して継続する** — 採用されなかった系列は当該実体に追随せず、以後の walk で通常の
   delete 確認へ進む (実体の統合を反映した意図された遷移。決定論的 tie-break が無いと採用が
   実装・スキャン順に依存し、実体の無い系列が現在版のまま恒久残留し得る)。
   「判定だけ折り畳み、保存は readdir 表記」の方式は**不可** —
   保存表記が揺れると (a) file_versions の複合 FK (file_name, previous_commit_hash) が BINARY
   照合で参照先 ("Report.pdf", C1) を見つけられず INSERT が FK 違反で失敗する (**SQLite の
   ON CONFLICT (OR IGNORE) は FK 違反には適用されない** — 「黙って欠落」ではなくコミット Tx が
   毎スキャン音を立てて失敗し続ける)、(b) §11.1 の PARTITION BY file_name が raw 比較で同一ファイルを 2 系列に分割して
   現在版が二重化する。保存表記の固定により、DB 内の比較 (FK / LWW SQL / PARTITION) はすべて
   BINARY のままで正しく、折り畳みは walk 照合の入口 1 箇所に閉じる。
   case 感度は**走査時のボリューム属性から判定する** — 「フォルダごと」の固定はそのボリューム上に
   ある間の話であり、**フォルダ移動 (rebind §21.1 / 再発見 §20.4) 後は新ボリュームの属性で再判定
   する** (保存済み論理名は不変。insensitive → sensitive への移動で case 違いの複数実体が現れた
   場合、折り畳みが無効になるため既存系列は BINARY 一致する 1 実体に追随し、他は新規系列 =
   create になる — 系列の分裂であってデータ喪失ではない)。折り畳まないと
   "Report.pdf"→"report.pdf" の rename が偽 delete + 偽 create になる
   **file_name の検証 (fail-closed)**: 論理名にパス区切り (`/` `\`)・`..`・単独 `.`・絶対パス・
   NUL・空白のみ・`.folder-history` を含むものは**管理対象にしない** (name_invalid + status)。
   管理対象はフォルダ直下の base name のみ (§1) なので本来こうした名前は生じないが、共有された
   細工 `.folder-history` の file_versions が working ツリー外を指し restore (§21.4) が root_path
   外へ書き込む path traversal を、保存側と restore 側の両方で塞ぐ
   **NFC / case 折り畳みで衝突する複数の物理ファイル** (稀) は、**物理名の UTF-8 バイト列昇順で
   最初の 1 件だけを採用**し、残りに専用ステータス **name_collision** を付けて表示する
   (衝突集合の増減 — 敗者の削除・改名 — で採用実体が入れ替わった場合、同一論理名への update が
   1 回記録される。これは実体の変化を反映した意図された遷移であり、readdir 順の非決定による
   毎スキャンの揺れとは異なる)
   (readdir の列挙順に依存させない — 順序が非決定だと採用実体がスキャンごとに揺れ偽 update を
   量産する。§4.1「同名 1 件のみ」を fail-closed で守る)。**name_collision は「読み取りの一時
   失敗」= skipped (§20.4) とは別の恒久ステータス**として明示する — skipped に混ぜると §20.4 の
   「skipped は一時失敗のみ」と矛盾し、敗者の変更が黙って追跡外になる
3. Commit Hash 計算: そのフォルダで確定した全変更を 1 コミットにまとめ、§4.1 の JCS 直列化で
   commit_hash を計算する
4. 実体保存: 手順 1 で書いた tmp/ のファイルを fsync → content_hash の正式パスへ atomic rename →
   **格納ディレクトリ (objects/sha256/<プレフィックス>/) を fsync する** (新規プレフィックス
   作成時はその親も)。ファイルの fsync だけでは rename のディレクトリエントリが電源断に
   耐えない — 「metadata は commit 済み (synchronous=FULL)・object 名が消えた」という規約 6
   違反の状態が生まれ得る。この規則は §6 の派生・画像保存を含む **objects/ への全書き込み**に
   適用する。同一 content_hash の実体が既に存在すれば再保存しない (tmp は破棄)。**破棄の前に既存
   実体の bytes を読み SHA-256 を再計算して照合する** — 一致なら破棄、**不一致 (bit-rot) なら tmp で
   既存実体を置換して修復し fsck へ報告する** (検証なしの破棄は「破損 object を参照する新しい履歴行」を
   作り、tmp が持つ正しい bytes という唯一の修復機会を捨てる)
5. metadata.sqlite 更新 (実体保存の後 — 規約 6 の書き込み順序):
     BEGIN IMMEDIATE;
     INSERT OR IGNORE INTO commits (...);           -- 同一 commit_hash は重複登録しない
     INSERT OR IGNORE INTO file_versions (...);     -- 変更されたファイルの行のみ
     COMMIT;
6. scan_cache を更新する: 存在するファイルは (mtime_ns, size_bytes, inode, content_hash,
   verified_at = now) で UPSERT し、**delete を記録したファイルの行は DELETE する**
   (pending_deletes の該当行も同時に DELETE する — 確定済みの保留を残さない。
   孤児行の蓄積防止 — 正しさには影響しないが掃除はここで行う)
```

**コミット入力の決定規範** (§4.1 commit_record への対応 — 1 回のスキャン結果から一意に決まる):

```text
parent_hash          = そのフォルダの最新コミット (created_at DESC, commit_hash DESC の先頭) の
                       commit_hash。コミットが 1 つも無ければフィールド省略
previous_commit_hash = 当該 file_name の現在版バージョン (LWW 先頭。delete 行を含む) の
                       commit_hash。当該 file_name の行が 1 つも無ければ省略。
                       delete 後の再作成は event_type=1 (create) とし、previous_commit_hash は
                       その delete 行の commit_hash を指す
created_at           = max(スキャン確定時刻 (UTC ミリ秒), そのフォルダの最新コミットの
                       created_at + 1)。1 コミット内では単一値。**単調クランプは必須** —
                       無いと時計後退中の編集が LWW で旧版に負け続け「現在版が古いまま +
                       同内容コミットの量産」が起き、§9.3-a のカーソルからも脱落する
                       (generated_at §5.3 と同型の防御)
message              = 常に省略 — 手動コミット (message 付き) の明示操作は現行カタログ (§21) に
                       存在しない (提供するなら §19 の将来拡張として §21 に入力・排他・失敗回復を
                       定義してから)。「明示操作時のみ任意指定」という到達不能の分岐を残さない
event_type           = 手順 2 の判定 (1=create / 2=update / 3=delete)
```

**時計の大幅な前進はクランプでは直せない** — 誤って未来時刻 (年単位で進んだ時計等) でコミット
すると、時計を直した後も latest+1 の未来系列が続き、時点指定検索 (§11.1 C) と履歴表示が実時刻と
乖離し続ける。now が「そのフォルダの最新コミット created_at − 設定閾値 (既定 72 時間)」より
過去の場合 (= 過去に未来時刻で汚染された兆候)、コミットは latest+1 で続行しつつ status に
警告する (可用性優先 — 停止はしない)。修復手段は履歴の再初期化 (§21.3 と同型) のみとする —
created_at の書き換えは全 commit_hash の再計算になるため提供しない (「履歴使い捨て可」の範囲)。

# 21. 明示操作 (操作カタログ)

本文の各所で「明示操作」「明示解決」として参照される操作の入力・手順・失敗回復を 1 箇所に
固定する。**いずれも tick.lock を取得して実行する** (tick と並行しない)。**取得は tick の
即終了 (§10) とは異なり、明示操作は最大 N 秒ブロッキングで待つ** (N = 設定値、**既定 30 秒** —
0 は即失敗、上限は設定で制限。単位は秒) — 対話操作を進行中 tick との
競合で即失敗させないため。タイムアウト時は「tick 実行中」を示す再試行可能エラーとして
再試行を促す (自動リトライはしない)。
**各操作は tick.lock 取得直後に、まず §21.3 の fork 回復 (fork_in_progress / journal の走査) を
完了してから本体を実行する** — lock は同時実行しか防がず、未完 fork を跨いで直列実行された操作は
後の回復に反転される (例: ID_WRITTEN クラッシュ後の unregister(old) が、次 tick の回復手順 3 の
folders(new) INSERT で取り消される)。回復を先行させれば操作は常に回復後の状態を入力にでき、
別 fork の起動が単一の fork_in_progress を上書きすることもない (**唯一の例外 = 破損 journal の
明示解決** — 回復が完了し得ないため、§21.3「journal の破損」の解決経路だけはこのゲートを
bypass する)。UI / CLI の形は
実装裁量だが、操作の効果はここが正本。

## 21.1 管理開始 (register)

入力: 対象フォルダの絶対パス。

```text
1. パスを正規化する (§20.4 の realpath)。**対象の `.folder-history/` に fork-journal (§21.3) が
   存在する場合は先に処理する**: 有効 (digest 一致) なら §21.3 の回復を完了してから本手順を
   判定する — watch_roots 外へ移動された未完 fork はここが検出点になる (素通しで register すると、
   後の walk の journal 走査による回復が register 後のコミットを反転する)。**破損 (読めたが digest
   不整合・構文不正) なら §21.3「journal の破損」の明示解決のみを提示する。一時的に読めない
   (AV/EDR ロック・EIO) は破損と区別して無変更で保留 + status** — 規約 12 の「読めない ≠ 壊れて
   いる」を journal にも適用する (区別しないと、有効 journal の一時ロックが履歴破棄 (明示解決) へ
   誤誘導される)。
   対象の `.folder-history/` の**存在**と**可読性**を分離して
   扱う (§13 の「読めない ≠ 壊れている」を register にも適用): **`.folder-history/` が存在するが
   一時的に読めない (AV/EDR ロック・マウント断・一時 EIO) 場合は、新規初期化にも再発見にも進めず
   無変更で保留・status 表示する** — 存在を見落として手順 2 へ進むと既存履歴を空 DB + 新 id で
   破壊的に置換する。対象に `.folder-history/` が既に存在して**開ける**なら「再発見」: その
   repository-id を読み、
   - folders に同 repository_id が別の root_path で登録済みで、**その旧 root_path が現存し
     同一 repository-id の `.folder-history` を実際に持つ**場合のみ **conflict + status** とする
     (同一 repo の実体が 2 箇所 — コピーの持ち込み等で元の追跡を黙って失わせない)
   - 旧 root_path が不在 (missing — フォルダ移動後の明示再登録) なら **rebind**: folders の
     root_path を新パスへ UPDATE + missing_since を NULL へ戻す + **旧 root_path 配下の fp_cache 行を
     DELETE する** (§21.5 の watch_root 解除と同じ理由 — 移動で walk の主体を失った旧領域の dir_fp は
     誰にも掃除されず永久残留する) (§20.4 の missing 回復はこの経路 —
     「別 root_path 登録済みは常に conflict」にすると missing からの回復が自己衝突して不可能になる)
   - **旧 root_path は現存するが別の実体 (異なる repository-id / `.folder-history` 無し) に
     なっている場合も rebind とする** — 旧位置は当該 repo ではもう無い (移動後に別フォルダが
     同パスへ作られたケース。conflict は「同一 id の実体が 2 箇所」の場合に限る)。**この分岐の
     rebind action も上と共通** (root_path UPDATE + missing_since NULL + 旧 root_path 配下の
     fp_cache DELETE)。旧位置が
     一時的に読めない (マウント断等) 場合は判定を保留して status 表示
   - **対象 root_path が別の repository_id の folders 行に既に登録されている**場合 (旧 repo が別 id の
     実体へ置き換わったのに旧行が残存) は、その旧行を先に §9.3-d で退役してから本 repository-id を
     INSERT する — root_path は 1 実体 1 行。退役しないと Rold / Rnew の 2 行が同一 root_path を指し、
     Rold の tick が規約 12 で恒久の偽 conflict になる (damaged 再登録の退役規則 (下記) と同型)
   - 未登録なら folders へ INSERT。いずれも手順 3 の fp_cache 無効化を行い終了
     (repository-id が登録済みの証拠 — 規約 9)
2. 新規初期化: repository-id (UUIDv7) を生成し、.folder-history/tmp/ 経由で repository-id ファイルと
   空の metadata.sqlite を作成 → ディレクトリ fsync (§20.5)。**embedding_vec は profile 確定まで
   作らない** — §5.6 テンプレートの <dim> が未解決のため。§10 step 3 冒頭の次元検査 (§8-c) が
   初回に vec 不在を検知して作成する。それ以外の §5 テーブル + user_version は作成する
3. app Tx: folders へ INSERT。**対象パス配下の fp_cache 行を DELETE する** — watch_root 配下を
   register した場合、過去 walk の dir_fp が残っていると次 tick の段 0 が「変更なし」でスキップし
   初回コミットが作られない (deep-scan まで検知されない)。無効化で初回は必ず段 1〜2 へ落ちる
4. 直後の tick ステップ 0 が初回スキャンとして全ファイルをコミットする (特別な初回処理は無い)
```

失敗回復: 手順 2 の途中クラッシュは不完全な `.folder-history` を残す — metadata.sqlite が
**構造的に不正 (読めるが user_version が期待外・スキーマ破損)** の場合は damaged (§20.4) と同様に
扱い、tmp 掃除の後に最初からやり直す (原本ファイルには一切触れないため再実行は常に安全)。
**一時的に読めないだけ (ロック・EIO) の既存 store は damaged にしない** — damaged 誘導は §20.4 の
「新 repository-id 再登録」= 破壊的再初期化に繋がるため、一時失敗を構造破損と混同せず手順 1 の保留へ倒す。**damaged からの新 repository-id
再登録では、同一 root_path を指す旧 folders 行 (旧 repository_id) があれば先に §9.3-d 相当で
退役してから手順 2 へ進む** — 残すと旧 id 行が walk 対象に残り、実フォルダの新 id と規約 12 照合で
永久に偽 conflict になる。

## 21.2 退役 (unregister)

入力: repository_id。フォルダ実体と `.folder-history/` は削除しない (履歴を残したまま管理だけ外す)。

```text
1. in-flight の batch_requests (state IN (0, 1)) にプロバイダ cancel を試みる。
   **cancel が確定した行は state=3 (error='cancelled') + attempts = 上限 + completed_at で terminal 化し、
   batch_job_id 非 NULL なら「terminal 化時の課金記帳」(§9.1) と同じ冪等記帳を同一 Tx で行う** (実行途中の
   cancel は部分課金され得る。terminal 遷移なしの「削除対象」だと state=1 のまま token sweep の
   「全行終端」条件に入れず、intent_token が永久残留して削除ガードと恒久矛盾する。**attempts = 上限は
   submit_rejected と同じ規律** — cancel はユーザーの停止意図であり、遷移表の「成果なし・state=3・
   attempts < 上限 → 再投入」の対象にしない。cancel Tx と folders 退役 Tx の間のクラッシュや後の
   再登録があっても自動再課金せず、復帰は明示 retry のみ。**この規範は行が存在する間のもの** —
   行が削除条件 (段階遷移) へ到達して消えた後の再登録は、§9.1 detached 注記と同じ「有界・ledger
   追跡済みの意図されたコスト」として通常投入に戻る) — これで下記 2 の
   削除条件へ段階遷移で到達する。**batch_job_id NULL かつ intent_token 非 NULL の行は「cancel 確定」に
   してはならない** — provider へ cancel を届ける handle が無く、確定扱いは相 2b 完了・相 3 前
   クラッシュで実在し得る job を未照合のまま記帳なしで閉じる。この行は「確定できない行」として
   下記 2 の detached 例外に回す (detached (b) の三値照合が found なら採用・記帳する)。
   その他の確定できない行も同様に detached 例外に回す
2. app Tx: §9.3-d と同一の削除 (agg 4 表 + sync_state + scan_cache + pending_deletes +
   配下 fp_cache) + folders から DELETE。**batch_requests は「(cancel 確定 or terminal (2/3))
   かつ (upload_id IS NULL or upload_cleaned=1) かつ intent_token IS NULL」の行だけ削除し、
   それ以外 (cancel 未確定の in-flight・upload 未清掃・**token 残存 = close 後の (b')/token sweep の
   記帳・掃除が未完了** — §9.1 detached 削除条件と同一) は detached として残す** — 消すと課金され得る job を追跡できず、
   直後の再登録が同一 target を再投入して二重課金し、未清掃 upload の handle も失って TTL まで
   機密残留する。detached 行の処理は **§9.1 の
   「detached 行の処理規範」に従う** (課金追跡専用 — folders.root_path が消えた時点で成果の
   書込先は無いため、collect は結果 payload を破棄して cost_ledger 記帳と終端遷移のみ行う。
   **state=0 も §9.1 の client / server 分岐に従う** — client (batch_job_id 非 NULL) は terminal 記帳 +
   state=3 (error='detached') + completed_at で terminal 化 — **削除は本項の 3 条件 ((cancel 確定 or
   terminal) かつ upload 清掃済み (or 無) かつ intent_token IS NULL) の段階遷移に委ねる (§9.1
   detached (a) と同一。「記帳後に即削除」ではない)**、server (NULL) は intent_token で job 一覧を照合し実在なら state=1 detached へ採用・
   照合不能なら保持。**「state=0 は即削除」は不可** — 相 2b 完了・相 3 前クラッシュの state=0 は job
   作成済みであり得、即削除すると課金と upload handle を落として再登録が同一 target を二重課金する)。
   再登録 (21.1 再発見) が先でも submit は detached の state=1 を「回収待ち」と見て二重投入しない。
   cost_ledger は削除しない (§9.1)
```

再登録は 21.1 の「再発見」経路で復帰し、レプリケーションがカーソル NULL から全量再同期する。
**注記**: active watch_root 配下のフォルダを unregister しても、`.folder-history` が残る限り次の walk が
marker (= 規約 9 の登録証拠) で再発見・再登録する — unregister は「今の管理を外す」であり再発見の恒久
抑止ではない (退役事実の非永続は規約 7-f の明示的トレードオフ)。ただし**完成済みの派生が保持されている場合**、再 OCR / re-embed は派生保持・
content-addressed のため発生せず、再同期は集約キャッシュの再構築に留まる (**detached が payload を
破棄した行・cancel された行は成果なしのため、再登録後は通常投入として再課金され得る** — 上記の
意図されたコストの注記どおり。無条件の「発生せず」ではない)。恒久的に外すには対象を
watch_root 外へ移すか、移動後に unregister する。

## 21.3 fork (repository-id の再生成)

§20.4 の同一 repository-id conflict、または「履歴を捨てて再開」の解決手段。**fork = 履歴の
再初期化**であり (commit_hash は repository_id を直列化入力に含む — §4.1 — ため旧履歴を新 ID で
引き継ぐことは原理的に不可能)、派生台帳と objects は内容アドレスで repository に依存しないため
保持する (再 OCR・再 embed 不要)。**耐久手続きとして tick.lock 下で次の順に実行し、各境界の
クラッシュから再開可能にする**:

入力: **fork する対象フォルダの絶対パス** (repository_id ではない — conflict では同一 id の実体が
複数箇所にあり、id だけでは「どちらを fork するか」を耐久的に特定できない)。**パスは開始時に
realpath 正規化して固定する** — 非 canonical 表記 (`/a/../b`・symlink 別名) のまま比較すると、
手順 3 の「folders[old_id].root_path と一致するか」の判定が誤り、tracked 実体を非追跡コピーと
誤分類して生存側を wipe し得る。

```text
0. **fork journal を層 1 に書く**: **journal 作成の前に、folders[old_id] 行が存在するが root_path が
   対象 realpath と不一致 (移動済み・未 rebind) の場合は、§20.4 の rebind 判定 (旧位置が当該 repo の
   実体でなくなっているか) を先に完了する** — 未 rebind のまま進めると移動済みの追跡フォルダが
   was_tracked=false に誤判定され、手順 3 が旧 root_path の folders 行を退役せず残す (旧位置が
   別実体に再利用されると恒久の damaged 偽表示)。同一 id の実体が 2 箇所に現存する conflict の
   非追跡側 fork は意図どおり was_tracked=false (生存側に触れない)。
   対象フォルダの .folder-history/fork-journal へ **版付き canonical
   record** {v: 1, old_id, new_id (この時点で採番), realpath, was_tracked (開始時点の
   folders[old_id].root_path 一致判定), **started_at (fork 開始時刻 — stalled 猶予の起点。app 側
   flag と二重化し、app.sqlite 全損後も journal 単体で stalled 判定を可能にする)**, phase} を
   JCS 直列化し、**末尾に SHA-256 digest を付す** (バイト形式は固定:
   **UTF8(JCS(record)) ‖ LF ‖ lower_hex64(SHA-256(UTF8(JCS(record)))) ‖ LF、BOM 禁止** —
   §20.3 の fp 表現と同じ規律。区切り・hex 大小・終端を固定しないと、適合実装・版の間で
   正常な journal を damaged 誤判定し得る) —
   {old_id, new_id, was_tracked} は構文上有効なまま**部分破損・意図しない書換**が起き得るので、回復時に digest を
   再計算・照合し不一致は damaged 扱いにする (下記「journal の破損」。**悪意ある改竄への耐性では
   ない** — 書込権限を持つ主体は digest ごと再計算できる。目的は部分書込・bit-rot の検出)。これを **tmp へ書き → fsync →
   atomic rename → dir fsync** (§20.5 と同じ規律 — journal 自体が耐久でないと回復の根拠にならない) で
   永続化する。phase は各手順の完了時に同じ安全書込で進める
   (PREPARED → HISTORY_CLEARED → ID_WRITTEN → APP_DONE)。
   journal を app 側でなく層 1 に置くのは、(a) 対象パスの特定を journal の所在自体が担う、
   (b) app.sqlite 全損を挟んでも「fork 中断」と「空履歴の通常 repo」を区別できるようにするため。
   app 側には fork_in_progress = (old_id, realpath) を軽い印として記録し (**保存先 = app_config の
   'fork_in_progress' key、JSON {old_id, new_id, realpath, started_at}** — §21 前文の tick.lock 直列化 +
   毎 tick 冒頭の回復完了により同時に高々 1 件で、単一 key で足りる)、**この realpath の
   実体のみを tick の全ステップ (scan / submit / collect / replicate) から除外し、規約 12 の
   conflict 判定も抑止する** — 除外・抑止の粒度は (old_id, realpath) の**パス単位**であり
   old_id 単位ではない (id 単位だと conflict の非追跡側を fork する間、生存側の追跡まで凍結する)。
   照合だけの抑止では fork 中の通常 tick が旧 id で新規コミットを作る
1. metadata.sqlite (フォルダ側 1 Tx): 履歴を初期化する → phase = HISTORY_CLEARED。
   PRAGMA defer_foreign_keys = ON; BEGIN IMMEDIATE;
     DELETE FROM commits;          -- file_versions は FK CASCADE。defer は COMMIT 時検査へ遅延する
                                   --  防御的指定 (自己参照 FK (file_name, previous_commit_hash) の
                                   --  CASCADE 削除順は SQLite の実装詳細で、即時検査でも成功する
                                   --  実装・版があるが、順序保証は仕様に無いため defer で固定する)
   COMMIT;
   派生台帳 (markdown_documents / chunks / embeddings / profiles) と objects/ は保持する
2. repository-id ファイルを journal の new_id へ**安全書込で**置き換える → phase = ID_WRITTEN。
   ファイル fsync だけでは電源断で壊れた UUID 文字列が残り damaged にも conflict にも該当しない
   未定義状態になる
3. app Tx: **was_tracked (journal に固定済み) の場合のみ**、旧 repository_id の app 行を退役する
   (folders の旧行 DELETE + agg 4 表 + sync_state + scan_cache + pending_deletes + 配下 fp_cache を
   DELETE — **folders を消すことを明示する**: 残すと旧 root_path × 新 id の規約 12 照合が恒久の
   偽 conflict になる。batch_requests は §21.2 と同一規則 — 「(cancel 確定 or terminal) かつ upload 清掃済み (or 無)
   かつ intent_token IS NULL」のみ削除し、それ以外 (in-flight・upload 未清掃・token 残存) は
   detached として残す)。**was_tracked でない場合 (conflict の
   非追跡側コピー) は旧行に触れない**。その後、新 repository_id の folders 行を
   **INSERT OR REPLACE** (再実行で PK 衝突しない) + 配下 fp_cache を無効化 (21.1 手順 3 と同型)
   → phase = APP_DONE。**新 folders 行の root_path = この手順を実行している時点の実体の realpath
   (回復経由なら journal を発見した現在の場所) — journal の realpath フィールドではない**
   (journal の realpath は fork 開始時に凍結したスナップショットで、中断中の移動後は物理的に
   誤った値になる。journal の realpath の用途は対象の識別・除外判定・flag 削除キーに限る)。
   **INSERT の前に、同じ root_path を指す別 repository_id の folders 行があれば §9.3-d で先に
   退役する** (§21.1 の同 root_path 退役と同型 — was_tracked の旧行 DELETE は old_id の行しか
   消さないため、無関係な stale 行が残ると新 id との規約 12 恒久偽 conflict になる)
4. **fork_in_progress (app 側の印) を先に消し、その後 journal を消す** — 逆順 (journal 先) で
   電断すると「journal なき fork_in_progress」が残る。実体が現存すれば次 tick の (a) が flag を
   掃除して無害だが、**電断後にフォルダごと移動されると (a) の掃除条件 (実体現存) を満たせず、
   journal も無いため回復経路が無いまま当該 path が恒久除外される** — 削除順はこの複合ケースを
   塞ぐ (journal が残る側はどの組合せでも回復ルーチンが処理できる)。直後の tick ステップ 0 が現状態を
   新 repository の初回コミットとして取り直す (backfill 対象)
5. 旧履歴だけが参照していた**過去版のみの原本 object** は次 GC (§13、24h grace 後) が回収する —
   fork は履歴破棄が趣旨で過去版検索は成立しないため正しい挙動 (冒頭「objects は保持」は現在版の
   派生の再 OCR 回避を指し、過去版のみの原本 object の永続までは保証しない)。**GC は fork 完了
   直後・次 tick の scan (初回コミットの再確立) 完了前には実行しない** — この窓では現在版の原本
   object も参照ゼロに見える (file_versions は手順 1 で空)。回収されても次 scan が working から
   再保存するため喪失はしないが、無駄な回収・再保存と §12 解決の一時失敗を生む (GC は scan を
   含む tick の step 5 以降の実行点でのみ走らせる — §13)
```

失敗回復 — **検出契機は 2 つ**: (a) **毎 tick 冒頭**に fork_in_progress の realpath を確認する —
**journal 有 → 回復を先に完了 / journal 無だが realpath に `.folder-history` 実体が現存し、
かつその repository-id が fork_in_progress 記録 (journal 不在の分岐なので照合元は flag の JSON) の
new_id と一致 (= 手順 4 の中間 — 手順 3 完了済み。flag 掃除だけで通常運用へ収束する) →
fork_in_progress を掃除 / **実体の id が old_id と一致 (journal 無)** → 掃除しない — 手順 4 の
削除順 (flag が先・journal が後) の下でこの組合せは正常系で生じず、journal の異常喪失
(HISTORY_CLEARED 中の bit-rot 等) を示唆する。damaged (§20.4) と同様に status 表示して明示解決
(§21.3「journal の破損」と同じ経路) を待つ (old でも掃除する規則は、履歴消去済み・id=old の
未完 fork を通常運用へ復帰させる — 直後の §9.3-z が後退として拾いデータは wipe + resync で
収束するが、fork の意図 (新 id への移行) が黙って破棄される) / journal 無かつ実体も不在
(フォルダごと移動・削除)、
または**実体はあるが id が old/new のどちらでもない (旧パスが別 repo に再利用された)・
読取不能**の場合 → 掃除せず保持**し (b) の journal 走査に委ねる (id を確認せず「実体があれば
完了」と推定すると、移動した未完 fork の flag を無関係な再利用フォルダが誤掃除させる)。「journal 無 = 常に手順 4 中間」と即断すると、
fork 中断中に移動されたフォルダの flag を誤掃除して未完 fork (履歴消去済み・id=old) が通常運用へ
復帰する。(b) bootstrap **および毎 tick の walk が watch_roots 配下と既知 folders から fork-journal を
持つフォルダを検出したら、再発見・root_path 更新より先に**回復を完了する (移動先で journal ごと
発見する)。**滞留の可視化**: fork_in_progress の started_at (**flag 不在・app 全損時は journal の started_at** —
二重化の読出し側もフォールバックする) から猶予 (既定 30 日 — missing §20.4 と
同じ) を超えても回復が完了しない場合 (手順 1 の恒久ストレージ障害・watch_roots 外かつ既知 folders 外
への移動で journal を発見できない等)、status を「fork 進行中」から「**fork stalled — 手動介入が必要**
(対象 realpath と経過日数を提示)」へ格上げする — 表示のみで自動では何も変更しない (残る回復経路 =
対象パスの register (§21.1 — 手順 1 の journal 検出で回復が先行する) または明示解決)。
再開位置は **journal の phase + 実体の repository-id** から一意に決まる:

```text
phase = PREPARED         : repository-id を読む — old なら手順 1 から (履歴が残っていても全削除は
                           冪等)、new なら手順 3 から (ID_WRITTEN 相当まで進んでいた)
phase = HISTORY_CLEARED  : id = old → 手順 2 から (空 commits の再 DELETE は無害) /
                           id = new → 手順 3 から。**ただし commits が空でない場合** (中断中に移動・
                           再発見され old_id で新規コミットが積まれた等) **は手順 1 からやり直す** —
                           手順 1 の全 DELETE は冪等ゆえ常に 1 起点でも安全で、旧 id 時代のコミットを
                           残したまま id を new へ書き換え fsck が全 commit を偽破損と報告するのを防ぐ
phase = ID_WRITTEN       : 手順 3 から (was_tracked は journal の固定値を使う — folders の現状から
                           再判定しない。手順 3 の途中失敗も INSERT OR REPLACE で再実行安全)
phase = APP_DONE         : 手順 4 (印 → journal の順の削除) のみ
phase = ID_WRITTEN /
APP_DONE なのに id = old : **不可能組合せ (手順の順序では生じ得ない — 部分 restore・手動コピーの
                           兆候)。damaged として停止し明示解決を待つ** — 下の「old / new 以外」の
                           第三 id 条件だけでは id = old が素通りし、手順 3/4 の実行が journal /
                           flag を消して回復根拠ごと失う
実体の id が old / new の
いずれでもない・読取不能  : **第三の id (置換 — journal の対象実体がもう存在しない兆候) は
                           damaged として停止し明示解決を待つ / 一時読取不能は無変更で保留** —
                           表の old / new 分岐だけを実装して推測で正常化しない (規約 12 の 4 分類
                           と同じ fail-closed)
app.sqlite 全損を挟む場合: journal だけで回復できる — phase と id から上記どおり分岐する
                           (**id = old の場合は手順 1〜2 も再実行する** — 「常に手順 3〜4 から」に
                           固定すると旧 id のまま新 folders 行を作り規約 12 が即 conflict する)
fsck との関係            : fork 完了後の fsck は新 id で commit_record を再構築するため、旧 id 由来の
                           偽「破損」報告は生じない (手順 1 で旧 commits を消しているため)
journal の破損           : **読めたが digest 不整合・構文不正**の journal は damaged (§20.4) と
                           同様に扱い、status 表示してユーザーの明示解決を待つ (自動で推測して
                           進めない)。**一時的に読めない (ロック・EIO) は破損ではなく保留** —
                           規約 12 の 4 分類と同じく次 tick が再試行する (破損と混同すると有効
                           fork の履歴を不要に破棄させる)。
                           **明示解決の実体 = §20.4 の damaged 復旧 (新 repository-id での §21.1
                           再登録)**: この経路に限り §21 前文の回復先行ゲートの例外とし、
                           ユーザー確認の上で次の順に進む — **(1) 破損 journal を除去 (flag は
                           残す) → (2) §21.1 手順 2 の初期化 — ただし repository-id は新規採番
                           せず、flag (fork_in_progress) が現存すればその new_id を採用する
                           (id の自己記述化 — (3) の掃除条件 (実体 id = new_id) を成立させる。
                           §21.1 手順 2 のまま新規採番すると第三の id が生まれ、(a) 規則は
                           「old / new のどちらでもない」で掃除せず保持 → journal は (1) で除去
                           済みで (b) も不発 → flag が恒久残留し、当該 realpath が tick 全ステップ
                           から恒久除外される。flag 不在・読取不能の場合のみ新規採番でよい —
                           その場合 (a) の照合対象も無く恒久除外は生じない。flag 不在での
                           journal 除去 → 初期化の間のクラッシュは「fork 意図の記録が無い素の
                           旧 repo」への着地 = 解決前の運用状態への復帰であり安全側 — 意図は
                           ユーザーが再操作で表明する) → (3) flag は毎 tick
                           冒頭の (a) 規則 (実体 id = new_id → 掃除) が回収する**。この順序なら途中
                           クラッシュは「journal 無 + flag 有 + id=old = 明示解決待ち ((a) 規則) →
                           再実行で冪等」か「id=new = flag 掃除で完了」のどちらかに着地し、解決の
                           意図が黙って失われない (journal と flag を同時に除去してから初期化する
                           手順は、間のクラッシュで空履歴の old-id repo が通常運用へ復帰し、依頼
                           した再初期化が消える)。破損 journal では phase を復元
                           できず、履歴は fork 中断時点の中間状態で信頼できないため、「履歴は
                           失われるが原本は無傷」の再出発 (§20.4 damaged と同じ位置づけ) になる。
                           この解決経路が定義されていないと、前文の回復先行ゲートが全明示操作を
                           恒久ブロックし脱出経路が存在しない
```

**課金の注記 (fork 中に in-flight だった OCR / embedding)**: fork は派生台帳を保持するため、
成果ありの (content, tool) は新 repository で再投入されない。ただし **fork 時点で in-flight
(成果なし) だった job** は、旧 job が detached として終端時に記帳 (payload 破棄) される一方、
新 repository が同一内容を成果なしとして再投入するため当該 content が二重課金され得る。これは
fork 時点の in-flight job に**有界**で、ledger に追跡され、per-repository 課金モデル (§18.6) と
整合する意図されたコストである (旧 job を新 id へ引き継ぐ handoff は detached モデルを複雑化する
ため採らない)。

## 21.4 過去版の復元 (restore)

入力: 復元対象の解決キーと**宛先の指定**。
- in-place 復元は **(repository_id, file_name, commit_hash) の非 delete 版**を要求する
  (event_type=3 の版は content_hash を持たず復元対象にできない — delete 版を選んだら拒否)。
- content_hash 単独 (§12 の逆引きで複数 file_name に属し得る) は宛先が一意に定まらないため、
  **明示的な宛先パスを必須**とする (エクスポート扱い)

```text
1. **規約 12 の照合を先に行う**: 対象フォルダの .folder-history/repository-id を folders 行と
   照合し、不一致 (バックアップ復元・別 repo への置き換え等) なら中止して conflict 表示する —
   restore もフォルダ DB を開く操作であり例外ではない (照合を飛ばすと、置き換わった別 repo の
   working ツリーへ旧 repo の版を書き込む)。objects/<content_hash> を読み、SHA-256 を再計算して
   名前と照合する (破損実体を配らない — 不一致は fsck §13 へ誘導)
2. 宛先を検証する: in-place の file_name は §20.5 の file_name 検証 (パス区切り・.. 等の拒否) を
   通し、root_path との正規化 join で外への脱出を拒否する。管理フォルダ内へのエクスポート宛先も同様
3. 宛先へ tmp → fsync → atomic rename → ディレクトリ fsync (§20.5 と同じ規律) で書き出す:
   a. in-place (元の file_name へ上書き) — **書込の前に対象ファイルを §20.5 手順 1 の安定確認で
      読み、現内容の content_hash が現在版 (LWW) と異なる場合は、先に通常のコミット (§20.5
      手順 3〜6 — tick.lock 下なので競合しない) で履歴化してから上書きする** — 最終 scan 後の
      未取り込み編集を restore が黙って上書きすると、その内容は working からも履歴からも消える
      (履歴ツール自身の操作による唯一の不可逆なデータ喪失経路になるため、必ず先に保全する)。
      **安定確認自体が失敗した場合 (2 回の stat の食い違い・読取エラー — 外部プロセスが書込み中)
      は上書きへ進まず restore を中止**して status で再試行を促す — スキャン文脈の「スキップして
      次回」をここへ転用して上書きへ進むと、保全を素通りして上記の喪失経路が再開する。
      **対象の raw エントリが不在の場合は「安定確認の失敗」と区別する**: 保全対象なしとして
      安定確認・保全をスキップし、§20.5 resolver の規則どおり NFC 表記で新規作成へ進む (不在を
      失敗と混同して中止すると、raw 無しへの正当な復元 (§20.5 が明示的に許す分岐) が恒久不能になる)。
      **rename の直前に解決先 raw エントリを再 lstat し、保全時の (size, mtime_ns, inode) と
      不一致なら中止**して再試行を促す (§20.5 の「rename 直前の再 lstat」を in-place restore では
      任意でなく**義務**とする — 保全と置換の間に外部 editor が書いた内容を上書きで消さない)。
      **この義務は raw 不在分岐にも適用する**: 比較基準は「不在」であり、再 lstat でエントリが
      出現していれば不一致として中止する (absent 確認後に外部が作成した同名ファイルを rename が
      置換すると、その内容は working からも履歴からも消える — 保全が塞いだ喪失経路の不在側の再開。
      「既存実体が無い以上どれとも衝突しない」(§20.5) は解決時点の判定で、書出しまでの窓は覆わない)。
      **可能なプラットフォームでは不在分岐の書出しに置換しない rename (Linux renameat2
      RENAME_NOREPLACE / macOS renamex_np RENAME_EXCL / Windows MoveFileEx 非置換) を用い、
      EEXIST 相当は中止・再試行とする** — 再 lstat と rename の残余窓ごと原子的に閉じる。
      **no-replace が使えない環境 (ENOSYS / EINVAL / EOPNOTSUPP — FAT/exFAT・旧 NFS・SMB 等) では、
      黙って通常 rename に置き換えてはならない**: 非対応の判定は初回試行のエラーで確定してよい
      (ボリューム単位に記憶可)。fallback は「rename 直前の再 lstat (不在 → 出現 = 不一致で中止) +
      通常 rename」の形に限り、残余窓が §20.5 の TOCTOU 残余と同族の既知の残余として残ることを
      実装が明示的に引き受ける — この明示なしに置換 rename へ落ちる実装は本規範に適合しない。
      EEXIST 相当は常に「出現 = 中止・再試行」。
      再検証と rename の間の残余窓は §20.5 の TOCTOU 残余と同族の既知の残余 (原子的には塞げない —
      編集中のファイルへの restore を避ける運用が前提)。
      **宛先の物理名は §20.5 の「論理名 → 物理名の解決」で
      raw エントリへ解決してから書く** (論理名 = NFC をそのまま path に使うと、正規化非依存 FS で
      NFD 実体の隣に別エントリを作り、復元物が name_collision の敗者になり得る。対応する raw
      エントリが無ければ NFC 表記で新規作成)。現在版と異なる内容なら次 tick のスキャンが通常の update
      としてコミットする (restore 専用のコミット種別・DB 書き込みは設けない — 履歴への反映は
      常にスキャン経由の単一経路。規約 11)
   b. エクスポート (別名 / 管理外) — 管理フォルダ外なら履歴に影響しない。管理フォルダ内の別名は
      次 tick で create としてコミットされる。**export の宛先は新規作成に限る** — 書出しは
      no-replace rename を必須とし (in-place の不在分岐と同じ規律 — 非対応環境の fallback も同様)、
      既存実体があれば中止する (既存パスへ重ねたい場合は保全つきの in-place restore を使う —
      export 側に保全規範は無いため、上書きを許すと未取り込み編集の無痕跡喪失経路が再開する)
```

失敗回復: rename 前のクラッシュは tmp 残骸のみ (tick 開始時の tmp 掃除が回収する)。**rename の
同期的失敗 (宛先のパス長超過・権限拒否・ディスク満杯) は tmp を保持したまま status に報告**し、
working ツリーを半端な状態にしない (別名エクスポートへの誘導も可)。

## 21.5 監視 Root の登録・解除 (watch_root)

register (§21.1) はフォルダ単位の管理開始だが、その前提となる**監視 Root 自体の出し入れ**を定義する。

```text
watch_root 追加: パスを realpath 正規化 (§20.4) して watch_roots へ INSERT。既存 root と同一は
                 no-op、包含関係は拒否 + status (§20.4)。追加後の初回 tick が配下を全 walk して
                 .folder-history 保有フォルダを再発見する
watch_root 解除: watch_roots から DELETE。**配下の folders / 履歴・派生は消さない** (監視をやめる
                 だけ)。ただし watch_root 外に出た登録フォルダは §20.4 のとおり root_path が
                 有効な限り folders 起点で検知が続くため、完全に監視を切るには対象フォルダを
                 個別に unregister (§21.2) する。**解除の app Tx で、残存する watch_roots /
                 folders.root_path の walk 範囲に含まれなくなる配下の fp_cache 行を明示 DELETE
                 する** — mark-and-sweep は「対象の完全 walk 成功時」に走るため、解除で walk の
                 主体が消えた領域の孤児行は誰にも掃除されない (「M&S が掃除」の旧記述は誤り)
app 全損後の bootstrap: watch_roots はユーザー設定であり app 全損で失われる (**復元の起点は
                 規約 9** — 規約 7-f が列挙するのは watch_roots **外**の個別パス等)。再入力が
                 復元の起点で、再入力後の walk が repository-id 検出で folders を再構築する (規約 9)。
                 **watch_roots の外にある登録フォルダ (§20.3 の folders 起点 walk 対象) は
                 watch_roots 再入力では発見できない** — その存在の記憶は app 側にしか無いため、
                 bootstrap ではフォルダの個別パスも再入力する (規約 7 の損失 (f) に含まれる —
                 忘れられた standalone フォルダは層 1 が無傷のまま検知だけが止まる。watch_root
                 配下への移動または再入力で復帰)。
                 **app_config (現行 tool / embedding profile・および image_filter 設定) も同時に
                 再入力・確認する** — これが無いと submit の :current_tool / :current_profile と横断検索の
                 query embedding が構成できず、さらに既存 chunks がどのフィルタ設定で作られたかを
                 復元できない (§8 — 未再入力だと現行フィルタと既存派生の差分検出が不能になる)。
                 profiles 表は履歴の保管庫で current を示さない — §11.2 の単独検索規則は embeddings の
                 一意 profile から導けるが、app 側の current は入力が必要。unregister の退役事実も
                 失われる (規約 7-f) — 再発見された退役済みフォルダは不要なら再度 unregister する。
                 fork-journal を持つフォルダは再発見より先に fork 回復を完了させる (§21.3)
```

## 21.6 派生破棄 (drop-derivation)

GC が原本 + 派生の同時喪失で恒久 fail-closed に陥った場合 (§13) や、旧 tool_profile の派生を
明示的に捨てたい場合の回復操作。入力: **(対象フォルダ, content_hash, tool_profile_hash)** —
派生台帳はフォルダごとに独立 (§18.6) なので、フォルダ指定が無いと同一 (content, tool) の派生を
持つ別フォルダのどれを操作するか定まらない。効果は指定フォルダの metadata.sqlite に閉じる。

```text
1. metadata.sqlite 1 Tx: markdown_documents の該当行を DELETE (CASCADE で chunks / FTS も消える)
2. フォルダ側 embeddings の孤児掃除 (§13 — (chunk_type, embed_hash) 差集合で vec → embeddings 順)
3. 集約側は §9.3-b の逆差集合が次 Replicate で伝播 (agg から該当派生を削除)
4. 宙吊りだった obj: 参照が消え、次 GC が該当 object を回収できるようになる (fail-closed 解除)
```

原本が健在なら明示再生成 (§5.3) で派生を作り直せる (「派生は再生成可能・原本が正」の帰結)。
原本も失われている場合は喪失の確定操作になる。
**注記**: (a) **原本が健在で現在版の場合、および backfill (§10 — 既定 ON) の下では過去版のみから
参照される場合も**、drop の直後から §10 step 1 の差集合が同ペアを「成果なし」として**自動的に
再投入する** (drop は「その時点の派生の破棄」であり将来の生成の禁止ではない。「現在版なら」に
限った旧記述は誤り — backfill ON では過去版の drop も次 tick に再 OCR = 再課金される)。
再課金を望まない場合は、対象を先に unregister **して watch_root 外へ移す** (unregister 単独では
active watch_root 配下は次 walk の marker 再発見で再登録され再投入される — §21.2)・原本を退避する
(現在版 — **ただし backfill ON では退避だけでは止まらない**: 退避後の削除コミットで同 content が
過去版になり backfill が再投入する。退避は backfill OFF と併用する)、または
**backfill を OFF にしてから drop する** (過去版のみの場合 — 過去版参照の再投入経路は backfill
だけなので OFF で止まる。§5.3 の floor 設定済み対象は例外的に backfill 設定を無視する点に注意)。(b) drop 時に同対象の
in-flight job (state=1) が残っていた場合、その後の collect は成果なしとして通常どおり新派生を
作成する — これも意図された挙動 (破棄したのは旧派生であり、新結果の受け入れは妨げない)。

## 21.7 その他 (定義済みの参照)

```text
terminal failed の再試行     : §9.1 (attempts を 0 にリセットする操作)
明示再生成 (再 OCR)          : §5.3 (floor_generated_at — app 1 Tx のみ)
damaged フォルダの復旧       : §20.4 (新 repository-id での 21.1 再登録)
conflict の解決              : §20.4 + 21.3 (fork)
チャンク規則・フィルタ変更   : §7 / §8 (再チャンク — ローカル操作)
embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)
```
