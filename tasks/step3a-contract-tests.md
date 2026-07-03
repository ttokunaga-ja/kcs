# Step3a 契約テスト仕様書: Step 3 (kcs-index + kcs-search)

> 本書は **実装より先にテストを固定する** ためのケース仕様。Rust 実装コードは含まない。
> Step 3 実装者 (別エージェント) はこの仕様を「動かしてはならない契約」として消化する。
> 正本 spec は `docs/` の 03〜10。**本書は spec を写経・補間せず、各テストに根拠 § を必ず付す**。
> spec に記述がない挙動は勝手に契約化せず、末尾 §C「未定義事項」に切り出す。
>
> 手本は `tasks/ws1a-contract-tests.md` (Step 1) と `tasks/step2a-contract-tests.md` (Step 2)。
> ID 体系・ベクタの書き方・§C の未定義リストの扱い方・§D の除外リストを踏襲する。
> chunk 段の identity ベクタ (ws1a A.5, step2a §D で P2 参考に据え置かれたもの) は本書で実 Step 3 の
> 確定契約へ昇格する (CT3-CHUNK-001 が ws1a A.5 と再計算一致することを確認済み)。

対象クレート (Step 3): `kcs-index` + `kcs-search`
実装範囲の正本: `docs/09-mvp-scope.md §3.1` の **Step 3 行** —
chunk / Embedding / FTS5 / sqlite-vec / hybrid search (RRF / MMR / paging / cursor) /
Evidence Pointer 発行・解決 / `kcs open` / `kcs view` / `kcs search --json` + `index_status` /
`kcs reindex` (gen+1) / 観測ログ `metrics.jsonl` / `access.jsonl`。

**Step 境界の明示 (最重要)**: time-travel 検索フラグ (`--at` / `--all-history` / `--include-deleted` /
`--since`) とその chunk 集合 join 意味論 (`05 §1.6`)、`restore`、`purge` の**実行**、
`kcs evidence verify` **CLI** (単発) は `09 §3.1` により **Step 4**。Step 3 が作るのは
その基盤 (tree_entries の HEAD 射影 `04 §4.5`、chunks append-only `04 §4.1`、
auto snapshot 時の `first_seen_commit` 刻印 `05 §1.6`) と、**デフォルト検索 (HEAD join)** のみ。
北極星シナリオ M3-2 / M3-3 は time-travel フラグを要するため **Step 4 完了扱い**、Step 3 の Done 条件は
M3-1 (hybrid + Evidence Pointer + `kcs open`) が担う。根拠と除外リストは §D。

---

## 0. テスト ID 体系と優先度

| 接頭辞 | 対象契約 | 主な根拠 |
| --- | --- | --- |
| `CT3-CHUNK-*` | chunking (heading + max_chars) / chunk identity (chunk_hash) / gen 連動 / chunking_config_hash 世代 / append-only / tree_entries HEAD 射影 | `03 §8.1, §5.3` / `04 §4.1, §4.5, §4.6` |
| `CT3-EMBED-*` | embedding_hash / 互換性ルール (dim/distance/modality/profile) / vector 検索拒否 + text fallback / content 再利用 / text-only 緩和 / embeddings 正・chunk_vec 導出 | `03 §7, §8.1` / `04 §4.3, §5.5` / `07 §5.3` |
| `CT3-FTS-*` | FTS5 外部 content + trigger 同期 / `chunks_au` 限定 / trigram (CJK) / rebuild-db 再構築 | `04 §4.1, §4.2, §5.7` |
| `CT3-HYBRID-*` | mode 解決 (auto→hybrid→text fallback) / fail_behavior / fallback_reason / RRF 決定論 (同点 chunk_id 昇順) | `05 §1.1, §1.3, §1.7` |
| `CT3-MMR-*` | MMR 選択則 / 決定性 / mmr_depth / max_per_raw_hash (ページ跨ぎ) / group_by_raw_hash | `05 §1.4` |
| `CT3-CURSOR-*` | ページング再現性 / max_rowid 固定 / query_hash 不一致 `KCS-E-SEARCH-CURSOR-001` / shallow `KCS-E-COMMIT-SHALLOW-001` | `05 §1.5, §1.8, §2.2` |
| `CT3-MULTI-*` | multi-scope: 並列列挙 / rank ベース統合 (raw スコア比較禁止) / searched_scopes / excluded_scopes / 部分失敗 exit 3 / 全失敗 exit 4 / 性能前提 | `05 §1.8` / `09 §4.1` |
| `CT3-EVIDENCE-*` | pointer 発行 (必須フィールド + evidence_uri) / 解決手順 (scope 2 段 / gen / working tree / CAS / tombstoned / not_found / scope_unreachable) | `08 §2, §3` / `05 §1.7` |
| `CT3-URI-*` | URI 正規形 / JSON⇄URI 往復 (optional 脱落) / object 参照区別 / `sv` / 受理規則 | `08 §2.3` |
| `CT3-OPEN-*` | `kcs open` 解決順 (working tree 優先 → 一時展開) / dead pointer exit 4 / `kcs view` 過去 object | `06 §1.1, §7` / `05 §4.2` |
| `CT3-REINDEX-*` | `kcs reindex --force`: gen+1 / 旧 gen 残置 / Evidence Pointer 不変 / 確認プロンプト | `07 §9` / `03 §2.1` / `06 §1` |
| `CT3-OBS-*` | `index_status` (部分 index 可視化) / `metrics.jsonl` (latency) / `access.jsonl` | `05 §1.7, §7` / `06 §13` |

**優先度**

- **P0** = Step 3 完了条件。全て緑でなければ Step 3 を「完了」と呼べない。
- **P1** = 推奨。契約の周辺・堅牢性。落ちても致命ではないが実装欠陥の強い兆候。
- **P2** = あれば良い。Step 4 以降の前倒し検証や参考ベクタ。

P0 総数は末尾に集計。

---

## A. 具体的テストベクタ (最重要)

以下は `python3` (3.14) で実計算した固定ベクタ。**再現手順**: 各 JSON を JCS 直列化して sha256 する。
JCS 近似は `json.dumps(obj, separators=(',',':'), ensure_ascii=False, sort_keys=True).encode('utf-8')`。

> **RFC 8785 との差異について**: 本書 A.1〜A.3 の hash 入力キーはすべて ASCII、数値はすべて整数
> (`spec_version=1`, `gen`, `char_*`, `dimensions=1536`) である。この条件下では上記 Python 近似は
> RFC 8785 JCS と **バイト一致** する (ws1a §A 冒頭注記と同じ論拠)。非 ASCII は `heading_path` /
> `section_id` の **値** にのみ現れ、UTF-8 リテラル直列化で両者一致する (ws1a CT-HASH-009 で確認済み)。
> RRF (A.4) / MMR (A.5) は Fraction で有理数厳密計算し、float 値は参考表示。

### A.1 chunk_hash ベクタ (`03 §8.1` chunk identity)

入力素材 (ws1a / step2a から流用):
`raw_hash = sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a` (ws1a report.pdf raw)、
`tool_profile_hash = sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0` (ws1a placeholder)。

**CHUNK-1 (gen=0, section_id 在) — ws1a A.5 の再計算一致確認**:

```text
canonical: {"char_end":1500,"char_start":1200,"gen":0,"heading_path":["認証仕様","API Token"],"raw_hash":"sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a","section_id":"auth/api-token","spec_version":1,"tool_profile_hash":"sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0","unit_key":"page:12"}
chunk_hash = sha256:8fefa4825444efb1a120df709f45764a9ac074a9a2c0002ee4307baa7bbfe15a
```

ws1a A.5 の値と **バイト一致** (再計算確認済み)。Step 1 で P2 参考だった chunk identity を Step 3 の確定契約へ昇格する。

**CHUNK-2 (gen=3, 他は CHUNK-1 と同一) — `kcs reindex --force` の gen+1 で別 identity になることの固定**:

```text
canonical: {"char_end":1500,"char_start":1200,"gen":3,"heading_path":["認証仕様","API Token"],"raw_hash":"sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a","section_id":"auth/api-token","spec_version":1,"tool_profile_hash":"sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0","unit_key":"page:12"}
chunk_hash = sha256:4e170d694a19589e035f95ff0aae4cc0d1c8212a2e873aa10de00d20d65784d9
```

`gen` のみ 0→3 で chunk_hash が変わる。`(raw_hash, tool_profile_hash)` は不変 (identity は §2.1 のとおり不変、gen は世代の区別)。

**CHUNK-3 (section_id 省略, `unit_key=doc:1`) — null/未設定は hash 入力から落とす**:

```text
canonical: {"char_end":600,"char_start":0,"gen":0,"heading_path":["Overview"],"raw_hash":"sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a","spec_version":1,"tool_profile_hash":"sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0","unit_key":"doc:1"}
chunk_hash = sha256:ae2198890a11cac4a7853728d1ada4dd95e88086ec094e139ecbc64984504f30
```

`section_id` を持たない chunking strategy では入力から**省略**する (`03 §8.1` / `§5.1` の「省略と null を識別しない」)。
`section_id: null` を明示した入力も canonicalize 時に null キーを落とすため、この値と**完全一致**する (CT3-CHUNK-003 で検証)。

### A.2 embedding_hash ベクタ (`03 §8.1` embedding identity)

`target_hash` は A.1 CHUNK-1 の chunk_hash、`profile_hash` は step2a PROFILE-3 の embedding profile
(`sha256:c2bda78e...7226`)。緩和適用時の `modality="text"` ケース:

