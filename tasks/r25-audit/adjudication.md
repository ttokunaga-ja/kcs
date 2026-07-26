# R25 裁定と次作業の計画 (2026-07-25)

4 系統 (sol ×1 / terra ×2 / glm ×1) の 19 指摘を名寄せし、**すべて原文と実コードで再検証した上で**
裁定した。多数決では決めていない — 単独指摘でも根拠が実在すれば採用し、複数一致でも根拠が
弱ければ降格した。

判定分布: 不合格 2 (sol1, terra1) / 条件付き合格 2 (terra2, glm1)。

**裁定結果: 条件付き合格。** 設計 (replication + write-through の向き) は正しい。ただし
**適用条件と鮮度キーに実装漏れがあり、うち 1 件は北極星シナリオを壊す。**

---

## 1. 確定 (私が実コードで再現・確認した)

### R25-1 [fatal] 時間選択子付き検索と cursor replay に aggregator を無条件適用している

**系統**: terra1 A1 / terra2 A1 (2 系統独立一致)

`docs/05-runtime.md:557-560` は適用条件を明記する。

> aggregator は既定検索 — 次を**すべて**満たすもの — を答える。
> - 時間選択子が無い (`--at` / `--all-history` / `--since` / `--include-deleted` のいずれも未指定)
> - cursor が凍結済み commit を再生しているのではない

`main.rs:3256` の `global_ranks_for(...)` 呼び出しは **この 2 条件をどちらも見ていない**。
引数に時間選択子も cursor も渡っていない。

**何が起きるか**: `--at <commit>` の履歴検索で、候補は per-scope 経路が過去 commit から正しく
選ぶが、順位は `apply_global_ranks` が**現行 replica の順位**で上書きする。さらに
`main.rs` の `apply_global_ranks` は

```rust
if ranks.scored_text && candidate.text_rank.is_some() {
    candidate.text_rank = ranks.text.get(&key).copied();   // 現行 replica に無ければ None
}
```

なので、**履歴にしか存在しない chunk は `text_rank = None` になり RRF の text 項が 0 に潰れる**。
purge 済み・config 世代が変わった・削除された chunk がまさにそれである。

北極星 M3-3「削除したはずの数字を再発見」が直撃する。eval が 1.0 のままなのは、
**計測が replication 変更前 (`58cea60`) のものであり、かつ eval の多くが単一 scope で
`searched.len() <= 1` の早期 return に落ちるため**。つまり**この欠陥は一度も計測されていない**。

### R25-2 [major] 2 文字クエリで異尺度 RRF が復活する

**系統**: terra1 A4 / terra2 A2 (2 系統独立一致)

`build_query_plan` (`main.rs:5884`) は trigram の下限から unit を `chars().count() >= 3` で絞り、
全 unit が短い「pure-short query」では `match_expr: None` を返す (`main.rs:5907`)。

すると `global_ranks_for` は `scored_text = false` のまま vector だけ採点し、
`apply_global_ranks` は `if ranks.scored_text && ...` が偽なので **text_rank を per-scope のまま
残し、vector_rank だけ global に差し替える**。

**per-scope の text 順位と global の vector 順位を RRF で加算する** — これは今回の変更が
消すために作られた欠陥そのものである。

日本語では 2 文字語 (認証・設計・課金・障害・監査…) が最も普通のクエリ長で、実際に私が
実コーパスで叩いた `認証` がこの経路だった。

### R25-3 [major] delta が「在るが stale な scope」に最新 generation を刻む

**系統**: sol1 A5 / terra1 A3 (2 系統独立一致)

`aggregator.rs` の `apply_delta` は scope 不在なら何も書かず `false` を返すガードを持つ。
だが **「scope は在るが chunk が欠けている」場合を守っていない**。欠落 chunk は
`else { continue }` で飛ばした上で、最後に現行 generation を刻む。

**筋道**: 索引が G2 へ回転 → `write_through_projection` が失敗 (ログのみ、非致命) →
replica は G1 のまま chunk {a} → 埋め込みレーンが b のベクタを書き `apply_delta` →
scope は在るので `false` にならず、b は replica に無いので skip → **G2 を刻む** →
次の検索は「最新」と判断して射影を飛ばす → **chunk b は恒久的に corpus から消える**。

私のガードは「一度も複製されていない scope」だけを想定しており、「部分的に古い scope」を
想定していなかった。**自分の fix が開けた穴**の定番脈がまた出た。

### R25-4 [major] 非回転の in-place 経路では write-through 失敗が恒久 stale になる

**系統**: sol1 A4 / terra2 A4 (2 系統独立一致、両者とも「非回転の in-place」に正しく限定)

再構築経路なら write-through が失敗してもスタンプが動いているので次の検索が再射影する
(自己修復)。しかし**回転しない in-place 経路** (同期埋め込みレーン・reuse link・`reindex --at`)
では、write-through が失敗するとスタンプが動かないので **lazy refresh も発火せず**、
replica は恒久的に古いままになる。

