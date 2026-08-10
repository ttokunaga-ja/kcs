# 契約テストの是正 — 作業ブリーフ

このファイルはそのまま作業者 (人でもエージェントでも) への指示として読める形にしてある。

**状態: 未着手。** [2026-08-10]

---

# 任務

**契約テストを「機能が起動すること」の検証から「契約の観測量」の検証に直す。**
とくに**順位**は、競合の居ないコーパスでは構造的に検証できない。その層を作る。

## なぜこれをやるのか — 実際に起きたこと

2026-08-10、日本語の語レーンを実装し、契約テスト 4 本すべて green で入れた。
その後 eval ハーネスで測ったところ:

- 作った目的 (短いクエリ) での効果は **0** (0.9167 → 0.9167、外した 2 問も同一)
- 既存 50 問で **M3-2 / M3-3 が 1.000 → 0.938 に悪化**、改善は 0 件
- 正解が **6 位**まで落ち、1〜5 位を「`廃止` を含むだけ」の文書が占めた

**契約テスト 4 本が 1 本も落ちなかった理由は、4 本とも索引した文書が 1 件だったから。**
レーンの主張は順位についてのもので、**1 件しかないコーパスには順位が無い**。
とくに `wl4_a_document_both_lanes_find_is_returned_once` は「融合が文書を重複させない」を
**文書 1 件**に対して主張していた。

詳細と数字: **[tasks/word-lane-measurement.md](word-lane-measurement.md)**
(レーン自体は `2693e6d` で revert 済み。直すのはテストの方)

---

# 0. 先に測ってある事実 (再導出しないこと)

再現コマンドは各項に付けてあるが、**この数字を前提に始めてよい**。

| | |
|---|---|
| `search` を叩くテスト | **219 本** |
| コーパス 0-1 文書 | 57 本 |
| コーパス 2-4 文書 | 159 本 |
| **コーパス 5 文書以上** | **3 本** |
| 主力 fixture `indexed_scope()` (`crates/kio-cli/tests/step3_p0_contract.rs:115`) | **2 文書 / 4 chunk**、**82 本**が使用 |

- 実使用規模: eval fixture は **200-500 files × 8 scope**、`candidate_depth` は **200**
  (`docs/05-runtime.md`)。**4 chunk のコーパスでは MMR も RRF も候補打ち切りも
  実質的に何もしていない** — 全部が top 10 に入るから
- 実行時間の現状: `step3_p0_contract` 244 本で **78 秒**、`step4b_p2c_contract` 38 本で **31 秒**
- CI の recall ゲートは**存在する**: `.github/workflows/ci.yml` の
  `synthetic-history-eval` が `run_eval.py` を M3-1 / M3-2 / M3-3 で走らせている

**語レーンがそのゲートをすり抜けたのは、既定 off の cargo feature だったから。**
CI は feature 無しでビルドするので、順位を見られる唯一のゲートが
そのコードを一度もコンパイルしていなかった。ゲートが無かったのではなく、
**ゲートの外を通る道があった。**

---

# 1. 主張とコーパスの不一致を解消する

下の 20 本は、**0-1 文書のコーパスに対して top1 / 順序 / 件数を主張している**。

> **これは欠陥リストではなく候補リストである。**各本について
> 「その主張は本当に選択に依存するのか、それとも二値なのか」を判断すること。
> 二値なら現状で正しい。**判断した結果を必ず記録すること** (下記)。