```text
canonical: {"dimensions":1536,"distance":"cosine","modality":"text","profile_hash":"sha256:c2bda78e217e1f9e12cd17ddac6c46e28a50b8060976f533f76f14193a807226","spec_version":1,"target_hash":"sha256:8fefa4825444efb1a120df709f45764a9ac074a9a2c0002ee4307baa7bbfe15a","target_type":"chunk"}
embedding_hash = sha256:4af13668332498f223787967c0f26e2e41d3425bbe5d657a2db1a7d27c56ba8c
```

`vector` (BLOB 実体) は identity 入力に含めない (identity は target + profile + modality/dim/distance のみ、`03 §8.1`)。

### A.3 chunking_config_hash ベクタ (`03 §5.3` 世代 hash)

`[chunking]` のデフォルト値 (`strategy="heading"`, `max_chars=6000`, `03 §11`) を明示的に畳み込む
(キー省略と明示指定を識別しない):

```text
canonical: {"max_chars":6000,"spec_version":1,"strategy":"heading"}
chunking_config_hash = sha256:7810328ffa7f0dd9a558294e166f20d8038d8d779809ee519582e3d6ba1b98ea
```

これは chunk の**世代**を表すメタデータであり identity には含めない (`03 §5.3`)。`max_chars` 変更や
`strategy` 変更でこの hash が変わり、chunk / embedding の再生成トリガになる (CT3-CHUNK-007)。

### A.4 RRF 数値例 (`05 §1.3` weighted RRF)

`RRF_score(c) = w_text/(k+rank_text) + w_vector/(k+rank_vector)`、`k=60, w_text=w_vector=1.0`、
片側にしか現れない候補は現れない側の項を 0。実運用の `candidate_depth=200` (各バックエンド上位 200 件)
のうち小さな 5 候補を抜き出した例。有理数厳密計算:

| chunk | rank_text | rank_vector | w/(k+r_text) | w/(k+r_vector) | RRF_score | float |
| --- | --- | --- | --- | --- | --- | --- |
| c1 | 1 | 3 | 1/61 | 1/63 | 124/3843 | 0.032266 |
| c2 | 2 | 1 | 1/62 | 1/61 | 123/3782 | 0.032522 |
| c3 | 3 | 2 | 1/63 | 1/62 | 125/3906 | 0.032002 |
| c4 | 4 | (なし) | 1/64 | 0 | 1/64 | 0.015625 |
| c5 | (なし) | 4 | 0 | 1/64 | 1/64 | 0.015625 |

**最終順位 (score 降順、同点は chunk_id 昇順)**:

```text
1. c2  (123/3782 = 0.032522)
2. c1  (124/3843 = 0.032266)
3. c3  (125/3906 = 0.032002)
4. c4  (1/64     = 0.015625)   ┐ 同点 → chunk_id 昇順 (c4 < c5) で確定
5. c5  (1/64     = 0.015625)   ┘
```

要点: text の 1 位 c1 は融合後 c2 に抜かれる (c2 が vector で 1 位のため)。片側のみの c4/c5 は低スコア。
c4/c5 の同点は `05 §1.3` の「同点は chunk_id 昇順」で決定論的に確定する。

### A.5 MMR 数値例 (`05 §1.4` 多様化)

`score(c) = λ·relevance(c) - (1-λ)·max_{c'∈selected} similarity(c,c')`、`λ=0.7`、`relevance(c)=RRF_score(c)`。
4 候補、対称類似度行列 (vector cosine 相当)、上位 3 件を選択:

```text
relevance:  c1=0.90  c2=0.80  c3=0.78  c4=0.60
similarity: sim(c1,c2)=0.95  sim(c1,c3)=0.30  sim(c1,c4)=0.20
            sim(c2,c3)=0.25  sim(c2,c4)=0.15  sim(c3,c4)=0.40
```

| step | selected | 候補ごとの MMR score | 選択 |
| --- | --- | --- | --- |
| 1 | {} | c1=0.630, c2=0.560, c3=0.546, c4=0.420 | **c1** |
| 2 | {c1} | c2=0.7·0.80−0.3·0.95=**0.275**, c3=0.7·0.78−0.3·0.30=**0.456**, c4=0.7·0.60−0.3·0.20=**0.360** | **c3** |
| 3 | {c1,c3} | c2=0.7·0.80−0.3·max(0.95,0.25)=**0.275**, c4=0.7·0.60−0.3·max(0.20,0.40)=**0.300** | **c4** |
| 4 | {c1,c3,c4} | c2=**0.275** | c2 |

**MMR 確定順序: c1, c3, c4, c2**。

要点: c2 は relevance 2 位 (0.80) だが c1 との類似度 0.95 (near-duplicate) のため罰則を受け、
relevance 3 位の c3 (0.78) / 4 位の c4 (0.60) より後ろに落ちる。これが「同一原文の隣接 chunk が
上位を独占する」問題 (`05 §1.4`) の回避を示す。MMR score の同点は RRF 順、さらに同点は chunk_id 昇順 (`05 §1.4`)。

### A.6 Evidence Pointer URI 往復ベクタ (`08 §2.3`)

`05 §1.7` 例と同形の完全 JSON pointer (optional 全部入り) を URI 化 → 再 parse する。
URI は**必須フィールドのみ** (`scope_id / commit / raw_hash / tool_profile_hash / chunk_hash [+ ?sv]`)。

```text
JSON (完全形, 12 フィールド):
  schema_version, commit, tree, raw_hash, tool_profile_hash, chunk_hash,
  path_at_commit, heading_path, section_id, char_start, char_end, scope_id, scope_path

URI (正規テキスト形):
kcs://scope_01J8ZQABCDEFGHJKMNPQRS/sha256:9f2c1a7b04dee5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e/sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a/sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0/sha256:8fefa4825444efb1a120df709f45764a9ac074a9a2c0002ee4307baa7bbfe15a

URI → JSON (必須フィールドのみ復元, sv 省略 = 1):
  { schema_version=1, scope_id, commit, raw_hash, tool_profile_hash, chunk_hash }

往復で脱落する optional (7 件):
  char_start, char_end, heading_path, path_at_commit, scope_path, section_id, tree
```

全セグメントが `[A-Za-z0-9_:.-]` に閉じるため percent-encoding 不要 (`08 §2.3`)。
`sv` 省略時は `1`、未知 `sv` は `KCS-E-CONFIG-SCHEMA` 系 error (exit 2) (`08 §2.3`)。

---

## B. テストケース

各ケース: **ID / 優先度 / Given-When-Then / 正本根拠**。

### CT3-CHUNK-* — chunking / chunk identity / 世代 / append-only (`03 §8.1, §5.3` / `04 §4.1, §4.5, §4.6`)

**CT3-CHUNK-001** — P0 — chunk_hash: gen=0, section_id 在 (ws1a A.5 一致)
- Given: A.1 CHUNK-1 の identity タプル。
- When: `JCS → sha256`。
- Then: canonical バイト列が A.1 と一致し、`chunk_hash = sha256:8fefa482…e15a`。ws1a A.5 の値とバイト一致。
- 根拠: `03 §8.1` (chunk identity hash / `text_hash` 非包含 / null 省略) / `08 §2.1` (chunk_hash は
  `(raw_hash, tool_profile_hash, gen, unit_key, heading_path, section_id, char_start, char_end)` から導出)。

**CT3-CHUNK-002** — P0 — chunk_hash は gen に連動 (gen+1 で別 identity)
- Given: A.1 CHUNK-2 (CHUNK-1 の gen のみ 0→3)。
- When: `JCS → sha256`。
- Then: `chunk_hash = sha256:4e170d69…84d9`。CHUNK-1 と異なる。`(raw_hash, tool_profile_hash)` は不変。
- 根拠: `03 §8.1` (gen は hash 入力) / `03 §2.1` (identity は `(raw_hash, tool_profile_hash)`、gen は世代区別)。

**CT3-CHUNK-003** — P0 — section_id 省略と null を識別しない
- Given: A.1 CHUNK-3 (section_id 省略) と、同一だが `section_id: null` を明示した入力。
- When: canonicalize (null キー除去) → `JCS → sha256`。
- Then: 両者の canonical・hash が完全一致 (`sha256:ae219889…4f30`)。
- 根拠: `03 §8.1` (「null / 未設定フィールドは hash 入力に含めない (§5.1 と同じ規則。section_id を持たない
  chunking strategy では省略)」)。

**CT3-CHUNK-004** — P0 — chunking は heading 単位 + max_chars 上限
- Given: 複数 heading を持つ normalized unit と `[chunking] strategy="heading" max_chars=6000`。
- When: chunk を生成。
- Then: chunk は heading 単位で切り出され、各 chunk の `heading_path` は当該見出しの階層、`char_start`/`char_end`
  は当該 unit 本文先頭を 0 とする **unit-local** span。max_chars を超える section は分割される (分割規則は §C-1)。
- 根拠: `03 §11` (`strategy="heading"`, `max_chars=6000`) / `04 §4.1` (`char_start/char_end` は unit-local) /
  `03 §8.1` (span は unit-local)。
- 補足: heading_path 導出規則・section_id 生成規則・max_chars 超過時の分割規則は spec 未定義 (§C-1)。
  本テストは「heading 単位で切れる」「span が unit-local」「max_chars を超える chunk を生成しない」のみ assert。

**CT3-CHUNK-005** — P0 — char_start/char_end は unit-local (全文 view の位置に非依存)
- Given: 全文 view で末尾側に結合される unit 由来の chunk。
- When: chunk の span を検査。
- Then: `char_start`/`char_end` は当該 unit の `markdown` 本文先頭を 0 とする文字 offset であり、
  view 結合順・ヘッダ・他 unit の長さに影響されない。同一 unit なら view 構成が変わっても span 不変。
- 根拠: `03 §2.1` 手順5 (「chunk の char offset は unit-local … 全文 view 上の位置・ヘッダ・結合順は
  chunk identity に影響しない」) / `04 §4.1`。

