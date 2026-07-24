# Step3a 契約テスト仕様書: Step 3 (kio-index + kio-search)

> 本書は **実装より先にテストを固定する** ためのケース仕様。Rust 実装コードは含まない。
> Step 3 実装者 (別エージェント) はこの仕様を「動かしてはならない契約」として消化する。
> 正本 spec は `docs/` の 03〜10。**本書は spec を写経・補間せず、各テストに根拠 § を必ず付す**。
> spec に記述がない挙動は勝手に契約化せず、末尾 §C「未定義事項」に切り出す。
>
> 手本は `tasks/ws1a-contract-tests.md` (Step 1) と `tasks/step2a-contract-tests.md` (Step 2)。
> ID 体系・ベクタの書き方・§C の未定義リストの扱い方・§D の除外リストを踏襲する。
> chunk 段の identity ベクタ (ws1a A.5, step2a §D で P2 参考に据え置かれたもの) は本書で実 Step 3 の
> 確定契約へ昇格する (r3 で slug 規則確定に伴い section_id 正準例を更新 — A.1 冒頭注記参照)。
>
> 改訂 r3 (2026-07-03): 4 エンジン監査の裁定反映。(1) A.5 MMR を「生 RRF スコア → min-max 正規化 →
> MMR」の一貫ベクタに差し替え (`05 §1.4` 確定規則。確定順序は c1,c3,c4,c2 → **c1,c3,c2,c4** に変化、
> Fraction 厳密再計算で確定)。(2) §C-1〜C-4 は 2026-07-03 の spec 追記 (`04 §4.1` / `05 §1.8` /
> `05 §1.4` / `05 §7`) で**解消済み**に更新 — 要-spec 残 0 件 (§C-6 も同追記で解消)。(3) A.7 に
> query_hash 固定ベクタを新設。(4) `04 §4.1` の slug 規則 (翻訳なし・日本語保持) に合わせ CHUNK-1/2 の
> section_id を `認証仕様/api-token` で再凍結、CHUNK-3 を「見出し未出現 (heading_path=[])」fixture に
> 再設計。**ws1a A.5 の旧値 `sha256:8fefa482…` (section_id="auth/api-token") は規則確定前の例示値であり
> 歴史的参照**。(5) text-only 緩和撤回 (WS-embed-2 裁定、`07 §5.3` 更新済み) に伴い EMB 系を
> `gemini-embedding-2` / 768 (MRL) / cosine / `modality="multimodal"` で再凍結、CT3-EMBED-004 を
> multimodal 前提に改訂 (旧 gemini-embedding-001 ベクタは削除)。契約は不変、P0 は CT3-EMBED-008 追加で 59→60。
>
> 改訂 r2 (2026-07-03): Codex クロスレビュー反映。既存ベクタは全件再計算一致につき不変 (chunk_hash の
> ws1a 整合 / RRF 全行 / MMR 算術 / URI 往復)。誤引用・過剰契約 4 件を修正 (CT3-EVIDENCE-001 の
> 必須/optional を 08 §2.1/§2.2 に厳密整合、A.5 に relevance スケール注記 + §C-3 新設、A.2 に fixture
> 注記 + EMB-2 追加、CT3-OBS-002 の per-search 記録 schema を §C-4 要-spec 化)。カバレッジ 3 件を
> 追加/昇格 (CT3-EVIDENCE-009 eval 結合点、CT3-CHUNK-012 rebuild end-to-end を P0 昇格、
> CT3-MULTI-008 `--all-scopes`)。§C は stale の「eval/ 未存在」項を削除し 9 件に再編 (要-spec 4 件)。
> §D 末尾に Step 3 Done gate (M3-1 の 18 クエリ + P0 全緑 / M3-2・M3-3 の Recall 判定は Step 4) を明記。

対象クレート (Step 3): `kio-index` + `kio-search`
実装範囲の正本: `docs/09-mvp-scope.md §3.1` の **Step 3 行** —
chunk / Embedding / FTS5 / sqlite-vec / hybrid search (RRF / MMR / paging / cursor) /
Evidence Pointer 発行・解決 / `kio open` / `kio view` / `kio search --json` + `index_status` /
`kio reindex` (gen+1) / 観測ログ `metrics.jsonl` / `access.jsonl`。

**Step 境界の明示 (最重要)**: time-travel 検索フラグ (`--at` / `--all-history` / `--include-deleted` /
`--since`) とその chunk 集合 join 意味論 (`05 §1.6`)、`restore`、`purge` の**実行**、
`kio evidence verify` **CLI** (単発) は `09 §3.1` により **Step 4**。Step 3 が作るのは
その基盤 (tree_entries の HEAD 射影 `04 §4.5`、chunks append-only `04 §4.1`、
auto snapshot 時の `first_seen_commit` 刻印 `05 §1.6`) と、**デフォルト検索 (HEAD join)** のみ。
北極星シナリオ M3-2 / M3-3 は time-travel フラグを要するため **Step 4 完了扱い**、Step 3 の Done 条件は
M3-1 (hybrid + Evidence Pointer + `kio open`) が担う。根拠と除外リストは §D。

---

## 0. テスト ID 体系と優先度

| 接頭辞 | 対象契約 | 主な根拠 |
| --- | --- | --- |
| `CT3-CHUNK-*` | chunking (heading + max_chars) / chunk identity (chunk_hash) / gen 連動 / chunking_config_hash 世代 / append-only / tree_entries HEAD 射影 | `03 §8.1, §5.3` / `04 §4.1, §4.5, §4.6` |
| `CT3-EMBED-*` | embedding_hash / 互換性ルール (dim/distance/modality/profile) / vector 検索拒否 + text fallback / content 再利用 / 採用確定 multimodal profile / embeddings 正・chunk_vec 導出 | `03 §7, §8.1` / `04 §4.3, §5.5` / `07 §5.3` |
| `CT3-FTS-*` | FTS5 外部 content + trigger 同期 / `chunks_au` 限定 / trigram (CJK) / rebuild-db 再構築 | `04 §4.1, §4.2, §5.7` |
| `CT3-HYBRID-*` | mode 解決 (auto→hybrid→text fallback) / fail_behavior / fallback_reason / RRF 決定論 (同点 chunk_id 昇順) | `05 §1.1, §1.3, §1.7` |
| `CT3-MMR-*` | MMR 選択則 / 決定性 / mmr_depth / max_per_raw_hash (ページ跨ぎ) / group_by_raw_hash | `05 §1.4` |
| `CT3-CURSOR-*` | ページング再現性 / max_rowid 固定 / query_hash 不一致 `KIO-E-SEARCH-CURSOR-001` / shallow `KIO-E-COMMIT-SHALLOW-001` | `05 §1.5, §1.8, §2.2` |
| `CT3-MULTI-*` | multi-scope: 並列列挙 / rank ベース統合 (raw スコア比較禁止) / searched_scopes / excluded_scopes / 部分失敗 exit 3 / 全失敗 exit 4 / 性能前提 | `05 §1.8` / `09 §4.1` |
| `CT3-EVIDENCE-*` | pointer 発行 (必須フィールド + evidence_uri) / 解決手順 (scope 2 段 / gen / working tree / CAS / tombstoned / not_found / scope_unreachable) | `08 §2, §3` / `05 §1.7` |
| `CT3-URI-*` | URI 正規形 / JSON⇄URI 往復 (optional 脱落) / object 参照区別 / `sv` / 受理規則 | `08 §2.3` |
| `CT3-OPEN-*` | `kio open` 解決順 (working tree 優先 → 一時展開) / dead pointer exit 4 / `kio view` 過去 object | `06 §1.1, §7` / `05 §4.2` |
| `CT3-REINDEX-*` | `kio reindex --force`: gen+1 / 旧 gen 残置 / Evidence Pointer 不変 / 確認プロンプト | `07 §9` / `03 §2.1` / `06 §1` |
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
> (`spec_version=1`, `gen`, `char_*`, `dimensions=768`) である。この条件下では上記 Python 近似は
> RFC 8785 JCS と **バイト一致** する (ws1a §A 冒頭注記と同じ論拠)。非 ASCII は `heading_path` /
> `section_id` / `query` の **値** にのみ現れ、UTF-8 リテラル直列化で両者一致する (ws1a CT-HASH-009 で
> 確認済み)。**A.7 (query_hash) のみ浮動小数点が入力に現れる**: RFC 8785 (ECMAScript 数値直列化) では
> 整数値 float は小数点なしで直列化される (`1.0 → "1"`)。`0.7` は最短表現 `"0.7"` で両者一致。A.7 の
> Python 近似は整数値 float を int へ変換して RFC 8785 に一致させた (canonical バイト列を正とする)。
> RRF (A.4) / MMR (A.5) は Fraction で有理数厳密計算し、float 値は参考表示。

### A.1 chunk_hash ベクタ (`03 §8.1` chunk identity / `04 §4.1` 正準規則)

入力素材 (ws1a / step2a から流用):
`raw_hash = sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a` (ws1a report.pdf raw)、
`tool_profile_hash = sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0` (ws1a placeholder)。

> **旧値の扱い (r3)**: `04 §4.1` の slug 規則 (2026-07-03 確定 — 翻訳なし・日本語保持) では
> `heading_path ["認証仕様","API Token"]` から導出できる section_id は **`認証仕様/api-token`** であり、
> 旧例の `auth/api-token` は導出不能。発注側裁定により正準例を更新した。**ws1a A.5 の旧値
> `sha256:8fefa4825444efb1a120df709f45764a9ac074a9a2c0002ee4307baa7bbfe15a` (section_id="auth/api-token")
> は規則確定前の例示値であり歴史的参照** (JCS 直列化の検証データとしては今も有効)。`03 §8.1` の
> chunk object 例・`08 §2` の例示値の section_id 同期は発注側にて実施。