### R25-5 [major] purge は replica 消去の失敗を無視して成功を返す

**系統**: sol1 A2 (fatal 主張) / terra2 A5 (major)

`purge.rs:502` の `crate::write_through_projection(repo.kio_dir());` は `()` を返す。
失敗時は stderr にログを出すだけで、**purge は成功を報告する**。

purge の目的は本文を存在させなくすることであり、replica は chunk 本文を cache root に持つ。
消去に失敗したまま「成功」と言うのは、法務要件を持つ操作として成立しない。

**sol1 の fatal は major へ降格**: 正本 (`objects/`・SQLite) の削除自体は成功しており、
残るのは cache の投影である。ただし「成功と報告する」ことが問題の芯なので major は動かさない。

### R25-6 [major] spec が宣言する embedding CAS object が実装に存在しない

**系統**: sol1 A1 (fatal 主張、単独指摘)

`docs/04-pipeline.md:25` は object type に `embedding (CAS)` を挙げ、`:546` は
「真実は `objects/` にある」「再構築順は `objects/` → `embeddings` → `chunk_vec`」と定める。

**実コーパスで確認した**: `.kio/objects/` は `chunks commits manifests normalized
normalized_units prepared raw trees` の 8 種で、**embedding は無い**。DB には embedding 行が
10 件ある。実装コメント (`main.rs:7277`) も
「Embeddings live only in SQLite (objects/ holds no embedding objects in the MVP)」と自認する。

`kio repair rebuild-db` は正本からではなく**これから置き換える DB から snapshot している**。
`sqlite.db` を失えばベクタは API から買い直すしかない。

**fatal → major へ降格**: ユーザーの知識 (本文) は `objects/normalized` にあり失われない。
失うのは金銭コストと時間である。ただし **spec が誤り**であり `repair rebuild-db` の保証は
過大表示なので、どちらかを直す必要がある。

### R25-7 [minor] `ScopeDelta.removed` に本番の書き手が無い

**系統**: glm G2 (単独指摘、確認済み)

`grep` で確認した。`removed` に値を入れるのは `aggregator.rs:699` の単体テストだけである。
purge を全射影に切り替えたときに delta 側の機構を残し、doc コメントは
「purge holds the chunk ids it just deleted」と**今は偽になった説明**を残した。私の後始末漏れ。

### R25-8 [minor] refresh の並列度と timeout が spec 未実装

**系統**: glm G3 (単独指摘、確認済み)

`docs/05-runtime.md:518` は「並列度は min(4, 差分 scope 数)、per-scope timeout は 2 秒」と
定めるが、`global_ranks_for` の refresh は直列ループで timeout が無い。
write-through 導入後は通常ここが no-op なので実害は縮んだが、**spec が実装より先行している**
状態は I19 で自ら批判した形と同型である。

---

## 2. 妥当 (根拠は実在するが未追跡 — 着手前に検証する)

| ID | 内容 | 系統 | 状況 |
|---|---|---|---|
| R25-9 | replica が「解決済み live 集合」でなく `first_seen_commit IS NOT NULL` の全行を複製する。config 世代更新・削除・履歴が入ると df/N/avgdl が誤り、`LIMIT depth` の切り詰めが live chunk を押し出す | terra1 A2 / terra2 A3 | **現コーパスでは潜在**。428 scope で 3,851 = 3,851 と一致しており、単一 config・削除なしのため差が出ていない。通常の運用で必ず顕在化する |
| R25-10 | `reindex --at` が pinned manifest object でなく作業コピーを見るため、後日の same-gen 完了が過去 commit へ逆流する | sol1 A3 | 引用した `03-data-model.md:232-237` の規範は実在。実装側の追跡は未実施 |
| R25-11 | profile 切替が sibling の旧 `chunk_vec` を残す / 絞り込み検索が未参加 scope と不互換 profile のベクタを global rank の母集団に混入させる | terra1 A5, A6 | 後者は `vector_scores` が replica 全体を採点する構造から筋が通る。次元不一致は skip 済みだが同次元別 profile は素通りする |
| R25-12 | 同期レーン・reuse link・`reindex --at` が cursor を退役させない (LC25 違反) | glm G1 | **私が `docs/05-runtime.md:507-509` に「未解決」と明記済み**。glm はそれを再発見した形 |

---

## 3. 構造的な芯 — 2 つの根本原因に畳める

19 指摘のうち確定 8 件は、**独立した 8 個のバグではなく 2 つの原因の派生**である。

### 原因 A — 鮮度キーが「replica が遅れている」を表現できない

**R25-3・R25-4・R25-12 は同一の根**。write-through は通知の**向き**を直したが、
`index_generation` という**鍵**をそのままにした。回転しない経路では、

- スタンプが動かないので lazy refresh が発火しない (R25-4)
- スタンプが一致するので stale な scope に delta を重ねて刻める (R25-3)
- スタンプが動かないので cursor が退役しない (R25-12)