**CT3-CHUNK-006** — P0 — chunking_config_hash の算出 (デフォルト値も明示畳み込み)
- Given: A.3 の `[chunking]` デフォルト (`strategy="heading", max_chars=6000`)。
- When: `JCS → sha256` (spec_version 込み)。
- Then: canonical `{"max_chars":6000,"spec_version":1,"strategy":"heading"}`、
  `chunking_config_hash = sha256:7810328f…98ea`。キー省略と明示指定を識別しない。
- 根拠: `03 §5.3` (計算規約 / デフォルト値も明示畳み込み / identity には使わない)。

**CT3-CHUNK-007** — P0 — chunking_config 変更で再 chunk + 旧世代 chunk 行残置
- Given: `chunking_config_hash` = H1 で chunk 済みの instance。`[chunking] max_chars` を変更し H2 になる。
- When: 次回 `kcs index`。
- Then: 全 normalized instance に H2 の再 chunk + 再 embedding task を積む。**旧 H1 の chunk 行は削除しない**
  (Evidence Pointer の chunk_hash 解決用に残置)。検索対象は現行 `chunking_config_hash` の chunk のみ。
  再 chunk はローカル処理 (LLM 不要)、embedding のみ再課金。
- 根拠: `04 §4.6` (chunk 世代判定 / 再 chunk task / 旧世代残置 / 検索は現行 config のみ) / `03 §5.3`。
- 補足: 再生成前の確認 (対象 chunk 数 + embedding 概算) は `04 §4.6`。`--yes` で省略。

**CT3-CHUNK-008** — P0 — chunks 行は append-only (更新/リネーム/削除で既存行を消さない)
- Given: chunk 済みファイルを更新・リネーム・OS 削除する。
- When: 次回 index。
- Then: 既存 chunk 行を DELETE / 変更しない。新 raw の chunk は新行として追加。既存行への UPDATE は
  `first_seen_commit` 付与のみ許可。chunk 行を物理削除する経路は `kcs purge` のみ (Step 4)。
- 根拠: `04 §4.1` (「chunks 行は append-only … 削除する経路は kcs purge のみ … UPDATE は first_seen_commit
  の付与のみ許可」)。
- 補足: append-only が time-travel (`--at`/`--all-history`/`--include-deleted`) の実体だが、それらの検索
  フラグ自体は Step 4 (§D)。本テストは「Step 3 の index が既存 chunk 行を破壊しない」不変条件のみ。

**CT3-CHUNK-009** — P0 — chunk 行が検索対象になるのは auto snapshot 作成後 + first_seen_commit 刻印
- Given: `kcs index` 実行中 (auto snapshot 前) の chunk と、成功完了後の chunk。
- When: 検索対象集合を確認。
- Then: indexing 途中の chunk はどのモードでも返さない。`kcs index` 成功完了時の auto snapshot 作成後に
  検索対象化し、その時点で新規 chunk 行に `first_seen_commit` (当該 commit_hash) を刻む。
- 根拠: `05 §1.6` (「chunk 行が検索対象になるのは kcs index 成功完了時の auto snapshot 作成後 …
  auto snapshot 作成時に新規 chunk 行へ first_seen_commit を刻む」) / `04 §4.1`。

**CT3-CHUNK-010** — P0 — tree_entries HEAD 射影 (デフォルト検索の liveness join)
- Given: HEAD commit を作った直後。
- When: `tree_entries` テーブルを検査。
- Then: HEAD commit 分の行が `(commit_hash, path, raw_hash, tool_profile_hash, gen)` で常駐する。
  `gen` は tree entry の `normalize.gen` の射影で、欠落時は 0 と読む。デフォルト検索は
  `chunks ⨝ tree_entries(HEAD) on (raw_hash, tool_profile_hash, gen)`。
- 根拠: `04 §4.5` (「常駐必須は HEAD commit 分のみ … commit 作成時に新 HEAD 分を挿入」/ gen 射影) /
  `05 §1.6` (デフォルト集合 = `chunks ⨝ tree_entries(HEAD)`)。
- 補足: 非 HEAD commit 分の射影 (`--at` 時の展開) は time-travel につき Step 4 (§D)。本テストは HEAD 射影のみ。

**CT3-CHUNK-011** — P1 — chunk object schema と text_hash 非包含
- Given: 生成された chunk object。
- When: フィールドを検査。
- Then: `chunk_hash / raw_hash / tool_profile_hash / gen / unit_key / heading_path / section_id /
  char_start / char_end / chunking_config_hash / text_hash` を持つ。`text_hash` は chunk 抽出範囲のみの
  hash で **chunk_hash 入力に含めない**。`chunk_id` (SQLite PK) = `chunk_hash` と同一文字列。
- 根拠: `03 §8` chunk schema / `03 §8.1` (text_hash 非包含) / `04 §4.1` (`chunk_id` = `chunk_hash`)。

**CT3-CHUNK-012** — P1 — chunks / FTS / embeddings は rebuild-db で objects/ から再導出
- Given: `.kcs/index/sqlite.db` を消去し `kcs repair --rebuild-db`。
- When: 再構築。
- Then: normalized instance から chunks / embeddings / FTS index を再導出する。真実は objects/。
- 根拠: `04 §4` 冒頭 (「真実は objects/、SQLite は再構築可能」) / `04 §5.7` (復元範囲に chunks/embeddings/FTS)。
- 補足: `kcs repair --rebuild-db` コマンド枠は step2a CT2-TASK-010 で担保済み。本書は chunk/FTS/embedding の
  **再導出内容** が Step 3 artifact として一致することを追加検証する。

### CT3-EMBED-* — embedding identity / 互換性 / fallback (`03 §7, §8.1` / `04 §4.3, §5.5` / `07 §5.3`)

**CT3-EMBED-001** — P0 — embedding_hash の算出 (vector BLOB 非包含)
- Given: A.2 の identity タプル (target_type=chunk, target_hash=CHUNK-1, profile/modality/dim/distance)。
- When: `JCS → sha256`。
- Then: canonical バイト列が A.2 と一致し、`embedding_hash = sha256:4af13668…ba8c`。`vector` BLOB 実体は入力外。
- 根拠: `03 §8.1` (embedding identity hash)。

**CT3-EMBED-002** — P0 — 互換性不一致で vector 検索拒否 → text fallback
- Given: query embedding profile と index 側 embedding の `dimensions`/`distance`/`modality`/`profile_hash`
  のいずれかが不一致。`fail_behavior="fallback"`。
- When: `kcs search`（auto/hybrid）。
- Then: vector 検索を強行せず text (BM25) に fallback。`resolved_mode="text"`, `fallback=true`,
  `fallback_reason` 記録、`error_code=KCS-E-SEARCH-VEC-INCOMPAT-001`。
- 根拠: `03 §7` (互換性ルール: dim/distance/modality/profile_hash 全一致が条件) / `05 §1.1` (auto 解決:
  profile_hash 不一致 → text fallback `KCS-E-SEARCH-VEC-INCOMPAT-001`) / `07 §5.3` (profile 不一致で再生成/text fallback)。

**CT3-EMBED-003** — P0 — 横断 vector 検索の互換性条件 (全 scope 一致でなければ text 統合)
- Given: multi-scope 検索で embedding profile が全 scope で一致しない。
- When: 横断 vector / hybrid 検索。
- Then: 横断部分は text (BM25 rank) のみで統合し、`fallback_reason` に記録する。
- 根拠: `05 §1.8` (5) (「embedding profile が全 scope で一致しない場合、横断部分は text (BM25 rank) のみで
  統合し fallback_reason に記録」) / `03 §7`。

**CT3-EMBED-004** — P0 — text-only 緩和適用時の契約 (modality=text 単一 Embedding)
- Given: `07 §5.3` の凍結例外が適用され、`modality="text"` の単一 Embedding Adapter を採用。
- When: chunk の embedding 生成 + vector 検索。
- Then: `embeddings.modality="text"`、embedding_hash は A.2 と同形 (modality=text) で算出。
  text chunk の vector 検索が成立し、M3-1〜M3-3 (text 検索で完結) の Done 条件に影響しない。
- 根拠: `07 §5.3` (「凍結例外 … MVP は modality=text の単一 Embedding Adapter を許容 … 北極星シナリオ
  M3-1〜M3-3 は text 検索のみで完結するため、この緩和は MVP の Done 条件に影響しない」) / `03 §7`。
- 補足: 緩和は事前承認済みの凍結例外 (`09 §6.2` 条件1)。本テストは緩和適用**時**の契約であり、
  multimodal 実採用時は modality=multimodal の embedding_hash を別途固定する。

**CT3-EMBED-005** — P1 — embeddings 正 / chunk_vec 導出 (rebuild 順序)
- Given: `embeddings` テーブルと `chunk_vec` (vec0) の不整合、または `kcs repair --rebuild-db`。
- When: 再構築。
- Then: `objects/ → embeddings → chunk_vec` の順に再構築する。`embeddings` を正とし `chunk_vec` は導出物。
- 根拠: `04 §4.3` (「embeddings テーブルを正とし chunk_vec は導出物 … objects/ → embeddings → chunk_vec の順に再構築」)。

**CT3-EMBED-006** — P1 — content ベース再利用 (同一 text_hash × profile で Adapter を呼ばない)
- Given: `(text_hash, embedding profile_hash, dimensions, distance, modality)` 一致の既存 embedding が同一 .kcs 内。
- When: embedding task。
- Then: Adapter を呼ばず既存 vector を再利用。incremental Markdownize 後の unchanged unit 由来で本文不変の
  chunk は embedding を再生成しない。
- 根拠: `04 §5.5` (embedding の content ベース再利用) / `03 §8` (text_hash は抽出範囲のみの hash)。