**CHUNK-1 (gen=0, section_id 在)** — section_id は `04 §4.1` 規則 4 の slug 導出
(`認証仕様` → `認証仕様` / `API Token` → 小文字化 + 空白→`-` → `api-token`):

```text
canonical: {"char_end":1500,"char_start":1200,"gen":0,"heading_path":["認証仕様","API Token"],"raw_hash":"sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a","section_id":"認証仕様/api-token","spec_version":1,"tool_profile_hash":"sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0","unit_key":"page:12"}
chunk_hash = sha256:c5e31f10da04b722769bdbbd60a55b94c177b5f3bf9c64e5341be7281d115c3d
```

**CHUNK-2 (gen=3, 他は CHUNK-1 と同一) — `kio reindex --force` の gen+1 で別 identity になることの固定**:

```text
canonical: {"char_end":1500,"char_start":1200,"gen":3,"heading_path":["認証仕様","API Token"],"raw_hash":"sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a","section_id":"認証仕様/api-token","spec_version":1,"tool_profile_hash":"sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0","unit_key":"page:12"}
chunk_hash = sha256:688cc82734bed7cb37ff1e40674dfdf4e48670bfde263962aabaac4f88d75e54
```

`gen` のみ 0→3 で chunk_hash が変わる。`(raw_hash, tool_profile_hash)` は不変 (identity は §2.1 のとおり不変、gen は世代の区別)。

**CHUNK-3 (見出し未出現領域, `unit_key=doc:1`) — heading_path=[] 保持 + section_id 省略**
(r3 で再設計: `04 §4.1` 規則 3「unit 先頭から見出し未出現の間は heading_path = []」の領域では
slug の結合対象が無く section_id は**未設定 → 省略**。旧 fixture の「heading_path 在 × section_id 省略」は
規則 4 で導出不能になったため):

```text
canonical: {"char_end":600,"char_start":0,"gen":0,"heading_path":[],"raw_hash":"sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a","spec_version":1,"tool_profile_hash":"sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0","unit_key":"doc:1"}
chunk_hash = sha256:d1fe73cef624a76949293ca550ae305ce8a2c46517a83e7d52b2bcc700b2c8d6
```

`heading_path = []` は **null ではなく定義値** なので hash 入力に残す (`04 §4.1` 規則 3)。`section_id` は
未設定につき入力から**省略** (`03 §8.1` / `§5.1` の「省略と null を識別しない」)。`section_id: null` を
明示した入力も canonicalize 時に null キーを落とすため、この値と**完全一致**する (CT3-CHUNK-003 で検証)。

### A.2 embedding_hash ベクタ (`03 §8.1` embedding identity / `07 §5.3` 採用確定 profile)

> **r3 で再凍結**: text-only 緩和は撤回され (`07 §5.3` 2026-07-03 再検証で確定、WS-embed-2 裁定)、
> **`gemini-embedding-2` (GA、Adapter が起動時解決して pin) / 768 次元 (MRL 切り詰め — 切り詰め後次元も
> profile に固定) / cosine / `modality="multimodal"` / `mode="online"`** の単一 multimodal profile 採用が
> 確定。**MVP で実際に embed するのは text chunk のみ**だが、profile を multimodal にしておくことで
> Phase 4+ の image/audio embedding を全 re-index なしに追加できる (`07 §5.3`)。旧 r2 の
> EMB-1 (multimodal 1536 fixture) / EMB-2 (gemini-embedding-001 text) は削除。
> profile の `model_version_pin` は Adapter が起動時に解決する GA 版付き名 (`07 §6`) であり、本ベクタの
> `"gemini-embedding-2"` は**算出規約の検証用 fixture 値** — 契約は「この入力ならこの hash」の算出関数固定のみ。

**EMB-1 (採用確定 profile: gemini-embedding-2 / 768 MRL / cosine / multimodal)** —
profile も `03 §5.1` の規約で実算出。`target_hash` は A.1 CHUNK-1 (r3 値):

```text
profile canonical: {"adapter_kind":"embedding","adapter_role":"multimodal","dimensions":768,"distance":"cosine","modality":"multimodal","model_or_tool_family":"gemini-embedding","model_version_pin":"gemini-embedding-2","runtime_kind":"cloud","spec_version":1}
tool_profile_hash = sha256:66aff638f38a099ff989ca97675ebd3c573a40ee53cc1cdfe05fb06102d2bb09

embedding canonical (target_hash = CHUNK-1): {"dimensions":768,"distance":"cosine","modality":"multimodal","profile_hash":"sha256:66aff638f38a099ff989ca97675ebd3c573a40ee53cc1cdfe05fb06102d2bb09","spec_version":1,"target_hash":"sha256:c5e31f10da04b722769bdbbd60a55b94c177b5f3bf9c64e5341be7281d115c3d","target_type":"chunk"}
embedding_hash = sha256:7bd32d26ad2b721e32c99536513abf58c6aeee626d1edc65e30069abce01a975
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

### A.5 MMR 数値例 (`05 §1.4` 多様化 — 生 RRF スコア → min-max 正規化 → MMR の一貫ベクタ)

`05 §1.4` (2026-07-03 確定): `relevance(c)` = **RRF スコアを MMR 候補プール内で min-max 正規化した値**
([0,1]。全候補が同スコアなら一律 1.0)。`similarity` は embedding の cosine (embedding 無しの text-only
検索では MMR を適用せず RRF 順のまま)。`score(c) = λ·relevance(c) - (1-λ)·max_{c'∈selected} sim(c,c')`、
`λ=0.7`。4 候補、Fraction 厳密計算:

**手順 1 — 生 RRF スコア (現実的スケール ~1/61) と min-max 正規化**:

| chunk | 生 RRF_score | float | 正規化 relevance = (raw−min)/(max−min) | float |
| --- | --- | --- | --- | --- |
| c1 | 3/100 | 0.030000 | (3/100−1/50)/(1/100) = **1** | 1.000000 |
| c2 | 2/75 | 0.026667 | (2/75−1/50)/(1/100) = **2/3** | 0.666667 |
| c3 | 13/500 | 0.026000 | (13/500−1/50)/(1/100) = **3/5** | 0.600000 |
| c4 | 1/50 | 0.020000 | (1/50−1/50)/(1/100) = **0** | 0.000000 |

(min = 1/50, max = 3/100, range = 1/100)

**手順 2 — MMR 選択 (類似度行列は embedding cosine)**:

```text
similarity: sim(c1,c2)=0.95  sim(c1,c3)=0.30  sim(c1,c4)=0.20
            sim(c2,c3)=0.25  sim(c2,c4)=0.15  sim(c3,c4)=0.40
```

| step | selected | 候補ごとの MMR score (厳密値) | 選択 |
| --- | --- | --- | --- |
| 1 | {} | c1=0.7·1=**7/10 (0.700)**, c2=0.7·2/3=7/15 (0.46667), c3=0.7·3/5=21/50 (0.420), c4=0 | **c1** |
| 2 | {c1} | c2=7/15−0.3·0.95=**109/600 (0.18167)**, c3=21/50−0.3·0.30=**33/100 (0.330)**, c4=0−0.3·0.20=−3/50 (−0.060) | **c3** |
| 3 | {c1,c3} | c2=7/15−0.3·max(0.95,0.25)=**109/600 (0.18167)**, c4=0−0.3·max(0.20,0.40)=−3/25 (−0.120) | **c2** |
| 4 | {c1,c3,c2} | c4=**−3/25 (−0.120)** | c4 |

**MMR 確定順序: c1, c3, c2, c4** (r2 の c1,c3,c4,c2 から変化 — min-max 正規化で c4 の relevance が 0 に
落ち、c2 の罰則後スコア 109/600 を下回るため)。

要点: (1) min-max 正規化はスケール・平行移動不変なので、生 RRF スコアの絶対値 (~1/61) に依らず
`mmr_lambda` の意味 (relevance と diversity の混合比) が保たれる。(2) c2 は正規化 relevance 2 位 (2/3)
だが c1 との cosine 0.95 (near-duplicate) の罰則で 3 位に後退する — 「同一原文の隣接 chunk が上位を
独占する」問題 (`05 §1.4`) の回避。(3) MMR score の同点は RRF 順、さらに同点は chunk_id 昇順 (`05 §1.4`)。
(4) 全候補が同スコアの縮退時は relevance 一律 1.0 (`05 §1.4`)。

### A.6 Evidence Pointer URI 往復ベクタ (`08 §2.3`)

`05 §1.7` 例と同形の完全 JSON pointer (optional 全部入り) を URI 化 → 再 parse する。
URI は**必須フィールドのみ** (`scope_id / commit / raw_hash / tool_profile_hash / chunk_hash [+ ?sv]`)。

```text
JSON (完全形, 13 フィールド):
  schema_version, commit, tree, raw_hash, tool_profile_hash, chunk_hash,
  path_at_commit, heading_path, section_id, char_start, char_end, scope_id, scope_path

URI (正規テキスト形。chunk_hash は A.1 CHUNK-1 の r3 値):
kio://scope_01J8ZQABCDEFGHJKMNPQRS/sha256:9f2c1a7b04dee5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e/sha256:74bcb92d8088c950e45e4c43563332da2ca1e04b25d6d4016aa43f830d4cca8a/sha256:e067e42e6634b8043f46a4b7f55257ab10ca6266be80cc47b6a68a5aacd2c8f0/sha256:c5e31f10da04b722769bdbbd60a55b94c177b5f3bf9c64e5341be7281d115c3d

URI → JSON (必須フィールドのみ復元, sv 省略 = 1):
  { schema_version=1, scope_id, commit, raw_hash, tool_profile_hash, chunk_hash }