**1 つの変更で 3 件が閉じる**: **索引を in-place に変える全経路で `index_generation` を回転させる。**
そうすれば lazy refresh が本当の安全網に戻り、R25-3 の stale scope はスタンプ不一致で
全射影に落ち、cursor は LC25 どおり退役する。

回転を「上端に足す」のが脆いことは I21 で確認済みなので、**回転も write-through と同じ下端**
(`persist_group_vector` / `link_chunk_vec` を通る書き込み点、`project_selected_snapshot` の commit) に
置く。回転は per-scope 1 回でよいので、write-through の flush と同じ場所に同居させる。

### 原因 B — aggregator の適用条件が実装に存在しない

**R25-1・R25-2 は同一の根**。spec は「既定検索のときだけ答える」と定めるのに、実装には
その判定が 1 行も無い。R25-1 は時間軸の条件、R25-2 は「両レーンが同じ母集団か」の条件である。

**1 つの述語で 2 件が閉じる**: `global_ranks_for` の入口に適用条件を置く。

1. 時間選択子が無い
2. cursor が凍結済み commit を再生していない
3. **`scored_text` と `scored_vector` が一致する** — 片方だけ global になるなら適用しない

3 は spec に無い条項なので**spec 側にも追記する**。「両レーンを同一母集団の順位にする」が
この変更の目的なのだから、片方だけ差し替える状態は仕様として禁止されるべきである。

---

## 4. 次の作業の計画

| 順位 | 作業 | なぜこの順位か | 規模 |
|---|---|---|---|
| 1 | **原因 B を閉じる** — `aggregator_applicable()` を `global_ranks_for` の入口に置く (時間選択子なし / cursor が凍結 commit の replay でない / 両レーンが同時に global)。満たさなければ scatter-gather へ委譲し `fallback_reason` に記録。契約テストは「`--at` の順位が replication 前と一致する」「2 文字クエリで per-scope + global の混在が起きない」の 2 本を、**ガードを外すと落ちること**まで確認する | R25-1 は北極星 M3-3 を壊しており、しかも一度も計測されていない。他の全項目より先 | 数日 |
| 2 | **原因 A を閉じる** — in-place 索引書き込みの全経路で `index_generation` を回転させる。回転は write-through と同じ下端に置き、per-scope 1 回に集約。あわせて `apply_delta` のガードを「scope 不在なら書かない」から「**スタンプが期待値と一致しなければ書かない**」へ強化する | R25-3/4/12 が一度に閉じる。1 の後にするのは、1 が fallback 経路を触るため両方同時だと切り分けが効かなくなるから | 数日 |
| 3 | **purge の消去を fail-closed にする** (R25-5) — `write_through_projection` に失敗を返させ、purge は replica 消去に失敗したら**成功を報告しない**。cache だから非致命という一般則の例外として扱う | purge は法務要件を持つ唯一の操作。1・2 と独立に進められるが、`write_through_*` の戻り値型を変えるので 2 と同じ回で触るのが安い | 1 日未満 |
| 4 | **R25-9 の検証と是正** — 「config 世代を更新した scope」「ファイルを削除した scope」を作って replica の chunk 数と live 数が乖離するかを実測する。乖離するなら `collect_scope_projection` を解決済み live 集合に合わせる (不変条件 7 を守るため、liveness は per-scope 経路の関数を**呼ぶ**。replica 側で再実装しない) | 現コーパスでは潜在だが通常運用で必ず顕在化する。まず**計測**であり、実装は結果次第 | 数日 |
| 5 | **R25-6 の裁定** — `embedding (CAS)` を実装するか、spec から降ろして `repair rebuild-db` の保証を「embeddings は再取得が必要」に訂正するか。**ユーザー裁定が必要** (金銭コストの受容範囲の話であり、私が決める事柄ではない) | 判断が先で実装は後。放置すると spec が誤ったまま次の監査で毎回上がる | 裁定は即日 / 実装は数日 |
| 6 | **R25-7 / R25-8 の後始末** — `ScopeDelta.removed` と `delete_chunks` を削除して doc を訂正 (または purge を delta 経路へ寄せる)。refresh に並列度と timeout を実装するか、spec の数値を実装に合わせて降ろす | 1〜3 で `apply_delta` と `write_through_*` を触るので、同じ回で片付けるのが最も安い | 1 日未満 |
| 7 | **R25-10 / R25-11 の追跡** | 妥当だが未検証。1〜4 で `reindex --at` と vector 採点の周辺を触るため、そこで自然に確認できる | 数日 |
| 8 | **eval の再計測** — replication + write-through 後の M3-1/2/3 を測り直し、**複数 scope を跨ぐ問題を含める**。現在の 0.944/1.0/1.0 は変更前の数字であり、単一 scope に落ちる問題では今回の変更を測れない | 1〜4 の後。先にやっても直す前の数字しか出ない。ただし**「今の eval は今の実装を測っていない」ことは今すぐ認識しておく必要がある** | 数日 |

### やらない / 後回しにするもの

