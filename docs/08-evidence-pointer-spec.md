# 08 Evidence Pointer Spec

KCS の中核概念 **Evidence Pointer** の正式仕様。外部 AI Agent や他ツールが KCS と相互運用する際の契約となるため、独立 spec として保持する。

> 関連: [03-data-model.md §1, §5](03-data-model.md) (CAS / identity) / [05-runtime.md §3](05-runtime.md) (purge / Dead Pointer) / [02-philosophy.md](02-philosophy.md) (なぜ Evidence Pointer か)

---

# 1. なぜ Evidence Pointer か

通常のファイル検索ツールは「path + 行番号」で根拠を指す。これは:

- ファイル移動・リネームで死ぬ
- 削除で死ぬ
- 上書き保存で意味が変わる
- 過去版に戻れない

KCS は **path ではなく content-addressed object** で根拠を指すことで、これらの脆弱性を排除する。

```
通常:  "report.pdf:42"                  → 移動・リネーム・削除で死ぬ
KCS:   commit + raw_hash + chunk_hash   → ファイル移動・リネーム・削除に耐える
       + path_at_commit + span            (purge されない限り永続)
```

これは KCS の差別化の中核 ([01-positioning.md](01-positioning.md))。

---

# 2. Evidence Pointer のスキーマ

```json
{
  "schema_version": 1,
  "commit": "sha256:9f2c...",
  "tree": "sha256:3f9a...",
  "raw_hash": "sha256:abc123...",
  "tool_profile_hash": "sha256:tool1...",
  "chunk_hash": "sha256:chunk456...",
  "path_at_commit": "report.pdf",
  "heading_path": ["認証仕様", "API Token", "有効期限"],
  "section_id": "認証仕様/api-token/有効期限",
  "byte_start": 1200,
  "byte_end": 1500,
  "scope_id": "scope_01J8ZQ...",
  "scope_path": "/Users/foo/Research/.kcs"
}
```

`path_at_commit` は **commit 時点の scope フォルダ直下でのファイル名** であり、パス区切り (`/`) を含まない ([03-data-model.md §3](03-data-model.md)。**例外**: 03 §3 の forward 規則以前に作られた検証済み legacy tree 由来の entry に限り、区切り等を含む旧 path をそのまま保持する — 表示専用であり resolver 入力には使わない。物理化時の検査は現行どおり)。フォルダ階層上の位置は `scope_path` が示す。人間向け表示ではこの 2 つを組み合わせて表示する (§7.2)。

## 2.1 必須フィールド

| フィールド | 役割 | 不変条件 |
| --- | --- | --- |
| `schema_version` | Evidence Pointer schema の semver | breaking change で bump |
| `commit` | commit object の content hash (commit_hash, [03-data-model.md §8.1](03-data-model.md)) | append-only。GC (shallow 化) でも失われない |
| `raw_hash` | 原文バイト列の identity | 移動・リネームで不変 |
| `tool_profile_hash` | Markdownize Adapter capability の identity | tool 変更で別 chunk に飛ばない保証 |
| `chunk_hash` | chunk object の identity | `(raw_hash, tool_profile_hash, gen, unit_key, heading_path, section_id, byte_start, byte_end)` から導出 (算出式は [03-data-model.md §8.1](03-data-model.md)) |
| `scope_id` | 正本 `.kcs` の path 非依存 identity (`.kcs/scope.json` 保持) | `.kcs` の移動・export/import で不変 |

## 2.2 Optional フィールド

| フィールド | 役割 |
| --- | --- |
| `tree` | 当該 commit の tree_hash (高速解決用。shallow 化済み commit では tree object 自体は存在しないことがある) |
| `path_at_commit` | commit 時点の表示用 path (UI 表示・人間可読性) |
| `heading_path` / `section_id` | chunk の構造的位置 (UI 表示・semantic retarget 用) |
| `byte_start` / `byte_end` | normalized unit 本文内の UTF-8 byte span (unit-local・0-based half-open、[03-data-model.md §8.1](03-data-model.md)) |
| `scope_path` | 生成時点の正本 `.kcs` の絶対パス (解決の高速ヒント + 表示用。解決の root 信頼は `scope_id`) |