**CT3-EMBED-007** — P1 — vector-only モードで互換性 NG は error (fallback しない)
- Given: `kcs search --vector` で embedding 互換性 NG。
- When: 検索。
- Then: text に fallback せず error (`--vector` は失敗時 error)。auto/hybrid の fallback とは分岐する。
- 根拠: `05 §1.2` (「--vector … 失敗時は error」) / `05 §1.1` (両方不可 → error `KCS-E-SEARCH-VEC-UNAVAIL-001`)。

### CT3-FTS-* — FTS5 外部 content + trigger + trigram (`04 §4.1, §4.2, §5.7`)

**CT3-FTS-001** — P0 — 外部 content + trigger で chunks と自動同期
- Given: chunks へ INSERT / DELETE。
- When: `chunk_fts` を検索。
- Then: `chunks_ai` (AFTER INSERT) で FTS 行が追加、`chunks_ad` (AFTER DELETE) で FTS の
  `'delete'` 疑似行により除去される。外部 content モード (`content='chunks'`) で本文重複保存しない。
- 根拠: `04 §4.2` (外部 content モード / `chunks_ai` / `chunks_ad` trigger)。
- 補足: 通常運用で chunks は append-only (delete しない) だが、trigger 契約は DELETE でも整合することを保証する。

**CT3-FTS-002** — P0 — `chunks_au` は `UPDATE OF text, heading_path` に限定 (first_seen_commit で再書き込みしない)
- Given: chunk 行の `first_seen_commit` のみを UPDATE (§4.1 で唯一許可された UPDATE)。
- When: FTS を検査。
- Then: `chunks_au` は発火せず FTS は再書き込みされない。`text` / `heading_path` を UPDATE した場合のみ
  `chunks_au` が delete→insert で FTS を更新する。
- 根拠: `04 §4.2` (「chunks_au を UPDATE OF text, heading_path に限定するのは、first_seen_commit の付与で
  FTS が再書き込みされるのを防ぐため」) / `04 §4.1`。

**CT3-FTS-003** — P0 — trigram tokenizer で CJK 部分一致 (単語分割なし)
- Given: 日本語本文 (例「認証仕様の更新」) を含む chunk。デフォルト tokenizer = `trigram`。
- When: 3 文字 CJK クエリ (例「認証仕様」の部分) で FTS 検索。
- Then: 単語境界に依らず部分一致でヒットする (trigram は 3-gram 索引)。
- 根拠: `04 §4.2` (「Tokenizer: デフォルト trigram (CJK 対応)」)。
- 補足: 2 文字クエリは trigram の最小 gram 長 (3) を下回るため索引効率が落ちる境界ケース。firm 契約は
  3 文字以上の CJK 部分一致とし、2 文字挙動は実装依存 (§C-6)。tokenizer 切替 (`unicode61`) は
  `[search.fts]` config (`04 §4.2`)。

**CT3-FTS-004** — P0 — FTS index は rebuild-db で chunks から再構築
- Given: FTS index を破棄し `kcs repair --rebuild-db`。
- When: 再構築。
- Then: `chunks` から FTS を再導出する (真実は objects/ 由来の chunks)。
- 根拠: `04 §5.7` (復元範囲に FTS index) / `04 §4` 冒頭。

### CT3-HYBRID-* — mode 解決 / fallback / RRF 決定論 (`05 §1.1, §1.3, §1.7`)

**CT3-HYBRID-001** — P0 — auto 解決: 両方利用可能 → hybrid
- Given: text + vector 両方利用可能 (embedding 互換性 OK)、`default_mode="auto"`。
- When: `kcs search "..."`。
- Then: `resolved_mode="hybrid"`。RRF(text, vector) で融合する。
- 根拠: `05 §1.1` (auto 解決順: 両方利用可能 → hybrid)。

**CT3-HYBRID-002** — P0 — auto 解決: vector のみ NG → text fallback + 可視化
- Given: vector 不可 (embedding 未設定 or 互換性 NG)、`fail_behavior="fallback"`。
- When: `kcs search`。
- Then: `requested_mode="auto"`, `resolved_mode="text"`, `fallback=true`, `fallback_reason` (例
  `"embedding_endpoint_not_configured"`), `error_code` (該当時 `KCS-E-SEARCH-VEC-*`)。fallback を隠さない。
- 根拠: `05 §1.1` (vector のみ NG → text) / `05 §1.7` (レスポンス schema: fallback / fallback_reason / error_code)。

**CT3-HYBRID-003** — P0 — 両方不可 → error
- Given: text も vector も不可。
- When: `kcs search`。
- Then: error (`KCS-E-SEARCH-VEC-UNAVAIL-001`)。
- 根拠: `05 §1.1` (両方不可 → error `KCS-E-SEARCH-VEC-UNAVAIL-001`)。

**CT3-HYBRID-004** — P0 — RRF 融合スコアと最終順位 (数値ベクタ)
- Given: A.4 の rank 表 (text: c1..c4, vector: c2,c3,c1,c5)、`k=60, w_text=w_vector=1.0`。
- When: RRF_score を計算し降順に並べる。
- Then: 各 RRF_score が A.4 と一致し、最終順位 `c2, c1, c3, c4, c5`。片側のみの候補は現れない側の項を 0。
- 根拠: `05 §1.3` (RRF 式 / 片側 0 / w/k デフォルト)。

**CT3-HYBRID-005** — P0 — RRF 決定論: 同点は chunk_id 昇順
- Given: A.4 の c4 / c5 (RRF_score = 1/64 で同点)。
- When: 順位確定。
- Then: chunk_id 昇順で c4 → c5 に確定 (同一入力で毎回同一)。バックエンド内の同点も chunk_id 昇順で順位確定。
- 根拠: `05 §1.3` (「RRF_score の同点は chunk_id 昇順」/「バックエンド内の同点は chunk_id 昇順で順位を確定」)。

**CT3-HYBRID-006** — P0 — text-only / vector-only は fusion せず当該順位をそのまま使う
- Given: `--text` または `--vector` 単一モード。
- When: 検索。
- Then: RRF fusion を行わず、当該バックエンドの順位をそのまま結果順とする。
- 根拠: `05 §1.3` (「text-only / vector-only モードでは fusion せず当該バックエンドの順位をそのまま使う」)。

**CT3-HYBRID-007** — P1 — 候補プール上限 = candidate_depth (ページングしても超えない)
- Given: `candidate_depth=200`。各バックエンド上位 200 件の和集合が候補プール。
- When: `--limit`/`--cursor` でページング。
- Then: 1 クエリで返しうる結果の上限は候補プール件数を超えない (ページングしても超えない)。
- 根拠: `05 §1.3` (「1 クエリで返しうる結果の上限は候補プール件数 (ページングしても超えない)」)。

**CT3-HYBRID-008** — P1 — `--hybrid` 強制時の vector 失敗は fail_behavior に従う
- Given: `kcs search --hybrid`、vector 失敗、`fail_behavior ∈ {fallback, error, warn}`。
- When: 検索。
- Then: `fallback` → text へ、`error` → error、`warn` → 警告付きで text。設定に従い分岐する。
- 根拠: `05 §1.2` (「--hybrid … vector 失敗時は fail_behavior に従う」) / `05 §1.1` (fail_behavior)。

### CT3-MMR-* — 多様化 (`05 §1.4`)

**CT3-MMR-001** — P0 — MMR 選択順 (数値ベクタ)
- Given: A.5 の relevance + 類似度行列、`λ=0.7`、上位 3 選択。
- When: MMR を適用。
- Then: 各 step の MMR score が A.5 と一致し、確定順序 `c1, c3, c4, c2`。relevance 2 位 c2 は c1 との
  near-duplicate (sim 0.95) 罰則で後退する。
- 根拠: `05 §1.4` (MMR 選択則 `score(c)=λ·rel-(1-λ)·max sim` / `relevance(c)=RRF_score(c)`)。

**CT3-MMR-002** — P0 — MMR 決定性 (同入力で確定順序が常に同一)
- Given: 同一の候補集合・query・設定。
- When: MMR を 2 回適用。
- Then: 確定順序が完全一致。MMR score 同点は RRF 順、さらに同点は chunk_id 昇順。これがページング (§1.5) の前提。
- 根拠: `05 §1.4` (「入力が同じなら確定順序は常に同一 (決定論)」/ 同点規則)。

**CT3-MMR-003** — P0 — MMR は上位 mmr_depth 件に 1 回だけ適用、以降は RRF 順で末尾接続
- Given: 候補プール、`mmr_depth=100` (≤ candidate_depth)。
- When: 多様化。
- Then: RRF 上位 mmr_depth 件にのみ MMR を 1 回適用して確定順序を得る。mmr_depth 以降は RRF 順のまま末尾へ接続。
- 根拠: `05 §1.4` (「候補プールの RRF 上位 mmr_depth 件 … に 1 回だけ適用 … 以降の候補は RRF 順のまま末尾に接続」)。

**CT3-MMR-004** — P0 — max_per_raw_hash はページを跨いで結果ストリーム全体に適用
- Given: `max_per_raw_hash=3`、同一 raw_hash に 5 chunk がヒット。
- When: 確定順序を構築しページングする。
- Then: 当該 raw_hash からの結果は全ページ通算で最大 3 件。ページ内でなくストリーム全体に適用される。
- 根拠: `05 §1.4` (「max_per_raw_hash は確定順序の構築時に結果ストリーム全体へ適用する (ページを跨いで
  raw_hash あたり最大 N 件)」)。

**CT3-MMR-005** — P1 — strategy 切替 (mmr / group_by_raw_hash / off)
- Given: `[search.diversify] strategy` を各値に設定。
- When: 検索。
- Then: `mmr` → MMR、`group_by_raw_hash` → raw_hash グルーピング、`off` → 素の RRF 順。いずれも決定論的。
- 根拠: `05 §1.4` (`strategy = "mmr" | "group_by_raw_hash" | "off"`)。