- **Stage 2 (`agg_approvals`) と Stage 3 (replica が候補選択)**: 4 系統すべてが後回しを支持した。
  理由も一致している — 適用条件・鮮度キー・purge・live 集合が固まらないまま読み手を増やすと、
  同じ欠陥の影響面と migration 規模だけが広がる。Stage 3 の動機である 1.2 秒のレイテンシは
  実害の小さい性能課題であり、順位の正しさより優先しない。
- **RRF の片レーン問題** (`docs/05-runtime.md:571-574` の既知の限界): replication で解決しない
  RRF 自体の性質。Cross-Encoder 再ランク等は別軸の話であり、今回の系列に混ぜない。

---

## 5. 監査運用の学び

- **パス渡し・自律読込は codex 3 系統すべてで完走した** (sol 30 分 / terra 18 分)。
  読了証明 (3 ファイルの行数 + 最終 2 行 verbatim) は 4 系統すべて一致。
  R17 の「codex 完全適合」は今回も再現。
- **glm は文書埋め込みで 4 分半・50 行で完走**し、length 死しなかった。250 行の出力上限を
  明示したことが効いている。R23 の「巨大ファイル探索型で凍結」に対する回避策は有効。
- **同一モデル 2 サンプル (terra ×2) が独立に同じ 3 件へ収束した** (時間選択子・pure-short
  query・live 集合)。同一モデルでも `--ephemeral` の別セッションなら独立性は確保できる。
- **codex の fatal インフレは今回も出た** — sol1 の fatal 2 件はいずれも major へ降格。
  ただし**両方とも実在の欠陥**であり、R23 の「fatal 10 → 確定 0」とは質が違う。
  降格は重大度のみで、指摘そのものは採用した。
- **最も価値が高かったのは「私が spec に書いた条件を実装が満たしていない」型**である。
  R25-1・R25-2・R25-8 はすべてこの型。**自分が書いた規範を自分の実装で検算していない**のが
  今回の主要な失敗モードであり、I20 の学び (「要約を実装で検算していなかった」) と同じ形が
  spec と実装の間で再発している。

---

## 6. 実装記録 — 順位 1 (原因 B) の完了 (2026-07-25)

適用条件を `aggregator_decline_reason` として実装した。裁定時の設計から**2 点を変更**している。

### 変更 1 — 条件 3 の定式化を「`scored_text == scored_vector`」から改めた

裁定では「両レーンが同時に global か」と書いたが、実装中に**その定式化では過剰にも過少にも
なる**ことが分かった。正しい条件は「**融合に加算されるレーンをすべて replica が採点できるか**」である。

| mode | text 項 | vector 項 | `scored_*` 一致か | 正しい判定 |
|---|---|---|---|---|
| text (長) | あり | なし | 不一致 | **適用**してよい (加数が 1 つなら尺度の食い違いは起こらない) |
| vector (短) | なし | あり | 不一致 | **適用**してよい (同上) |
| hybrid (短) | あり | あり | 不一致 | 委譲 |
| text (短) | あり | なし | 一致 (両方 false) | 委譲 (replica は text を採点できない) |

`scored_text == scored_vector` は最初の 2 行を誤って委譲させ、最後の 1 行を誤って
適用させる。実装は mode から「どのレーンが加算されるか」を決め、そのレーンごとに
採点可能性を問う。

### 変更 2 — 実装中に新しい fatal を 1 件発見した (4 系統いずれも未検出)

**絞り込み検索の順位が完全に壊れていた。** `text_scores`/`vector_scores` の
`LIMIT candidate_depth` が **device 全体**に対して取られていたため、device 全体では
下位に沈む subtree を `--scope`/`--descendants` で検索すると **1 行も返らず、全候補が
text 項を失い、融合が `(scope_id, chunk_hash)` の tie-break へ落ちた**。

実コーパスで確認:

```
$ kio search "the " --mode text --scope .../p03/home/compliance --descendants
scopes searched: 3
0.0  sha256:a66a69a5728caf0
0.0  sha256:c36e601ced2a2c8
0.0  sha256:ebf488774c0723e
0.0  sha256:7d3fa7c6350ff1a
```

**全件 0.0 = hash 順**。既定 depth 200 のもとで、`the ` に一致する chunk を持つ 263 scope の
うち打ち切りが届くのは 76 scope、**残る 187 scope の絞り込み検索はこの状態**だった。

terra1 A6 (= R25-11 後半) が「絞り込み検索が未参加 scope を global rank の母集団に混入させる」と
**構造は指摘していた**が、`LIMIT` 打ち切りによる順位の全損という帰結には誰も到達していない。

修正は「**行は絞る・統計は絞らない**」。BM25 の df/`N`/`avgdl` は `agg_fts` 全体のものを使い
(部分集合ごとに取り直せば per-corpus IDF が戻る)、返す行だけを参加 scope に限定する。

### 変更 3 — cursor 条件に `collection_generation` を新設した