表示用 field は、解決が成功した場合は**解決結果の canonical 値 (tree / chunk object 由来) を優先して
表示し、pointer 入力値と相違するときは入力値を無視する** — 正しい必須 tuple に偽の表示 metadata
(path / heading / span) を付けた pointer が、alive 判定のままそのまま人間向け引用に使われることを
防ぐ (これらは解決には元々使わない — §3.1 手順 8 の整合検証は必須 tuple のみ)。

`path_at_commit` は **表示用** であり、解決には使わない。実際の解決は `commit + raw_hash` で行う (path はリネーム履歴をまたいでも追えるが、root 信頼は raw_hash 側)。

`scope_path` も `path_at_commit` と同様 **ヒント** であり、解決の root 信頼にしない。`.kcs` の移動・別マシンへの import 後も、`scope_id` が一致する限り pointer は解決可能である。

## 2.3 正規シリアライズ (canonical serialization)

Evidence Pointer の交換形式は 2 つ。**完全形は §2 の JSON object**、**正規テキスト形は以下の URI** とする。

```text
kcs://<scope_id>/<commit>/<raw_hash>/<tool_profile_hash>/<chunk_hash>[?sv=<schema_version>]

例:
kcs://scope_01J8ZQ.../sha256:9f2c.../sha256:abc123.../sha256:tool1.../sha256:chunk456...
```

規則:

- URI は **必須フィールドのみ** を持つ。optional フィールド (path_at_commit / heading_path / byte_start 等) は
  表示用であり (§2.2)、URI ⇄ JSON の往復で失われてよいのは optional フィールドだけ。
- `sv` (schema_version) 省略時は `1`。**wire 上の `sv` は MAJOR のみの整数** (MINOR/PATCH は載せない —
  optional フィールド追加は sv 不変で、未知フィールド無視則 (§8) が前方互換を担う)。未知の `sv`
  (= 未知 MAJOR) は KCS-E-CONFIG-SCHEMA 系 error (exit 2)。**URI は opaque として扱い、authority 位置
  (scope_id) の大文字小文字を保存する** — 一般 URI 正規化 (authority の小文字化) を適用してはならない。
  lookup は case-sensitive (registry の TEXT キーと一致 — ULID は大文字表記が正)。
- 各セグメントは §2 の同名フィールド値をそのまま置く (hash は `sha256:` prefix 込み、commit は commit_hash、
  [03-data-model.md §8.1](03-data-model.md))。percent-encoding は不要 (値域が `[A-Za-z0-9_:.-]` に閉じるため)。
- 第 2 セグメントがリテラル `object` の URI は **object 参照**であり、Evidence Pointer ではない:
  `kcs://<scope_id>/object/<type>/<hash>` (例: normalized view 内の画像参照
  `kcs://<scope_id>/object/image/<image_hash>`、[07-adapter-spec.md §5.2](07-adapter-spec.md))。
  `kcs open` はこれを受理して該当 object を解決する。Evidence Pointer URI の第 2 セグメント (commit) は
  常に `sha256:` prefix を持つため、リテラル `object` と衝突しない。fork 複製 (`kcs import
  --as-new-scope`) 内の旧 scope_id を含む object URI は、文脈 store に該当 hash の object があれば
  自 store で解決する ([06-cli-spec.md §1.1](06-cli-spec.md) 手順 1a — hash が identity)。

CLI の `<pointer>` 引数はすべて以下の受理規則に従う (優先順位順に prefix で判定):

```text
1. "-"          stdin から 1 つ読む (JSON object または URI 1 行)
2. "kcs://"     URI 形
3. "{"          inline JSON (§2 schema)
4. "sha256:"    短縮形 (kcs open / kcs view のみ): object store を照会して種別を判別し、
                chunk_hash なら chunk、raw_hash なら raw として、カレント .kcs + HEAD を
                文脈に解決する。複数種別に該当し多義なら候補一覧を error で返す
5. その他       parse 失敗 → exit 2 (invalid usage)
```

bulk 系 (`kcs evidence verify --batch <pointers.jsonl>`) は従来どおり各行 JSON object。

---

# 3. Evidence Pointer の解決

```
入力: Evidence Pointer
出力: { raw_object | normalized_unit | chunk_text } または error
```

