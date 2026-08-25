# Step2a 契約テスト仕様書: Step 2 (kio-pipeline + kio-adapter)

> 本書は **実装より先にテストを固定する** ためのケース仕様。Rust 実装コードは含まない。
> Step 2 実装者 (別エージェント) はこの仕様を「動かしてはならない契約」として消化する。
> 正本 spec は `docs/` の 03〜10。**本書は spec を写経・補間せず、各テストに根拠 § を必ず付す**。
> spec に記述がない挙動は勝手に契約化せず、末尾 §C「未定義事項」に切り出す。
>
> Step 1 の現行 Rust behavior tests (`crates/kio-core/tests/contract_vectors.rs` と
> `crates/kio-cli/tests/`) の ID 体系・ベクタの書き方・未定義事項の切り出し方を踏襲する。Step 1 から
> 持ち越した **CT-COMMIT-008** (`kio index` 成功完了時 commit_type=auto)
> は本書 CT2-INDEX-* に取り込む (2026-07-03 監査裁定で Step 2 ゲートへ移動済み)。
>
> 改訂 r2 (2026-07-03): Codex クロスレビュー反映。ベクタ 6 件 + 変化率 4 件は再計算一致につき不変
> (A.2 のバイト数は NFD 形 78 / NFC 形 76 の両論併記で曖昧性を解消)。過剰契約・誤引用 8 件を修正、
> カバレッジ 10 件を反映 (新規テスト 8 / 既存拡充 2)。§C から「spec 定義済み」1 件を A 節注記へ移設し、
> 要-spec を 5 件に再集計 (うち 4 件は 2026-07-03 に発注側が spec 追記予定)。A.1/A.3 の profile ベクタは
> **計算規約検証用 fixture** であり、実装が採用する実 profile 値の契約ではないことを明記。

対象クレート (Step 2): `kio-pipeline` + `kio-adapter`
実装範囲の正本: `docs/09-mvp-scope.md §3.1` の **Step 2 行** — 初回スキャン preview + 承認 / `.kioignore` /
preview コスト概算 / Prepare / Markdownize (full + incremental) / 同梱 deterministic Adapter (ベースライン index) /
Mistral OCR 標準 Adapter + image object / batch / retry / resume / budget guardrail / task・artifact descriptor /
secrets Tier A/B + quarantine + `--yes` 制約。

---

## 0. テスト ID 体系と優先度

| 接頭辞 | 対象契約 | 主な根拠 |
| --- | --- | --- |
| `CT2-PROFILE-*` | `tool_profile_hash` / `tool_lock_hash` / `prompt_template_hash` 算出規約 (cmd/url/auth 排除・null 省略・alias 禁止) + Step 2 追加 schema validation | `03 §5.1, §5.2` / `07 §4, §6` / `06 §11` |
| `CT2-UNIT-*` | prepared unit / `unit_ref` / normalized instance レイアウト / manifest / fingerprint 再利用 / unit_mapping / 変化率 | `03 §2, §2.1` / `04 §2, §2.1, §2.2` |
| `CT2-INCR-*` | incremental 発動条件 (AND 5) と各否定 → full fallback / identity 不変性 | `04 §3.1` / `07 §8.4` |
| `CT2-ACCEPT-*` | incremental 出力の受け入れ検査 V1〜V6 + `KIO-E-ADAPTER-CONTRACT-001` | `04 §3.2` / `07 §8.1` |
| `CT2-TASK-*` | task 状態機械 / retry budget / resume / 冪等性 / partial | `04 §5.1, §5.2, §5.3, §5.5, §5.7` |
| `CT2-BUDGET-*` | 二層 cap 判定 / pause / `--override-budget` / cost ledger | `04 §5.4` |
| `CT2-APPROVE-*` | 初回スキャン preview + 明示承認 / `.kioignore` / 非対話 exit 2 / cost 概算 | `10 §1` / `06 §2` |
| `CT2-SECRETS-*` | secrets Tier A/B / quarantine / `--yes` 制約 / `approval_method` | `10 §1.1` / `06 §2` |
| `CT2-NETWORK-*` | network opt-in (scope × adapter / 未承認 pending / revoke / `--approve` 成立・`--yes` 不成立) | `07 §3` / `06 §2` |
| `CT2-ADAPTER-*` | 同梱 deterministic Adapter (ベースライン index) / Mistral OCR 規約 / 共通メタデータ / policy | `07 §2.1, §5.2, §4, §7` |
| `CT2-IMAGE-*` | embedded image 抽出・image object 保存 / `kio://` object 参照置換 | `03 §2` / `07 §5.2` / `08 §2.3` |
| `CT2-INDEX-*` | index preview→approve→snapshot / index 完了時 auto snapshot (CT-COMMIT-008 継承) / no-op | `05 §8.1` / `06 §1` / `09 §1.1` |

**優先度**

- **P0** = Step 2 完了条件。全て緑でなければ Step 2 を「完了」と呼べない。
- **P1** = 推奨。契約の周辺・堅牢性。落ちても致命ではないが実装欠陥の強い兆候。
- **P2** = あれば良い。Step 3 以降の前倒し検証や参考ベクタ。

P0 総数は §D 末尾に集計。

---

## A. 具体的テストベクタ (最重要)

以下は `python3` (3.14) で実計算した固定ベクタ。**再現手順**: 各 JSON を JCS 直列化して sha256 する。
JCS 近似は `json.dumps(obj, separators=(',',':'), ensure_ascii=False, sort_keys=True).encode('utf-8')`。

> **RFC 8785 との差異について**: 本書の profile ベクタが使うキーはすべて ASCII、数値はすべて整数
> (`spec_version=1`, `dimensions=1536`) である。この条件下では上記 Python 近似は RFC 8785 JCS と
> **バイト一致** する。差異が顕在化するのは (a) 非 ASCII のキー名、(b) 浮動小数点の数値 の場合のみ。
> `sampling` (`temperature` 等の float) を含む生成 LLM 系 profile は本ベクタ集に**含めない**: float の
> ECMAScript 数値直列化 (RFC 8785 §3.2.2.3) は Python 近似の安全域外のため。これは **spec の未定義では
> なく本書の計算手段の制約** (`03 §5.1` は RFC 8785 準拠と定義済み)。生成 LLM 系 profile のベクタは
> 実装の RFC 8785 準拠 JCS で別途固定する。実装が本ベクタと不一致になった場合、まず「実装の JCS が
> RFC 8785 準拠か」を疑うこと。
>
> **fixture と契約の分離 (重要)**: A.1〜A.3 / A.6 の profile 値 (`mistral-ocr-2505` / `kio-deterministic-text` /
> `gemini-multimodal-embedding` 等) は**計算規約を検証するための入力 fixture** であり、Kio 公式 Adapter の
> 実 profile 値・実 tool-lock 値の契約では**ない**。特に `gemini_multimodal_embedding` (1536 次元) は
> `07 §5.3` が「例示であり、ベンダー・次元数の裏取り済み値ではない」と明記する未確定 profile。
> 契約は「この入力ならこの hash」という**算出関数の固定**のみで、実装の実運用 profile が
> これらの値と一致することは要求しない。

### A.1 tool_profile_hash ベクタ (`03 §5.1`)

**PROFILE-1 (mistral_ocr, online_api / 文書処理 API)** — prompt/sampling は当該 Adapter に無く null 省略:

```text
canonical: {"adapter_kind":"markdownize","adapter_role":"multimodal","model_or_tool_family":"mistral-ocr","model_version_pin":"mistral-ocr-2505","output_schema":"kio-markdown-v1","runtime_kind":"cloud","spec_version":1}
tool_profile_hash = sha256:24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed
```

**PROFILE-2 (同梱 deterministic markdownize, deterministic_library)**:

```text
canonical: {"adapter_kind":"markdownize","adapter_role":"text","model_or_tool_family":"kio-deterministic-text","model_version_pin":"1.0.0","output_schema":"kio-markdown-v1","runtime_kind":"local","spec_version":1}
tool_profile_hash = sha256:76c01950d19edffc1b8ca75e06d7754fb52cd05db1bb10e3268f81392bf54095
```

**PROFILE-3 (multimodal embedding, online_api)** — embedding 専用フィールド在:

```text
canonical: {"adapter_kind":"embedding","adapter_role":"multimodal","dimensions":1536,"distance":"cosine","modality":"multimodal","model_or_tool_family":"gemini-multimodal-embedding","model_version_pin":"gemini-embedding-001","runtime_kind":"cloud","spec_version":1}
tool_profile_hash = sha256:c2bda78e217e1f9e12cd17ddac6c46e28a50b8060976f533f76f14193a807226
```

**PROFILE-4 (同梱 deterministic prepare, deterministic_library)** — tool_lock ベクタ用:

```text
canonical: {"adapter_kind":"prepare","adapter_role":"text","model_or_tool_family":"kio-deterministic-prepare","model_version_pin":"1.0.0","runtime_kind":"local","spec_version":1}
tool_profile_hash = sha256:20b67a9d7e7e2654379f16f20b445d007e95abac7c8f85d6da65beccff7e6b03
```

**null 省略規則の検証 (PROFILE-1-NULL)**: PROFILE-1 に
`prompt_template_id / prompt_template_hash / sampling / dimensions / distance / modality` を
**すべて `null` 値で追加**した profile を canonicalize すると、Kio は null キーを hash 入力から落とすため、
canonical バイト列と `tool_profile_hash` は PROFILE-1 と**完全一致**する
(= `sha256:24bd9e90...81ed`)。「省略と null を識別しない」(`03 §5.1`) の実証。

### A.2 prompt_template_hash 正規化 5 手順ベクタ (`03 §5.1`)

入力 (末尾空白・タブ・CRLF・NFD 分解文字・末尾空行を含む。**NFD 分解**: 各アクセント文字は
基底文字 + U+0301 結合アキュートで与える):

```text
raw (NFD 形 utf-8 = 78 bytes / NFC 形 utf-8 = 76 bytes。下記参照):
  "You are a markdownize adapter.␠␠\r\n"        (行末に半角空白 2)
  "Process the café unchánged unit.\t\t\r\n"  (e+U+0301, a+U+0301, 行末タブ 2)
  "\r\n\r\n"                                       (末尾空行)
```

> バイト数の注意: fixture 入力は **NFD 形 (78 bytes)** — アクセント文字は基底文字 + U+0301 (2 バイト `cc 81`)。
> 本文書からアクセント文字を NFC 合成済みでコピーした場合の入力は **76 bytes** になるが、手順 3 (NFC) が
> 両者を同一文字列に正規化するため **最終 hash はどちらの入力でも同一** (NFC は冪等)。NFD 形を入力に使うと
> 手順 3 が実際にバイトを変えることまで検証できる。

5 手順 (`03 §5.1`): 1. 各行の行末空白除去 → 2. 改行を `\n` に正規化 → 3. NFC → 4. 末尾空行削除 → 5. sha256。