### CT3-CURSOR-* — ページング / カーソル (`05 §1.5, §1.8, §2.2`)

**CT3-CURSOR-001** — P0 — 同一 cursor で同一結果 (決定論的再計算)
- Given: 1 ページ目の `next_cursor` を取得。
- When: 同じ cursor で 2 ページ目を 2 回取得。
- Then: 2 回とも同一結果。ページングは「確定順序 (§1.4) の決定論的再計算 + consumed 件 skip」で実現。
  CLI 呼び出しを跨いでも成立する。
- 根拠: `05 §1.5` (「ページングは確定順序の決定論的再計算で実現 … CLI 呼び出しを跨いでも成立」)。

**CT3-CURSOR-002** — P0 — max_rowid で chunk 集合を固定 (発行後の新規 chunk を混ぜない)
- Given: cursor 発行後に新しい chunk 行が append される (rowid 単調増加)。
- When: 同 cursor で次ページを取得。
- Then: `rowid <= max_rowid` で chunk 集合が固定され、発行後の新規 chunk は次ページに混入しない。
- 根拠: `05 §1.5` (「max_rowid: cursor 発行時点の chunks 最大 rowid … chunks 行は append-only なので単調増加」) /
  `05 §1.8` (cursor の per-scope sub-cursor に `max_rowid`)。

**CT3-CURSOR-003** — P0 — query_hash 不一致の cursor は `KCS-E-SEARCH-CURSOR-001` で拒否
- Given: あるクエリ・条件で発行した cursor を、別クエリ (または別 mode/diversify 設定) の検索に渡す。
- When: cursor を使う。
- Then: token 全体の `query_hash` 不一致を検出し `KCS-E-SEARCH-CURSOR-001` で拒否 (exit は横断規約)。
- 根拠: `05 §1.5` (「query_hash が不一致の cursor は KCS-E-SEARCH-CURSOR-001 で拒否」) / `05 §1.8`
  (query_hash = query + mode + diversify 設定の hash、token 全体に 1 つ)。
- 補足: query_hash の厳密な canonical 入力構成 (含めるキー) は spec 未定義 (§C-2)。本テストは「別クエリの
  cursor が拒否される」不変条件のみ assert し、hash 値は固定しない。

**CT3-CURSOR-004** — P0 — cursor は opaque token (JCS の base64url)
- Given: multi-scope cursor (`05 §1.8` の per-scope sub-cursor 合成)。
- When: `next_cursor` を検査。
- Then: `{v, scope_mode, query_hash, scopes[]}` JSON の JCS を base64url した opaque token。
  各 sub-cursor は `{scope_id, snapshot_commit, max_rowid, consumed}`。
- 根拠: `05 §1.8` (cursor の multi-scope 拡張 / opaque token)。

**CT3-CURSOR-005** — P0 — shallow 化 commit を snapshot とする cursor 再計算は `KCS-E-COMMIT-SHALLOW-001`
- Given: cursor 中の `snapshot_commit` が shallow 化済み (tree 破棄)。
- When: 次ページの再計算。
- Then: `KCS-E-COMMIT-SHALLOW-001` で失敗し、cursor なしの再検索を案内する。
- 根拠: `05 §1.8` (「cursor 中の snapshot_commit が shallow 化済みの場合、cursor の再計算は
  KCS-E-COMMIT-SHALLOW-001 で失敗する」) / `05 §2.2`。
- 補足: shallow 化の**生成**は GC (Phase 4+、§D)。本テストは手置きの shallow commit (tree object 不在) に
  対する **再計算失敗の契約**のみ検証する。

**CT3-CURSOR-006** — P1 — `--offset` は cursor の糖衣 (同じ再現規則)
- Given: `--limit 20 --offset 20` と、同条件の cursor 2 ページ目。
- When: 両者を実行。
- Then: 同一の確定順序の offset 位置から limit 件を返す。確定順序末尾を超えたら `next_cursor: null` で終端。
- 根拠: `05 §1.5` (「--offset は cursor の糖衣 … 末尾を超えたら next_cursor: null で終端」)。

### CT3-MULTI-* — 複数 scope 横断検索 (`05 §1.8` / `09 §4.1`)

**CT3-MULTI-001** — P0 — デフォルトは全 indexed scope 横断、対象は participates_in_global_search=true
- Given: scope_registry に複数 scope (一部 `participates_in_global_search=false`)。
- When: `kcs search "..."` (scope 指定なし)。
- Then: `participates_in_global_search=true` の scope を列挙して横断検索。`--scope <path>` / `--descendants`
  指定時は root_path 前方一致で絞り込む。
- 根拠: `05 §1.8` (対象 scope の列挙 1-2) / `06 §3` (デフォルト全 indexed scope 横断)。

**CT3-MULTI-002** — P0 — scope 間統合は rank ベース (raw スコア比較禁止)
- Given: 各 scope が RRF 済み上位 candidate_depth 件を返す。BM25/vector の raw スコアは index ごとに
  コーパス統計が異なる。
- When: scope 間マージ。
- Then: 各 scope の **RRF スコア (rank のみから決まる)** をそのまま比較して降順マージ。BM25/vector の
  raw スコアを scope 間で比較・正規化しない。同点は `(scope_path, chunk_hash)` の辞書順で安定化。
- 根拠: `05 §1.8` (実行とマージ 3) (「rank ベース … raw スコアを scope 間で比較・正規化してはならない …
  同点は (scope_path, chunk_hash) の辞書順」)。

**CT3-MULTI-003** — P0 — diversify は統合後の候補列に適用
- Given: 複数 scope マージ後の候補列。
- When: MMR / group_by_raw_hash を適用。
- Then: diversify (§1.4) は統合後の列に対して適用する (scope ごとではない)。
- 根拠: `05 §1.8` (実行とマージ 4)。

**CT3-MULTI-004** — P0 — searched_scopes / excluded_scopes を必ず返す
- Given: 一部 scope が到達不能 / stale / timeout。
- When: 検索レスポンスを検査。
- Then: `searched_scopes[] = {scope_id, scope_path, snapshot_at}`、`excluded_scopes[] = {scope_id,
  scope_path, reason}`。単一 scope 検索でも要素 1 個の配列で同形式を返す。
- 根拠: `05 §1.8` (レスポンス契約の拡張 / 対象 scope の列挙 3: excluded_scopes に理由付き記録) /
  `05 §1.7` / `06 §9` (Agent API 保証: searched_scopes / excluded_scopes / fallback_reason)。

**CT3-MULTI-005** — P0 — 部分失敗は結果を返し exit 3、全失敗は `KCS-E-SEARCH-SCOPE-ALL-FAILED-001` exit 4
- Given: (a) 一部 scope 失敗 / stale / timeout、(b) 全 scope 失敗。
- When: 検索。
- Then: (a) 結果を返し `excluded_scopes` に記録、exit 3。(b) error `KCS-E-SEARCH-SCOPE-ALL-FAILED-001`、exit 4。
- 根拠: `05 §1.8` (部分失敗と exit code 表: 一部失敗=3 / 全失敗=`SCOPE-ALL-FAILED-001`=4) / `06 §7`。

**CT3-MULTI-006** — P1 — 並列度と per-scope timeout
- Given: N scope、`parallelism=4` (default), `per_scope_timeout_seconds=2` (default)。
- When: 横断検索。
- Then: 並列度は `min(4, scope 数)`。timeout 超過 scope は `excluded_scopes` (reason=timeout) に落とす。
- 根拠: `05 §1.8` (実行とマージ 1 / 設定 / per_scope_timeout)。

**CT3-MULTI-007** — P1 — 性能前提の注記 (20 scopes / 10 万 chunk / p95 < 5 秒)
- Given: 20 scopes / 合計 10 万 chunk の構成。
- When: M3-1 の latency 計測 (横断検索デフォルト)。
- Then: p95 < 5 秒を満たす。これは MVP の性能保証前提であり、数百 scope 超は保証外 (`--scope` 絞り込み /
  `participates_in_global_search=false` を案内)。
- 根拠: `05 §1.8` (性能目標の前提) / `09 §4.1` (M3-1 p95 < 5 秒 / 20 scopes / 10 万 chunk) / `09 §4.3` (Recall 規約)。
- 補足: 実 latency は環境依存のため CI では合成コーパス (`09 §4.3` synthetic, `eval/golden-queries.jsonl`) で
  計測する。本テストは「計測対象構成と閾値」を契約として固定し、実測は eval ハーネスに委ねる (§C-4 / §D)。

### CT3-EVIDENCE-* — Evidence Pointer 発行・解決 (`08 §2, §3` / `05 §1.7`)

**CT3-EVIDENCE-001** — P0 — 検索結果に必須フィールド全部 + evidence_uri を発行
- Given: hybrid 検索がヒット chunk を返す。
- When: 各 result の `evidence_pointer` / `evidence_uri` を検査。
- Then: 必須フィールド `schema_version / commit / raw_hash / tool_profile_hash / chunk_hash / scope_id`
  を全て持ち (充足率 100%)、optional の `commit`/`tree`/`path_at_commit`/`heading_path`/`char_start`/
  `char_end`/`section_id`/`scope_path` を伴う。`evidence_uri` は §2.3 正規テキスト形で、そのまま
  `kcs open`/`kcs view` に渡せる。M3-1 の「commit + raw_hash + chunk_hash + heading_path + span」を満たす。
- 根拠: `08 §2.1` (必須フィールド) / `08 §2.2` (optional) / `05 §1.7` (レスポンス schema / evidence_uri /
  evidence_pointer をそのまま埋め込む) / `09 §4.1` (Evidence 必須フィールド充足率 100%) / `09 §M3-1`。