往復で脱落する optional (7 件):
  char_start, char_end, heading_path, path_at_commit, scope_path, section_id, tree
```

全セグメントが `[A-Za-z0-9_:.-]` に閉じるため percent-encoding 不要 (`08 §2.3`)。
`sv` 省略時は `1`、未知 `sv` は `KIO-E-CONFIG-SCHEMA` 系 error (exit 2) (`08 §2.3`)。

### A.7 query_hash 固定ベクタ (`05 §1.8` 正準構成 — r3 新設)

`05 §1.8` (2026-07-03 確定、§C-2 解消): `query_hash = "sha256:" + base16(sha256(JCS({ query, mode,
scope_mode, scopes, diversify, time_travel })))`。`query` は NFC 正規化後のクエリ文字列、`mode` は解決後の
実効 mode、`scopes` は対象 scope_id の**昇順配列**、`diversify` は `[search.diversify]` の実効値、
`time_travel` は `--at`/`--all-history`/`--include-deleted`/`--since` の実効値 (未指定キーは省略)。
`limit` / `--offset` / `--cursor` / `--json` は**含めない** (ページング操作で hash が変わってはならない)。
**`rrf` キー (`[search.rrf]` の実効値 k / candidate_depth / w_text / w_vector) を含める最終形は 2026-07-03
発注側裁定** (05 §1.8 本文への `rrf` キー同期は発注側にて実施)。

fixture (デフォルト設定 + 2 scope + time-travel フラグ未指定):

```text
入力: query="認証仕様" (NFC), mode="hybrid", scope_mode="all",
      scopes=["scope_01J8ZQABCDEFGHJKMNPQRS","scope_01K3ABCDEFGHJKMNPQRSTV"] (昇順),
      diversify={enabled:true, strategy:"mmr", mmr_lambda:0.7, max_per_raw_hash:3, mmr_depth:100},
      rrf={k:60, candidate_depth:200, w_text:1.0, w_vector:1.0},
      time_travel={} (全キー未指定 → 空 object として固定。本 fixture で凍結)

canonical (RFC 8785 — 整数値 float は "1" に直列化される点に注意):
{"diversify":{"enabled":true,"max_per_raw_hash":3,"mmr_depth":100,"mmr_lambda":0.7,"strategy":"mmr"},"mode":"hybrid","query":"認証仕様","rrf":{"candidate_depth":200,"k":60,"w_text":1,"w_vector":1},"scope_mode":"all","scopes":["scope_01J8ZQABCDEFGHJKMNPQRS","scope_01K3ABCDEFGHJKMNPQRSTV"],"time_travel":{}}

query_hash = sha256:08820fbe38f26821717a56fde4cc1db4e104c5ff1221f62477127c070503d773
```

同一入力の再計算は常にこの値 (cursor validity の基盤、CT3-CURSOR-003/004)。`w_text=1.0` が `"1"` に
直列化されることは RFC 8785 準拠 JCS の float 検証を兼ねる (A 節冒頭注記)。

---

## B. テストケース

各ケース: **ID / 優先度 / Given-When-Then / 正本根拠**。

### CT3-CHUNK-* — chunking / chunk identity / 世代 / append-only (`03 §8.1, §5.3` / `04 §4.1, §4.5, §4.6`)

**CT3-CHUNK-001** — P0 — chunk_hash: gen=0, section_id 在 (slug 導出整合)
- Given: A.1 CHUNK-1 の identity タプル (section_id は `04 §4.1` 規則 4 の slug 導出値 `認証仕様/api-token`)。
- When: `JCS → sha256`。
- Then: canonical バイト列が A.1 と一致し、`chunk_hash = sha256:c5e31f10…5c3d`。
- 根拠: `03 §8.1` (chunk identity hash / `text_hash` 非包含 / null 省略) / `04 §4.1` 規則 3-4 (heading_path /
  section_id の正準導出) / `08 §2.1` (chunk_hash は
  `(raw_hash, tool_profile_hash, gen, unit_key, heading_path, section_id, char_start, char_end)` から導出)。
- 補足 (r3): ws1a A.5 の旧値 `sha256:8fefa482…e15a` (section_id="auth/api-token") は slug 規則確定前の
  例示値であり歴史的参照 (A.1 冒頭注記)。

**CT3-CHUNK-002** — P0 — chunk_hash は gen に連動 (gen+1 で別 identity)
- Given: A.1 CHUNK-2 (CHUNK-1 の gen のみ 0→3)。
- When: `JCS → sha256`。
- Then: `chunk_hash = sha256:688cc827…5e54`。CHUNK-1 と異なる。`(raw_hash, tool_profile_hash)` は不変。
- 根拠: `03 §8.1` (gen は hash 入力) / `03 §2.1` (identity は `(raw_hash, tool_profile_hash)`、gen は世代区別)。

**CT3-CHUNK-003** — P0 — section_id 省略と null を識別しない (+ heading_path=[] の保持)
- Given: A.1 CHUNK-3 (見出し未出現領域: heading_path=[], section_id 省略) と、同一だが `section_id: null`
  を明示した入力。
- When: canonicalize (null キー除去) → `JCS → sha256`。
- Then: 両者の canonical・hash が完全一致 (`sha256:d1fe73ce…c8d6`)。`heading_path: []` は定義値として
  canonical に残る (null 省略の対象ではない)。
- 根拠: `03 §8.1` (「null / 未設定フィールドは hash 入力に含めない (§5.1 と同じ規則。section_id を持たない
  chunking strategy では省略)」) / `04 §4.1` 規則 3 (見出し未出現の間は heading_path = [])。

**CT3-CHUNK-004** — P0 — chunking の正準規則 (heading 単位 + max_chars + slug)
- Given: 複数 heading (ATX 形式・コードフェンス内の `#` を含む) を持つ normalized unit と
  `[chunking] strategy="heading" max_chars=6000`。
- When: chunk を生成。
- Then: `04 §4.1` の正準規則 1-5 に従う: (1) chunk は unit 境界を跨がない。(2) heading 検出は ATX
  (行頭 1-6 個の `#` + 空白) のみ — setext・コードフェンス内 `#` は heading と見なさない。
  (3) `heading_path` = chunk 先頭位置で有効な ATX 見出しスタック (見出し未出現の間は [])。
  (4) `section_id` = 各要素の slug (NFC → ASCII 小文字化 → 空白列→`-` → 英数・`-`・`_`・日本語以外を
  除去 → `-` 連結圧縮 → 先頭末尾 `-` 除去。同一 unit 内重複は `#2` 付番) を `/` 結合。
  (5) max_chars 超過は段落境界 (空行) で貪欲分割、単一段落超過のみ文字位置で機械分割 — 分割片は同一
  heading_path / section_id を共有し unit-local span で区別。`char_start`/`char_end` は unit-local。
- 根拠: `04 §4.1` (chunk 境界の正準規則 1-5、2026-07-03 確定) / `03 §11` (`strategy` / `max_chars`) /
  `03 §8.1` (span は unit-local)。
- 補足 (r3): r2 まで §C-1 (未定義) だった heading_path 導出・section_id 生成・分割規則は `04 §4.1` への
  spec 追記で**解消済み** — 本テストの Then が firm 契約になった。

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
- When: 次回 `kio index`。
- Then: 全 normalized instance に H2 の再 chunk + 再 embedding task を積む。**旧 H1 の chunk 行は削除しない**
  (Evidence Pointer の chunk_hash 解決用に残置)。検索対象は現行 `chunking_config_hash` の chunk のみ。
  再 chunk はローカル処理 (LLM 不要)、embedding のみ再課金。
- 根拠: `04 §4.6` (chunk 世代判定 / 再 chunk task / 旧世代残置 / 検索は現行 config のみ) / `03 §5.3`。
- 補足: 再生成前の確認 (対象 chunk 数 + embedding 概算) は `04 §4.6`。`--yes` で省略。

**CT3-CHUNK-008** — P0 — chunks 行は append-only (更新/リネーム/削除で既存行を消さない)
- Given: chunk 済みファイルを更新・リネーム・OS 削除する。
- When: 次回 index。
- Then: 既存 chunk 行を DELETE / 変更しない。新 raw の chunk は新行として追加。既存行への UPDATE は
  `first_seen_commit` 付与のみ許可。chunk 行を物理削除する経路は `kio purge` のみ (Step 4)。
- 根拠: `04 §4.1` (「chunks 行は append-only … 削除する経路は kio purge のみ … UPDATE は first_seen_commit
  の付与のみ許可」)。
- 補足: append-only が time-travel (`--at`/`--all-history`/`--include-deleted`) の実体だが、それらの検索
  フラグ自体は Step 4 (§D)。本テストは「Step 3 の index が既存 chunk 行を破壊しない」不変条件のみ。

**CT3-CHUNK-009** — P0 — chunk 行が検索対象になるのは auto snapshot 作成後 + first_seen_commit 刻印
- Given: `kio index` 実行中 (auto snapshot 前) の chunk と、成功完了後の chunk。
- When: 検索対象集合を確認。
- Then: indexing 途中の chunk はどのモードでも返さない。`kio index` 成功完了時の auto snapshot 作成後に
  検索対象化し、その時点で新規 chunk 行に `first_seen_commit` (当該 commit_hash) を刻む。