```text
正規化後 (repr):     'You are a markdownize adapter.\nProcess the café unchánged unit.'
正規化後 utf-8 hex:  596f75206172652061206d61726b646f776e697a6520616461707465722e0a
                     50726f636573732074686520636166c3a920756e6368c3a16e67656420756e69742e
                     (café=63 61 66 c3a9, unchánged の á=c3a1 — NFC 合成済み)
prompt_template_hash = sha256:3f5200e929d23e1f113f605fb528b1b7b75e183d226064d319f57fb3e467d238
```

NFC ステップが実際にバイトを変える (`e`+`U+0301` → `é`=`c3 a9`) ことをこのベクタで固定する。

### A.3 tool_lock_hash ベクタ (`03 §5.2`, optional adapter 省略ケース)

`summary` / `classification` / `rerank` を**省略** (未設定 → null と識別せず落とす)。
`profile_hash` は A.1 の実計算値を使う (prepare=PROFILE-4, markdown=PROFILE-1, embedding=PROFILE-3):

```text
canonical:
{"embedding":{"dimensions":1536,"distance":"cosine","modality":"multimodal","profile_hash":"sha256:c2bda78e217e1f9e12cd17ddac6c46e28a50b8060976f533f76f14193a807226","tool_id":"gemini_multimodal_embedding"},"markdown":{"profile_hash":"sha256:24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed","tool_id":"mistral_ocr_markdownize"},"prepare":{"profile_hash":"sha256:20b67a9d7e7e2654379f16f20b445d007e95abac7c8f85d6da65beccff7e6b03","tool_id":"prepare_default"},"spec_version":1}
tool_lock_hash = sha256:e24d8b76742e441e894181f9210453e0da60a6e84c663560214d10aeeee0b264
```

`cmd`/`args`/`url`/`config_hash`/`capabilities` は入力に含めない (`03 §5.2` / `07 §6`)。
本ベクタも A 節冒頭の注記どおり**計算規約検証用 fixture** である (`gemini_multimodal_embedding` は
`07 §5.3` の例示 profile)。commit object の `tool_lock_hash` (Step 1 の historical CT-HASH-004 ではダミー値) は Step 2 で
**実装の実 tool-lock.json から同じ規約で算出した値**が注入される (CT2-INDEX-002) — 本 fixture 値との
一致は要求しない。

### A.4 unit_ref 導出ベクタ (`03 §2.1`: `unit_ref = base16(sha256(unit_key))[0:16]`)

`unit_key` 文字列の UTF-8 バイト列を sha256 し、小文字 hex 先頭 16 文字 (= 先頭 8 バイト)。

| unit_key | sha256 (先頭) | `unit_ref` |
| --- | --- | --- |
| `page:12` | `3c2fa650872d5484…` | `3c2fa650872d5484` |
| `page:1` | `00f081779b832543…` | `00f081779b832543` |
| `page:57` | `d2255263b6d52dc8…` | `d2255263b6d52dc8` |
| `slide:3` | `22814b0d608d29b9…` | `22814b0d608d29b9` |
| `sheet:Sheet1` | `fae07767a7986381…` | `fae07767a7986381` |
| `image:0` | `beadc43287ae0d1a…` | `beadc43287ae0d1a` |

補足: `03 §2.1` manifest 例の `unit_ref`「3f2a9c0d1b4e5f60」(page:1) 等は**説明用の架空値**であり、
契約ベクタは本表の実算出値。unit object のファイル名は `<unit_ref>.json`。

### A.5 変化率ベクタ (`04 §2.2`。分母 = `max(|新 unit 集合|, 1)`。hash 不要)

`変化率 = (|changed| + |added| + |removed|) / max(|新 unit 集合|, 1)`

| # | シナリオ | old / new | changed / added / removed | 変化率 | 発動条件4 (threshold 0.30) |
| --- | --- | --- | --- | --- | --- |
| RATE-A | 先頭に 1 ページ挿入 | 10 / 11 | 0 / 1 / 0 | 1/11 ≈ **0.0909** | `<` → incremental 候補 |
| RATE-B | 本文 4 ページ改稿 | 10 / 10 | 4 / 0 / 0 | 4/10 = **0.40** | `≥` → full |
| RATE-C | 末尾 2 ページ削除 | 10 / 8 | 0 / 0 / 2 | 2/8 = **0.25** | `<` → incremental 候補 |
| RATE-D | 新 unit 集合 0 (全削除) | 3 / 0 | 0 / 0 / 3 | 3/max(0,1)=**3.0** | `≥` → full (分母 0 割回避) |

RATE-A は「先頭挿入 1 枚で全 unit が changed になる」素朴比較の誤りを、fingerprint LCS が
unchanged 10 + added 1 に分解して回避することを示す (`04 §2.2` アルゴリズム 1)。

### A.6 normalized instance レイアウトベクタ (`03 §2.1` / `04 §2`)

`raw_hash = sha256:bbe1da2edd1819b58ce32163144923f850fc7f2c7b4fe130635c6b54a8e7ac59`
(本書 A.1 RAW-2 の値を流用)、`tool_profile_hash = sha256:24bd…81ed` (A.1 PROFILE-1)、`gen=0` のとき:

```text
instance dir: .kio/objects/normalized_units/bb/e1/
              sha256:bbe1da2edd1819b58ce32163144923f850fc7f2c7b4fe130635c6b54a8e7ac59.sha256:24bd9e903241740fc9fe94fb72a6ff3e697b3c0859bd5aef1b49728a207e81ed.g0/
  manifest.json                 # order 付き unit 一覧 + unit status (正本)
  3c2fa650872d5484.json         # unit object (unit_key=page:12, A.4)
全文 view (cache): .kio/objects/normalized/bb/e1/
              <raw_hash>.<tool_profile_hash>.g0.md
```

fan-out `ab/cd` は raw_hash の digest 先頭 2/次 2 文字 (`bb`/`e1`、`03 §8.1`)。
ディレクトリ名は `<raw_hash>.<tool_profile_hash>.g<gen>` (両 hash とも `sha256:` prefix 込み)。

---

## B. テストケース

各ケース: **ID / 優先度 / Given-When-Then / 正本根拠**。

### CT2-PROFILE-* — identity 算出規約 (`03 §5.1, §5.2` / `07 §4, §6`)

**CT2-PROFILE-001** — P0 — tool_profile_hash: mistral_ocr (online_api)
- Given: A.1 PROFILE-1 の capability フィールド。
- When: `canonicalize → JCS → sha256`。
- Then: canonical バイト列が A.1 と一致し、`tool_profile_hash = sha256:24bd9e90…81ed`。
- 根拠: `03 §5.1` (ハッシュ対象フィールド / RFC 8785 JCS / `"sha256:" + base16(sha256(...))`)。

**CT2-PROFILE-002** — P0 — tool_profile_hash: 同梱 deterministic markdownize
- Given: A.1 PROFILE-2。
- When: 同上。
- Then: `tool_profile_hash = sha256:76c01950…4095`。PROFILE-1 と別 identity になる (別 artifact)。
- 根拠: `03 §5.1` / `07 §2.1` (ベースライン artifact は別 tool_profile_hash)。

**CT2-PROFILE-003** — P0 — null フィールドは hash 入力から落とす (省略と null を識別しない)
- Given: A.1 PROFILE-1-NULL (PROFILE-1 に 6 個の null フィールドを付与)。
- When: canonicalize (null キー除去) → JCS → sha256。
- Then: canonical・hash とも PROFILE-1 と完全一致 (`sha256:24bd9e90…81ed`)。
- 根拠: `03 §5.1` (「null フィールドは hash 入力に含めない (省略と null を識別しない)」)。

**CT2-PROFILE-004** — P0 — cmd / args / url / 認証情報は tool_profile_hash に絶対含めない
- Given: 同一 capability だが `cmd` / `url` / `auth` が異なる 2 Adapter 設定。
- When: それぞれ tool_profile_hash を算出。
- Then: 同一 hash になる (実行情報は identity に影響しない)。認証情報を profile 入力へ混入させた
  実装は本テストで検出される。
- 根拠: `03 §5.1` (「`cmd`/`args`/`url`/認証情報は絶対に含めない」) / `07 §1` (認証情報の混入禁止)。

**CT2-PROFILE-005** — P0 — prompt_template_hash の正規化 5 手順
- Given: A.2 の入力 (行末空白・タブ・CRLF・NFD 分解・末尾空行)。
- When: 5 手順 (行末空白除去 → `\n` 化 → NFC → 末尾空行削除 → sha256)。
- Then: 正規化後 utf-8 hex が A.2 と一致し、`prompt_template_hash = sha256:3f5200e9…d238`。
  NFC 手順で `e+U+0301` が `é` (`c3 a9`) に合成される。
- 根拠: `03 §5.1` (prompt_template_hash の 5 手順)。
- 補足: step1 の「trailing whitespace」の文字集合と CRLF/lone-CR の扱いは spec に明記が無い (§C-4、
  **2026-07-03 に発注側で spec 追記予定**)。本ベクタは「半角空白・タブを行末空白、CRLF を step2 で
  `\n` 化」の解釈で計算した。spec 追記がこの解釈と一致すれば本ベクタで確定、相違すれば再計算する
  (追記までは hash 値を確定契約とせず、5 手順の実装のみ先行してよい)。

**CT2-PROFILE-006** — P0 — tool_lock_hash (optional adapter 省略ケース)
- Given: A.3 の tool-lock.json (prepare/markdown/embedding のみ、summary/classification/rerank 省略)。
- When: JCS → sha256。
- Then: canonical バイト列が A.3 と一致し、`tool_lock_hash = sha256:e24d8b76…b264`。
  embedding のみ dimensions/distance/modality を含む。
- 根拠: `03 §5.2` (計算式 / optional adapter は未設定なら省略 / cmd/url/config_hash/capabilities 非包含) /
  `07 §6` (実行可能情報を含めない)。
- 補足: A.3 は**算出規約の fixture** (A 節冒頭注記)。実装の実 tool-lock.json (embedding profile は
  `07 §5.3` の実地検証で確定) がこの fixture 値と一致することは要求しない。

**CT2-PROFILE-007** — P1 — model_version_pin は immutable 版、可変 alias は禁止
- Given: config が `mistral-ocr-latest` (可変 alias) を指定。
- When: Adapter が実行開始時に提供元モデル一覧 API で現行版付き名を解決し、`model_version_pin` に記録。
- Then: `tool_profile_hash` 入力の `model_version_pin` は `mistral-ocr-2505` 等の版付き名であり、
  `latest` の文字列はそのまま入らない。版付き名を pin できないと算出を失敗させる (alias 混入拒否)。
- 根拠: `03 §5.1` (「latest 等の可変 alias は禁止」) / `07 §6` (「API 呼び出し自体を版付きモデル名で行う」)。

**CT2-PROFILE-008** — P1 — adapter_binary_version は tool_profile_hash に含めず binary_hash へ別保存
- Given: capability 不変で実装バイナリのみ更新 (bug fix)。
- When: tool_profile_hash を算出。
- Then: hash 不変 (= 全 re-index が走らない)。バイナリ版は `binary_hash` として別記録。
- 根拠: `03 §5.1` (「実装バイナリのバージョンは binary_hash として別保存し tool_profile_hash に含めない」)。