**CT3-EVIDENCE-002** — P0 — live chunk の evidence_pointer.commit = snapshot_at (HEAD)
- Given: HEAD snapshot で live な chunk。
- When: pointer を発行。
- Then: `evidence_pointer.commit` = 当該 scope の `snapshot_at` (デフォルト検索では HEAD commit)。
  `path_at_commit` = その commit の tree における path。`searched_scopes[].snapshot_at` と整合。
- 根拠: `05 §1.7` (snapshot_at と evidence_pointer.commit の決定規則: live chunk はその commit /
  path_at_commit はその commit の tree の path)。
- 補足: live でない chunk (`--all-history` の旧版等) の commit = first_seen_commit 分岐は time-travel につき
  Step 4 (§D)。本テストは HEAD live chunk のみ。

**CT3-EVIDENCE-003** — P0 — 解決手順: scope 2 段解決 (scope_path → registry)
- Given: pointer の (a) scope_path が有効で scope_id 一致 / (b) scope_path 不達だが registry に scope_id 登録あり。
- When: pointer を解決。
- Then: (a) scope_path の .kcs を使う。(b) scope_registry を scope_id で照会し kcs_path を得る (同一 scope_id
  複数登録は last_seen_at 最新優先、曖昧なら候補一覧 error)。どちらも失敗 →
  `KCS-E-EVIDENCE-SCOPE-UNREACHABLE-001` (scope_unreachable)。root 信頼は scope_id。
- 根拠: `08 §3.1` 手順1 (scope の 2 段解決) / `08 §3.2` (scope_unreachable) / `05 §1.7` (root 信頼は scope_id)。

**CT3-EVIDENCE-004** — P0 — 解決手順: commit → tree → raw_hash entry → gen で normalized instance → chunk text
- Given: 非 shallow commit を指す alive pointer。
- When: 解決。
- Then: commit を取得 → tree (commit.tree) → raw_hash で entry 検索 → tombstone チェック →
  `normalize.(tool_profile_hash, gen)` で normalized instance を解決 (gen 欠落は 0) → chunk_hash で
  chunk object を解決し `char_start/char_end` の text を取り出す。出力は
  `{ raw_object | normalized_unit | chunk_text }`。
- 根拠: `08 §3.1` 手順 2-7 / `08 §3` (入出力)。

**CT3-EVIDENCE-005** — P0 — shallow commit は tree を省略し raw_hash/chunk_hash で直接解決
- Given: pointer.commit が shallow (tree 破棄済み)。
- When: 解決。
- Then: 手順 3-4 (tree 経由) を省略し、raw_hash / tool_profile_hash / chunk_hash で直接解決する
  (chunk object が gen を保持するため chunk_hash → chunk object → gen → normalized unit)。
  レスポンスに `"commit_shallow": true`。shallow は解決の失敗要因にしない。
- 根拠: `08 §3.1` 手順 2a / `08 §3.2` 補足 (「shallow commit は pointer 解決の失敗要因ではない」) /
  `03 §8` (chunk object が gen を保持)。
- 補足: shallow の生成 (GC) は Phase 4+。手置きの shallow commit で直接解決経路を検証する (§D)。

**CT3-EVIDENCE-006** — P0 — 解決失敗の 3 値: tombstoned / not_found / scope_unreachable
- Given: (a) raw_hash が tombstone を持つ / (b) tombstone なしで raw object 不在 / (c) scope 不達。
- When: 解決。
- Then: (a) `status="purged"` の tombstone レスポンス (`purged_at/purged_reason/purged_in_commit/raw_hash`)。
  (b) `KCS-E-PURGE-NOT-FOUND-001` (not_found)。(c) `KCS-E-EVIDENCE-SCOPE-UNREACHABLE-001` (scope_unreachable)。
- 根拠: `08 §3.2` (部分的失敗 3 値) / `08 §4.1` (tombstone schema) / `08 §4.2` (not_found)。
- 補足: tombstone の**生成** (`kcs purge`) は Step 4 (§D)。本テストは `05 §3.5` の tombstone ファイル形式
  (`.kcs/tombstones/ab/cd/<raw_hash>`) を**手置き**して、Step 3 の resolver が tombstone/not_found を
  正しく返すことを検証する (`kcs open` の dead pointer exit 4 が Step 3 で必要なため resolver は Step 3)。

**CT3-EVIDENCE-007** — P1 — results[].scope_path は表示・高速化ヒント (解決の root 信頼にしない)
- Given: pointer の scope_path が実際の .kcs 位置と食い違う (移動後) が scope_id は一致。
- When: 解決。
- Then: scope_id が一致する限り解決可能 (registry 経由)。scope_path は解決の root 信頼にしない。
- 根拠: `08 §2.2` (「scope_path も … ヒントであり、解決の root 信頼にしない … scope_id が一致する限り
  pointer は解決可能」) / `05 §1.7` (truth vs cache)。

**CT3-EVIDENCE-008** — P1 — schema forward compatible (未知フィールド無視)
- Given: 未知 optional フィールドを持つ pointer (MINOR 追加想定)。
- When: 解決。
- Then: エラーなく必須フィールドで解決 (未知フィールドは無視)。
- 根拠: `08 §8` (「新 schema は古い解決ロジックでもエラーなく扱える (forward compatible) … 未知フィールドは無視」)。

### CT3-URI-* — URI 正規形と受理規則 (`08 §2.3`)

**CT3-URI-001** — P0 — JSON → URI → JSON 往復 (optional 脱落)
- Given: A.6 の完全 JSON pointer (optional 全部入り)。
- When: URI 化 → 再 parse。
- Then: URI = A.6 の正規テキスト形。往復後の JSON は必須フィールドのみ (`schema_version=1` 補完)、
  optional 7 件 (`char_start/char_end/heading_path/path_at_commit/scope_path/section_id/tree`) が脱落する。
  必須フィールドは失われない。
- 根拠: `08 §2.3` (「URI は必須フィールドのみ … 往復で失われてよいのは optional フィールドだけ」)。

**CT3-URI-002** — P0 — object 参照 URI (第 2 セグメント `object`) を Evidence Pointer と区別
- Given: `kcs://<scope_id>/object/image/<image_hash>` と Evidence Pointer URI
  (`kcs://<scope_id>/sha256:.../.../.../...`)。
- When: URI を判別。
- Then: 第 2 セグメントがリテラル `object` なら object 参照、`sha256:` prefix なら Evidence Pointer。
  Evidence Pointer の第 2 セグメント (commit) は常に `sha256:` prefix を持つため衝突しない。`kcs open` は
  object 参照も受理して該当 object を解決する。
- 根拠: `08 §2.3` (第 2 セグメント `object` の区別 / commit は常に sha256: prefix) / step2a CT2-IMAGE-002/003
  (object 参照 URI の生成は Step 2、解決は Step 3)。

**CT3-URI-003** — P0 — `<pointer>` 受理規則 (prefix 優先順位)
- Given: (1) `-` (stdin) / (2) `kcs://` (URI) / (3) `{` (inline JSON) / (4) `sha256:` (短縮形) / (5) その他。
- When: CLI の `<pointer>` 引数を解釈。
- Then: prefix 優先順で判定。(4) 短縮形は `kcs open`/`kcs view` のみで object store を照会し種別判別
  (chunk_hash/raw_hash)、多義なら候補一覧 error。(5) parse 失敗 → exit 2 (invalid usage)。
- 根拠: `08 §2.3` (CLI `<pointer>` 受理規則 5 分岐) / `06 §1` (受理形式は 08 §2.3 を正本)。

**CT3-URI-004** — P1 — `sv` 省略 = 1、未知 sv は exit 2
- Given: (a) `?sv` なし URI / (b) `?sv=99` (未知)。
- When: parse。
- Then: (a) `schema_version=1`。(b) `KCS-E-CONFIG-SCHEMA` 系 error、exit 2。
- 根拠: `08 §2.3` (「sv 省略時は 1。未知の sv は KCS-E-CONFIG-SCHEMA 系 error (exit 2)」)。

### CT3-OPEN-* — kcs open / kcs view (`06 §1.1, §7` / `05 §4.2`)

**CT3-OPEN-001** — P0 — 解決順: working tree に同一 raw_hash があればそれを開く (リネーム耐性)
- Given: pointer を解決した raw_hash を持つファイルが working tree に存在 (path_at_commit と異なる path でもよい)。
- When: `kcs open <pointer>`。
- Then: その実ファイルを OS 規定アプリで開く (一時展開しない)。
- 根拠: `06 §1.1` 手順 1-2 (「pointer を解決して raw_hash … working tree に同一 raw_hash を持つファイルが
  存在すれば … その実ファイルを OS 規定アプリで開く」)。

**CT3-OPEN-002** — P0 — 一時展開: working tree に無ければ CAS から read-only 展開して開く
- Given: working tree に該当 raw_hash が無い (削除済み / 過去版 / raw_hash 直指定)。
- When: `kcs open`。
- Then: raw object を `~/.cache/kcs/open/<raw_hash 先頭 12 桁>/<path_at_commit の basename>` に
  read-only 展開し OS 規定アプリで開く。restore ではない (working tree に書かない)。stderr に
  「原本は working tree に存在しない … 永続コピーは kcs restore --to」を表示。
- 根拠: `06 §1.1` 手順 3 (一時展開 / read-only / 展開先) / 一時展開は restore ではない旨。

**CT3-OPEN-003** — P0 — dead pointer (tombstoned / not_found / scope_unreachable) は exit 4
- Given: 解決が tombstoned / not_found / scope_unreachable のいずれか。
- When: `kcs open` / `kcs view` / `kcs restore`。
- Then: exit 4。
- 根拠: `06 §7` (「kcs open / view / restore  dead pointer (tombstoned / not_found / scope_unreachable) は 4」) /
  `06 §1.1` 手順 4。