裁定では「cursor が凍結 commit の replay でない」とだけ書いたが、実装すると
**per-scope `index_generation` では表現できない**ことが分かった。global BM25 は collection 全体の
df/`N`/`avgdl` を読むので、**誰も検索していない folder を index するだけで検索した scope の順位が動く**
一方、per-scope stamp は全て一致したままになる。cursor は replica 全体の
`(scope_id, index_generation)` hash を凍結し、不一致は `KIO-E-SEARCH-CURSOR-001` /
`reason = collection_generation_mismatch` とする。

副産物として `retain_scopes` の穴も 1 つ塞いだ: **cursor replay は collection を prune しない**。
replay の scope 集合は page 1 が凍結した古い一覧であり、それで prune すると page 1 以降に
登録された scope が追い出され、**検出すべき collection 変化そのものが隠れる**
(この経路が実際に ct3_multi_017 を偽陽性で通した)。

### 成果物

- `crates/kio-cli/src/main.rs` — `aggregator_decline_reason`、`global_ranks_for` を
  `Result<GlobalRanks, String>` 化、cursor 照合、応答の `aggregator` object
- `crates/kio-index/src/aggregator.rs` — `collection_generation()`、
  `text_scores`/`vector_scores` の scope 制限、`load_query_scopes`、`scope_ids` を pub 化
- `crates/kio-search/src/cursor.rs` — `CursorToken.collection_generation`
- `docs/05-runtime.md` §1.8 「aggregator が答える条件と fallback」を実装に合わせて全面改訂
- テスト: aggregator 単体 +3 (計 14)、契約 +4 (CT3-MULTI-014〜017)。
  **7 本すべてガードを外すと落ちることを確認済み** (無効化して再実行し 4/4 FAILED)

### 未解決として残したこと

`ct3_multi_014` の「履歴 hit の score が 0 でない」という assertion は**現在は R25-9 に
masking されて発火しない**。`collect_scope_projection` が解決済み live 集合でなく
`first_seen_commit IS NOT NULL` の全行を射影しているため、削除済み chunk も replica に残り
順位を得てしまう。つまり今日ガードを外すと履歴は **0 点になるのではなく誤った順位になる**。
順位 4 (R25-9) で射影を live 集合へ絞った時点で、この assertion が本来の番人になる。
テスト本文にこの経緯を明記した。

---

## 7. 実装記録 — 順位 2・3・4 の完了 (2026-07-26)

### 順位 2 (原因 A) — 回転と write-through を 1 つの関数に統合した

`publish_in_place_delta` が両方を行う。**どちらか一方だけを行うのが欠陥である**ことは 2 度確認された:

- 回転だけして複製しない → cursor を退役させたうえで次の検索に無駄な再射影をさせる
- 複製だけして回転しない (**R25-4**) → write-through の失敗を**誰も検知できない**。スタンプが動かないので
  安全網であるはずの lazy refresh が発火せず、replica は永久に誤ったままになる

回転を追加した経路: 同期埋め込みレーン (`kio index` では直前の再構築が回転させるが、
**`batch resume` で batch レーンが使えず同期ループへ落ちた場合は他に何も回転しない**)、
内容アドレス再利用の link、`reindex --at`。

**batch 回収の回転条件を狭めた**: 旧 `outcome.executed > 0` は、全 member が secrets hold の group
(= `content_vectors` は書くが `chunk_vec` に link しない) でも回転していた。検索は `chunk_vec` を
読むのでどの replay も順位を変えられず、LC25 が求める回転は無い。`publish_in_place_delta` の
空 delta no-op がこれを正しく表現する。

`apply_delta` のガードは「scope 不在」から「**期待した generation を replica が正確に持っている**」へ
強化した。拒否時は呼び出し側が**全射影へ落ちる** — 次の検索まで stale を放置しない。

### 順位 3 (R25-5) — purge の fail-closed

`write_through_projection` が理由文字列を返すようにし、purge だけがそれで失敗する
(`KIO-E-PURGE-REPLICA-001` / exit 1)。他の全呼び出し元は `write_through_projection_or_log`。
error code は 06 §8 と 10 §11 の両カタログへ登録済み。

### 順位 4 (R25-9) — 実測してから直した

**実測 (3 ファイル fixture、1 つ削除して再 index)**:

```
削除前:  replica 6 chunk / committed 6
削除後:  replica 6 chunk / committed 6   ← 乖離。live は 4
```

replica の 1/3 が「どの検索も返せない行」で、それが `N` と df を押し上げ depth 枠も奪っていた。

修正後:

```
削除後:  replica 4 chunk / committed 6   ← 履歴は index に残り、replica は live のみ
```

射影は per-scope 検索と**同じ関数**を呼ぶ (`current_history_plan_from_cache` +
`install_eligible_identities`)。不変条件 7 は「答えをどこから得るか」の規範であり、
**問いを省いてよいという意味ではなかった** — 初版はその読み違えだった。