**CT2-PROFILE-009** — P2 — spec_version bump は breaking change
- Given: profile_hash_spec の `spec_version` を bump した profile。
- When: 旧 spec_version の artifact と比較。
- Then: 別 identity として扱う (migration plan 必須の扱い)。
- 根拠: `03 §5.1` (「spec_version の bump は breaking change 扱い」) / `10 §12.5`。

**CT2-PROFILE-010** — P0 — Step 2 追加 schema validation (tools.toml / tool-lock.json)
- Given: (a) schema 違反の `~/.config/kio/tools.toml` (例: `auth` が `^(keychain|env|plain):` 形式外)、
  (b) schema 違反の `.kio/tool-lock.json`。
- When: CLI 起動 / 当該ファイルを使う操作。
- Then: いずれも exit 2 + `KIO-E-CONFIG-SCHEMA-NNN`。Step 1 対象 (scope/manifest/config) に加え、
  Step 2 で tools.toml / tool-lock.json が validation 対象に入る。
- 根拠: `06 §11` (schema 一覧 / validation 失敗 exit 2 + `KIO-E-CONFIG-SCHEMA-NNN` / `auth` 形式は 07 §1) /
  `09 §3.1` (「JSON Schema validation (Step 1 は scope / manifest / config。以後各 Step で対象 schema を追加)」) /
  `10 §12.3`。

**CT2-PROFILE-011** — P1 — tool_lock_hash の hash 対象/除外フィールド分離
- Given: `07 §6` 例のとおり `kind` / `capabilities` / `mode` フィールドを含む tool-lock.json と、
  それらを除いた同内容の tool-lock.json。
- When: それぞれ tool_lock_hash を算出。
- Then: 同一 hash。入力は `03 §5.2` の式が選択するフィールドのみ
  (`spec_version` + 各 adapter の `{ tool_id, profile_hash }` + embedding のみ `dimensions/distance/modality`)。
  `kind` / `capabilities` / `mode` / `cmd` / `url` / `config_hash` の変更で hash は変わらない。
- 根拠: `03 §5.2` (「cmd/args/url/config_hash/capabilities は入力に含めない」/ フィールド選択式)。
- 補足: `07 §6` の「tool-lock.json 全体を JCS 畳み込み」という文言と `03 §5.2` のフィールド選択式は、
  `07 §6` 自身が `03 §5.2` を計算規約として参照しているため **03 §5.2 を正** とする。

### CT2-UNIT-* — prepared unit / normalized instance / unit_mapping (`03 §2.1` / `04 §2, §2.1, §2.2`)

**CT2-UNIT-001** — P0 — unit_ref = base16(sha256(unit_key))[0:16]
- Given: A.4 の unit_key 群。
- When: 各 unit_ref を導出し、unit object を `<unit_ref>.json` に保存。
- Then: `page:12 → 3c2fa650872d5484`, `page:1 → 00f081779b832543`, `sheet:Sheet1 → fae07767a7986381`
  等 (A.4 全行)。ファイル名は `<unit_ref>.json`。
- 根拠: `03 §2.1` (「unit_ref = base16(sha256(unit_key))[0:16]」)。

**CT2-UNIT-002** — P0 — normalized instance の物理レイアウト
- Given: A.6 の (raw_hash, tool_profile_hash, gen=0)。
- When: normalized instance を保存。
- Then: `objects/normalized_units/bb/e1/<raw_hash>.<tool_profile_hash>.g0/` 配下に
  `manifest.json` + `<unit_ref>.json` 群を置く。fan-out は raw_hash digest の `bb`/`e1`。
- 根拠: `03 §2, §2.1` (レイアウト / instance ディレクトリ命名) / `04 §2` (物理配置)。

**CT2-UNIT-003** — P0 — manifest schema と unit status
- Given: 一部 unit が failed の instance。
- When: manifest.json を検査。
- Then: `raw_hash / tool_profile_hash / gen / parent_gen / run_id / units[] / generated_at` を持ち、
  各 `units[]` は `order / unit_key / unit_ref / unit_type / status / prepared_hash / error_kind`。
  `status ∈ {done, failed, ...}`。
- 根拠: `03 §2.1` (manifest schema)。

**CT2-UNIT-004** — P0 — fingerprint 一致の unit は再 Markdownize しない (LLM 呼び出しなし)
- Given: 同一 file の再取り込みで、ある unit の `(prepared_hash / raw_hash+page_fingerprint / tool_profile_hash)`
  がいずれも不変。
- When: Markdownize を実行。
- Then: 当該 unit は既存 Markdown をそのまま再利用し、Adapter (LLM) を呼ばない。unit object は新 instance
  へ複製し `reused_from` に旧 `(raw_hash, gen, unit_key)` を記録。
- 根拠: `04 §2.1` (再利用判定 3 条件 / 「一致時は再 Markdownize 不要を契約として明記」) / `04 §2.2` (unchanged の帰結)。

**CT2-UNIT-005** — P0 — 変化率の計算 (分母 = max(|新 unit 集合|, 1))
- Given: A.5 の RATE-A〜D。
- When: unit_mapping の帰結から変化率を計算。
- Then: RATE-A=0.0909 / RATE-B=0.40 / RATE-C=0.25 / RATE-D=3.0。新 unit 集合 0 でも 0 割しない。
- 根拠: `04 §2.2` (変化率式 / 分母定義)。

**CT2-UNIT-006** — P1 — unit_mapping: fingerprint exact LCS で unchanged を 1:1 対応
- Given: 旧 10 unit の先頭に fingerprint の異なる 1 unit を挿入した新 11 unit。
- When: unit_mapping を計算。
- Then: order 保存 LCS により 10 unit が unchanged (`confidence=1.0, reason="fingerprint_exact"`)、
  挿入 1 unit が added。位置ベース単純比較のような「全 unit changed」にならない。
- 根拠: `04 §2.2` (アルゴリズム 1 exact / 3 残余 added)。

**CT2-UNIT-007** — P1 — unit_mapping: 区間対応 (changed) は order 順 1:1
- Given: exact アンカー間の区間に未対応の旧 m / 新 n unit。
- When: 区間対応を計算。
- Then: `min(m,n)` 組を order 順に対応 (`confidence=0.5, reason="order_aligned"` = changed)、余りは added/removed。
- 根拠: `04 §2.2` (アルゴリズム 2 区間対応 / 3 残余)。

**CT2-UNIT-008** — P1 — reused_from の provenance 記録
- Given: unchanged 判定で再利用された unit object。
- When: 新 instance の unit object を検査。
- Then: `reused_from = { raw_hash, gen, unit_key }` (旧 instance 由来) を保持。unit object 本体は新 instance へ複製。
- 根拠: `03 §2.1` (reused_from schema / 複製) / `04 §2.2` (unchanged の帰結)。

**CT2-UNIT-009** — P1 — 全文 view は決定論的結合の cache (正本ではない)
- Given: done/failed 混在の instance。
- When: 全文 view を組み立てる。
- Then: `order` 昇順、done は末尾連続改行除去、failed は `<!-- KIO-MISSING-UNIT <unit_key> <error_kind> -->`、
  `"\n\n"` 結合 + 末尾 `"\n"`、§10 ヘッダ付与。view の破損・喪失は `kio repair` 再生成で解消し、
  up_to_date 判定に view の存在を使わない。
- 根拠: `03 §2.1` (view 組み立て規則 5 手順 + ヘッダ) / `03 §6` (「全文 view の存在は判定に使わない」)。

**CT2-UNIT-010** — P1 — unit object は read-only artifact (直接編集は up_to_date を変えない)
- Given: 保存済み unit object を直接編集。
- When: 次回 index の up_to_date 判定。
- Then: `(raw_hash, tool_profile_hash)` 一致で up_to_date 判定 (Markdown 内容は正本でない)。書き換え・削除しない
  (purge/reindex --force を除く)。
- 根拠: `03 §2.1` (不変条件: read-only) / `03 §10` (「unit object が直接編集されても up-to-date 判定」) / `03 §5` (content hash 不採用)。

**CT2-UNIT-011** — P1 — up_to_date 状態分類 (Step 2 で判定可能な全状態)
- Given: (a) 未 Markdownize / (b) 全 unit done / (c) raw 変化 / (d) tool_profile 変化 / (e) 一部 unit failed /
  (f) manifest done だが unit object 欠落。
- When: `kio status` 相当の判定。
- Then: (a)`pending` (b)`up_to_date` (c)`modified` (d)`tool_changed` (e)`partial` (f)`missing_output`。
  判定は「最新 instance の manifest + unit object の存在のみ」で、Markdown content hash 一致は条件に含めない。
- 根拠: `03 §6` (判定擬似コード / 状態分類 8 種) / `03 §5`。
- 補足: `corrupted` (Markdown content hash 不一致) は採用しない (`03 §6`)。

**CT2-UNIT-012** — P2 — prepared_units 台帳は cache (再構築可能)
- Given: prepared_units 台帳を消去。
- When: raw object + 決定論的 prepare で再構築。
- Then: `(raw_hash, unit_key, prepared_hash, unit_type, fingerprint, order_index)` が同一に再生成される。
- 根拠: `04 §4.7` (「この表は cache。raw object + 決定論的 prepare から再構築可能」) / `04 §5.7`。

**CT2-UNIT-013** — P0 — full Markdownize 初回出力の schema と永続化
- Given: 未 Markdownize のファイル (done run なし)。full モードで Markdownize が成功。
- When: 生成された normalized instance を検査。
- Then: instance `g0` が生成され、manifest は `03 §2.1` schema (CT2-UNIT-003) を満たし全 unit
  `status="done"`。各 unit object は `unit_key / unit_type / raw_hash / prepared_hash /
  tool_profile_hash / gen=0 / mode="full" / markdown / reused_from=null / generated_at (UTC ISO8601+Z)`
  を持つ。以後の up_to_date 判定 (`03 §6`) が `up_to_date` を返す。
- 根拠: `03 §2.1` (unit object schema / manifest) / `04 §2` (unit 単位 Markdownize) / `03 §6` / `06 §12` (timestamp)。
- 補足: incremental 偏重を避けるための full 経路の直接検証。V6 (full 出力契約) の正常系に相当。

### CT2-INCR-* — incremental 発動条件 (AND 5) と否定 (`04 §3.1` / `07 §8.4`)

> 5 条件は AND。**1 条件でも欠ければ full へ自動 fallback** (`04 §3.1` 末尾)。各否定を個別テスト化する。

**CT2-INCR-001** — P0 — 5 条件すべて成立 → incremental で呼ぶ
- Given: (1) 同一 file_id に既存 done run あり (2) raw_hash のみ変化・tool_profile_hash 不変
  (3) Adapter が `capabilities=["incremental_update"]` を宣言 (4) 変化率 0.09 (RATE-A, < 0.30)
  (5) 直前連続 incremental 回数 < 5。
- When: Markdownize task を組む。
- Then: `mode=incremental` で Adapter を呼び、入力契約 (`04 §3.1`) の `new_raw / previous / hints / tool_profile_hash / spec_version`
  を渡す。`hints.changed/added/removed` は unit_mapping の帰結、unchanged unit は Adapter に渡さない。