## 3.1 解決手順

```text
1.  scope の解決 (2 段):
    a. scope_path が指定され、その .kcs の scope.json の scope_id が pointer と一致 → それを使う —
       **ただし「validated scope_path の canonical path ∪ registry の live 行」の重複除去済み候補が
       2 以上の場合は 1a でも選択せず、1b と同じ候補一覧 error とする** (scope_path は表示用 hint で
       ありユーザーの明示選択ではない。registry 未登録 clone の path 指定でも、既知 live 行と合わせて
       2 以上なら同じ error — URI ⇄ JSON の表現差で alive / error が変わることを防ぐ —
       [10-operations.md §3](10-operations.md))
    b. 一致しない・存在しない・scope_path 省略 → scope_registry を scope_id で照会し kcs_path を得る
       (同一 scope_id が複数 **live** 登録されている場合は選択しない — `KCS-E-REGISTRY-DUP-001` の
       候補一覧 error で fail-closed とし、dedupe を要求する ([10-operations.md §3](10-operations.md))。
       purge 状態の異なる clone へ黙って解決すると scope 単位 purge の判定を取り違えるため。
       **候補集合は registry の live 行に加えて validated scope_path の canonical path を含めて数える** —
       registry 未登録の clone を scope_path で指した場合も、既知 live 行と合わせて 2 以上なら同じ error
       (URI 化で optional path が落ちた場合と結果を変えない))
    c. どちらも失敗 → KCS-E-EVIDENCE-SCOPE-UNREACHABLE-001 (scope_unreachable, §3.2)
    (1a/1b の「表現差で変えない」の対象は既知候補集合に対する判定 — scope_path が registry 未登録の
    clone を新たに教える場合に候補が増えて error 側へ倒れるのは fail-closed の意図どおりの**情報差**で
    あり、表現差ではない)
2.  commit を refs / objects/commits/ から取得
2a. commit が shallow (tree 破棄済み) の場合の適用手順は次に限る: **手順 5 (tombstone /
    raw 存在) → pointer の chunk_hash → chunk object → gen で normalized unit instance を
    直接解決 → 手順 7 → 手順 8 (tree entry 系の照合句は対象外)**。手順 3-4・6・6a・6b は
    tree / entry を要するため適用しない — 時点帰属・membership は検証できず、手順 8 の
    shallow 句のとおり --strict verify は unverifiable (exit 3)。chunk object 本体が gen を
    保持するため直接解決できる (03-data-model.md §8)。
    レスポンスに "commit_shallow": true を付す。
3.  tree (commit.tree) を取得
4.  tree から raw_hash で entry を検索 (同一 raw_hash の entry が複数ある場合 — 複数 path への重複配置。
    同一 commit 内では同一 (raw, tool_profile) の normalize binding は共有される — は、**pointer の
    tool_profile_hash と一致する binding の entry を選ぶ** (pointer は gen を持たない — gen の整合は
    手順 8 が tree entry と chunk object の間で検証する)。同一 binding の entry が複数残る場合は
    **path の UTF-8 byte 順最小の entry を決定的に選ぶ** ([05-runtime.md §1.7](05-runtime.md) の `path_at_commit` と同じ規則 — 表示もこの canonical path を使い、pointer 入力の optional path は使わない)。一致 entry が
    無ければ手順 5〜7 を実行せず KCS-E-STORE-CORRUPT-001 (not_found 扱い — 手順 8 の不一致処理と同じ
    終端) へ短絡する)
5.  raw_hash の marker と raw object の存在を、次の評価順で判定する
    (§3.2 の解決成功条件「raw object が存在」をここで検査する):
    (i) **active な tombstone** (lifecycle の末尾 event が `purged` — [05-runtime.md §3.5](05-runtime.md)) が
    あるなら → tombstone を返す (§4)。
    (ii) **active な erase receipt (末尾 event = `erased`) があり raw object が不在**なら not_found —
    `KCS-E-PURGE-NOT-FOUND-001` (§4.2 の表と同一の終端)。
    (iii) **retired (tombstone・erase receipt とも末尾 event = `retired`) は tombstone 扱いしない**が、
    手順 6 へ進む**前に raw object の存在を検査する** — 存在すれば手順 6 へ進む (resurrection 後の
    旧 pointer を alive に戻すための必須条件)。**不在なら not_found — `KCS-E-STORE-CORRUPT-001`**
    (retired 後の再作成分の欠落は corruption — [10-operations.md §7.5.1](10-operations.md) と整合。
    chunk object が残存していても本文を返さない)。
    (iv) marker (tombstone / erase receipt) が無いのに raw object が不在なら not_found — code は
    `KCS-E-STORE-CORRUPT-001` (marker なしの欠落は
    purge の痕跡ではなく **corruption の疑い** — 手順 4 の短絡と同じ not_found 扱いで返し、
    `kcs repair --verify-objects` を案内する。purge 済みの正規欠落 (marker あり) と混同しない)
6.  tree entry の normalize.(tool_profile_hash, gen) で normalized instance (unit object 群) を解決
    (gen フィールド欠落は gen=0 と読む)
6a. **時点帰属の検証 (v2 tree)**: entry の normalize.manifest_hash が指す manifest object を読み、
    chunk の unit_key が当該 manifest で status=done であることを検証する (unit_key は chunk_hash から chunk object の header を読み取って得る — 手順 7 の本文取り出しに先行する read-only 参照) — done でない unit の
    chunk は当該 commit 時点に存在しない (same-gen retry の後着 chunk を過去 commit の証拠として
    返さない → not_found)。**v2/v3 tree ではさらに、chunk の publication と config association の
    introduction ([04-pipeline.md §4.1](04-pipeline.md)) が pointer の commit の ancestor-or-equal で
    あることも検証する** (config association は**対象 tree の `chunking_config_hash` のもの** —
    [05-runtime.md §1.6](05-runtime.md) の検索側と同一の絞り込み。別 config の association は当該
    commit への帰属を証明しない) — manifest で done でも当該 commit 時点で未公開の chunk を証拠にしない
    (cache 参照のため、association の**不在**による失敗は corruption ではなく not_found — rebuild 後に
    再評価できる。**sqlite.db 自体の不在・再構築中はこの検証を実行できない — not_found ではなく
    `KCS-E-INDEX-REBUILDING-001` の再構築要求を返し ([05-runtime.md §6](05-runtime.md))、検証不能を
    「不在の確定」と混同しない**)。
    v1 tree (manifest_hash 欠落) はこれらの検証を行えない — legacy 解決とし、
    --strict verify は shallow 経路と同じく unverifiable (exit 3) を返す
6b. entry の manifest object が purge により欠落している場合 (raw_hash の **tombstone または
    erase receipt** の lifecycle — active / retired を問わず — が説明する欠落): 手順 2a と同じ
    直接解決へ降格し、レスポンスに `manifest_missing: true` を付す。**ただし 2a と異なり 6b は
    手順 4 の tree entry を取得済みであり、手順 8 の entry 系照合 (normalize.tool_profile_hash の
    pointer 一致・gen 一致) は実施する** (降格するのは manifest 依存の検証のみ)。**retired event に
    `resurrection_commit` があれば、そのリンク先 commit の publication を参照して本文を解決し
    alive を返してよい** ([05-runtime.md §3.5](05-runtime.md) — 検索の時点条件には影響しない)。
    時点帰属は検証できないため --strict verify は
    unverifiable (exit 3) — 再 ingest 後の manifest は run_id 等が異なり旧 hash を再生できない
    ([03-data-model.md §2.1](03-data-model.md)) ので、この降格は恒久である。**6b でも 6a の v2/v3 検証
    (publication / association の introduction ancestry) は実施する** — cache は manifest と独立に
    参照でき、失敗 = not_found。ただし**基準 commit は経路で異なる**: リンクを使わない直接解決は
    従来どおり pointer の commit を基準にする (purge → 再 ingest 後の後着 chunk を旧 commit の
    証拠にしない)。**resurrection link 経由の解決は、当該 retired event の `resurrection_commit` を
    基準に検証する** — リンク先 commit が当該 chunk の publication / config association の
    introduction を ancestor-or-equal に持つこと (再 ingest の publication は旧 pointer commit の
    後続にあるため、旧 commit 基準ではリンク経路が恒久に不達になる)。resurrection で alive に
    戻るのは、リンク先 commit 側で**同一 chunking config** の下に同一 chunk が再公開された場合に
    限る — config が変わって chunk 境界が消えた場合の not_found は正 (境界非互換の物理的帰結で
    あり、alive 保証の破れではない)。リンクとして有効なのは
    **末尾が `retired` の lifecycle の最終 retired event のみ** (再 purge 済み = 末尾 `purged` は
    手順 5 で tombstoned)。リンク先 commit が不在・ref 不達、または上記検証に失敗した場合は
    リンクを使わず直接解決の規則へ戻る (それも失敗なら not_found)。
    unverifiable になるのは manifest done 検査のみ。`manifest_missing` は `commit_shallow` と
    独立の response field であり併存し得る
7.  chunk_hash で chunk object を解決し byte_start/byte_end の text を取り出す
8.  **整合検証**: 解決した chunk object の raw_hash / tool_profile_hash が pointer の値と一致し、
    手順 4-6 を経た場合はさらに **tree entry の normalize.tool_profile_hash が pointer の
    tool_profile_hash と一致し**、chunk object の gen が tree entry の gen と一致することを検証する
    (手順 4 の tool 一致選択とは独立に、終端で entry 側の tool 一致を再検証する defense-in-depth —
    この postcondition を欠くと、手順 4 の選択が破損・改変した store 上で迂回された場合に、同一 raw を
    別 tool で normalize した commit に対して gen 値の偶然一致 (双方 0 等) だけで別 tool の chunk が
    当該 commit の証拠として通ってしまう)
    (pointer は gen を持たない — gen の照合対象は tree entry と chunk object 内部のみ)。不一致は
    store corruption として KCS-E-STORE-CORRUPT-001 (not_found 扱い) — cross-wired な pointer が
    別文書の本文を「解決成功」として返すことを防ぐ。**shallow 経路 (2a) は tree membership を検証
    できない** — この限界は `commit_shallow: true` が表明し、`--strict` verify は shallow 経路の解決を
    alive でなく **unverifiable (exit 3)** として返す (時点帰属の偽装を「検証済み」と誤認させない)
```