**副次的に、順位 1 で「masking されている」と記録した assertion が本来の番人になった。**
`ct3_multi_014` の時間選択子ガードを外すと、履歴 hit の score が**実際に 0.0 になる**ことを確認した
(修正前は 0.0164/0.0161/0.0159 と誤った順位が付くだけだった)。R25-1 の帰結が初めて end-to-end で
再現可能になっている。

### この回の重大な作業ミス

**`git checkout -- crates/kio-cli/tests/step3_p0_contract.rs` を実行し、未コミットの契約テスト 10 本
(CT3-MULTI-010 の書き換え + 011〜019) を消した。** サボタージュ検証用の一時編集を戻すつもりだったが、
同じファイルに本編の変更が同居していた。

復旧は 3 経路の突き合わせで行った: (a) 会話中の Edit 呼び出し全文、(b) 直前にビルドされた
テストバイナリからの `strings` 抽出 (`ct3_multi_011` の欠落部 — 最終 assertion のメッセージと
fixture 本文 `# A\n\n## Sec\nzephyrterm alpha\n` 等をバイト単位で回収)、(c) 復元後の全テスト実行。
20 本すべて復旧・green を確認済み。

**教訓**: 未コミットの本編変更があるファイルに `git checkout --` を使ってはならない。
一時編集は必ず `cp` バックアップから戻す (本編ファイルではそうしていた)。

---

## 8. 実装記録 — 順位 5・6 の完了 (2026-07-26)

### 順位 5 (R25-6) — CAS を実装した (ユーザー裁定: 実装)

**実装前に分かったこと**: object type は「宣言されているが存在しない」のではなく、
**存在するが仕様と別物で、しかも誰も書いていなかった**。`cas.rs` には PB01 由来の
`EmbeddingObject { dimensions, vector: Vec<f64> }` (canonical JSON・content hash key) があり、
`verify_objects.rs` がそれを検証していた。だが 03 §8.1 は

- 保存 bytes = `JCS(identity fields) + LF + base64(vector, f32 LE) + LF + lower_hex64(sha256(vector bytes))`
- 保存 key = **identity hash** (この vector が何の vector か)、bytes の hash ではない
- f32、f64 ではない

を定める。10 §7.5.1 は per-type algorithm を 03 §8.1 に委ねているので、**03 §8.1 が正**。
PB01 の型は仕様不一致の placeholder であり、書き手が居ないので on-disk data も無い。差し替えた。

**実装**:

| 層 | 変更 |
|---|---|
| `kio-core/cas.rs` | `EmbeddingObject` を 03 §8.1 形式へ全面差し替え。`identity_hash` / `to_bytes` / `from_bytes` (長さ・有限値・vector digest を全て検証) / `write_embedding` / `read_embedding` / `embedding_hashes` |
| `persist_group_vector` | **CAS を先、SQLite 行を後** — 間で crash した場合、object があって行が無い状態は次の rebuild が復元できるが、逆は復元不能な vector になる |
| `rebuild_sqlite_index` | `objects/` → `embeddings` → `chunk_vec` (04 §4.3)。旧 DB snapshot は**第 2 の source** として残す (object 導入前の store を運ぶのはこれだけ)。snapshot 由来の行はその場で object を書き出すので **1 回の rebuild で収束**する |
| `verify_objects.rs` | 汎用 content-hash 照合をやめ、identity 再計算 + 03 §8.1 の per-type 検査へ |
| `purge` | orphan `embeddings` 行の id を `RETURNING` で回収し、対応する object も削除。**object を残すと次の rebuild が purge 済み vector を復活させる** |

**契約テスト `ct3_embed_009_rebuild_db_restores_vectors_from_objects_after_the_db_is_lost`**:
`sqlite.db` を削除し、**embedding adapter を設定せずに** `repair rebuild-db` を実行する
(= 再送信が不可能)。それでも hybrid 検索が戻ることを確認。object replay を無効化すると
`resolved_mode` が `text` に落ちることも確認済み。

**PB01 の fixture 4 本は新形式へ書き直し、1 本追加**した
(`pb01_embedding_under_a_foreign_identity_is_a_finding` — 汎用 content-hash 照合が
できなくなった分を identity 再計算が埋めていることの確認)。

### 順位 6 — R25-7 / R25-8

**R25-7**: `ScopeDelta.removed` と `delete_chunks` を削除。テストは
`a_refresh_is_what_removes_a_purged_chunk_from_the_text_index` へ書き直し、
**実際に走る経路 (全置換)** に対して同じ契約を張った。

**R25-8**: spec の「min(4, 差分 scope 数) / per-scope timeout 2 秒」を実装した。
新しい pool は作らず、**per-scope 検索が既に使っている `multi_scope::run_ordered` を再利用**する。
**並列化するのは読み取りだけ**で書き込みは直列 — `Aggregator` は SQLite 接続を 1 本しか持たないので、
2 本目は並列化ではなく同一ファイルの奪い合いになる。

---

## 9. 実装記録 — 順位 7 の完了 (2026-07-26)

**R25-10 と R25-11 は「妥当だが未検証」から「確認済み・修正済み」へ移した。** 両方とも実在した。