- 根拠: `04 §3.1` (発動条件 5 / Adapter 入力契約)。

**CT2-INCR-002** — P0 — 否定1: 既存 done run 無し (初回) → full
- Given: 当該 file_id の done normalization_run が存在しない。
- When: Markdownize。
- Then: `mode=full`。
- 根拠: `04 §3.1` (条件 1)。

**CT2-INCR-003** — P0 — 否定2: tool_profile_hash も変化 → full
- Given: raw_hash と tool_profile_hash の両方が変化 (tool_changed)。
- When: Markdownize。
- Then: `mode=full` (別 identity のため incremental の previous を張れない)。
- 根拠: `04 §3.1` (条件 2「raw_hash のみ変化」) / `03 §6` (tool_changed)。

**CT2-INCR-004** — P0 — 否定3: capability 宣言なし → 常に full
- Given: Adapter が `incremental_update` を宣言しない (同梱 deterministic 等)。
- When: Markdownize。
- Then: Kio は**常に** full モードで呼ぶ (後方互換)。
- 根拠: `04 §3.1` (条件 3) / `07 §8.4` (「capabilities に incremental_update を含まない Adapter は常に full」)。

**CT2-INCR-005** — P0 — 否定4: 変化率 ≥ threshold → full
- Given: 変化率 0.40 (RATE-B ≥ default 0.30)。
- When: Markdownize。
- Then: `mode=full`。threshold は `.kio/config.toml [markdownize.incremental] threshold` (default 0.30)。
- 根拠: `04 §3.1` (条件 4) / `03 §11` (threshold 設定)。

**CT2-INCR-006** — P0 — 否定5: 直前 N 回連続 incremental → full 強制 (style drift 防止)
- Given: 直前 5 回 (default `max_consecutive`) 連続 incremental。
- When: 6 回目の Markdownize。
- Then: `mode=full` を強制。
- 根拠: `04 §3.1` (条件 5) / `03 §11` (`max_consecutive=5`)。

**CT2-INCR-007** — P1 — 連続回数カウンタ復元不能時は full 強制 (安全側)
- Given: `kio repair --rebuild-db` で incremental 連続回数カウンタが復元不能。
- When: 次回 Markdownize。
- Then: full を強制 (style drift 防止側に倒す)。
- 根拠: `04 §5.7` (「incremental の連続回数が復元不能な場合、次回 Markdownize は full を強制」)。

**CT2-INCR-008** — P0 — identity は incremental/full で不変
- Given: 同一 (raw_hash, tool_profile_hash) を incremental と full で生成 (出力 Markdown は異なりうる)。
- When: identity を比較。
- Then: identity は `(raw_hash, tool_profile_hash)` のまま。`tool_profile_hash` 入力に incremental flag を含めない。
- 根拠: `04 §3.1` (「identity 不変性」)。

**CT2-INCR-009** — P1 — spec_version 不一致 → Adapter は invalid_input 失敗、Kio は full で呼び直す
- Given: Adapter 入出力 schema の `spec_version` が Kio と不一致。
- When: incremental 呼び出し。
- Then: Adapter は `invalid_input` として失敗し、Kio は当該 Adapter を capability なし扱いにして full で呼び直す
  (index を止めない)。
- 根拠: `07 §8.1` (5) / `07 §8.4` / `10 §12.5` (spec_version bump 規約と full fallback)。

**CT2-INCR-010** — P1 — fallback_to_full=true 受信で full 再投入
- Given: Adapter が incremental 出力で `fallback_to_full=true` を返す。
- When: Kio が受信。
- Then: 同一入力で full モードへ再投入する。閾値 hint が Kio 側と衝突したら Kio 側を優先。
- 根拠: `04 §3.1` (Adapter 拒否権) / `07 §8.1` (4)。

### CT2-ACCEPT-* — incremental 出力の受け入れ検査 V1〜V6 (`04 §3.2` / `07 §8.1`)

> 新 unit 全集合 `N = unchanged 候補 ∪ changed ∪ added` (`04 §3.2`)。各違反を個別テスト化する。
> 違反時は `KIO-E-ADAPTER-CONTRACT-001` で**全体 reject** (unit 1 つも persist しない)、full へ自動 fallback。

**CT2-ACCEPT-001** — P0 — V1 被覆・排他: 3 集合の和 = N かつ互いに素
- Given: `keys(updated_units) ∪ keys(added_units) ∪ unchanged_unit_keys ≠ N` (unit の返し忘れ)、
  または 3 集合が交差 (二重出力)。
- When: persist 前検査。
- Then: reject (`KIO-E-ADAPTER-CONTRACT-001`)、full fallback (`fallback_reason="contract_violation"`)。
- 根拠: `04 §3.2` (V1)。

**CT2-ACCEPT-002** — P0 — V2 removed 一致: removed_unit_keys = hints.removed_unit_keys
- Given: Adapter の `removed_unit_keys` が hints と不一致。
- When: 検査。
- Then: reject + full fallback。
- 根拠: `04 §3.2` (V2)。

**CT2-ACCEPT-003** — P0 — V3 越権禁止: keys(updated_units) ⊆ hints.changed_unit_keys
- Given: hints.changed に無い unit を updated_units で書き換え (unchanged unit の再出力)。
- When: 検査。
- Then: reject + full fallback。
- 根拠: `04 §3.2` (V3)。

**CT2-ACCEPT-004** — P0 — V4 added 一致: keys(added_units) = hints.added_unit_keys
- Given: `keys(added_units) ≠ hints.added_unit_keys`。
- When: 検査。
- Then: reject + full fallback。
- 根拠: `04 §3.2` (V4)。

**CT2-ACCEPT-005** — P0 — V5 形式: markdown 非空 + unit_key/unit_type 整合
- Given: updated/added unit の `markdown` が空文字列、または `unit_key`/`unit_type` が prepared unit 側と不整合。
- When: 検査。
- Then: reject + full fallback。
- 根拠: `04 §3.2` (V5)。

**CT2-ACCEPT-006** — P0 — V6 mode: mode_used="full" は full 契約として検証
- Given: Adapter が `mode_used="full"` を返す (全 unit を返す)。
- When: 検査。
- Then: full 出力契約 (全 unit が揃っている) で検証し、V1〜V5 は適用しない。
- 根拠: `04 §3.2` (V6)。

**CT2-ACCEPT-007** — P0 — reject の全体性 + full fallback 自動投入
- Given: いずれかの V 違反。
- When: reject。
- Then: 当該応答は unit を 1 つも persist しない (全体 reject)。同一入力で full へ自動 fallback を 1 回投入。
- 根拠: `04 §3.2` (違反時の挙動) / `04 §5.3` (contract_violation: full fallback を 1 回自動投入)。

**CT2-ACCEPT-008** — P1 — full 出力でも V6 違反 → run を failed (invalid_input 系, retry しない)
- Given: full fallback の出力も V6 (全 unit 揃い) に違反。
- When: 検査。
- Then: run を `failed` (invalid_input 系)。retry しない。
- 根拠: `04 §3.2` (「full 出力でも V6 に違反する場合は run を failed (invalid_input 系, retry しない)」)。

**CT2-ACCEPT-009** — P1 — 受け入れ検査は全 Adapter 共通 (Mistral OCR にも適用)
- Given: 文書処理 API 系 (Mistral OCR) の incremental 経路出力。
- When: 検査。
- Then: プロンプト規約 (`07 §8` 生成 LLM 系のみ) は適用されないが、受け入れ検査 (V1〜V6) と入出力 schema は
  適用される。
- 根拠: `07 §8` 冒頭 (「§8.1 の 6 (受け入れ検査) と入出力 schema は全 Markdownize Adapter 共通」)。

**CT2-ACCEPT-010** — P2 — ストリーミング応答は staging → 完了後に一括検査
- Given: SSE / chunked JSON で unit 完了ごとに persist。
- When: 応答完了後。
- Then: staging に貯めた unit を、応答完了後の全体集合に対し受け入れ検査を通した時点で manifest へ一括確定。
  失敗時は完了済み unit のみ確定、未完了は pending で再開。
- 根拠: `07 §8.3` (ストリーミング応答)。

### CT2-TASK-* — task 状態機械 / retry / resume / 冪等性 (`04 §5`)

**CT2-TASK-001** — P0 — 状態遷移: pending → running → done / partial / failed
- Given: markdownize task。
- When: 実行。
- Then: 全 unit done → `done`。1+ done かつ 1+ failed → `partial`。全 unit 失敗 or run 前提失敗 → `failed`
  (retryable, `failed → pending`)。`partial → done` は失敗 unit 再投入が全成功時。
- 根拠: `04 §5.2` (状態遷移)。

**CT2-TASK-002** — P0 — retry budget: エラー種別ごとの max_attempts と error_code
- Given: 各エラー種別。
- When: retry を評価。
- Then:
  - `network_error` retryable, max 5, deterministic exp(base=2s, cap=60s), `KIO-E-BATCH-NET-001`
  - `rate_limit` retryable, max ∞, honor Retry-After, `KIO-E-BATCH-RATE-001`
  - `auth_error` max 0 (user action), `KIO-E-BATCH-AUTH-001`
  - `quota_exceeded` retryable, max 3, fixed 1h, `KIO-E-BATCH-QUOTA-001`
  - `invalid_input` permanent, max 0, `KIO-E-BATCH-INPUT-001`
  - `contract_violation` permanent, max 0 (full fallback 1 回自動), `KIO-E-ADAPTER-CONTRACT-001`
  - `budget_exceeded` paused, `KIO-E-BATCH-BUDGET-001`
- 根拠: `04 §5.3` (エラー種別と Retry Budget)。

**CT2-TASK-003** — P0 — 冪等性: 同一 (input_hash, tool_profile_hash) 再実行で二重 artifact を作らない
- Given: `(input_hash, tool_profile_hash) → output_ref` が既存 (done)。
- When: 同一 task を再実行。
- Then: done として短絡 (キャッシュヒット、first-instance-wins)。新規 instance を作らず二重課金しない。
  Adapter 層に idempotency_key を要求。
- 根拠: `04 §5.5` (冪等性 / first-instance-wins / idempotency_key) / `03 §6`。

**CT2-TASK-004** — P0 — partial: done unit 保全 + 失敗 unit のみ retry
- Given: partial task (一部 unit failed)。
- When: retry。
- Then: done unit は保全 (first-instance-wins)。retry は**失敗 unit のみ**対象。chunking/embedding/index は
  done unit 由来のみ実行 (failed unit 由来 chunk は index に載せない)。`kio status` に失敗 unit_key と error_kind を表示。
- 根拠: `04 §5.2` (partial の規範) / `03 §6` (partial)。

**CT2-TASK-005** — P1 — retry の再投入形 (capability 有無で分岐)
- Given: 失敗 unit の retry。
- When: 再投入。
- Then: `incremental_update` あり → `mode=incremental`, `hints.changed_unit_keys=失敗 unit`, `previous=同一 instance の done unit`。
  無し → `mode=full` だが done unit は first-instance-wins で保持し失敗 unit の出力のみ採用。