- 補足: `kcs restore` 自体は Step 4 だが、`kcs open`/`kcs view` の dead pointer exit 4 は Step 3。本テストは
  open/view で検証 (restore は §D)。

**CT3-OPEN-004** — P0 — `kcs view` は過去版 object をそのまま返す (再 Markdownize しない)
- Given: pointer / path を指す chunk / normalized unit。
- When: `kcs view <pointer>`。
- Then: 当該 commit の object をそのまま返す (再 Markdownize / 再生成しない)。
- 根拠: `05 §4.2` (「過去 commit 時点の Markdown を再生成せず、当該 commit の object をそのまま返す」) /
  `08 §7.1` (`kcs view <pointer>` = 該当 chunk の Markdown 取得)。
- 補足: `kcs view <path> --at <commit>` の `--at` は time-travel につき Step 4 (§D)。本テストは pointer 指定の
  過去 object 返却 (再生成しない契約) のみ。

**CT3-OPEN-005** — P1 — 短縮形 `sha256:` を kcs open が種別判別して解決
- Given: `kcs open sha256:<chunk_hash>` / `kcs open sha256:<raw_hash>`。
- When: 解決。
- Then: object store を照会して種別を判別し、chunk_hash なら chunk、raw_hash なら raw として
  カレント .kcs + HEAD 文脈に解決。多義なら候補一覧 error。
- 根拠: `08 §2.3` (受理規則 4 / 短縮形は kcs open / kcs view のみ)。

### CT3-REINDEX-* — kcs reindex --force (`07 §9` / `03 §2.1` / `06 §1`)

**CT3-REINDEX-001** — P0 — `--force` は gen+1 の新 instance を作り旧 gen を残置
- Given: `g0` instance が存在する `(raw_hash, tool_profile_hash)`。
- When: `kcs reindex --force`。
- Then: `gen = 現最大 + 1` (= g1) の新 normalized instance を作る。既存 `g0` instance (manifest / unit object)
  は保全 (上書き・削除しない)。`--force` は first-instance-wins の唯一の上書き経路。
- 根拠: `07 §9` (「explicit re-normalize … gen+1 の新 normalized instance … 旧 instance は保全」) /
  `03 §2.1` (gen / 「kcs reindex --force だけが gen = 現最大 + 1 の新 instance を作り、既存 instance は保全」) /
  `06 §1` (reindex --force)。

