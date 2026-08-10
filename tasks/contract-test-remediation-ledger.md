# 契約テスト是正台帳

§0 の測定値を前提に、§1 の候補を実アサーションまで確認して判定した。ここでの「二値」は、結果集合の順位ではなく、存在・不在・重複排除・状態遷移・出力内容を直接観測していることを指す。

| test 名 | 判定 | 取った道 | 理由 |
| --- | --- | --- | --- |
| `r15_3_reinit_same_path_does_not_duplicate_registry_target` | 二値 | 現状維持 | dead scope による重複排除は件数そのものの契約で、順位を選んでいない。 |
| `ct3_multi_011_a_departed_scope_stops_skewing_corpus_statistics` | 二値 | 現状維持 | 到達不能 scope の射影削除と結果からの不在を観測している。 |
| `ct3_multi_012_a_narrowed_search_does_not_prune_the_replica` | 二値 | 現状維持 | narrowed read が replica の scope 数を削らない、という状態不変条件である。 |
| `ct3_multi_016_a_narrowed_search_is_ranked_among_the_scopes_it_searched` | 選択依存 | 現状維持 | 既に競合を置いている。 |
| `ct3_multi_010_single_scope_search_is_not_reranked_by_the_replica` | 二値 | 現状維持 | 一 scope の固定 RRF score と replica 非変化を検査しており、競合選択を主張しない。 |
| `ct3_multi_003_diversify_caps_raw_hash_across_scopes` | 選択依存 | 現状維持 | 既に競合を置いている。 |
| `an_image_row_carries_the_referencing_chunks_evidence_pointer` | 二値 | 現状維持 | image row の pointer shape と検証可能性を確認するデータ整合性契約である。 |
| `an_image_inherits_the_text_lane_standing_of_the_chunk_that_cites_it` | 選択依存 | 現状維持 | 既に競合を置いている。 |
| `r17_6_repair_softens_guidance_for_searchable_cached_document` | 二値 | 現状維持 | cached chunk の生存と guidance の状態遷移を確認する。 |
| `r17_6_repair_keeps_emergency_guidance_when_no_cached_chunks_survive` | 二値 | 現状維持 | cached chunk 不在時の非検索可能性と emergency guidance を確認する。 |
| `ct4_promotion_respects_bbox_disabled_profile_identity` | 二値 | 現状維持 | promotion による HEAD 変化と OCR row の存在を確認する。 |
| `ct4_timetravel_011_historical_reindex_enriches_only_selected_snapshot` | 二値 | 現状維持 | snapshot ごとの association 数を直接比較する隔離契約である。 |
| `pc15_pc17_candidate_depth_configuration_is_not_hardcoded_to_200` | 選択依存 | 現状維持 | 既に競合を置いている。 |
| `r23_17_bounded_escalation_recovers_eligible_row_starved_by_inner_limit` | 選択依存 | 現状維持 | 既に競合を置いている。 |
| `f3_escaped_punctuation_is_findable_by_the_plain_query_and_shown_unescaped` | 二値 | 現状維持 | plain query で見つかることと snippet 表示の文字列が契約で、順位は関与しない。 |
| `f3_fenced_code_keeps_the_backslashes_the_corpus_actually_contains` | 二値 | 現状維持 | fence 内の backslash が snippet に保存されるかという二値の内容契約である。 |
| `batch_resume_collects_the_vectors_and_clears_the_intent_token` | 二値 | 現状維持 | batch state、token cleanup、vector の存在を検証する。 |
| `s3e_the_local_pipelines_figure_is_reachable_from_the_chunk_that_cites_it` | 二値 | 現状維持 | related image の URI と `open` の到達可能性を検証する。 |
| `s3e_a_chunks_related_images_offer_the_figure_and_not_the_decoration` | 二値 | 現状維持 | 開いた bytes で figure を同定し decoration を除外する内容契約である。 |
| `s3e_the_related_image_floor_can_be_lowered_without_reindexing` | 二値 | 現状維持 | read-side config 変更で related image 数が増えることを検証する。 |

## `57850f0` 再適用確認（2026-08-10）

**結論: 長問テストは語レーン下で赤くなる。**

### 経過（途中の 2 回は無効な確認だった）

1 回目と 2 回目の再適用確認はどちらも「6/6 green、再現できず」と記録したが、
**どちらも無効**である。語レーンは既定 off の cargo feature なので、
`cargo test -p kio-cli --test step3_p0_contract ranking_` では
**レーンがコンパイルされない**。`57850f0` を適用しただけでは有効にならず、
`--features word-lane` が要る。したがってあの 2 回は、レーンの無い
バイナリを 2 回測っていた。fixture を 2 度調整したのはこの誤りに引きずられた結果で、
**fixture 側に問題は無かった。**

### 確定した測定

語レーンを実際に有効にしたバイナリで、同一 fixture コーパスに対し
`廃止した旧フォーマット v0.1.0 の仕様書` を実行した結果:

| | 結果件数 | 内容 |
|---|---|---|
| **off** | **3 件** | すべて `legacy-format-v0.md` |
| **on** | **10 件** | 1-3 位 `legacy-format-v0.md`、4 位 `leaked-draft-pricing`、5-6 位 `deprecated-approach`、**8 位 `filler-00.md`** |

アサーション別の判定:

| | off | on |
|---|---|---|
| `assert_ranked_first(legacy)` | PASS | **PASS** |
| `filler-*` が出ない | PASS | **FAIL** |
| 異なり文書 == `[legacy-format-v0.md]` | PASS | **FAIL** |
| | GREEN | **RED** |

**rank 1 は語レーン下でも保たれる。**追加した精度アサーション 2 本だけが発火する。
実コーパス (8 scope 横断・2000 件規模) では正解が 6 位まで落ちたが、
40 文書の単一 scope ではその形にはならず、**精度の劣化として現れる** —
off の「3 件すべて正解」が、on では 10 件中 6 文書に薄まり、
クエリと共通語を 1 つも持たない filler まで混入する。原因は同じ等重み RRF 融合で、
40 文書で捕まえられるのはここまでで、それで足りる。

`57850f0` の一時適用は確認後に戻し、作業ツリーに索引・検索実装の変更は無い
(`Cargo.lock` の lindera 0 件、`word_lane.rs` / `word_lane_contract.rs` 不在で確認)。