- 根拠: `04 §5.2` (retry は失敗 unit のみ / 分岐)。

**CT2-TASK-006** — P1 — manifest unit status は failed → done の一方向のみ
- Given: partial の失敗 unit。
- When: 再投入成功 / permanent error。
- Then: `failed → done` の一方向遷移のみ。error_kind が permanent (invalid_input 等) の unit は再投入せず
  partial のまま `kio status` に表示し続ける。
- 根拠: `04 §5.2` (manifest unit status 遷移) / `03 §2.1` (`failed → done` 一方向)。

**CT2-TASK-007** — P1 — stale detection: heartbeat + 5min 超過で別 worker が pull 可能
- Given: `running` task の `heartbeat_at + 5min` 超過。
- When: 別 worker が pull。
- Then: stale とみなし再取得可能。
- 根拠: `04 §5.2` (「running が heartbeat_at + 5min を超えたら stale」)。

**CT2-TASK-008** — P1 — resume: 中断状態 (running stale / pending) を再開
- Given: `kio batch resume`。
- When: 実行。
- Then: running stale / pending の task を再開する。
- 根拠: `04 §5.7` (「kio batch resume: 中断状態 (running stale, pending) を再開」) / `06 §1`。

**CT2-TASK-009** — P1 — task テーブル喪失は object store から再検出可能 (attempts のみ喪失容認)
- Given: `task` テーブルを消去。
- When: 次回 index。
- Then: object store + tool profile から未完了作業を再検出・再投入。`attempts` 履歴は失われる (retry 予算リセット) が許容。
  failed の喪失は pending への退行として扱う。
- 根拠: `04 §5.2` / `04 §5.7` (「failed の喪失は pending への退行」/ task 喪失許容)。

**CT2-TASK-010** — P1 — repair --rebuild-db の復元範囲
- Given: SQLite を消去し `kio repair --rebuild-db`。
- When: 再構築。
- Then: 復元される: normalization_runs の done/partial/missing_output 相当、最新 gen、run_id/parent_gen、
  prepared_units 台帳、chunks/embeddings/FTS。喪失容認: failed run 記録 (error/fallback_reason/attempts)、
  parent_run_id チェーン、incremental 連続回数カウンタ。
- 根拠: `04 §5.7` (復元範囲 / 喪失を許容するもの)。

**CT2-TASK-011** — P1 — batch 系 exit code
- Given: batch 実行結果。
- When: exit。
- Then: `0` 全 success/up_to_date、`3` 一部 failed (retryable 残)、`4` 全 failed permanent、
  `5` auth_error あり、`6` budget_exceeded で paused、`7` user 中断。
- 根拠: `04 §5.6` / `10 §12.2`。

**CT2-TASK-012** — P2 — embedding の content ベース再利用
- Given: `(text_hash, embedding profile_hash, dimensions, distance, modality)` 一致の既存 embedding が同一 .kio 内。
- When: embedding task。
- Then: Adapter を呼ばず既存 vector を再利用 (incremental 後の unchanged unit 由来 chunk は再生成しない)。
- 根拠: `04 §5.5` (embedding の content ベース再利用)。**embedding は Step 3 主対象**につき P2。

**CT2-TASK-013** — P1 — task descriptor schema (04 §5.1)
- Given: markdownize task (full / incremental / partial retry の各ケース)。
- When: task descriptor を検査。
- Then: `task_id / type / mode / input_path / input_hash / output_ref / unit_keys / status / attempts /
  next_retry_at / deadline / heartbeat_at / fallback_reason / created_at` を持ち、incremental 時は
  `previous_raw_hash / parent_run_id / changed_unit_keys` を持つ。`unit_keys` は **null = 全 unit 対象**、
  非 null = partial retry の unit スコープ再投入時のみ対象 unit_key の配列。`input_path` は `/` を含まない
  (`03 §3` 規則3)。
- 根拠: `04 §5.1` (タスクモデル / unit_keys の意味) / `03 §3`。

### CT2-BUDGET-* — 二層 cost guardrail (`04 §5.4`)

**CT2-BUDGET-001** — P0 — 二層 cap の判定式 (device と folder の残余 min)
- Given: device cap $50 (当月合算)、folder cap $10 (当該 .kio)。
- When: scope S の新規タスク起動可否を判定。
- Then: 起動可は `ledger(S, 当月) < folder_cap(S)` **かつ** `ledger(device, 当月) < device_cap`。
  effective cap = 両者の残余の min。folder cap 未設定なら device cap のみ。`per_adapter` 下限も両層で判定。
- 根拠: `04 §5.4` (判定式 / 二層)。

**CT2-BUDGET-002** — P0 — cap 到達で新規 paused、走行中タスクは完走
- Given: いずれかの cap を超過。
- When: 判定。
- Then: 走行中タスクは完了させ、新規タスクは `paused`。`kio status` に超過 cap 種別 (`device`|`folder`) と scope を表示。
- 根拠: `04 §5.4` (「走行中タスクは完了させ、新規タスクは paused」/ status 表示)。

**CT2-BUDGET-003** — P0 — --override-budget で両層無視して再開
- Given: budget pause 状態。
- When: `kio batch resume --override-budget`。
- Then: 当月の device cap / folder cap の**両方**を無視して再開。
- 根拠: `04 §5.4` / `06 §1` (「budget 超過 pause は --override-budget 必須」)。

**CT2-BUDGET-004** — P1 — cost ledger はデバイスグローバル 1 個 + scope_id 付与
- Given: 複数 .kio のタスク実行。
- When: コスト記録。
- Then: `~/.local/share/kio/cost-ledger.sqlite` (デバイスグローバル 1 個) に Adapter 報告値
  (input/output token × 単価) を記録し、各記録に `scope_id` を付与。`.kio` 内に ledger を置かない。
  folder cap 判定は ledger の scope 別集計。
- 根拠: `04 §5.4` (ledger の配置 / scope_id 付与 / cache-truth 規約)。

**CT2-BUDGET-005** — P1 — budget pause 時の batch exit code = 6
- Given: budget_exceeded で paused。
- When: batch コマンドが exit。
- Then: exit 6。
- 根拠: `04 §5.6` / `10 §12.2` (`6 budget_exceeded により paused`)。

**CT2-BUDGET-006** — P2 — ローカル LLM は単価 0 (cap に効かない)
- Given: offline_api ローカル LLM 利用。
- When: コスト記録。
- Then: 単価 0 として記録 (= cap に効かない)。
- 根拠: `04 §5.4` (「ローカル LLM 利用時は単価 0」)。

**CT2-BUDGET-007** — P1 — deterministic タスク優先スケジュール (budget pause の影響範囲)
- Given: 初回大量投入 (deterministic タスクと online Adapter タスクが混在)、途中で budget cap 到達。
- When: スケジュールと task 状態を検査。
- Then: deterministic タスク (Prepare / ベースライン抽出) が online Adapter タスク (Markdownize online /
  Embedding) より優先してスケジュールされ、ベースライン index のタスク群が budget pause 下でも
  `done` まで完走する (paused になるのは online タスクのみ)。
- 根拠: `04 §5` (「deterministic なタスク…を online Adapter タスク…より優先してスケジュールし、
  ベースライン index を先に完了させる」) / `07 §2.1`。
- 補足: 「検索の成立自体は阻害されない」(`04 §5`) の**検索側の検証は Step 3** (§D)。本テストは
  その前提となる task 状態のみを assert する。

### CT2-APPROVE-* — 初回スキャン preview + 承認 (`10 §1` / `06 §2`)

**CT2-APPROVE-001** — P0 — 未承認 scope の非対話 index は exit 2 で失敗
- Given: 未承認 scope、非対話環境 (`isatty=false`)、`--yes`/`--approve` なし。
- When: `kio index`。
- Then: exit 2 で失敗 (何も書き込まない)。
- 根拠: `06 §2` (「非対話環境では … `--yes`/`--approve` がない限り exit 2」) / `10 §1`。

**CT2-APPROVE-002** — P0 — --preview は何も書き込まない
- Given: 未承認 scope。
- When: `kio index --preview`。
- Then: preview のみ表示、raw object 保存・Adapter 実行を開始しない。
- 根拠: `06 §2` (「preview のみ。何も書き込まない」)。

**CT2-APPROVE-003** — P0 — preview の必須表示項目
- Given: `kio index --preview`。
- When: preview を検査。
- Then: 少なくとも root/scope、推定ファイル数、推定容量、大容量ファイル、有効 ignore、除外候補、
  secrets 機微候補警告 (Tier A/B)、network transmission policy、adapter execution mode、
  markdownize/embedding コスト概算、現行 budget cap での推定完了時期 を表示。
- 根拠: `10 §1` (preview 表示項目リスト) / `06 §2` (preview 内容)。
- 補足: テスト実装は上記を**項目ごとに個別 assert** する (一括文字列比較にしない)。項目欠落を
  個別に検出できることが目的。

**CT2-APPROVE-004** — P0 — --approve で承認し index 開始
- Given: 未承認 scope。
- When: `kio index --approve`。
- Then: preview を承認して index を開始する。承認記録を残す (CT2-SECRETS-005)。
- 根拠: `06 §2` (「preview を承認、index 開始」) / `10 §1`。

**CT2-APPROVE-005** — P1 — .kioignore + config の除外適用 (自動除外しない)
- Given: `.kioignore` に除外パターン、config の ignore。
- When: index。
- Then: 除外候補は**提案**でありユーザー承認なしに自動除外しない (唯一の例外は secrets Tier A、CT2-SECRETS-001)。
  `.kioignore` で明示除外したパターンは管理対象外。
- 根拠: `10 §1` (「除外候補は提案であり、ユーザーの承認なしに自動除外しない」) / `06 §2`。
- 補足: `.kioignore` の文法 (gitignore 互換 / negation `!pattern` の順序) は spec 未確定 (§C-5)。

**CT2-APPROVE-006** — P1 — cost 概算が effective budget cap を超える場合は承認前に警告 + 選択肢提示
- Given: 概算合計が当月 effective budget cap を超過。
- When: preview。
- Then: 承認前に警告し、cap 内での推定完了時期 (月数) と選択肢 (ベースラインのみ / .kioignore 調整 / cap 変更 / 続行)
  を提示。
- 根拠: `10 §1` (cost 超過警告と選択肢) / `04 §5.4` (effective cap)。

**CT2-APPROVE-007** — P1 — ベースライン index はどの選択でも先に完了 (初日の検索成立)
- Given: preview の選択肢いずれか。
- When: index。
- Then: ベースライン index は選択に依らず先に完了し、初日の検索が成立する。AI 強化は後段。
- 根拠: `10 §1` (「ベースライン index は選択肢に依らず先に完了」) / `07 §2.1`。

**CT2-APPROVE-008** — P2 — 承認後の AI 強化進捗を隠さない
- Given: AI 強化が paused/pending。
- When: `kio status`。
- Then: done/pending/paused 件数と paused 理由 (budget/auth/rate limit) を表示。検索は部分 index 時 `index_status` を返す
  (返却自体は Step 3)。