## 3.2 不変条件

```text
解決成功条件:
  - scope (.kcs) に到達できる
  - commit object が存在 (shallow でもよい。commit object は GC で削除されない)
  - raw object が存在 (purge されていない)
  - chunk object が存在 (= 同一 tool_profile_hash で生成済み)

部分的失敗 (代表例 — status union の正本は §4.3):
  - purged raw_hash (tombstone あり):   tombstoned — tombstone を返す (§4.1)
  - scope 解決の重複 (validated ∪ live 候補 ≥2): registry_duplicate
                                        — KCS-E-REGISTRY-DUP-001 (§3.1 手順 1a)
  - tombstone / erase receipt なしで raw object 不在: not_found — KCS-E-STORE-CORRUPT-001
                                        (corruption の疑い — §3.1 手順 5。repair --verify-objects を案内)
  - 有効 erase receipt (末尾 event = `erased` の active receipt) ありで raw object 不在:
                                        not_found — KCS-E-PURGE-NOT-FOUND-001 (§4.2。`retired` 済み
                                        receipt での欠落は上段の corruption 側 — [10-operations.md §7.5.1](10-operations.md)
                                        の説明範囲限定と整合)
  - scope の .kcs に到達できない:        scope_unreachable — scope_path 不達かつ
                                        scope_registry に scope_id 未登録
                                        → KCS-E-EVIDENCE-SCOPE-UNREACHABLE-001
                                        (.kcs を再接続 / kcs index で registry 再登録すれば回復可能)
  - tool_profile_hash 不一致:           chunk が存在しない場合は retarget が必要 (§5)

補足: shallow commit は pointer 解決の失敗要因ではない (§3.1 手順 2a)。
KCS-E-COMMIT-SHALLOW-001 は restore / diff / `--at <shallow-commit>` 検索 /
cursor 再計算など tree 全体を要する操作に限る ([05-runtime.md §2.2](05-runtime.md))。
```