**CT3-REINDEX-002** — P0 — Evidence Pointer 不変: 過去 commit の tree entry は旧 gen を参照し続ける
- Given: `g0` を指す既存 Evidence Pointer / 過去 commit の tree entry。`kcs reindex --force` で g1 を作成。
- When: 過去 commit の tree entry / 既存 pointer を解決 (`kcs view --at 相当の gen 保全)。
- Then: 過去 commit の tree entry は旧 gen (g0) を指し続け、既存 pointer は g0 の chunk を解決する。
  新規参照 (新 commit の tree entry / 新 chunk) のみ最新 gen (g1) を使う。
- 根拠: `03 §2.1` (「kcs reindex --force 後も過去 commit の tree entry は旧 gen を指し続ける」/
  「新規参照は常に最新 gen」) / `03 §8` (tree entry の gen 保全で `kcs view --at` と pointer 不変性が成立) /
  `08 §6` (不変性保証)。

**CT3-REINDEX-003** — P0 — `--force` は確認プロンプト必須 (--yes で省略可)
- Given: `kcs reindex --force` を対話環境で実行。
- When: 実行。
- Then: 確認プロンプトを表示 (拒否で exit 9)。`--yes` で省略可。
- 根拠: `06 §1` (「--force は確認プロンプト必須 (--yes で省略可)」) / `06 §7` (exit 9 = confirm 拒否)。

**CT3-REINDEX-004** — P1 — 上書きチェーンは parent_run_id で記録
- Given: g0 → g1 の reindex。
- When: g1 の provenance を検査。
- Then: 上書きチェーンを `parent_run_id` で記録する (manifest の parent_gen で世代関係)。
- 根拠: `07 §9` / `09 §5.1` (「上書きチェーンは parent_run_id で記録」) / `03 §2.1` (parent_gen)。

### CT3-OBS-* — 観測ログ (`05 §1.7, §7` / `06 §13`)

**CT3-OBS-001** — P0 — index_status: 部分 index (AI 強化未完了) を可視化
- Given: AI 強化 (Markdownize / Embedding) が全対象に行き渡っていない (`enriched_ratio < 1.0`)。
- When: `kcs search --json`。
- Then: `index_status = { enriched_ratio, pending_enrichment_tasks, budget_paused }` を返す
  (enriched_ratio < 1.0 のときのみ必須)。人間向けは「AI 強化 42% (budget により一時停止中)」の 1 行に翻訳。
- 根拠: `05 §1.7` (index_status / enriched_ratio < 1.0 のとき必須 / 人間向け翻訳) / `09 §3.1` (index_status = Step 3)。
- 補足: `enriched_ratio` の分子分母定義 (何を「強化済み」と数えるか) は spec 未定義 (§C-3)。本テストは
  「部分 index 時に index_status を返し done/pending/paused を隠さない」ことのみ assert。

**CT3-OBS-002** — P0 — metrics.jsonl に検索 latency を記録 (M3 計測の前提)
- Given: `kcs search` を実行。
- When: `~/.local/share/kcs/logs/metrics.jsonl` を読む。
- Then: 数値メトリクス行が記録され、各行は JSON 必須フィールド `ts, level, code, component, message, context`
  を持つ。`ts` は UTC ISO8601+Z。latency (M3-1 の p95 計測に必要) が context に含まれる。
- 根拠: `05 §7` (metrics.jsonl) / `06 §13` (必須フィールド / timestamp) / `09 §3.1` (metrics.jsonl = Step 3、
  M3 の latency 計測に必要) / `09 §4.1` (Latency p50/p95/p99)。
- 補足: metric 名 / latency 記録粒度の schema は spec 未定義 (§C-3)。本テストは「search が latency を
  metrics.jsonl に記録する」ことと必須フィールド形式のみ assert。

**CT3-OBS-003** — P0 — access.jsonl に検索アクセスを記録 (redact_logs 既定 true)
- Given: `kcs search`。
- When: `.kcs/logs/access.jsonl` を読む。
- Then: 検索アクセスログ行が追記される。`redact_logs` 既定 true のとき `context` の `query` 等機微
  フィールドをマスクする。行は JSON 必須フィールド `ts, level, code, component, message, context` を持つ。
- 根拠: `05 §7` (access.jsonl / redact_logs 既定 true) / `06 §13` (必須フィールド / redact_logs) / `09 §3.1`
  (access.jsonl = Step 3)。
- 補足: access.jsonl の記録フィールド詳細 (どのフィールドを残すか) は spec 未定義 (§C-3)。

**CT3-OBS-004** — P1 — 検索の fallback / excluded を隠さない (AI Agent 保証)
- Given: fallback (text 落ち) / excluded_scopes ありの検索。
- When: レスポンス。
- Then: `resolved_mode` / `fallback` / `fallback_reason` / `searched_scopes` / `excluded_scopes` を必ず返す。
  Rerank Adapter 併用時も searched_scopes / fallback_reason を隠蔽しない。
- 根拠: `06 §9` (Agent API 保証: searched_scopes / excluded_scopes / fallback_reason) / `05 §1.7` / `07 §5.6`
  (Rerank は searched_scopes / fallback_reason を隠蔽してはならない)。

---

## C. 未定義事項 (spec に無い挙動 — 実装者判断 + 要 spec 追記)

> これらは **憶測で契約化しない**。各テストは「実装が選んだ挙動を固定し決定論性を assert する」に留め、
> 値の正本化は spec 追記後に行う。**要-spec は #1〜#2 の 2 件** (いずれも chunk 段の決定性 / cursor validity に
> 関わり、chunk_hash = Evidence Pointer identity の再現性を左右する)。#3 以降は実装者判断で固定し、
> 事後に spec へ反映すれば足りる。
>
> (注記: Step 2 で 2026-07-03 に確定した unit_key 正準生成 (`04 §2`)・page fingerprint (`04 §2.1`)・
> prompt_template_hash step1-2 (`03 §5.1`) は本書では前提として扱い、§C に再掲しない。)

1. **chunk 境界の決定性 (要-spec, 決定性)** — `03 §11` は `strategy="heading"` / `max_chars=6000` を定めるが、
   Step 3 の chunk 段で (a) `heading_path` の導出規則 (どの heading level を親に積むか / 正規化)、
   (b) `section_id` の生成規則 (heading_path からの slug 化か / 別採番か)、(c) max_chars 超過 section の
   分割規則 (`char_start`/`char_end` の落ち方 / 分割境界) が未定義。これらは **chunk_hash の入力**
   (`03 §8.1`) であり、実装ごとに揺れると chunk identity = Evidence Pointer の永続性 (`08 §6`) が崩れる。
   影響: CT3-CHUNK-004 / CT3-CHUNK-001 (ベクタは与えられた identity タプルには確定するが、**その
   heading_path / section_id / span をどう作るか**が未定義)。**Step 3 実装の最初の意思決定点**。

2. **query_hash の正準入力構成 (要-spec, cursor validity)** — `05 §1.8` は query_hash を
   「query + mode + diversify 設定の hash」と定めるが、厳密な canonical form (含めるキー: `k` /
   `candidate_depth` / `w_text`/`w_vector` / `mmr_lambda` / `scope_mode` を含むか、JCS か) が未定義。
   query_hash は cursor の誤用検出 (`KCS-E-SEARCH-CURSOR-001`) の基盤であり、含めるキーが実装で揺れると
   「同一クエリ扱い」の境界が変わる。影響: CT3-CURSOR-003。実装者が固定し spec へ追記推奨。

3. **観測ログの metric / index_status / access schema** — (a) `index_status.enriched_ratio` の分子分母
   (何を「強化済み」と数えるか: Markdownize done? embedding done? chunk indexed?)、(b) `metrics.jsonl` の
   metric 名と latency 記録粒度、(c) `access.jsonl` の記録フィールドと redact 対象、が未定義 (`05 §1.7` /
   `06 §13` は行の必須フィールドと存在のみ規定)。影響: CT3-OBS-001/002/003。実装者判断で固定。

4. **latency 計測ハーネスと eval コーパス** — `09 §4.1` は M3-1 p95 < 5 秒 / 20 scopes / 10 万 chunk を
   定め、`09 §4.3` は synthetic コーパス + `eval/golden-queries.jsonl` を Done 判定の正本とするが、
   本リポジトリに `eval/` はまだ存在しない (2026-07-03 時点)。計測ハーネスの実装形態・fixture script は
   Step 3 着手前に整備予定 (`09 §5.5` #5 draft)。影響: CT3-MULTI-007。契約テストは「閾値と対象構成」を
   固定し、実測は eval ハーネスに委ねる。**eval ハーネスが並行整備される場合は §4.3 の規約 (Recall@10 >= 0.8 /
   scenario 15 件以上 / expected は {scope,file,section} 分離形式) と整合させること**。

5. **MMR similarity 関数の選択規則** — `05 §1.4` は `similarity = vector cosine, または heading_path /
   section_id の Jaccard` と「または」で列挙するが、vector 利用可能時に cosine を使うか Jaccard を使うか、
   embedding 不可時の切替が未定義。影響: CT3-MMR-001 (ベクタは与えた類似度行列には確定するが、**実データで
   どの similarity を使うか**が未定義)。実装者判断で固定 (vector 検索成立時は cosine が自然)。

6. **trigram の 2 文字 CJK クエリ挙動** — `04 §4.2` は trigram (3-gram) を定めるが、gram 長 (3) 未満の
   2 文字 CJK クエリで索引を使うか linear scan に落ちるかが未定義。影響: CT3-FTS-003。実装者判断
   (firm 契約は 3 文字以上の部分一致)。

7. **`kcs reindex` のオペランド範囲** — `06 §1` は `kcs reindex [--force] [--at <commit>]` の構文を示すが、
   対象 (path 指定 / scope 全体 / 特定 raw_hash) の既定が未定義。`--at` は time-travel 系につき Step 4 寄り
   (§D)。影響: CT3-REINDEX-*。実装者判断。

8. **embeddings の vector BLOB シリアライズ形式** — `04 §4.3` は `vector BLOB` / `chunk_vec FLOAT[<dim>]` を
   定めるが、float 精度 (f32/f64) / endianness / 正規化の有無が未定義。sqlite-vec 依存の実装詳細。
   影響: CT3-EMBED-001 (identity は BLOB 非包含なので identity には影響しないが、再現性検証に関わる)。実装者判断。

---

## D. Step 3 範囲外として意図的に除外したもの (根拠付き)

以下は Step 3 の契約テストに **含めない**。理由は `09 §3.1` (機能×Step 割当) と各正本 §。

| 除外項目 | 除外理由 (根拠) |
| --- | --- |
| time-travel 検索フラグ `--at` / `--all-history` / `--include-deleted` / `--since` と、その chunk 集合 join 意味論 (`05 §1.6`: `chunks ⨝ tree_entries(<commit>)` / `files[status='deleted']` / 全 chunk / created_at フィルタ) | `09 §3.1` line 125: **Step 4** (`restore --to` / `--at` / `--all-history` / `--include-deleted` は同一行で Step 4)。Step 3 は基盤 (tree_entries HEAD 射影 `04 §4.5` / chunks append-only `04 §4.1` / first_seen_commit 刻印 `05 §1.6`) を作り、**デフォルト検索 (HEAD join) のみ**を検証 (CT3-CHUNK-008/009/010)。M3-2 (`--all-history`) / M3-3 (`--include-deleted`) は time-travel を要するため **Step 4 完了扱い**。Step 3 の Done は M3-1 |
| 非 HEAD commit の tree_entries 展開 (`--at` 時の tree object 展開挿入) | `04 §4.5` (「--at <commit> 検索時、当該 commit 分が無ければ tree object を展開して挿入」) は time-travel の一部 → Step 4。Step 3 は HEAD 分の常駐のみ (CT3-CHUNK-010) |
| `restore --to` / `--force` / working tree 非破壊 | `09 §3.1` line 125: Step 4 (`05 §4`)。`kcs open` の一時展開 (restore ではない、`06 §1.1`) は Step 3 (CT3-OPEN-002) として区別 |
| `kcs view <path> --at <commit>` の `--at` 分岐 | `--at` は time-travel → Step 4。Step 3 は pointer 指定の過去 object 返却 (再生成しない契約、CT3-OPEN-004) のみ |
| purge の**実行** (tombstone 発行 / `commit_type=purged` commit / `--erase-tombstone` / chunk 行物理削除) | `09 §3.1` line 126: Step 4 (`05 §3`)。Step 3 は tombstone **解決** (手置きファイルで resolver が tombstoned/not_found を返す、`kcs open` exit 4 に必要、CT3-EVIDENCE-006 / CT3-OPEN-003) のみ。tombstone の生成はしない |
| `kcs evidence verify <pointer>` (単発) CLI と `--strict` | `09 §3.1` line 128: **Step 4** (`08 §4.3`)。Step 3 は verify が surface する alive/tombstoned/not_found の **resolver 計算** (CT3-EVIDENCE-006) を担うが、`kcs evidence verify` サブコマンド枠は Step 4。exit code 4 の検証は `kcs open`/`kcs view` (Step 3) で行う (CT3-OPEN-003) |
| `kcs evidence verify --batch` / `kcs evidence retarget` | `09 §3.1` line 135-136: Phase 4+ (`08 §4.3`, `08 §5`) |
| `kcs repair --verify-objects` (CAS 整合性検証) | `09 §3.1` line 127: Step 4 (`10 §7.5`)。`kcs repair --rebuild-db` の chunk/FTS/embedding 再導出 (CT3-CHUNK-012 / CT3-FTS-004 / CT3-EMBED-005) は Step 3 (`04 §5.7`)。コマンド枠は step2a CT2-TASK-010 で担保済み |
| shallow 化の**生成** (tiered retention / `kcs gc` / tree 破棄) | `05 §2.2`, `09 §3.1` line 130-132: Phase 4+。Step 3 は shallow commit の **解決/失敗契約** (手置きの shallow commit で CT3-EVIDENCE-005 / CT3-CURSOR-005) のみ |
| GC の**実行** (shallow / prune / tiered / CoW / power-loss sweep) | `05 §2.2`, `09 §3.1`: Phase 4+。Step 1 CT-GC-* の schema 遵守を変えない |
| chunk レベル semantic_fingerprint / retarget の match_method | `08 §5` / `09 §5.2`: retarget は Phase 4+。Step 3 は chunk identity (hash) のみ扱い、類似性 fingerprint は扱わない (`03 §5` hash vs fingerprint 分離) |
| multimodal embedding のベンダー実地検証 (次元/料金/deprecation) | `07 §5.3` リスク注記: Step 2 着手前の採用判断。Step 3 は text-only 緩和適用時の契約 (CT3-EMBED-004) を検証し、multimodal 実採用時の embedding_hash は別途固定 |
| Summary / Classification / Rerank Adapter の生成本体 | `07 §5.4-5.6` optional。`09 §3.1` の Step 3 行に無い。Rerank の searched_scopes 非隠蔽 (CT3-OBS-004) のみ横断契約として参照 |
| Prepare / Markdownize / incremental / task / budget / secrets / network opt-in | `09 §3.1`: Step 2。step2a で担保済み。Step 3 は normalized instance (unit object 群) を入力として受け、chunk 以降を担う |
| CAS / tree / commit / hash 算出 / CLI 7 コマンド / lock | Step 1 (ws1a) で担保。Step 3 は commit の tree entry 射影 (tree_entries) を読むが tree/commit 生成は Step 1 |
| `kcs search` と書き込み系の lock 相互作用 (`kcs index` と `kcs search` 同時実行 / rebuild 中の search) | `05 §6` (search は lock 取得しない / rebuild 中は旧 db or `KCS-E-INDEX-REBUILDING-001`) は横断契約。search が読み取り系で lock を取らない点は ws1a CT-LOCK-003 の延長で担保。`KCS-E-INDEX-REBUILDING-001` は rebuild-db (Step 2 枠) 実行中の search 挙動につき P2 参考に留め本書では固定しない |

---

## 集計 (報告用)

- **P0 テスト数**: 57 (総テスト数 74: P0 57 / P1 17)
  (CT3-CHUNK 10 / CT3-EMBED 4 / CT3-FTS 4 / CT3-HYBRID 6 / CT3-MMR 4 / CT3-CURSOR 5 / CT3-MULTI 5 /
   CT3-EVIDENCE 6 / CT3-URI 3 / CT3-OPEN 4 / CT3-REINDEX 3 / CT3-OBS 3)
- **spec 未定義事項**: 8 件 (§C)。うち **要-spec は 2 件**: §C-1 (chunk 境界の決定性 — heading_path 導出 /
  section_id 生成 / max_chars 分割。chunk_hash = Evidence Pointer identity の再現性を左右)、
  §C-2 (query_hash の正準入力構成 — cursor validity の基盤)。残り 6 件は実装者判断で固定 → 事後 spec 反映で足りる。