- 根拠: `10 §1` (「AI 強化が未完了・paused の間、その状態を隠してはならない」/ status 表示項目) /
  `05 §1.7` (`index_status` — Step 3)。

### CT2-SECRETS-* — secrets Tier A/B / quarantine / --yes 制約 (`10 §1.1` / `06 §2`)

**CT2-SECRETS-001** — P0 — Tier A はデフォルト除外 (「除外済み」で preview 表示)
- Given: scope に `.env` / `*.pem` / `id_rsa*` / `.ssh/` 等 Tier A 一致ファイル。
- When: `kio index --preview`。
- Then: built-in デフォルト除外として「除外済み」状態で preview に表示。取り込むには明示解除
  (対話承認時の個別選択 または `.kioignore` の negation `!pattern`) が必要。
- 根拠: `10 §1.1` (Tier A / パターン一覧 / 解除方法) / `10 §1`。

**CT2-SECRETS-002** — P0 — --yes は Tier A の解除ができない
- Given: Tier A 一致ファイルを含む scope、`kio index --yes`。
- When: index。
- Then: `--yes` はローカル取り込み承認のみ自動化し、Tier A の解除・Tier B 警告スキップを**行えない**。
  Tier A ファイルは除外されたまま。
- 根拠: `10 §1.1` (規約 3) / `06 §2` (`--yes` の制約 2)。

**CT2-SECRETS-003** — P0 — Tier B は取り込むが online 送信 task を保留 (警告のみ)
- Given: `*credentials*` / `*token*` 等 Tier B 一致ファイル。
- When: index。
- Then: ローカル取り込み (CAS 保存・ローカル index) は行うが、初回 preview の「機微ファイル候補」欄に列挙。
  承認後に追加された Tier B 新規ファイルは online_api Adapter への送信 task を pending のまま保留し `kio status` に表示。
- 根拠: `10 §1.1` (Tier B / 承認後追加の Tier B 扱い) / `10 §1`。

**CT2-SECRETS-004** — P0 — quarantine: 承認後追加の Tier A 新規ファイルは取り込み保留
- Given: scope 承認後にフォルダへ追加された Tier A 一致ファイル。
- When: 自動処理。
- Then: 取り込み自体を保留 (quarantine)。CAS 保存・snapshot への取り込みを行わない。`kio status` に
  「取り込み保留 (secrets 候補)」表示。取り込みには対話確認 または `.kioignore` 明示編集を要する。
- 根拠: `10 §1.1` (「承認後に追加されたファイルの扱い」Tier A: quarantine)。

**CT2-SECRETS-005** — P1 — approval_method の記録 (interactive | approve | yes)
- Given: 各承認経路。
- When: 承認記録を検査。
- Then: 承認記録に `scope_id / root_path / approved_at / actor / approval_method / kio_version /
  effective_ignore_hash / estimated_*` を残す。`approval_method` は対話=`interactive`、`--approve`=`approve`、
  `--yes`=`yes` を記録し、事後監査で区別できる。
- 根拠: `10 §1` (承認記録項目) / `06 §2` (「approval_method に "yes" が記録され、対話承認と事後監査で区別」)。

**CT2-SECRETS-006** — P2 — secrets テンプレート版を effective_ignore_hash に含める
- Given: built-in secrets テンプレート。
- When: effective_ignore_hash を算出。
- Then: テンプレートのバージョンを入力に含める。テンプレート変更は破壊的変更扱い。
- 根拠: `10 §1.1` (規約 1, 4)。

### CT2-NETWORK-* — network opt-in (`07 §3` / `06 §2`)

**CT2-NETWORK-001** — P0 — 未承認 scope では online task 不発行・pending 残留
- Given: network opt-in 未成立の scope、`kio index --yes`。
- When: index を開始。
- Then: online_api Adapter への送信 task は**発行されず pending のまま残る**。Markdownize は同梱 deterministic
  Adapter で実行 (タスクを止めない)、Embedding task は生成しない。
- 根拠: `07 §3` (default: no network transmission / opt-in 未成立) / `06 §2` (`--yes` の制約 1) / `07 §2.1`。

**CT2-NETWORK-002** — P0 — --approve で opt-in 成立、--yes では成立しない
- Given: 初回スキャン承認フロー。
- When: (a) 対話承認 または `--approve` で network transmission policy を承認 / (b) `--yes`。
- Then: (a) opt-in 成立 (online task 発行可) / (b) opt-in 不成立 (online task 不発行)。
- 根拠: `07 §3` (成立: 対話承認 または `--approve`。`--yes` では成立しない) / `06 §2`。

**CT2-NETWORK-003** — P1 — opt-in の単位は scope × adapter
- Given: 2 つの online_api Adapter (tool_id 別) と 2 scope。
- When: 一方の (scope, adapter) のみ承認。
- Then: 承認は当該 (scope_id, tool_id) の組にのみ効く。別 scope・別 adapter には波及しない。
- 根拠: `07 §3` (「単位: scope × adapter」)。

**CT2-NETWORK-004** — P1 — opt-in の寿命と失効 (tool_id / execution_mode 変更で再承認)
- Given: 承認済みの Adapter の `tool_id` または `execution_mode` が変わる。
- When: 送信判定。
- Then: opt-in は失効し再承認を要する。それ以外は永続 (revoke まで)。
- 根拠: `07 §3` (寿命: 永続。tool_id/execution_mode 変更で失効)。

**CT2-NETWORK-005** — P1 — revoke で新規オンライン送信 task を停止
- Given: `.kio/config.toml` の `adapter.policy.allow_network = false`。
- When: 以後の index。
- Then: 当該 scope の新規オンライン送信 task を発行しない (送信済みデータの取り消しは保証しない)。
- 根拠: `07 §3` (revoke)。

**CT2-NETWORK-006** — P1 — --online / --offline の一時 override と優先順位
- Given: (a) opt-in 未成立 scope で `--online` を 1 回指定 / (b) `allow_network=true` の scope で `--offline` を指定。
- When: 実行。
- Then: (a) その 1 回の実行に限り online task 発行可。**永続記録を作らない** (次回実行は opt-in 未成立に戻る)。
  (b) その実行では online task を発行しない。優先関係は
  `CLI (--online/--offline) > .kio/config.toml (scope) > ~/.config/kio/config.toml (user)`。
- 根拠: `07 §3` (`--online` は一時 opt-in / 優先関係)。
- 補足: `--online`/`--offline` フラグは `06 §1` の正本コマンド一覧 (kio index 構文) に**未掲載**。
  `06 §1` は「他 spec が新しいフラグに言及する場合、本節への追加を伴う」と定めるため 06 §1 への
  同期が必要 (**発注側で追記予定**)。それまで本テストの根拠は `07 §3` (network opt-in の正本) とする。

**CT2-NETWORK-007** — P1 — opt-in 承認記録の readback
- Given: network opt-in が成立 (対話承認 または `--approve`)。
- When: 承認記録を読み戻す。
- Then: 記録に `scope_id / tool_id / approved_at / approval_method` が含まれ、成立した (scope, adapter)
  の組を事後監査で特定できる。
- 根拠: `07 §3` (「記録: 承認記録 (10-operations.md §1) に scope_id / tool_id / approved_at /
  approval_method を残す」) / `10 §1` (承認記録)。

### CT2-ADAPTER-* — 同梱 deterministic Adapter / Mistral OCR 規約 / 共通メタ (`07 §2.1, §5.2, §4, §7`)

**CT2-ADAPTER-001** — P0 — ベースライン index: キーなしで init→snapshot→search→open が成立
- Given: online Adapter 未設定 (API キーなし)。
- When: `kio index` (承認後)。
- Then: 同梱 deterministic Adapter (plain text / Markdown / コード passthrough + fence 正規化 / PDF text layer 抽出)
  で Markdownize を実行し、ベースライン index を完了する。OCR・レイアウト解析・画像理解は行わない。
- 根拠: `07 §2.1` (同梱 deterministic Adapter / ベースライン index の最低体験ライン)。

**CT2-ADAPTER-002** — P0 — online 未設定/未承認時は deterministic fallback + Embedding task を生成しない
- Given: online Adapter 未設定または network 未承認。
- When: Markdownize / Embedding task を組む。
- Then: Markdownize は同梱 deterministic Adapter で実行 (止めない)。Embedding task は**生成しない**
  (検索は text fallback)。
- 根拠: `07 §2.1` (「Embedding タスクは生成しない (検索は text fallback)」)。

**CT2-ADAPTER-003** — P1 — Mistral OCR: 表は Markdown 本文に inline (独立 table object を作らない)
- Given: 表を含む文書を `mistral_ocr_markdownize` で Markdownize。
- When: 出力を検査。
- Then: 表は Markdown 本文に inline (`table_format=null` 相当)。独立 table object を作らない。
- 根拠: `07 §5.2` (表 inline / 独立 table object を作らない)。

**CT2-ADAPTER-004** — P1 — Mistral OCR: bbox / page / confidence は unit metadata に記録 (Evidence Pointer 必須 schema には含めない)
- Given: OCR 出力の bbox / page / confidence。
- When: 記録。
- Then: unit metadata に記録。Evidence Pointer の必須 schema には含めない (optional 露出は Phase 4+ 判断)。
- 根拠: `07 §5.2` (bbox/page/confidence は unit metadata / Evidence Pointer 必須 schema 非包含)。

**CT2-ADAPTER-005** — P1 — Mistral OCR は版付きモデル名で呼び、model_version_pin に記録
- Given: config が `mistral-ocr-latest` (可変 alias) を指定。OCR API は応答内で alias を実版に解決しない。
- When: Adapter 実行開始。
- Then: Adapter が提供元のモデル一覧 API から現行の版付き名を解決してから呼び出し、その版を
  `tool_profile_hash` の `model_version_pin` に記録。モデル更新は `tool_changed` として first-instance-wins / gen 機構に乗る。
- 根拠: `07 §6` (版付きモデル名で呼ぶ pin 規約) / `03 §5.1` (alias 禁止) / `07 §9`。

**CT2-ADAPTER-006** — P1 — 共通メタデータ (AdapterProfile / AdapterRun)
- Given: 任意 Adapter の返却。
- When: メタデータを検査。
- Then: `AdapterProfile` は `adapter_kind / adapter_id / execution_mode / tool_profile_hash / version /
  capability_flags / allow_network`。`AdapterRun` は `task_id / input_hashes / output_hashes / status
  (pending|running|done|partial|failed) / error_kind (=error_code)`。
- 根拠: `07 §4` (共通メタデータ) / `06 §8` (error_code)。

**CT2-ADAPTER-007** — P1 — task/artifact descriptor (Adapter 境界の内部 API)
- Given: Kio core → Adapter の呼び出し。
- When: descriptor を検査。
- Then: task descriptor は `task_id / adapter_kind / input_hash / allowed scope / network permission`。
  artifact descriptor は `output_hash / status / error_kind`。実行設定 (url/認証/コマンドパス) は
  device-local config に置き `.kio/` に保存しない。
- 根拠: `07 §2` (task/artifact descriptor) / `06 §9` (Adapter API / 実行設定は device-local)。