---

# 4. Dead Evidence Pointer (purge 対応)

「Evidence Pointer の不変性」(§6) と「法務 purge」([05-runtime.md §3](05-runtime.md)) の緊張領域。purge された raw_hash を指す既存 pointer の挙動を以下に固定する (確定。残未決 1 件 = bulk verify スループット — [09-mvp-scope.md §5.3](09-mvp-scope.md))。

## 4.1 Tombstone レスポンス

raw_hash に active な tombstone (末尾 event = `purged`) がある場合 (= purge 済みだが履歴上は記録。retired は該当しない)。レスポンス body の `status` は §4.3 の union と同じ語彙 (`tombstoned`) を使う — purge の事実は `purged_*` フィールドが表す:

```json
{
  "status": "tombstoned",
  "purged_at": "2026-04-25T12:00:00Z",
  "purged_reason": "legal" | "privacy" | "misingest" | "copyright" | "other",
  "purged_in_commit": "sha256:9f2c...",
  "raw_hash": "sha256:abc...",
  "scope_path": "/Users/foo/Research/.kcs"
}
```

「消した事実」は残し、本文・派生 artifact は到達不能にする (= 透明な忘却、[02-philosophy.md](02-philosophy.md))。

## 4.2 NOT-FOUND レスポンス

raw_hash が public tombstone なしで完全削除 (`--erase-tombstone`) されている場合:

```text
error_code: KCS-E-PURGE-NOT-FOUND-001
message: "Evidence target was purged without tombstone record"
context: { raw_hash, scope_path }
```

完全削除は法的要件上必要な場合のみ。デフォルトは tombstone。
`.kcs/purge/erase-receipts/` の bounded non-content receipt は public の tombstone 判定・re-ingest barrier には使わない (**手順 5 の not_found 分類 (§3.1 (ii)〜(iii))・手順 6b の欠落説明・resurrection link にのみ使用可** — [05-runtime.md §3.5](05-runtime.md))。
receipt は pointer state を tombstoned にせず、re-ingest も阻止しないため、レスポンスは上記
`not_found` である。**ただしこの保証は当該 bytes が store に不在の間のもの** — 同一 bytes が後日
再 ingest され (明示操作に限らず、working tree 残存原本の自動 scan を含む — [05-runtime.md §3.5](05-runtime.md)
の残存警告)、同じ identity の chunk が再生成された場合、既存 pointer は再び alive として
解決される (このとき active tombstone は raw の再 publication と同時に**退役**する — [05-runtime.md §3.5](05-runtime.md)
の resurrection 規則。退役なしには「tombstone 最優先」の解決と両立しない。**purge 前 commit を指す
旧 pointer の解決は retired event の `resurrection_commit` リンク経由** — 手順 6b)。ただし **復活後に解決される
本文は再生成 instance のものであり、purge 前と byte 同一である保証はない** (Markdown content hash
不採用の帰結 — [03-data-model.md §5](03-data-model.md))。また purge 前の commit を指す旧 pointer の
時点検証は、manifest object が purge で失われているため §3.1 手順 6b の降格 (strict = unverifiable) に従う (erase は resurrection barrier ではない設計 — [05-runtime.md §3.5](05-runtime.md)。
「erase 後も永続的に not_found」と読める保証はしない)。

## 4.3 検証 API

AI Agent が過去回答で使った Evidence Pointer の生存確認用:

```bash
kcs evidence verify <pointer> [--strict]   # <pointer> の受理形式は §2.3
```

```json
{
  "status": "alive" | "tombstoned" | "not_found" | "scope_unreachable" | "unverifiable" | "registry_duplicate",
  "details": { ... }
}
```

`unverifiable` は `--strict` 時の「時点帰属を検証できない解決」であり、`details.reason` で区別する:
`commit_shallow` (§3.1 手順 8 — 状況により解消し得る) / `tree_v1` (手順 6a — **恒久**: 既発行 pointer の
commit は不変であり再 snapshot では解消しない。v2/v3 snapshot 後に新規発行・明示 retarget した pointer
では生じない) /
`manifest_missing` (手順 6b — **恒久**)。exit はいずれも 3 (reason で自動化側が再試行の要否を判断する)。
live clone 重複は status `registry_duplicate` (候補一覧つき、exit 3 — §3.1 手順 1)。--batch は各行の
status にこれらをそのまま用いる。**sqlite.db が不在・利用不能の場合は status ではなく command-level の
retryable error `KCS-E-INDEX-REBUILDING-001` (exit 3)** — 検査は完了していないため --strict なしでも
0 を返さない (再構築中でも旧 sqlite.db が読めるなら通常応答 — [05-runtime.md §6](05-runtime.md)。
[06-cli-spec.md §7](06-cli-spec.md)、[05-runtime.md §2.6](05-runtime.md))。
非 strict では従来どおり alive + `commit_shallow: true` で返す。