- 根拠: `05 §1.6` (「chunk 行が検索対象になるのは kio index 成功完了時の auto snapshot 作成後 …
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

**CT3-CHUNK-012** — P0 (r2 で P1→P0 昇格) — rebuild-db end-to-end: sqlite.db 消去 → 再構築 → 検索結果等価
- Given: chunk / embedding / FTS / tree_entries 構築済みの scope。検索クエリ Q の確定順序
  (results / evidence_pointer) を記録してから `.kio/index/sqlite.db` を消去。
- When: `kio repair --rebuild-db` → 同一クエリ Q を再実行。
- Then: (a) chunks / embeddings / FTS index が normalized instance から再導出される。
  (b) `chunk_vec` は `objects/ → embeddings → chunk_vec` の順で再構築される。
  (c) `tree_entries` は HEAD commit 分が再構築される (他 commit 分は `--at` 時の再展開 = Step 4)。
  (d) クエリ Q の検索結果 (確定順序・evidence_pointer) が消去前と**等価**。真実は objects/。
- 根拠: `04 §4` 冒頭 (「真実は objects/、SQLite は再構築可能」) / `04 §5.7` (復元範囲に chunks/embeddings/FTS) /
  `04 §4.3` (embeddings → chunk_vec の再構築順) / `04 §4.5` (「kio repair --rebuild-db は HEAD 分のみ再構築」) /
  `05 §1.4-1.5` (決定論的確定順序 — 同一 chunk 集合 + 同一設定なら同一結果)。
- 補足: `kio repair --rebuild-db` コマンド枠は step2a CT2-TASK-010 で担保済み。本書は Step 3 artifact の
  再導出と検索等価性を end-to-end で追加検証する。

### CT3-EMBED-* — embedding identity / 互換性 / fallback (`03 §7, §8.1` / `04 §4.3, §5.5` / `07 §5.3`)

**CT3-EMBED-001** — P0 — embedding_hash の算出 (vector BLOB 非包含)
- Given: A.2 EMB-1 (採用確定 profile: gemini-embedding-2 / 768 MRL / cosine / multimodal) の identity
  タプル (target_type=chunk, target_hash=CHUNK-1 r3 値)。
- When: `JCS → sha256`。
- Then: canonical バイト列が A.2 と一致し、profile の `tool_profile_hash = sha256:66aff638…bb09`、
  `embedding_hash = sha256:7bd32d26…a975`。`vector` BLOB 実体は入力外。
- 根拠: `03 §8.1` (embedding identity hash) / `03 §5.1` (profile hash の算出規約) / `07 §5.3` (採用確定 profile)。
- 補足: A.2 冒頭注記のとおり `model_version_pin` の具体値は算出規約 fixture (実運用は Adapter が GA 版付き
  名を起動時解決して pin、`07 §6`)。

**CT3-EMBED-002** — P0 — 互換性不一致で vector 検索拒否 → text fallback
- Given: query embedding profile と index 側 embedding の `dimensions`/`distance`/`modality`/`profile_hash`
  のいずれかが不一致。`fail_behavior="fallback"`。
- When: `kio search`（auto/hybrid）。
- Then: vector 検索を強行せず text (BM25) に fallback。`resolved_mode="text"`, `fallback=true`,
  `fallback_reason` 記録、`error_code=KIO-E-SEARCH-VEC-INCOMPAT-001`。
- 根拠: `03 §7` (互換性ルール: dim/distance/modality/profile_hash 全一致が条件) / `05 §1.1` (auto 解決:
  profile_hash 不一致 → text fallback `KIO-E-SEARCH-VEC-INCOMPAT-001`) / `07 §5.3` (profile 不一致で再生成/text fallback)。

**CT3-EMBED-003** — P0 — 横断 vector 検索の互換性条件 (全 scope 一致でなければ text 統合)
- Given: multi-scope 検索で embedding profile が全 scope で一致しない。
- When: 横断 vector / hybrid 検索。
- Then: 横断部分は text (BM25 rank) のみで統合し、`fallback_reason` に記録する。
- 根拠: `05 §1.8` (5) (「embedding profile が全 scope で一致しない場合、横断部分は text (BM25 rank) のみで
  統合し fallback_reason に記録」) / `03 §7`。

**CT3-EMBED-004** — P0 — 採用確定 multimodal profile での embedding 生成と互換判定 (r3 改訂)
- Given: 採用確定 profile (`07 §5.3` 2026-07-03 再検証で確定: gemini-embedding-2 / 768 次元 MRL 切り詰め /
  cosine / `modality="multimodal"` / mode="online")。MVP の embedding 対象は **text chunk のみ**。
- When: chunk の embedding 生成 + vector 検索の互換判定。
- Then: `embeddings` 行は `modality="multimodal"` / `dimensions=768` / `distance="cosine"` /
  当該 profile_hash を持ち、embedding_hash は A.2 EMB-1 と同形で算出される。vector 検索の互換判定
  (`03 §7`) は `dimensions=768 / distance=cosine / modality=multimodal / profile_hash 一致` の全一致で
  成立する。image/audio embedding は MVP では生成しない (profile 予約のみ — Phase 4+ で全 re-index なしに
  追加可能)。
- 根拠: `07 §5.3` (「単一 multimodal profile を採用 (2026-07-03 再検証で確定)」/ text-only 緩和の撤回 /
  「MVP で実際に embed するのは text chunk のみ」) / `03 §7` (互換性: dimensions/distance/modality/
  profile_hash 全一致) / `04 §4.3` (単一マルチモーダル Embedding Adapter 前提)。
- 補足 (r3): r2 の text-only 緩和前提は WS-embed-2 裁定で撤回済み。MRL 切り詰め後次元 (768) も profile に
  固定されるため、切り詰め次元の変更は profile_hash 変化 = 別 identity (全 re-index) になる。

**CT3-EMBED-008** — P0 — 非 multimodal embedding profile の採用拒否 (2026-07-03 追加)
- Given: `modality != "multimodal"` の embedding adapter profile (例: `modality="text"`)。
- When: tool-lock への materialize / adapter 登録 / embedding 生成のいずれかの経路で当該 profile を使おうとする。
- Then: `KIO-E-EMBED-MODALITY-001` (exit 2) で**拒否**され、embeddings 行も chunk_vec 行も生成されない。
  エラーメッセージは採用可能な modality が "multimodal" のみであることを示す。
- 根拠: `03 §7` (modality="multimodal" 固定の強制) / `07 §5.3` (単一 multimodal profile 採用) /
  `06 §8` (`KIO-E-EMBED-MODALITY-001`)。別ベクトル空間 (text 専用等) の profile 採用を構造的に不可能にする。

**CT3-EMBED-005** — P1 — embeddings 正 / chunk_vec 導出 (rebuild 順序)
- Given: `embeddings` テーブルと `chunk_vec` (vec0) の不整合、または `kio repair --rebuild-db`。
- When: 再構築。
- Then: `objects/ → embeddings → chunk_vec` の順に再構築する。`embeddings` を正とし `chunk_vec` は導出物。
- 根拠: `04 §4.3` (「embeddings テーブルを正とし chunk_vec は導出物 … objects/ → embeddings → chunk_vec の順に再構築」)。

**CT3-EMBED-006** — P1 — content ベース再利用 (同一 text_hash × profile で Adapter を呼ばない)
- Given: `(text_hash, embedding profile_hash, dimensions, distance, modality)` 一致の既存 embedding が同一 .kio 内。
- When: embedding task。
- Then: Adapter を呼ばず既存 vector を再利用。incremental Markdownize 後の unchanged unit 由来で本文不変の
  chunk は embedding を再生成しない。
- 根拠: `04 §5.5` (embedding の content ベース再利用) / `03 §8` (text_hash は抽出範囲のみの hash)。

**CT3-EMBED-007** — P1 — vector-only モードで互換性 NG は error (fallback しない)
- Given: `kio search --vector` で embedding 互換性 NG。
- When: 検索。
- Then: text に fallback せず error (`--vector` は失敗時 error)。auto/hybrid の fallback とは分岐する。
- 根拠: `05 §1.2` (「--vector … 失敗時は error」) / `05 §1.1` (両方不可 → error `KIO-E-SEARCH-VEC-UNAVAIL-001`)。

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
  3 文字以上の CJK 部分一致とし、2 文字挙動は実装依存 (§C-7)。tokenizer 切替 (`unicode61`) は
  `[search.fts]` config (`04 §4.2`)。

**CT3-FTS-004** — P0 — FTS index は rebuild-db で chunks から再構築
- Given: FTS index を破棄し `kio repair --rebuild-db`。
- When: 再構築。
- Then: `chunks` から FTS を再導出する (真実は objects/ 由来の chunks)。
- 根拠: `04 §5.7` (復元範囲に FTS index) / `04 §4` 冒頭。

### CT3-HYBRID-* — mode 解決 / fallback / RRF 決定論 (`05 §1.1, §1.3, §1.7`)

**CT3-HYBRID-001** — P0 — auto 解決: 両方利用可能 → hybrid
- Given: text + vector 両方利用可能 (embedding 互換性 OK)、`default_mode="auto"`。
- When: `kio search "..."`。
- Then: `resolved_mode="hybrid"`。RRF(text, vector) で融合する。
- 根拠: `05 §1.1` (auto 解決順: 両方利用可能 → hybrid)。

**CT3-HYBRID-002** — P0 — auto 解決: vector のみ NG → text fallback + 可視化
- Given: vector 不可 (embedding 未設定 or 互換性 NG)、`fail_behavior="fallback"`。
- When: `kio search`。
- Then: `requested_mode="auto"`, `resolved_mode="text"`, `fallback=true`, `fallback_reason` (例
  `"embedding_endpoint_not_configured"`), `error_code` (該当時 `KIO-E-SEARCH-VEC-*`)。fallback を隠さない。
- 根拠: `05 §1.1` (vector のみ NG → text) / `05 §1.7` (レスポンス schema: fallback / fallback_reason / error_code)。

**CT3-HYBRID-003** — P0 — 両方不可 → error
- Given: text も vector も不可。
- When: `kio search`。
- Then: error (`KIO-E-SEARCH-VEC-UNAVAIL-001`)。
- 根拠: `05 §1.1` (両方不可 → error `KIO-E-SEARCH-VEC-UNAVAIL-001`)。

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
- Given: `kio search --hybrid`、vector 失敗、`fail_behavior ∈ {fallback, error, warn}`。
- When: 検索。
- Then: `fallback` → text へ、`error` → error、`warn` → 警告付きで text。設定に従い分岐する。
- 根拠: `05 §1.2` (「--hybrid … vector 失敗時は fail_behavior に従う」) / `05 §1.1` (fail_behavior)。

### CT3-MMR-* — 多様化 (`05 §1.4`)

**CT3-MMR-001** — P0 — MMR 選択順 (生 RRF → min-max 正規化 → MMR の一貫ベクタ)
- Given: A.5 の生 RRF スコア (c1=3/100, c2=2/75, c3=13/500, c4=1/50) + embedding cosine 類似度行列、`λ=0.7`。
- When: 候補プール内 min-max 正規化 → MMR を適用。
- Then: 正規化 relevance が A.5 手順 1 (c1=1, c2=2/3, c3=3/5, c4=0)、各 step の MMR score が A.5 手順 2 と
  一致し、**確定順序 `c1, c3, c2, c4`**。正規化 relevance 2 位の c2 は c1 との near-duplicate (cosine 0.95)
  罰則で 3 位に後退する。
- 根拠: `05 §1.4` (MMR 選択則 / 「relevance(c) = RRF スコアを MMR 候補プール内で min-max 正規化した値
  ([0,1]。全候補が同スコアなら一律 1.0)」— 2026-07-03 確定 / similarity = embedding cosine)。
- 補足 (r3): r2 の §C-3 (relevance スケール未定義) は `05 §1.4` への spec 追記で解消済み。本ベクタは
  生スコア → 正規化 → 選択の全経路を固定する。全同点 → 一律 1.0 の縮退分岐も P0 assert に含める。

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

**CT3-MMR-005** — P1 — strategy 切替 (mmr / group_by_raw_hash / off) + text-only の MMR 非適用
- Given: `[search.diversify] strategy` を各値に設定。加えて embedding 無し (text-only 検索) × `strategy="mmr"`。
- When: 検索。
- Then: `mmr` → MMR、`group_by_raw_hash` → raw_hash グルーピング、`off` → 素の RRF 順。いずれも決定論的。
  **embedding が無い場合 (text-only 検索) は `strategy="mmr"` でも MMR を適用せず RRF 順のまま** (similarity
  の計算基盤である cosine が無いため)。
- 根拠: `05 §1.4` (`strategy` 3 値 / 「similarity は embedding の cosine。embedding が無い場合 (text-only
  検索) は MMR を適用せず RRF 順のままとする」— 2026-07-03 確定)。

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

**CT3-CURSOR-003** — P0 — query_hash 不一致の cursor は `KIO-E-SEARCH-CURSOR-001` で拒否
- Given: あるクエリ・条件で発行した cursor を、別クエリ (または別 mode/diversify/rrf/time-travel 条件) の
  検索に渡す。
- When: cursor を使う。
- Then: token 全体の `query_hash` 不一致を検出し `KIO-E-SEARCH-CURSOR-001` で拒否 (exit は横断規約)。
  query_hash の算出は A.7 の正準構成 (`JCS({query, mode, scope_mode, scopes, diversify, rrf, time_travel})`)
  に一致し、A.7 fixture の入力なら `sha256:08820fbe…d773`。`limit`/`--offset`/`--cursor`/`--json` の違いでは
  hash は変わらない (拒否しない)。
- 根拠: `05 §1.5` (「query_hash が不一致の cursor は KIO-E-SEARCH-CURSOR-001 で拒否」) / `05 §1.8`
  (query_hash の正準構成 — 2026-07-03 確定、§C-2 解消。`rrf` キーを含む最終形は発注側裁定 — A.7 注記)。
- 補足 (r3): r2 の「canonical 入力構成が未定義につき hash 値は固定しない」は解消 — A.7 の固定ベクタで
  値まで assert する。

**CT3-CURSOR-004** — P0 — cursor は opaque token (JCS の base64url)
- Given: multi-scope cursor (`05 §1.8` の per-scope sub-cursor 合成)。
- When: `next_cursor` を検査。
- Then: `{v, scope_mode, query_hash, scopes[]}` JSON の JCS を base64url した opaque token。
  各 sub-cursor は `{scope_id, snapshot_commit, max_rowid, consumed}`。
- 根拠: `05 §1.8` (cursor の multi-scope 拡張 / opaque token)。

**CT3-CURSOR-005** — P0 — shallow 化 commit を snapshot とする cursor 再計算は `KIO-E-COMMIT-SHALLOW-001`
- Given: cursor 中の `snapshot_commit` が shallow 化済み (tree 破棄)。
- When: 次ページの再計算。
- Then: `KIO-E-COMMIT-SHALLOW-001` で失敗し、cursor なしの再検索を案内する。
- 根拠: `05 §1.8` (「cursor 中の snapshot_commit が shallow 化済みの場合、cursor の再計算は
  KIO-E-COMMIT-SHALLOW-001 で失敗する」) / `05 §2.2`。
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
- When: `kio search "..."` (scope 指定なし)。
- Then: `participates_in_global_search=true` の scope を列挙して横断検索。`--scope <path>` / `--descendants`
  指定時は root_path 前方一致で絞り込む。
- 根拠: `05 §1.8` (対象 scope の列挙 1-2) / `06 §3` (デフォルト全 indexed scope 横断)。

**CT3-MULTI-002** — P0 — scope 間統合は rank ベース (raw スコア比較禁止)
- Given: 各 scope が RRF 済み上位 candidate_depth 件を返す。BM25/vector の raw スコアは index ごとに
  コーパス統計が異なる。
- When: scope 間マージ。
- Then: 各 scope の **RRF スコア (rank のみから決まる)** をそのまま比較して降順マージ。BM25/vector の
  raw スコアを scope 間で比較・正規化しない。同点は `(scope_id, chunk_hash)` の辞書順で安定化。
- 根拠: `05 §1.8` (実行とマージ 3) (「rank ベース … raw スコアを scope 間で比較・正規化してはならない …
  同点は (scope_id, chunk_hash) の辞書順」)。

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

**CT3-MULTI-005** — P0 — 部分失敗は結果を返し exit 3、全失敗は `KIO-E-SEARCH-SCOPE-ALL-FAILED-001` exit 4
- Given: (a) 一部 scope 失敗 / stale / timeout、(b) 全 scope 失敗。
- When: 検索。
- Then: (a) 結果を返し `excluded_scopes` に記録、exit 3。(b) error `KIO-E-SEARCH-SCOPE-ALL-FAILED-001`、exit 4。
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
- 補足 (r2): **機能契約と性能契約を分離する**。eval/ の合成コーパス (305 ファイル / 7 scopes、
  `eval/corpus_spec.py`) は Recall 判定用であり、この性能前提 (20 scopes / 10 万 chunk) を測れない。
  **性能 fixture は別途 Step 3 後半に合成拡張スクリプトで生成**する。本テストは「計測対象構成と閾値」を
  契約として固定し、実測はその性能 fixture + metrics.jsonl (CT3-OBS-002) に委ねる。

**CT3-MULTI-008** — P1 (r2 新設) — `--all-scopes` の受理と対象範囲
- Given: scope_registry に複数 scope。カレントディレクトリは特定 scope 内。
- When: `kio search "..." --all-scopes`。
- Then: フラグを受理し、全 indexed scope を対象として横断検索する (デフォルト = 全 indexed scope 横断
  `06 §3` と同一の対象列挙)。`searched_scopes` に対象 scope を全列挙する。
- 根拠: `06 §3` (`--all-scopes` 構文 / デフォルトは全 indexed scope 横断) / `05 §1.8` (列挙規則)。
- 補足: `--all-scopes` とデフォルトの差分意味論 (`participates_in_global_search=false` の scope を含めるか)
  は spec 未定義 (§C-8 に併記)。本テストは受理と「全 indexed scope 対象」のみ assert し、差分は実装決定を
  固定して決定論性を assert する。

### CT3-EVIDENCE-* — Evidence Pointer 発行・解決 (`08 §2, §3` / `05 §1.7`)

**CT3-EVIDENCE-001** — P0 — 検索結果に必須フィールド全部 + evidence_uri を発行
- Given: hybrid 検索がヒット chunk を返す。
- When: 各 result の `evidence_pointer` / `evidence_uri` を検査。
- Then: `08 §2.1` の**必須 6 フィールド** `schema_version / commit / raw_hash / tool_profile_hash /
  chunk_hash / scope_id` を全て持つ (充足率 100%)。加えて**検索発行の pointer** は `heading_path` /
  `char_start` / `char_end` を持つ (M3-1 完了条件「Evidence Pointer に commit + raw_hash + chunk_hash +
  heading_path + span」)。`tree` / `path_at_commit` / `section_id` / `scope_path` は optional (`08 §2.2`)
  であり、存在を必須 assert しない (存在する場合は §2 schema に整合すること)。`evidence_uri` は
  §2.3 正規テキスト形で、そのまま `kio open`/`kio view` に渡せる。
- 根拠: `08 §2.1` (必須 6 フィールド) / `08 §2.2` (optional — 必須化しない) / `05 §1.7` (レスポンス schema /
  evidence_uri / evidence_pointer をそのまま埋め込む) / `09 §4.1` (Evidence 必須フィールド充足率 100%) /
  `09 §M3-1` (heading_path + span は検索発行 pointer の完了条件)。

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
- Then: (a) scope_path の .kio を使う。(b) scope_registry を scope_id で照会し kio_path を得る (同一 scope_id
  複数登録は last_seen_at 最新優先、曖昧なら候補一覧 error)。どちらも失敗 →
  `KIO-E-EVIDENCE-SCOPE-UNREACHABLE-001` (scope_unreachable)。root 信頼は scope_id。
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
  (b) `KIO-E-PURGE-NOT-FOUND-001` (not_found)。(c) `KIO-E-EVIDENCE-SCOPE-UNREACHABLE-001` (scope_unreachable)。
- 根拠: `08 §3.2` (部分的失敗 3 値) / `08 §4.1` (tombstone schema) / `08 §4.2` (not_found)。
- 補足: tombstone の**生成** (`kio purge`) は Step 4 (§D)。本テストは `05 §3.5` の tombstone ファイル形式
  (`.kio/tombstones/ab/cd/<raw_hash>`) を**手置き**して、Step 3 の resolver が tombstone/not_found を
  正しく返すことを検証する (`kio open` の dead pointer exit 4 が Step 3 で必要なため resolver は Step 3)。

**CT3-EVIDENCE-007** — P1 — results[].scope_path は表示・高速化ヒント (解決の root 信頼にしない)
- Given: pointer の scope_path が実際の .kio 位置と食い違う (移動後) が scope_id は一致。
- When: 解決。
- Then: scope_id が一致する限り解決可能 (registry 経由)。scope_path は解決の root 信頼にしない。
- 根拠: `08 §2.2` (「scope_path も … ヒントであり、解決の root 信頼にしない … scope_id が一致する限り
  pointer は解決可能」) / `05 §1.7` (truth vs cache)。

**CT3-EVIDENCE-008** — P1 — schema forward compatible (未知フィールド無視)
- Given: 未知 optional フィールドを持つ pointer (MINOR 追加想定)。
- When: 解決。
- Then: エラーなく必須フィールドで解決 (未知フィールドは無視)。
- 根拠: `08 §8` (「新 schema は古い解決ロジックでもエラーなく扱える (forward compatible) … 未知フィールドは無視」)。

**CT3-EVIDENCE-009** — P0 (r2 新設) — eval 結合点: raw_hash / section_id は results[].evidence_pointer から読む
- Given: `kio search --json` の結果と、eval ハーネス (`eval/run_eval.py`) の Recall@10 判定。
- When: eval ハーネスが上位 10 件の distinct `(raw_hash, section)` を数える。
- Then: `results[]` の各要素は top-level に `chunk_hash / evidence_pointer / evidence_uri / score /
  scope_path` を持ち (`05 §1.7` の例と同形)、`raw_hash` / `section_id` / `heading_path` は
  **`results[].evidence_pointer` (`08 §2` 準拠) の内側から読める**。eval ハーネスは evidence_pointer から
  `(raw_hash, section_id ?? heading_path 末尾)` を読み出せる (top-level の raw_hash に依存しない)。
- 根拠: `05 §1.7` (results[] schema — raw_hash は evidence_pointer 内にのみ定義 / 「evidence_pointer は
  08 §2 の schema をそのまま埋め込む」) / `08 §2` / `09 §4.3` (Recall@10 = distinct (raw_hash, section))。
- 補足: `eval/run_eval.py` は evidence_pointer 経由の読み出しに修正済み (2026-07-03、eval 側修正は発注側)。
  本テストは search 側 schema と eval 側読み出しの**結合点**を固定し、schema 変更による Recall 計測の
  silent 破壊を防ぐ。

### CT3-URI-* — URI 正規形と受理規則 (`08 §2.3`)

**CT3-URI-001** — P0 — JSON → URI → JSON 往復 (optional 脱落)
- Given: A.6 の完全 JSON pointer (optional 全部入り)。
- When: URI 化 → 再 parse。
- Then: URI = A.6 の正規テキスト形。往復後の JSON は必須フィールドのみ (`schema_version=1` 補完)、
  optional 7 件 (`char_start/char_end/heading_path/path_at_commit/scope_path/section_id/tree`) が脱落する。
  必須フィールドは失われない。
- 根拠: `08 §2.3` (「URI は必須フィールドのみ … 往復で失われてよいのは optional フィールドだけ」)。

**CT3-URI-002** — P0 — object 参照 URI (第 2 セグメント `object`) を Evidence Pointer と区別
- Given: `kio://<scope_id>/object/image/<image_hash>` と Evidence Pointer URI
  (`kio://<scope_id>/sha256:.../.../.../...`)。
- When: URI を判別。
- Then: 第 2 セグメントがリテラル `object` なら object 参照、`sha256:` prefix なら Evidence Pointer。
  Evidence Pointer の第 2 セグメント (commit) は常に `sha256:` prefix を持つため衝突しない。`kio open` は
  object 参照も受理して該当 object を解決する。
- 根拠: `08 §2.3` (第 2 セグメント `object` の区別 / commit は常に sha256: prefix) / step2a CT2-IMAGE-002/003
  (object 参照 URI の生成は Step 2、解決は Step 3)。

**CT3-URI-003** — P0 — `<pointer>` 受理規則 (prefix 優先順位)
- Given: (1) `-` (stdin) / (2) `kio://` (URI) / (3) `{` (inline JSON) / (4) `sha256:` (短縮形) / (5) その他。
- When: CLI の `<pointer>` 引数を解釈。
- Then: prefix 優先順で判定。(4) 短縮形は `kio open`/`kio view` のみで object store を照会し種別判別
  (chunk_hash/raw_hash)、多義なら候補一覧 error。(5) parse 失敗 → exit 2 (invalid usage)。
- 根拠: `08 §2.3` (CLI `<pointer>` 受理規則 5 分岐) / `06 §1` (受理形式は 08 §2.3 を正本)。

**CT3-URI-004** — P1 — `sv` 省略 = 1、未知 sv は exit 2
- Given: (a) `?sv` なし URI / (b) `?sv=99` (未知)。
- When: parse。
- Then: (a) `schema_version=1`。(b) `KIO-E-CONFIG-SCHEMA` 系 error、exit 2。
- 根拠: `08 §2.3` (「sv 省略時は 1。未知の sv は KIO-E-CONFIG-SCHEMA 系 error (exit 2)」)。

### CT3-OPEN-* — kio open / kio view (`06 §1.1, §7` / `05 §4.2`)

**CT3-OPEN-001** — P0 — 解決順: working tree に同一 raw_hash があればそれを開く (リネーム耐性)
- Given: pointer を解決した raw_hash を持つファイルが working tree に存在 (path_at_commit と異なる path でもよい)。
- When: `kio open <pointer>`。
- Then: その実ファイルを OS 規定アプリで開く (一時展開しない)。
- 根拠: `06 §1.1` 手順 1-2 (「pointer を解決して raw_hash … working tree に同一 raw_hash を持つファイルが
  存在すれば … その実ファイルを OS 規定アプリで開く」)。

**CT3-OPEN-002** — P0 — 一時展開: working tree に無ければ CAS から read-only 展開して開く
- Given: working tree に該当 raw_hash が無い (削除済み / 過去版 / raw_hash 直指定)。
- When: `kio open`。
- Then: raw object を `~/.cache/kio/open/<raw_hash 先頭 12 桁>/<path_at_commit の basename>` に
  read-only 展開し OS 規定アプリで開く。restore ではない (working tree に書かない)。stderr に
  「原本は working tree に存在しない … 永続コピーは kio restore --to」を表示。
- 根拠: `06 §1.1` 手順 3 (一時展開 / read-only / 展開先) / 一時展開は restore ではない旨。

**CT3-OPEN-003** — P0 — dead pointer (tombstoned / not_found / scope_unreachable) は exit 4
- Given: 解決が tombstoned / not_found / scope_unreachable のいずれか。
- When: `kio open` / `kio view` / `kio restore`。
- Then: exit 4。
- 根拠: `06 §7` (「kio open / view / restore  dead pointer (tombstoned / not_found / scope_unreachable) は 4」) /
  `06 §1.1` 手順 4。
- 補足: `kio restore` 自体は Step 4 だが、`kio open`/`kio view` の dead pointer exit 4 は Step 3。本テストは
  open/view で検証 (restore は §D)。

**CT3-OPEN-004** — P0 — `kio view` は過去版 object をそのまま返す (再 Markdownize しない)
- Given: pointer / path を指す chunk / normalized unit。
- When: `kio view <pointer>`。
- Then: 当該 commit の object をそのまま返す (再 Markdownize / 再生成しない)。
- 根拠: `05 §4.2` (「過去 commit 時点の Markdown を再生成せず、当該 commit の object をそのまま返す」) /
  `08 §7.1` (`kio view <pointer>` = 該当 chunk の Markdown 取得)。
- 補足: `kio view <path> --at <commit>` の `--at` は time-travel につき Step 4 (§D)。本テストは pointer 指定の
  過去 object 返却 (再生成しない契約) のみ。

**CT3-OPEN-005** — P1 — 短縮形 `sha256:` を kio open が種別判別して解決
- Given: `kio open sha256:<chunk_hash>` / `kio open sha256:<raw_hash>`。
- When: 解決。
- Then: object store を照会して種別を判別し、chunk_hash なら chunk、raw_hash なら raw として
  カレント .kio + HEAD 文脈に解決。多義なら候補一覧 error。
- 根拠: `08 §2.3` (受理規則 4 / 短縮形は kio open / kio view のみ)。

### CT3-REINDEX-* — kio reindex --force (`07 §9` / `03 §2.1` / `06 §1`)

**CT3-REINDEX-001** — P0 — `--force` は gen+1 の新 instance を作り旧 gen を残置
- Given: `g0` instance が存在する `(raw_hash, tool_profile_hash)`。
- When: `kio reindex --force`。
- Then: `gen = 現最大 + 1` (= g1) の新 normalized instance を作る。既存 `g0` instance (manifest / unit object)
  は保全 (上書き・削除しない)。`--force` は first-instance-wins の唯一の上書き経路。
- 根拠: `07 §9` (「explicit re-normalize … gen+1 の新 normalized instance … 旧 instance は保全」) /
  `03 §2.1` (gen / 「kio reindex --force だけが gen = 現最大 + 1 の新 instance を作り、既存 instance は保全」) /
  `06 §1` (reindex --force)。

**CT3-REINDEX-002** — P0 — Evidence Pointer 不変: 過去 commit の tree entry は旧 gen を参照し続ける
- Given: `g0` を指す既存 Evidence Pointer / 過去 commit の tree entry。`kio reindex --force` で g1 を作成。
- When: 過去 commit の tree entry / 既存 pointer を解決 (`kio view --at 相当の gen 保全)。
- Then: 過去 commit の tree entry は旧 gen (g0) を指し続け、既存 pointer は g0 の chunk を解決する。
  新規参照 (新 commit の tree entry / 新 chunk) のみ最新 gen (g1) を使う。
- 根拠: `03 §2.1` (「kio reindex --force 後も過去 commit の tree entry は旧 gen を指し続ける」/
  「新規参照は常に最新 gen」) / `03 §8` (tree entry の gen 保全で `kio view --at` と pointer 不変性が成立) /
  `08 §6` (不変性保証)。

**CT3-REINDEX-003** — P0 — `--force` は確認プロンプト必須 (--yes で省略可)
- Given: `kio reindex --force` を対話環境で実行。
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
- When: `kio search --json`。
- Then: `index_status = { enriched_ratio, pending_enrichment_tasks, budget_paused }` を返す
  (enriched_ratio < 1.0 のときのみ必須)。人間向けは「AI 強化 42% (budget により一時停止中)」の 1 行に翻訳。
- 根拠: `05 §1.7` (index_status / enriched_ratio < 1.0 のとき必須 / 人間向け翻訳) / `09 §3.1` (index_status = Step 3)。
- 補足: `enriched_ratio` の分子分母定義 (何を「強化済み」と数えるか) は spec 未定義 (§C-5)。本テストは
  「部分 index 時に index_status を返し done/pending/paused を隠さない」ことのみ assert。

**CT3-OBS-002** — P0 — metrics.jsonl への per-search latency 記録 (M3 計測の一次データ)
- Given: `kio search` を複数回実行 (redact_logs 既定 true)。
- When: `~/.local/share/kio/logs/metrics.jsonl` を読む。
- Then: **1 回の検索実行ごとに 1 行**が追記され、各行は envelope 必須フィールド `ts, level, code,
  component, message, context` (`ts` は UTC ISO8601+Z) に加え **`metric: "search.latency_ms"` /
  `value: <実測 ms>`** を持ち、`context` に `mode` (実効 mode) / `scope_count` / `result_count` を含む。
  クエリ本文・path は記録しない (redact_logs 既定)。この一次データから p50/p95/p99 (`09 §4.1`) が算出
  できる (1h 間隔の集計メトリクスはこの一次データから導出してよい)。
- 根拠: `05 §7` (「検索 latency の per-search 記録」— 2026-07-03 追記、§C-4 解消。record 形式 / redact 規則 /
  集計導出) / `06 §13` (envelope 必須フィールド / timestamp) / `09 §3.1` (metrics.jsonl = Step 3、M3 の
  latency 計測に必要) / `09 §4.1` (Latency p50/p95/p99)。
- 補足 (r3): r2 の保留マーク (§C-4 要-spec) は `05 §7` への spec 追記で解除。per-search 記録が firm 契約。

**CT3-OBS-003** — P0 — access.jsonl に検索アクセスを記録 (redact_logs 既定 true)
- Given: `kio search`。
- When: `.kio/logs/access.jsonl` を読む。
- Then: 検索アクセスログ行が追記される。`redact_logs` 既定 true のとき `context` の `query` 等機微
  フィールドをマスクする。行は JSON 必須フィールド `ts, level, code, component, message, context` を持つ。
- 根拠: `05 §7` (access.jsonl / redact_logs 既定 true) / `06 §13` (必須フィールド / redact_logs) / `09 §3.1`
  (access.jsonl = Step 3)。
- 補足: access.jsonl の記録フィールド詳細 (どのフィールドを残すか) は spec 未定義 (§C-5)。

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
> 値の正本化は spec 追記後に行う。**r3 現在、要-spec の残は 0 件**: r2 の要-spec 4 件 (#1〜#4) は
> 2026-07-03 の spec 追記 (`04 §4.1` / `05 §1.8` / `05 §1.4` / `05 §7`) で**解消済み** (#6 も同追記で解消)。
> 残る #5, #7〜#9 の 4 件は実装者判断で固定し、事後に spec へ反映すれば足りる。
>
> (注記: Step 2 で 2026-07-03 に確定した unit_key 正準生成 (`04 §2`)・page fingerprint (`04 §2.1`)・
> prompt_template_hash step1-2 (`03 §5.1`) は本書では前提として扱い、§C に再掲しない。)
>
> (r2 注記: 旧 #4「latency 計測ハーネスと eval コーパス」は stale につき削除 — `eval/` は 2026-07-03 に
> コミット済み (`eval/golden-queries.jsonl` M3-1: 18 / M3-2: 16 / M3-3: 16 件、合成コーパス 305 ファイル /
> 7 scopes)、宿題 #5 (`09 §5.5`) は decided。番号は r2 のまま維持し、r3 では各項の解消状態のみ更新。)

1. **[解消済み r3] chunk 境界の決定性** — `04 §4.1`「chunk 境界の正準規則」(2026-07-03 追記) で確定:
   (1) chunk は unit 境界を跨がない。(2) heading 検出は ATX のみ (setext・コードフェンス内 `#` は対象外)。
   (3) `heading_path` = chunk 先頭位置で有効な ATX 見出しスタック (見出し未出現の間は [])。
   (4) `section_id` = 各要素の slug (NFC → ASCII 小文字化 → 空白列→`-` → 英数・`-`・`_`・日本語以外を
   除去 → `-` 圧縮 → trim。unit 内重複は `#2` 付番) を `/` 結合。(5) max_chars 超過は段落境界で貪欲分割
   (分割片は heading_path / section_id を共有し unit-local span で区別)。これらは **chunk_hash の入力**
   (`03 §8.1`) であり、確定により chunk identity = Evidence Pointer の永続性 (`08 §6`) が実装非依存になった。
   反映: CT3-CHUNK-001/003/004 を firm 契約に昇格、A.1 を slug 導出整合値で再凍結 (旧 "auth/api-token" 例は
   歴史的参照)。なお `03 §8.1` chunk object 例・`08 §2` 例の section_id の同期は発注側にて実施。

2. **[解消済み r3] query_hash の正準入力構成** — `05 §1.8` (2026-07-03 追記) で確定:
   `"sha256:" + base16(sha256(JCS({query (NFC), mode (解決後の実効値), scope_mode, scopes (scope_id 昇順),
   diversify ([search.diversify] 実効値), time_travel (未指定キー省略)})))`。`limit` / `--offset` /
   `--cursor` / `--json` は含めない (ページング操作で hash が変わってはならない)。`rrf` ([search.rrf] の
   実効値 k / candidate_depth / w_text / w_vector) を含める最終形は 2026-07-03 発注側裁定 (05 §1.8 本文への
   `rrf` キー同期は発注側にて実施 — A.7 注記)。反映: A.7 に固定ベクタを新設、CT3-CURSOR-003 で値まで assert。

3. **[解消済み r3] MMR relevance の正規化・スケール** — `05 §1.4` (2026-07-03 追記) で確定:
   `relevance(c)` = RRF スコアを **MMR 候補プール内で min-max 正規化した値** ([0,1]。全候補が同スコアなら
   一律 1.0)。生の RRF スコア (最大 ~1/k) をそのまま使うと mmr_lambda の意味が損なわれるため。
   反映: A.5 を「生 RRF → min-max 正規化 → MMR」の一貫ベクタで再凍結 (確定順序は c1,c3,c2,c4 に変化)、
   CT3-MMR-001 同期済み。

4. **[解消済み r3] per-search latency の metrics.jsonl 記録 schema** — `05 §7` (2026-07-03 追記) で確定:
   `kio search` は 1 回の実行ごとに metrics.jsonl へ 1 行を追記 — envelope 必須フィールド (`ts, level,
   code, component, message, context`) に加え `metric: "search.latency_ms"` / `value: <実測 ms>` /
   `context: {mode, scope_count, result_count}`。redact_logs 既定に従いクエリ本文・path は記録しない。
   1h 間隔の集計メトリクスはこの一次データから導出してよい。反映: CT3-OBS-002 の保留マーク解除、firm 契約化。

5. **index_status / access.jsonl の詳細 schema** — (a) `index_status.enriched_ratio` の分子分母 (何を
   「強化済み」と数えるか: Markdownize done? embedding done? chunk indexed?)、(b) `access.jsonl` の
   記録フィールドと redact 対象の詳細、が未定義 (`05 §1.7` / `06 §13` は行の必須フィールドと存在のみ規定)。
   影響: CT3-OBS-001/003。実装者判断で固定。

6. **[解消済み r3] MMR similarity 関数の選択規則** — `05 §1.4` (2026-07-03 追記) で確定: `similarity` は
   **embedding の cosine**。embedding が無い場合 (text-only 検索) は **MMR を適用せず RRF 順のまま**とする。
   反映: CT3-MMR-005 に text-only 非適用分岐を追加、A.5 の類似度行列は embedding cosine と明記。
   (§1.4 の選択則コードブロックに残る「または heading_path / section_id の Jaccard」の併記は、同日追記の
   確定規則 (bullet) を正とする。)

7. **trigram の 2 文字 CJK クエリ挙動** — `04 §4.2` は trigram (3-gram) を定めるが、gram 長 (3) 未満の
   2 文字 CJK クエリで索引を使うか linear scan に落ちるかが未定義。影響: CT3-FTS-003。実装者判断
   (firm 契約は 3 文字以上の部分一致)。

8. **CLI オペランド・フラグの細部** — (a) `kio reindex [--force] [--at <commit>]` (`06 §1`) の対象
   (path 指定 / scope 全体 / 特定 raw_hash) の既定が未定義 (`--at` は time-travel 系につき Step 4 寄り、§D)。
   (b) `--all-scopes` (`06 §3`) とデフォルト (全 indexed scope 横断) の差分意味論
   (`participates_in_global_search=false` を含めるか) が未定義。影響: CT3-REINDEX-* / CT3-MULTI-008。実装者判断。

9. **embeddings の vector BLOB シリアライズ形式** — `04 §4.3` は `vector BLOB` / `chunk_vec FLOAT[<dim>]` を
   定めるが、float 精度 (f32/f64) / endianness / 正規化の有無が未定義。sqlite-vec 依存の実装詳細。
   影響: CT3-EMBED-001 (identity は BLOB 非包含なので identity には影響しないが、再現性検証に関わる)。実装者判断。

---

## D. Step 3 範囲外として意図的に除外したもの (根拠付き)

以下は Step 3 の契約テストに **含めない**。理由は `09 §3.1` (機能×Step 割当) と各正本 §。

| 除外項目 | 除外理由 (根拠) |
| --- | --- |
| time-travel 検索フラグ `--at` / `--all-history` / `--include-deleted` / `--since` と、その chunk 集合 join 意味論 (`05 §1.6`: `chunks ⨝ tree_entries(<commit>)` / `files[status='deleted']` / 全 chunk / created_at フィルタ) | `09 §3.1` line 125: **Step 4** (`restore --to` / `--at` / `--all-history` / `--include-deleted` は同一行で Step 4)。Step 3 は基盤 (tree_entries HEAD 射影 `04 §4.5` / chunks append-only `04 §4.1` / first_seen_commit 刻印 `05 §1.6`) を作り、**デフォルト検索 (HEAD join) のみ**を検証 (CT3-CHUNK-008/009/010)。M3-2 (`--all-history`) / M3-3 (`--include-deleted`) は time-travel を要するため **Step 4 完了扱い**。Step 3 の Done は M3-1 |
| 非 HEAD commit の tree_entries 展開 (`--at` 時の tree object 展開挿入) | `04 §4.5` (「--at <commit> 検索時、当該 commit 分が無ければ tree object を展開して挿入」) は time-travel の一部 → Step 4。Step 3 は HEAD 分の常駐のみ (CT3-CHUNK-010) |
| `restore --to` / `--force` / working tree 非破壊 | `09 §3.1` line 125: Step 4 (`05 §4`)。`kio open` の一時展開 (restore ではない、`06 §1.1`) は Step 3 (CT3-OPEN-002) として区別 |
| `kio view <path> --at <commit>` の `--at` 分岐 | `--at` は time-travel → Step 4。Step 3 は pointer 指定の過去 object 返却 (再生成しない契約、CT3-OPEN-004) のみ |
| purge の**実行** (tombstone 発行 / `commit_type=purged` commit / `--erase-tombstone` / chunk 行物理削除) | `09 §3.1` line 126: Step 4 (`05 §3`)。Step 3 は tombstone **解決** (手置きファイルで resolver が tombstoned/not_found を返す、`kio open` exit 4 に必要、CT3-EVIDENCE-006 / CT3-OPEN-003) のみ。tombstone の生成はしない |
| `kio evidence verify <pointer>` (単発) CLI と `--strict` | `09 §3.1` line 128: **Step 4** (`08 §4.3`)。Step 3 は verify が surface する alive/tombstoned/not_found の **resolver 計算** (CT3-EVIDENCE-006) を担うが、`kio evidence verify` サブコマンド枠は Step 4。exit code 4 の検証は `kio open`/`kio view` (Step 3) で行う (CT3-OPEN-003) |
| `kio evidence verify --batch` / `kio evidence retarget` | `09 §3.1` line 135-136: Phase 4+ (`08 §4.3`, `08 §5`) |
| `kio repair --verify-objects` (CAS 整合性検証) | `09 §3.1` line 127: Step 4 (`10 §7.5`)。`kio repair --rebuild-db` の chunk/FTS/embedding 再導出 (CT3-CHUNK-012 / CT3-FTS-004 / CT3-EMBED-005) は Step 3 (`04 §5.7`)。コマンド枠は step2a CT2-TASK-010 で担保済み |
| shallow 化の**生成** (tiered retention / `kio gc` / tree 破棄) | `05 §2.2`, `09 §3.1` line 130-132: Phase 4+。Step 3 は shallow commit の **解決/失敗契約** (手置きの shallow commit で CT3-EVIDENCE-005 / CT3-CURSOR-005) のみ |
| GC の**実行** (shallow / prune / tiered / CoW / power-loss sweep) | `05 §2.2`, `09 §3.1`: Phase 4+。Step 1 CT-GC-* の schema 遵守を変えない |
| chunk レベル semantic_fingerprint / retarget の match_method | `08 §5` / `09 §5.2`: retarget は Phase 4+。Step 3 は chunk identity (hash) のみ扱い、類似性 fingerprint は扱わない (`03 §5` hash vs fingerprint 分離) |
| multimodal embedding のベンダー実地検証 (次元/料金/deprecation) | `07 §5.3`: 2026-07-03 再検証で**採用確定済み** (gemini-embedding-2 / 768 MRL / cosine / multimodal — WS-embed-2 裁定、text-only 緩和は撤回)。Step 3 は確定 profile での生成・互換判定契約 (CT3-EMBED-004、A.2) を検証する。image/audio embedding の**実生成**は Phase 4+ (profile 予約のみ) |
| Summary / Classification / Rerank Adapter の生成本体 | `07 §5.4-5.6` optional。`09 §3.1` の Step 3 行に無い。Rerank の searched_scopes 非隠蔽 (CT3-OBS-004) のみ横断契約として参照 |
| Prepare / Markdownize / incremental / task / budget / secrets / network opt-in | `09 §3.1`: Step 2。step2a で担保済み。Step 3 は normalized instance (unit object 群) を入力として受け、chunk 以降を担う |
| CAS / tree / commit / hash 算出 / CLI 7 コマンド / lock | Step 1 (ws1a) で担保。Step 3 は commit の tree entry 射影 (tree_entries) を読むが tree/commit 生成は Step 1 |
| `kio search` と書き込み系の lock 相互作用 (`kio index` と `kio search` 同時実行 / rebuild 中の search) | `05 §6` (search は lock 取得しない / rebuild 中は旧 db or `KIO-E-INDEX-REBUILDING-001`) は横断契約。search が読み取り系で lock を取らない点は ws1a CT-LOCK-003 の延長で担保。`KIO-E-INDEX-REBUILDING-001` は rebuild-db (Step 2 枠) 実行中の search 挙動につき P2 参考に留め本書では固定しない |

**Step 3 の Done gate (r2 で整理)**: eval ハーネス (`eval/run_eval.py`) のフル実行は M3-2 (`--all-history`) /
M3-3 (`--include-deleted`) のクエリを含むが、これらのフラグは Step 4 実装 (`09 §3.1`)。したがって
**Step 3 の完了判定 = 「M3-1 の 18 クエリ (`eval/golden-queries.jsonl` の scenario=M3-1) で
Recall@10 >= 0.8」+「本書 P0 全緑」** とし、M3-2 / M3-3 の Recall 判定は Step 4 完了時に行う
(`09 §4.3` の Done 条件は Phase 3 完成時 = Step 4 完了後の全シナリオ判定)。M3-1 の p95 < 5 秒 (性能契約)
は機能契約と分離し、性能 fixture (20 scopes / 10 万 chunk、Step 3 後半に合成拡張スクリプトで生成) で
計測する (CT3-MULTI-007 補足)。

---

## 集計 (報告用)

- **P0 テスト数**: 60 (総テスト数 77: P0 60 / P1 17。CT3-EMBED-008 = 非 multimodal profile 拒否を 2026-07-03 追加)
  (CT3-CHUNK 11 / CT3-EMBED 5 / CT3-FTS 4 / CT3-HYBRID 6 / CT3-MMR 4 / CT3-CURSOR 5 / CT3-MULTI 5 /
   CT3-EVIDENCE 7 / CT3-URI 3 / CT3-OPEN 4 / CT3-REINDEX 3 / CT3-OBS 3)
  (r2: 57 + CT3-EVIDENCE-009 新設 + CT3-CHUNK-012 P1→P0 昇格。CT3-MULTI-008 は P1 新設。
   r3: CT3-EMBED-008 追加で P0 59→60。ベクタ再凍結と §C 解消状態の同期)
- **spec 未定義事項**: 9 件 (§C)。うち **#1〜#4 および #6 の 5 件は 2026-07-03 の spec 追記
  (`04 §4.1` chunk 境界正準規則 / `05 §1.8` query_hash 正準構成 / `05 §1.4` MMR min-max 正規化 +
  similarity=cosine / `05 §7` per-search latency 記録) で解消済み** — **要-spec の残は 0 件**。
  残り 4 件 (#5 index_status・access 詳細 schema / #7 trigram 2 文字 / #8 CLI オペランド細部 /
  #9 vector BLOB 形式) は実装者判断で固定 → 事後 spec 反映で足りる。