**CT2-ADAPTER-008** — P1 — Adapter policy: allowed_scope 外を渡さない / allow_network=false に online task を発行しない
- Given: `[adapter.policy] allowed_scope="." allow_network=false`。
- When: task 発行。
- Then: Kio は allowed_scope 外のファイルを Adapter に渡さない (入力制御)。allow_network=false の Adapter に
  オンライン送信前提の task を発行しない。AdapterRun を監査ログに残す。sandbox 強制ではなく宣言 + 事後監査。
- 根拠: `07 §7` (policy) / `07 §7.1` (信頼境界: 入力制御 + 事後監査、sandbox 保証ではない)。

**CT2-ADAPTER-009** — P1 — ログの redaction (原文本文 / request/response body / 秘密情報は残さない)
- Given: Adapter 実行のログ。
- When: ログを検査。
- Then: 残してよい: `task_id / adapter_id / tool_profile_hash / input_raw_hash / output_hash / status /
  error_kind / started_at / finished_at`。残してはならない: 原文本文 / normalized 本文 / API request body /
  API response body / 秘密情報。`redact_logs` デフォルト true。
- 根拠: `07 §7` (ログに残してよいもの / 残してはならないもの) / `10 §12.6` (redact_logs)。

**CT2-ADAPTER-010** — P1 — 認証情報は .kio/ に含めない (keychain/env/plain prefix)
- Given: Adapter 認証設定。
- When: 保存先を検査。
- Then: `~/.config/kio/tools.toml` or OS keychain に保存。`.kio/` (tool-lock.json / tool_profile_hash 入力) に
  認証情報を混入しない。`auth` は `^(keychain|env|plain):` 形式。`plain:` かつ tools.toml が 0600 でない場合は
  起動時 warn (errors.jsonl level=warn)。
- 根拠: `07 §1` (認証情報の保存規約 / 禁止) / `06 §11`。

**CT2-ADAPTER-011** — P1 — Prepare trait の入出力
- Given: `raw_hash` と `media_type` を入力に PDF を Prepare。
- When: 出力を検査。
- Then: `prepared_object_hashes` / `prepared_unit_hashes` (page 単位) / `image_object_hashes`
  (画像抽出があれば) を返し、metadata に `unit_kind / page_number / mime / fingerprint
  (semantic_fingerprint)` を持つ。prepared object は最初から unit 粒度の CAS object として
  `objects/prepared/ab/cd/<prepared_hash>` に保存される (prepared_hash = バイト列 content hash)。
- 根拠: `07 §5.1` (Prepare trait 入出力) / `04 §2` (物理配置 / unit 粒度 CAS) / `03 §8.1` (prepared_hash)。

**CT2-ADAPTER-012** — P1 — 任意コマンド/URL Adapter の初回実行承認
- Given: 任意コマンド (cmd) / 任意 URL を使う Adapter の初回実行。
- When: 実行前。
- Then: command / URL / scope / network policy を preview し、ユーザー承認を得てから実行する
  (`require_command_confirmation = true`)。承認 UI は信頼境界の前提 (Adapter は trusted code /
  ユーザー権限で実行) を反映した文言にする。
- 根拠: `07 §7` (「任意コマンド/任意 URL を使う Adapter は、初回実行時に command / URL / scope /
  network policy を preview し、ユーザー承認を得る」) / `07 §7.1` (承認 UI 文言)。

**CT2-ADAPTER-013** — P0 — ベースライン artifact と AI 強化 artifact の共存・不変性
- Given: ベースライン index 済み (deterministic 系 tool_profile_hash の instance が存在) の scope で、
  online Adapter の network opt-in が成立。
- When: AI 強化の Markdownize を実行。
- Then: AI 強化の結果は**別 tool_profile_hash** の新しい normalized instance として生成される。
  既存のベースライン instance (manifest / unit object) は**バイト不変**のまま残る (上書き・削除しない)。
- 根拠: `07 §2.1` (「online Adapter を承認した後の AI 強化は、別 tool_profile_hash の artifact として
  …生成する。ベースライン artifact とその Evidence Pointer は不変のまま残る」) / `03 §5` (identity =
  `(raw_hash, tool_profile_hash)`) / `03 §2.1` (unit object read-only)。
- 補足: Evidence Pointer 側の不変性検証は Step 3 (§D)。本テストは artifact (instance) の不変性のみ。

### CT2-IMAGE-* — embedded image 抽出・保存 / object 参照 (`03 §2` / `07 §5.2` / `08 §2.3`)

**CT2-IMAGE-001** — P0 — 文書内 embedded image を image object として保存
- Given: 埋め込み画像を含む文書を Markdownize。
- When: image 抽出。
- Then: 抽出画像を `objects/images/ab/cd/<image_hash>` に保存。`image_hash = "sha256:" + base16(sha256(抽出画像バイト列))`。
  fan-out は image_hash digest の先頭 2/次 2 文字。`media_type` は unit metadata に記録。
- 根拠: `03 §2` (images レイアウト / image type Step 2) / `03 §8.1` (image_hash = content hash) / `07 §5.2`。

**CT2-IMAGE-002** — P0 — Markdown 内の画像参照を kio:// object URI に置換
- Given: 抽出済み image_hash。
- When: Markdown を組み立て。
- Then: Markdown 内の参照を `kio://<scope_id>/object/image/<image_hash>` に置換。この URI は object 参照であり
  Evidence Pointer ではない (第 2 セグメントがリテラル `object`)。
- 根拠: `07 §5.2` (参照置換) / `08 §2.3` (`kio://<scope_id>/object/image/<image_hash>` / object 参照の区別)。

**CT2-IMAGE-003** — P1 — 生成する object 参照 URI の形式 (解決は Step 3)
- Given: Markdownize が生成した Markdown 内の image 参照 URI。
- When: URI を検査。
- Then: `kio://<scope_id>/object/image/<image_hash>` 形式で、`<scope_id>` は当該 scope の scope.json の
  実値、`<image_hash>` は `sha256:` prefix 込みの実 image_hash (CT2-IMAGE-001 で保存された object と一致)。
  第 2 セグメントはリテラル `object` (Evidence Pointer URI の第 2 セグメント commit は常に `sha256:`
  prefix を持つため衝突しない)。
- 根拠: `08 §2.3` (object 参照 URI の形式 / Evidence Pointer との区別)。
- 補足: `kio open` による当該 URI の**解決**は Step 3 (`09 §3.1`: kio open = Step 3)。Step 2 の契約は
  **URI 生成まで** (r2 で縮小)。

**CT2-IMAGE-004** — P2 — Mistral OCR の placeholder 形式も §5.2 想定どおり
- Given: OCR が画像を placeholder として返すケース (2026-07-03 実地検証: placeholder 形式 1/1)。
- When: image 抽出・参照置換。
- Then: placeholder 経由でも image object 保存 + kio:// 参照置換が成立。
- 根拠: `07 §5.2` (実地検証注記: placeholder 形式も §5.2 想定どおり)。

### CT2-INDEX-* — index preview→snapshot / auto snapshot (`05 §8.1` / `06 §1` / `09 §1.1`)

**CT2-INDEX-001** — P0 — index 一連: preview → approve → 取り込み → auto snapshot
- Given: 未承認 scope に変更あり。
- When: `kio index --approve` (承認後 index)。
- Then: preview 承認 → raw object 保存 → (deterministic/online) Markdownize → 成功完了時に同一プロセス内で
  auto snapshot (commit_type=auto) を作る。
- 根拠: `10 §1` (必須フロー) / `05 §8.1` (契機 2) / `09 §1.1` (「kio index 完了時の auto snapshot」)。

**CT2-INDEX-002** — P0 (CT-COMMIT-008 継承) — index 成功完了時に commit_type=auto を生成 (tree 変化時)
- Given: working tree に変更あり (tree_hash が HEAD と異なる)。
- When: `kio index` 成功完了。
- Then: 同一プロセス内で `commit_type=auto` の commit が 1 つ作られる。commit object は Step 1 の schema
  (`03 §8`) に従い、`tool_lock_hash` には**実装の実 tool-lock.json から `03 §5.2` の規約で算出した値**が
  注入される (Step 1 historical CT-HASH-004 のダミー値からの差分。A.3 は算出規約の fixture であり、実運用値が
  A.3 の値と一致することは要求しない)。
- 根拠: `05 §8.1` (契機 2) / `09 §1.1` / `03 §8.1` (commit schema)。旧 Step 1 の auto-commit case を本書の Step 2 ゲートへ移したもの。

**CT2-INDEX-003** — P0 — tree 不変なら auto snapshot は no-op
- Given: index 実行後、tree_hash が現在の HEAD の tree と一致 (working tree 実質不変)。
- When: index 成功完了時の auto snapshot 契機。
- Then: 新 commit を作らない (no-op)。tree も CAS なので新規 object を生成しない。HEAD 不変。
- 根拠: `05 §8.1` (「tree_hash が現在の HEAD の tree と一致する場合は commit を作らない (no-op)」) / `03 §8.2`。

**CT2-INDEX-004** — P1 — index 完了時 commit イベントが events.jsonl に記録される
- Given: auto snapshot が commit を作る。
- When: `~/.local/share/kio/logs/events.jsonl` を読む。
- Then: commit イベント行が追記され、必須フィールド `ts, level, code, component, message, context` を持つ。
  `ts` は UTC ISO8601+Z。
- 根拠: `05 §7` / `10 §12.6` / `06 §12` (timestamp)。

**CT2-INDEX-005** — P1 — Markdownize 済みファイルの tree entry は normalize ブロック付き
- Given: Step 2 で Markdownize されたファイルの commit tree。
- When: tree entry を検査。
- Then: 当該 entry は `normalize: { tool_profile_hash, gen }` を持つ。未 Markdownize のファイルは `normalize` を省略
  (null を書かない)。tree entry の `gen` は commit 時点で参照した instance の世代。
- 根拠: `03 §8` (「Step 2 で Markdownize されたファイルから順に normalize 付き entry へ移行」/ 省略と null を識別しない)。

**CT2-INDEX-006** — P2 — 直下ファイル数 soft limit (10,000) 超過で警告 + 継続
- Given: 直下ファイル数が 10,000 (soft limit) を超える scope。
- When: `kio index`。
- Then: 警告を表示 (サブフォルダ分割 or ignore を提案) するが処理は継続 (エラーにしない)。
- 根拠: `03 §8.2` (「超過時 kio index は警告を表示し … 処理自体は継続する」)。
- 補足: Step 1 には `kio index` が無く P2 だったが、Step 2 で index 実装につき本書で検証する。

**CT2-INDEX-007** — P1 — 対象ファイルを含むサブフォルダに子 .kio を生成 (ignore サブツリーには生成しない)
- Given: 対象ファイルを含むサブフォルダと、ignore されたサブフォルダ。
- When: `kio index`。
- Then: 対象ファイルを含むサブフォルダには子 `.kio` を生成 (独立スコープ)。ignore サブツリーには生成しない。
  親 tree にはサブフォルダ配下を含めない (直下のみ、`03 §3`)。