```
crates/kio-cli/tests/step3_p0_contract.rs:1163  [count] r15_3_reinit_same_path_does_not_duplicate_registry_target
crates/kio-cli/tests/step3_p0_contract.rs:1309  [count] ct3_multi_011_a_departed_scope_stops_skewing_corpus_statistics
crates/kio-cli/tests/step3_p0_contract.rs:1407  [count] ct3_multi_012_a_narrowed_search_does_not_prune_the_replica
crates/kio-cli/tests/step3_p0_contract.rs:1650  [count] ct3_multi_016_a_narrowed_search_is_ranked_among_the_scopes_it_searched
crates/kio-cli/tests/step3_p0_contract.rs:1930  [count] ct3_multi_010_single_scope_search_is_not_reranked_by_the_replica
crates/kio-cli/tests/step3_p0_contract.rs:2019  [count] ct3_multi_003_diversify_caps_raw_hash_across_scopes
crates/kio-cli/tests/step3_p0_contract.rs:6470  [top1] an_image_row_carries_the_referencing_chunks_evidence_pointer
crates/kio-cli/tests/step3_p0_contract.rs:6735  [top1] an_image_inherits_the_text_lane_standing_of_the_chunk_that_cites_it
crates/kio-cli/tests/step3_p0_contract.rs:7607  [count] r17_6_repair_softens_guidance_for_searchable_cached_document
crates/kio-cli/tests/step3_p0_contract.rs:7660  [count] r17_6_repair_keeps_emergency_guidance_when_no_cached_chunks_survive
crates/kio-cli/tests/step4_promotion.rs:403     [count] ct4_promotion_respects_bbox_disabled_profile_identity
crates/kio-cli/tests/step4_time_travel.rs:1175  [count] ct4_timetravel_011_historical_reindex_enriches_only_selected_snapshot
crates/kio-cli/tests/step4b_p2c_contract.rs:246 [count] pc15_pc17_candidate_depth_configuration_is_not_hardcoded_to_200
crates/kio-cli/tests/step4b_p2c_contract.rs:322 [top1/count] r23_17_bounded_escalation_recovers_eligible_row_starved_by_inner_limit
crates/kio-cli/tests/step4b_p2c_contract.rs:2116 [top1] f3_escaped_punctuation_is_findable_by_the_plain_query_and_shown_unescaped
crates/kio-cli/tests/step4b_p2c_contract.rs:2146 [top1] f3_fenced_code_keeps_the_backslashes_the_corpus_actually_contains
crates/kio-cli/tests/step5_embedding_batch_lane.rs:266 [count] batch_resume_collects_the_vectors_and_clears_the_intent_token
crates/kio-cli/tests/step5_local_ocr.rs:278     [count] s3e_the_local_pipelines_figure_is_reachable_from_the_chunk_that_cites_it
crates/kio-cli/tests/step5_local_ocr.rs:315     [count] s3e_a_chunks_related_images_offer_the_figure_and_not_the_decoration
crates/kio-cli/tests/step5_local_ocr.rs:364     [count] s3e_the_related_image_floor_can_be_lowered_without_reindexing
```

**既に判定済みで、変えなくてよいと分かっているもの:**

- `f3_escaped_punctuation_...` と `f3_fenced_code_...` — **現状で正しい**。あの欠陥は
  「見つかる / 見つからない」の二値で、順位が関与しない。1 文書コーパスでの
  `!results.is_empty()` + snippet の内容検査は契約の観測量そのもの。
  **問題はテストの層ではなく、コーパスと欠陥の種類が合っているかである**

各本について取れる道は 2 つだけ:

- **(a) 競合を足す** — その主張が選択に依存するなら、選択肢を置く
- **(b) 主張を、実際に証明できる範囲まで弱める** — 「1 位である」を
  「結果に含まれる」に落とすなど

**(b) を選んだ場合、テストのコメントに「何を主張しないことにしたか」と
「その性質はどこで担保されるか」を書くこと。**黙って弱めるのは、
いま直そうとしている問題そのものである。

成果物として `tasks/contract-test-remediation-ledger.md` に 20 行の表を作る:
`test 名 | 判定 (二値 / 選択依存) | 取った道 (現状維持 / a / b) | 理由 1 行`。

---

# 2. 順位の層を新設する

**ここが本体。**

## 2.1 fixture の要件

- **約 40 文書、決定論的、リポジトリにコミットする**
- **distractor (妨害文書) を設計して入れること。これが本体である。**
  クエリの語を共有するが答えではない文書。合成 eval コーパスが語レーンを
  測れなかった理由がまさにこれの不在で、anchor が `Osprey` `Komodo` `RRF` `HNSW`
  のような固有名詞を必ず持っていたので、**競合が居らず、順位が意味を持たなかった**
- **1 テスト 1 索引にしないこと。**`step3_p0_contract` は現在 244 本で 78 秒。
  テストごとに 40 文書を索引したら分単位になる。`OnceLock` などで
  **1 回だけ索引して複製する**形にすること
- 十分な件数を入れること。**top 10 が実際に絞りとして働く**規模が要る
  (全部が top 10 に入るなら 4 chunk と同じ)

## 2.2 主張の形

`!results.is_empty()` を書かないこと。書くのは:

- 「意図した文書が **1 位**である」
- 「**distractor がそれを上回らない**」
- 変更前後で比較する**差分**主張

## 2.3 クエリの形 — 実使用に合わせる

`docs/05-runtime.md` §1.3 が実際に扱っている形を網羅すること:

- **12 文字以下の短問** (`eval/golden-queries-short.jsonl` に 24 問ある。形の参考に)
- 自然文の日本語 (既存 `eval/golden-queries.jsonl` は最短 14 文字・中央値 29 文字)
- 識別子・パス・ハッシュ (トリグラムの領分)
- 混在字種
- 桁区切り数値 (`3600` と `3,600` の等価。eval M3-2/M3-3 で 13/14 件の失敗を
  出した実績のある形)

---

# 3. ゲートの穴を塞ぐ

`.github/workflows/ci.yml` の `synthetic-history-eval` に対して:

1. **`eval/golden-queries-short.jsonl` を追加する。**現在ゲートされている 50 問は
   **1.000 で飽和**していて、悪化しか検出できない。短問集合は **22/24 (0.9167)** で、
   **伸びしろが残っている唯一の集合**である
   - 呼び方: `python3 eval/run_eval.py --golden eval/golden-queries-short.jsonl --scenario M3-1 --corpus ... --bin ...`
   - **M3-1 のみで走らせること。**`run_eval.py:1151` の `HISTORY_QUERY_COUNT = 16` は
     M3-2 / M3-3 に対する**セット全体の契約**で、問題数の違う golden file を
     当てると落ちる (`run_crossscope.py` が別ランナーになっているのはこの理由)
   - **現行 HEAD での基準値は 22/24。**これを下回ったら失敗にすること

2. **順位に影響する cargo feature は、eval job で on 側も走らせる。
   さもなくば optional にしない。**語レーンが通った道はここだった

3. `run_crossscope.py` (16 問) の追加も検討する。`worst_expected_rank` という
   診断値を持っていて、Recall@10 が構造的に見えない融合の欠陥を見られる

---

# 4. 受け入れ条件

**最重要 — 新しいテストが「落ちうる」ことを実証すること。**

いま直している欠陥は「落ちないテスト」である。同じものをもう一度作らないために、
**順位を意図的に壊した状態で新しいテスト群が実際に赤くなることを示すこと。**
たとえば RRF の定数を極端な値にする、融合の重みを片側に倒す、
`candidate_depth` を 1 にする、といった一時的な改変で、
**どのテストが何本落ちたかを報告に含めること。**1 本も落ちないなら、
そのテストは書けていない。

そのほか:

- §1 の 20 本すべてについて判定と取った道が ledger に記録されている
- §2 の fixture が入り、`step3_p0_contract` の実行時間が **現状 (78 秒) の 2 倍以内**
- §3 の CI 変更が入り、短問集合が 22/24 を下回ると落ちる
- **既存テストを 1 本も黙って弱めていない** (弱めたものは理由付きで ledger にある)
- `cargo clippy --workspace --all-targets` が warning 0
- 既存の green を壊していない: `kio-index` 83 / `kio-adapter` 9 /
  `step3_p0_contract` 244 / `step4b_p2c_contract` 38

---

# 5. やってはいけないこと

- **テストを通すために主張を弱める。**弱めてよいのは「その主張が元々証明できて
  いなかった」と判断したときだけで、そのときは ledger に理由を書く
- **リポジトリ外の実文書を fixture にする。**`ttokunaga-ja/kio` は
  **public リポジトリ**である。入力はリポジトリ内のものに限ること
- **`cargo test` の結果をパイプで要約する。**パイプの exit code は cargo のものでは
  なく、実際に失敗しているクレートが「0 failed」に合算された事例がある。
  終了コードは直接受けること
- **`cargo test` が緑だから eval も緑だと考える。**eval は Python 側で、
  `cargo test` は一切走らせない。順位の判定は eval にしか無い
- **索引や検索の実装を「テストを通すために」変更する。**この任務はテストの是正で
  あって実装の変更ではない。実装の欠陥を見つけたら**報告する**こと

---

# 6. 環境メモ

- **このリポジトリの Mac ではビルドしたてのバイナリが最初の 1 行を出すまで
  数分止まることがある。**0:00.00 CPU のまま無反応に見える。
  `ps -o time` を見てから殺すこと。ハングと紛らわしい
- eval の一巡 (corpus 生成 → replay → run_eval) は数分かかる。
  `replay_history.py` は scope ごとに `init → index → snapshot` を 4 回まわす
- eval は API キーを環境から落とすので (`eval/eval_env.py`)、
  **text lane のみの評価**になる。順位の検証にはむしろ都合がよい