`--strict`: tombstoned / not_found / scope_unreachable を **error** として扱う (CI / 自動化用)。
exit code: 全 pointer が alive なら 0。tombstoned / not_found があれば **4** (permanent failure)。
**scope_unreachable のみ**の失敗は **3** (retryable — §3.2 のとおり再接続・registry 再登録で回復可能。
permanent の 4 と区別しないと自動化が再試行可能性を判定できない)。
`--strict` なしの verify は検査が完了すれば 0 を返し、生存状態は `status` フィールドで判定する。
exit code の横断規約は [06-cli-spec.md §7](06-cli-spec.md)。

bulk verify:

```bash
kcs evidence verify --batch <pointers.jsonl>
# 各行が pointer JSON。各行に対する status を返す
```

active purge journal 中の verify は評価を行わず、KCS-E-PURGE 系 retryable (exit 3) を返す
([05-runtime.md §3.5](05-runtime.md) の読取系規約 — marker 耐久化後・削除完了前の窓で
「削除対象が alive」と誤答しないため)。

`--batch` の実装は Phase 4+ ([09-mvp-scope.md §3.1](09-mvp-scope.md))。単発 verify は Step 4。

---

# 5. Retarget (最新版へ pointer を切り替える)

別 LLM で再 Markdownize すると `tool_profile_hash` が変わり chunk が別物になる。既存 Evidence Pointer は古い `tool_profile_hash` の chunk を指し続ける (これは設計として正しい)。

「最新 Markdown へ pointer を切り替える」のは **明示操作** ([09-mvp-scope.md §5.2](09-mvp-scope.md)):

> retarget の実装は Phase 4+ ([09-mvp-scope.md §3.1](09-mvp-scope.md))。CLI 契約 (以下) は Step 3 以降の Evidence Pointer 契約と整合させて確定済み。

```bash
kcs evidence retarget <pointer> [--latest|--at <commit>]
```

```json
// 入力 pointer は不変。新しい pointer を返す
{
  "status": "retargeted",
  "new_pointer": { ...更新後... },
  "retargeted_from": "<old_pointer>",
  "match_method": "heading_path_exact" | "heading_path_fuzzy",
  "confidence": 0.92
}
```

(上記に限らず**本書の json fence 内の `"a" | "b"` は union の schema 表記** — §4.1・§4.3・§5 共通 — であり、リテラル JSON ではない。`//` コメント付きの例も同様。Agent はこれらの fence を JSON として parse しない)

```json
// 対応が見つからない場合
{
  "status": "ambiguous",
  "candidates": [...],
  "error_code": "KCS-E-EVIDENCE-RETARGET-AMBIG-001"
}
```

対応付けは `heading_path` の完全一致 (`heading_path_exact`) → 正規化一致 + span 重なり率 (`heading_path_fuzzy`) の順に試みる。**span 重なり率は、新旧の normalized text 間で text alignment が成立した領域内でのみ用いる** — 異なる tool_profile の unit-local byte offset は共通座標を持たないため直接比較しない。alignment が成立しない場合は対応なし (ambiguous — fail-closed)。照合に使う旧側の heading・section・span は、**旧 pointer を解決した canonical 値 (旧 chunk / tree 由来) から取得する** — pointer 入力の optional 欄は使わない (偽 heading による別 section への誘導を防ぐ。§7.2 の表示規則と同じ姿勢)。**retarget の前提は旧 chunk / tree object が CAS に存在すること** (orphan 恒久保持の帰結として通常成立する) — 不在の場合 retarget は実行できず、§3.2 / §4.3 の解決規則に従い not_found / unverifiable 側へ降着する。**意味ベースの対応付け (semantic_fingerprint) は MVP に含めない**。chunk レベルの fingerprint 実体が未定義であり、embedding は retarget が必要な場面 (tool_profile 変更) で互換性ルール ([03-data-model.md §7](03-data-model.md)) により新旧比較が成立しない恐れがあるため。導入する場合は Phase 4+ で match_method の MINOR 追加 (§8) として行う。