### R25-10 — `reindex --at` が pinned manifest を見ていなかった (確認・修正)

`load_validated_normalized_instance_at` (`markdownize.rs:828`) は `dir.join("manifest.json")` を読み、
`status == Done` の unit だけを返す。03 §2.1 はこれを**最新版の作業コピー**と定義しており、
same-gen partial retry がその場で書き換える。

したがって commit `C` の時点で未完了だった unit が、後日 `done` になると
`reindex --at C` に拾われ、その chunk の publication が `C` として記録される。
以後 `search --at C` は **C 時点に存在しなかった本文を返す** — `--at` が防ぐために在る失敗そのもの。

**pin は最初から手元にあった**: `SelectedInstance.normalize` は tree entry の `NormalizeRef` 全体であり、
`manifest_hash` (tree schema v2) を含む。誰も参照していなかっただけである。

修正 = `pinned_done_unit_keys` で pinned manifest object を読み、その `Done` 集合で unit を絞る。
`manifest_hash` が `None` (v1 tree) なら従来どおり。object が**消えている**場合は
作業コピーへ fallback せず `skipped_units` に積む — 作業コピーこそが動いた可能性のあるものであり、
そこから答えるのが欠陥だからである。

契約テスト `pb45_historical_reindex_reads_the_pinned_manifest_not_the_working_copy`:
pinned object の unit を `failed` に書き換え (PB45 と同じ fixture 手法)、chunking config を変えて
`reindex --at` に実仕事を作り、`rebuilt_chunks == 0` を要求する。フィルタを外すと 1 になることを確認済み。

### R25-11 — 2 つの主張のうち 1 つは順位 1 で閉じ、もう 1 つは実在した

**(a) 絞り込み検索が未参加 scope のベクタを global rank 母集団に混入させる** — **順位 1 で解決済み**。
`vector_scores` が参加 scope に限定されたので、母集団は per-scope compat gate を通った scope だけになる。

**(b) profile 切替が sibling の旧 `chunk_vec` を残す** — **実在した**。
`write_chunk_embedding` は旧 profile の `embeddings` 行を `text_hash` 単位で削除するが、
そこから**導出された `chunk_vec` 行は消していなかった**。同じ `text_hash` を共有する sibling chunk が
再送信されない場合 (secrets hold・budget paused・failed)、その chunk は**引退した profile の vector を
持ったまま**、別空間で埋め込まれた query に対して cosine 採点され続ける。

修正 = eviction と同じ Tx で、当該 `text_hash` を持つ全 chunk の `chunk_vec` 行を消す。
`chunk_vec` は `embeddings` の導出物 (04 §4.3) なので、裏付けを失った行は stale ではなく**無効**である。
再送信されない sibling はそこで vector 検索を失うが、それが正直な結果であり、
残すのは静かに誤った順位である。

単体テスト `a_profile_switch_drops_a_sibling_chunk_vec_it_cannot_re_link`。

---

## 10. 実装記録 — 順位 8 (eval 再計測) と、私の誤った前提の訂正 (2026-07-26)

### 訂正: 「eval の多くが単一 scope で早期 return に落ちる」は**誤り**だった

裁定 §1 (R25-1) と §3 に「eval の多くが単一 scope で `searched.len() <= 1` の早期 return に落ちるため
横断経路を通らない」と書いたが、**ハーネスを読んで確かめたところ間違っていた**。

`eval/run_eval.py:477` は `[bin, "--json", "search", query, "--all-scopes"]` を実行し、
`corpus_spec.SCOPES` は 7 scope (`research / notes / downloads / projects-a / projects-b /
specs / journal`) である。したがって**全 50 クエリが `searched.len() == 7` で横断経路を通り、
replica が適用される**。実行して確認した — `aggregator.applied = true`。

正しい限界は別のところにある: **50 クエリすべて expected answer が単一 scope に閉じている**
(`golden-queries.jsonl` の全件で `{e["scope"] for e in expected}` の要素数は 1)。
つまり eval は「7 scope が競合する中で正しい chunk を見つけられるか」を測っており、
これは横断ランキングそのものである。測っていないのは「複数 scope から答えを組み立てる」ケースだけである。

**「今の eval は今の実装を測っていない」は言い過ぎだった。** 正しくは
「記録されていた数字が変更前のものだった」。

### 再計測結果 (この作業ツリー、text 経路)

| シナリオ | 変更前 (記録値) | 再計測 | n | p95 |
|---|---|---|---|---|
| M3-1 | 0.944 | **1.0000** | 18 | 206 ms |
| M3-2 | 1.0 | **1.0000** | 16 | 111 ms |
| M3-3 | 1.0 | **1.0000** | 16 | 118 ms |

`n_scored=50 / n_failed=0 / n_unimplemented=0`、pointer attestation 148 件。
target (0.8) と latency (7,000 ms) の両方を全シナリオで通過。
**M3-1 が 0.944 → 1.0 に改善している** (17/18 → 18/18)。