- 根拠: `03 §3` 規則2 (子 .kio 生成 / ignore は生成しない) / `10 §4` / `06 §1`。

---

## C. 未定義事項 (spec に無い挙動 — 実装者判断 + 要 spec 追記)

> これらは **憶測で契約化しない**。各テストは「実装が選んだ挙動を固定し決定論性を assert する」に留め、
> 値の正本化は spec 追記後に行う。**要-spec は #1〜#5 の 5 件**。#1〜#4 (いずれも fingerprint /
> prepared / unit_key / prompt 正規化の**決定性**に関わり、artifact identity の再現性を左右する) は
> **2026-07-03 に発注側が spec 追記予定** (クロスレビューで妥当性確認済み)。#5 (.kioignore) は
> `10 §11` が「追記予定」と明記済みの既知 TODO。#6 以降は実装者判断で固定し、事後に spec へ反映すれば足りる。
>
> (r2 注記: 旧 #6「sampling float の JCS 直列化」は spec 未定義ではない (`03 §5.1` が RFC 8785 準拠と
> 定義済み) と再判定し、本書の計算手段の制約として A 節冒頭の注記へ移設した。以降の番号を繰り上げ。)

1. **page fingerprint の具体アルゴリズム (要-spec, 決定性。2026-07-03 追記予定)** — `04 §2.1` は fingerprint を
   `(perceptual hash, text hash, visual hash)` の三つ組と定義するが、各 hash の**具体アルゴリズム**
   (どの perceptual hash / visual hash / 正規化・量子化パラメータ) が未定義。fingerprint 一致は
   unit 再利用 (LLM 呼び出し省略) と unit_mapping の分岐を左右するため、実装ごとに揺れると
   incremental の再現性が崩れる。影響: CT2-UNIT-004/006/007。**Step 2 実装の最初の意思決定点**。

2. **prepared_hash のバイト列決定性 (要-spec, 決定性。2026-07-03 追記予定)** — `04 §4.7` / `07 §2` は
   prepared object を「決定論的 prepare から再構築可能」とするが、PDF page image 等の**レンダリング決定性**
   (DPI / レンダラ / フォント埋め込み / 色空間) が未定義。prepared_hash 一致は再利用判定条件の一つ
   (`04 §2.1`) だが、レンダラ差でバイトが変わると prepared_hash が不一致になる。影響: CT2-UNIT-002/004/012 /
   CT2-ADAPTER-011。

3. **unit_key の正準生成規則 (要-spec, 決定性。2026-07-03 追記予定)** — `04 §2` は unit_key を `page:12` /
   `slide:3` / `sheet:Sheet1` 等と例示するが、page の 0/1-index 起点、sheet 名の正規化 (空白・大文字・重複名)、
   DOCX/Markdown の heading section の unit_key 生成規則が未定義。unit_key は `unit_ref` 算出
   (`03 §2.1`) と Evidence Pointer の入力なので determinism-critical。影響: CT2-UNIT-001 (ベクタは
   与えられた unit_key 文字列に対しては確定するが、**その文字列をどう作るか**が未定義)。

4. **prompt_template_hash step1 の空白定義と CR 単独の扱い (要-spec, 決定性。2026-07-03 追記予定)** —
   `03 §5.1` の「trim trailing whitespace per line」の**対象文字集合** (半角空白/タブのみか、`\f`/`\v`/
   全角空白も含むか) と、CRLF 以外の lone CR (`\r`) を step1/step2 のどちらで処理するかが未定義。
   A.2 ベクタは「半角空白・タブを行末空白、CRLF を step2 で `\n` 化」の解釈で計算した (spec 追記との
   一致確認後に確定契約とする — CT2-PROFILE-005 補足)。影響: CT2-PROFILE-005。

5. **.kioignore の文法仕様 (要-spec, 既知 TODO)** — `10 §11` が「.kioignore spec → 03-data-model.md へ
   追記予定」と**明示的に未統合**と認めている。gitignore 互換か、negation `!pattern` の評価順・文法詳細が
   未定義 (negation による Tier A 解除という**操作の存在自体**は `10 §1.1` 規約 2 で定義済み — 未定義なのは
   文法と評価順のみ)。影響: CT2-APPROVE-005 / CT2-SECRETS-001。

6. **incremental 連続回数カウンタの数え方** — `04 §3.1` 条件5 / `03 §11` `max_consecutive` の
   「直前 N 回連続」が file_id 単位か instance chain 単位か、full を挟んだらリセットされるか、が明示なし。
   `04 §5.7` は「復元不能なら full 強制」とのみ。影響: CT2-INCR-006/007。実装者判断で固定。

7. **task_id / run_id の生成形式** — descriptor 例 (`04 §5.1`) は `task_01H...` / `run_01H...` と ULID を
   示唆するが、生成規約 (ULID か / 一意性保証 / 衝突時挙動) が明記なし。影響: CT2-TASK-* / CT2-TASK-013。実装者判断。

8. **cost-ledger.sqlite の schema** — `04 §5.4` は配置とキー (`scope_id` 付与) を定めるが、テーブル schema
   (期間集計の粒度、月境界の TZ) が未定義。folder/device cap の集計に影響。影響: CT2-BUDGET-004。実装者判断。

9. **quarantine 解除の記録形式** — `10 §1.1` は quarantine 解除に「対話確認 または .kioignore 明示編集」を
   要すると定めるが、解除操作の記録 (誰が/いつ/どのファイル) の形式が未定義。影響: CT2-SECRETS-004。実装者判断。

10. **scanned PDF (text layer 無し) の deterministic Adapter 挙動** — `07 §2.1` は deterministic Adapter が
    「PDF text layer 抽出」を行うとするが、text layer が無い scanned PDF で unit をどう作るか
    (空 unit / skip / pending) が未定義。ベースライン index の被覆に影響。影響: CT2-ADAPTER-001。実装者判断。

11. **Mistral OCR image placeholder の正確な token 形式** — `07 §5.2` 実地検証注記は placeholder 形式に触れるが、
    Markdown 内の placeholder token の正確な文字列と kio:// 置換の対応規則が未明記。影響: CT2-IMAGE-004。実装者判断。

---

## D. Step 2 範囲外として意図的に除外したもの (根拠付き)

以下は Step 2 の契約テストに **含めない**。理由は `09 §3.1` (機能×Step 割当) と各正本 §。

| 除外項目 | 除外理由 (根拠) |
| --- | --- |
| chunk / Embedding の**生成本体** / FTS5 / sqlite-vec | `09 §3.1`: Step 3 (`04 §4`)。本書は embedding の再利用短絡 (CT2-TASK-012, CT2-BUDGET) を **P2 参考**に留め、chunk identity・chunking_config_hash・chunk_fts trigger は対象外 |
| 検索 (text/vector/hybrid/RRF/MMR/cursor/multi-scope) / `kio search` / `index_status` | `09 §3.1`: Step 3 (`05 §1`)。CT2-ADAPTER-002 の「text fallback で検索成立」は成立可能性の設計前提としてのみ言及し、検索実体は検証しない |
| Evidence Pointer の**発行・解決** / `kio open` / `kio view` / verify / retarget | `09 §3.1`: Step 3-4 (`08`)。本書は image object の `kio://object` URI の**生成形式** (CT2-IMAGE-002/003) と、Evidence Pointer に bbox を載せない契約 (CT2-ADAPTER-004) のみ参照。`kio open` による URI 解決・pointer 解決本体は Step 3 |
| chunking_config_hash の算出・chunk 世代判定・再 chunk task | `09 §3.1`: Step 3 (`04 §4.6` / `03 §5.3`)。Step 2 の identity は `(raw_hash, tool_profile_hash)` に閉じる |
| `kio reindex --force` (gen+1 の新 instance 作成) | `09 §3.1`: Step 3 (`07 §9`)。Step 2 は通常 gen=0 のみ。gen フィールドの**保持・読み取り**は CT2-UNIT/INDEX で確認するが `--force` 経路は張らない |
| restore / `--at` / `--all-history` / `--include-deleted` / time-travel | `09 §3.1`: Step 4 (`05 §4`) |
| purge (tombstone / `commit_type=purged` 発行 / `--erase-tombstone` / Dead Pointer) / ログスクラブ | `09 §3.1`: Step 4 (`05 §3`, `08 §4`, `10 §7`) |
| GC の**実行** (shallow 化 / tiered retention / prune / CoW / `kio gc`) | `05 §2.2`, `09 §3.1`: Phase 4+。Step 2 は gc_policy schema (Step 1 の CT-GC-* で担保済み) を変えない |
| 定期 auto snapshot / Downloads watch / OS スケジューラ委譲 / on_idle | `05 §8.2`, `09 §3.1`: Phase 4+。Step 2 の auto 契機は **index 完了時のみ** (CT2-INDEX-002) |
| 観測ログのうち `metrics.jsonl` / `access.jsonl` | `09 §3.1`: Step 3。Step 2 が新規に依存するのは events/errors (Step 1 で担保済み) + cost-ledger のみ |
| multimodal embedding profile の**ベンダー実地検証** (次元数/料金/deprecation) | `07 §5.3` リスク注記: Step 2 着手**前**の実地検証タスクであり、契約テストではなく採用判断。緩和 (text 単一 Embedding) 適用時も M3 Done 条件に影響しない |
| Step 1 で担保済みの CAS / tree / commit / hash 算出 / CLI 7 コマンド / lock | 現行の `crates/kio-core/tests/contract_vectors.rs` と CLI behavior tests で担保。本書は commit の `tool_lock_hash` を**実 tool-lock.json からの算出値**で注入する点 (CT2-INDEX-002。A.3 は算出規約の fixture) のみ Step 1 から差分追加 |
| export / import (`.kioz`) / `kio move` / agent API 外部公開 / MCP | `09 §3.1`: Phase 4-5 (`06 §10`, `05 §6`, `06 §9`) |

---

## 集計 (報告用)

- **P0 テスト数**: 52 (r2: 49 + 新規 3 — CT2-PROFILE-010 / CT2-UNIT-013 / CT2-ADAPTER-013)
  (CT2-PROFILE 7 / CT2-UNIT 6 / CT2-INCR 7 / CT2-ACCEPT 7 / CT2-TASK 4 / CT2-BUDGET 3 /
   CT2-APPROVE 4 / CT2-SECRETS 4 / CT2-NETWORK 2 / CT2-ADAPTER 3 / CT2-IMAGE 2 / CT2-INDEX 3)
- **spec 未定義事項**: 11 件 (§C。r2 で旧 #6 を A 節注記へ移設)。うち **要-spec は 5 件**:
  §C-1 (page fingerprint の具体アルゴリズム)、§C-2 (prepared_hash のレンダリング決定性)、
  §C-3 (unit_key の正準生成規則)、§C-4 (prompt_template_hash step1 の空白定義と lone CR) —
  以上 4 件は **2026-07-03 に発注側が spec 追記予定** — および §C-5 (.kioignore 文法、`10 §11` が
  未統合と明記済みの既知 TODO)。残り 6 件は実装者判断で固定 → 事後 spec 反映で足りる。