retarget は **AI Agent からの呼び出しを前提** にしているため、レスポンスは [06-cli-spec.md §4](06-cli-spec.md) の `--json` 契約に従う。Phase 5 で構造化 API を導入する際もこの JSON schema を互換性契約として維持する ([06-cli-spec.md §9](06-cli-spec.md))。

---

# 6. 不変性保証 (immutability guarantee)

```
- 既存 Evidence Pointer は KCS によって書き換えられない
- raw_hash / chunk_hash / tool_profile_hash / commit は append-only
- pointer の意味する場所 (= 生成時に解決可能だった raw + chunk) は purge されない限り解決可能
- 解決失敗は schema 上区別される (tombstoned / not_found / scope_unreachable)
- auto commit の GC (shallow 化) は pointer の解決可能性に影響しない (raw / chunk object は GC で削除されない、[05-runtime.md §2.6](05-runtime.md))
- "古い pointer" を "最新版" に勝手に飛ばさない (retarget は明示操作)
```

これは AI Agent が KCS から取得した Evidence を **長期参照** できる契約となる。

---

# 7. 外部 Agent との相互運用

KCS は Evidence Pointer を **JSON object として AI Agent に返す**。Agent はこれを記憶し、後続の検証・参照・引用に使える。

## 7.1 検索結果に含める形

```json
{
  "results": [
    {
      "score": 0.87,
      "evidence_pointer": { /* §2 schema */ },
      "preview": "API Token の有効期限は 30 日です..."
    }
  ]
}
```

Agent は `evidence_pointer` を保存し、後続のセッションで以下を実行できる:

```
- kcs evidence verify <pointer>     生存確認
- kcs view <pointer>                該当 chunk の Markdown 取得
- kcs open <pointer>                原本ファイルを OS で開く
- kcs evidence retarget <pointer>   最新版への切り替え (要承認)
```

## 7.2 引用フォーマット (人間向け)

UI / レポートでは Evidence Pointer を以下に整形して表示することを推奨:

```text
[report.pdf @ sha256:9f2c1a7b04de… > 認証仕様 > API Token > 有効期限]
      ↑                              ↑                      ↑
      path_at_commit                 heading_path           section
```

commit hash の短縮表示は [03-data-model.md §8.1](03-data-model.md) の規則 (先頭 12 hex) に従う。完全な hash は折りたたみ可能。

---

# 8. Evidence Pointer Schema 互換性

`schema_version` の semver 規約:

```
MAJOR  必須フィールド削除 / 既存フィールド意味変更    migration 必須
MINOR  新フィールド追加 (default で旧データを補える)
PATCH  typo / コメント修正
```

`path_at_commit` / `heading_path` 等の optional フィールドは **MINOR 互換** で追加してよい。`raw_hash` / `chunk_hash` / `commit` の意味変更は **MAJOR 扱い** (= migration plan + ユーザー通知)。

**未知 MAJOR の拒否は表現形式に依らない**: reader は自己の対応 MAJOR より新しい `schema_version` を、URI の `sv` (§2.3) と inline / batch JSON の `schema_version` field のどちらで受けても KCS-E-CONFIG-SCHEMA 系 error (exit 2) で拒否する (未知フィールド無視則が担う前方互換は、既知 MAJOR 内の MINOR 追加に限る)。

**既知 MAJOR 内の MINOR 追加による**新 schema は古い解決ロジックでもエラーなく扱えること (forward compatible) を要件とする (= 未知フィールドは無視。未知 MAJOR は上記のとおり拒否 — この要件の対象外)。

本仕様の 2026-07 改訂 (`scope_id` 必須化・`scope_path` の optional 降格) は、実装・pointer 発行前の `schema_version = 1` の定義確定であり、MAJOR bump ではない。公開後に同種の変更を行う場合は上記規約どおり MAJOR (migration plan + ユーザー通知) となる。