結果は `eval/results-2026-07-26-post-r25.json` に保存した。埋め込み endpoint は未設定なので
`fallback_reason = embedding_endpoint_not_configured` の text 経路での測定であり、
BM25 のコーパス統一と絞り込み修正が効く経路そのものである。

### 残る本当の穴

**複数 scope に跨る答えを要求するクエリが golden set に 1 件も無い。** これは
「Q_hard の増補」としてユーザー側 Done 条件に残っていた項目であり、私が勝手に作ると
golden の正本性 (`corpus_spec.py` 単一定義・決定論) を壊す。増補はユーザー裁定が要る。

### 順位 7 の修正が開けた穴 (同じ回で検出・修正)

R25-11 の `chunk_vec` eviction を**無条件**に書いたため、`purge_raw_is_atomic_and_
preserves_shared_content_embeddings` が落ちた (`deleted_chunk_vectors` が 2 → 1)。

同一 `text_hash` を共有する 2 chunk を**同じ profile で**続けて書くと、2 回目の write が
1 回目の `chunk_vec` 行を消していた。profile 切替でないのに消すのは行き過ぎである。

修正 = eviction が実際に行を消したとき (`evicted > 0`) だけ `chunk_vec` を掃除する。
**「fix が開けた穴」の定番脈がこの系列で 4 例目** (R25-3 のガード、私の適用条件の定式化 2 件、これ)。
今回は既存の契約テストが同じ回で捕まえた。

---

## 11. 横断増補の設計と実行 (2026-07-26)

§10 で残した唯一の穴 — 「複数 scope に跨る答えを要求するクエリが golden set に 1 件も無い」— を埋めた。

### 設計判断: 既存の凍結規律に乗せる

`docs/09 §4.3` は golden set の**別ファイル方式**を既に確立していた (2026-07-23 の Q_hard 増補)。
`golden-queries.jsonl` は digest ごと不変・増補は自分のファイルと自分の digest・専用ランナー。
**同じ形をそのまま再適用した** — 新しい規約は作っていない。

**コーパスには一切手を入れていない。** 16 問すべて正解担体は `corpus_spec.ANCHORS` の既存 anchor であり、
「同じ数値が 2 scope に現れる」既存の事実 (`ef_search 128` / `暫定スコア 0.71` / `p95 1900ms` 等) を
そのままクエリにした。決定論・履歴 fixture・既存 2 ファイルの digest はすべて不変を実測確認済み。

### 専用ランナーが必要だった理由

`run_eval.py` は**セット全体**の性質を 2 つ検査する。どちらも 50 問セットの契約であって増補の契約ではない:

- `HISTORY_QUERY_COUNT`(=16 **厳密一致**) — 増補を足すと 20 になって落ちる
- `assess_history_coverage` — その run が rename 7 / edit 3 / delete 9 の全 anchor を掘り起こしたこと。
  増補だけを流すと落ちる

したがって `run_crossscope.py` は**部分集合に意味のあるゲートだけ**を適用する
(Recall@10 目標・レイテンシ目標・Evidence Pointer 必須フィールド)。加えて
「expected が単一 scope に閉じたクエリが混ざったら error」という、このセットがこのセットである条件を自前で守る。

### 最も重要な計測所見: **Recall@10 はこの欠陥クラスをほぼ検出できない**

16 問すべて Recall@10 = 1.000 で通った。**replica を無効化しても 1.000 のままだった。**
合成コーパスは小さく、各 expected は固有の数値を持つので、per-scope 順位でも global 順位でも 10 位以内に入る。

横断融合の欠陥が動かすのは**順位**である — 「小さな folder の rank-1 がコーパス全体の最良 hit と並ぶ」が
元の症状であり、それは 1〜3 位で現れて 10 位では現れない。そこで診断値
`worst_expected_rank` (2 つの expected の**遅い方**の 1-based 順位) を併記した。

| | replica あり | replica 無効化 |
|---|---|---|
| replica が採点する 8 問 (M3-1) | **2.00** | 4.75 |
| replica が辞退する 8 問 (M3-2/M3-3) | 5.38 | 5.38 |

- **2.00 は expected 2 件時の理論下限** (1 位と 2 位)。**8 問すべてが下限に到達している。**
- 辞退側は**クエリ単位で完全同値** — 時間選択子ガードにより replica がそれらに触れていないことの裏付けであり、
  改善が replica に帰属することの対照群にもなっている。

**教訓: 指標が飽和しているとき「1.0 だから良い」と読んではならない。** 飽和した指標は
良し悪しを区別していないだけである。区別する量を別に持つまで、このセットは何も証明していなかった。

### 成果物

- `eval/golden-queries-crossscope.jsonl` (16 問、digest `sha256:1fe0ebf2…`)
- `eval/run_crossscope.py` (専用ランナー)
- `eval/crossscope-results.json` / `eval/crossscope-results-no-replica-2026-07-26.json` (対照)
- `eval/README.md` と `docs/09 §4.3` に凍結記録
