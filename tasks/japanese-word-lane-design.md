# 日本語の語レーン — 設計

> **状態: 実装は revert 済み。この文書は設計の記録として残す。** [2026-08-10]
>
> 実装 (`57850f0`) は測定の結果、席に値しないと判断して差し戻した。短いクエリでの
> 効果は**測定上ゼロ** (0.9167 → 0.9167、外した 2 問も同一) で、既存 50 問では
> **M3-2 / M3-3 が 1.000 → 0.938 に悪化**した (改善は 0 件)。数字と原因は
> **[tasks/word-lane-measurement.md](word-lane-measurement.md)** にある。
>
> **下の設計が誤りだと示されたわけではない。**示されたのは、合成コーパスでは
> 真偽を問えないということ (anchor が固有名詞を必ず持ち、length rule は
> カタカナも ASCII も落とさないので、漢字の内容語が落ちても文書が一意に決まる)。
> 再考するなら実文書コーパスに移った後で、そこで短問 recall の伸びしろが
> 実測できたときに限る。実装は `git show 57850f0` から復元できる。
>
> ただし §4.1 の「RRF の継ぎ目が既にある」を**利点として数えた判断は誤りだった**。
> 等重み RRF は、精度の低いレーンに精度の高いレーンを引きずり下ろす権利を与える。

trigram は**廃止しない**。語単位の第 2 レーンを**足す**。この文書は、どの実装を採るか
と、なぜ他を落としたかを、実測とともに記録する。

| | 差し戻し前の位置 |
|---|---|
| 分かち書き | `crates/kio-index/src/word_lane.rs` |
| schema | `chunks.text_words` + `chunk_word_fts` (`fts.rs` の `ensure_schema_on_connection`) |
| query 側 | `build_word_match_expr` / `merge_text_lanes` / `TextLane` (`kio-cli/src/main.rs`) |
| 契約 | `crates/kio-cli/tests/word_lane_contract.rs` |
| 正本 | docs/04-pipeline.md §4.2.1 |

---

# 1. 何が問題か — 長さが品詞の代理になっている

05 §1.3 L116-117 は、混在 query の 3 文字未満 unit を候補確定に用いない。**これは手抜き
ではなく実測に基づく修正である**:

> 旧規範…は自然文 query の助詞 (「が」「の」) や英語機能語を全候補への hard filter に変え、
> それらを含まない簡潔な文体の本命 chunk を構造的に排除した (**eval M3-2/M3-3 実測**)
> — docs/05-runtime.md:120

つまり現在の規則は「**機能語を落としたい**」という意図を「**長さ**」で代理している。
そして日本語では、その代理が効かない:

| | 例 | 長さ |
|---|---|---|
| 落としたい (助詞) | が / の / は / を | 1 |
| **落としたくない (内容語)** | **期限 / 会議 / 契約 / 承認 / 設計** | **2** |

**長さでは区別できない。**そして trigram の設定変更 (`unicode61 remove_diacritics 2` への
切替、04 §4.1:524) でも到達できない — どちらの tokenizer も品詞を知らないからである。

## 1.1 現状は「逆」に落ちている — `build_query_plan` の実測

`期限の確認をした議事録` を `build_query_plan` (kio-cli/src/main.rs) に通すと、
`segment_script_runs` は script 境界で次のように割る:

| unit | 種別 | 長さ | 3 文字規則 |
|---|---|---|---|
| `期限の確認をした議事録` | token 全体 | 11 | 残る |
| **`期限`** | **内容語 (Han)** | 2 | **落ちる** |
| `の` | 助詞 | 1 | 落ちる |
| **`確認`** | **内容語 (Han)** | 2 | **落ちる** |
| **`をした`** | **助詞+助動詞 (Hiragana)** | 3 | **残る** |
| `議事録` | 内容語 (Han) | 3 | 残る |

生成される MATCH は `"期限の確認をした議事録" OR "をした" OR "議事録"`。

**文書を指し示す内容語 2 つが落ち、純粋な機能語の連なりが残っている。**しかも先頭の
「token 全体」の arm は query 文字列そのものの部分一致を要求するので、実質ほぼ当たらない。
長さという代理は、日本語では**意図と逆向きに効くことがある**。

これは 05 §1.3 の規則が間違っていたという話ではない — 助詞を hard filter にした旧規範
より明確に良い。**長さで近似できる限界がここだ**という話である。

**品詞で落とせば区別できる。**これがこのレーンを足す唯一の論拠であり、一般論としての
「日本語には形態素解析」ではない。kio の eval が既に踏んだ問題の、正しい解き方である。

---

# 2. 候補の絞り込み — 実測 [2026-08-10]

09 §1 が固い制約を置いている:

> ベースライン index (deterministic 抽出 + FTS。**API キーなしで init→index→search→open が
> 成立** — 01-positioning.md §3) — docs/09-mvp-scope.md:25

| 候補 | 判定 | 根拠 |
|---|---|---|
| Elasticsearch / OpenSearch | **不可** | 常駐サービス。folder-local `.kio` が truth という前提と上の要件に反する。01 の比較対象は Obsidian / Khoj / AnythingLLM であり、ES を足した時点で別カテゴリの製品になる |
| Meilisearch | **不可** | 同上 |
| Kuromoji | **不可** | Java/Lucene。Rust の CLI に JVM は入れられない |
| Sudachi | **不可** | **crates.io に `sudachi` が存在しない** — `cargo info sudachi` が `could not find 'sudachi' in registry` を返す (2026-08-10 実測)。公式 sudachi.rs は crates.io に publish されていない |
| vibrato | 不採用 | 辞書を実行時ファイルとして持つ設計。folder-local な単一バイナリに合わない |
| **lindera 5.0.2** | **採用** | 下記 |

> **訂正の記録。**当初の推奨は「sudachi.rs があるので in-process で成立する、それが
> Sudachi を残す唯一の理由」だった。可用性は未検証と但し書きした上での推奨であり、
> 引いたら無かった。lindera はその代替であり、かつ kio にとっては形が良い。

---

# 3. lindera で確かめたこと

- `lindera::segmenter::Segmenter::new(mode, dictionary, user_dictionary)` と
  `segment(Cow<str>) -> Vec<Token>`
- `lindera::token::Token::details()` が**品詞を返す** — §1 が必要としているもの
- **`lindera` core だけで足りる。**`lindera-analysis` (YAML の解析チェーン) も
  `lindera-sqlite` (C ABI) も、`LINDERA_CONFIG_PATH` 環境変数も要らない
- `embed-ipadic` feature で**辞書をバイナリに埋め込む** — 実行時ダウンロードなし。
  §2 の「API キーなしで成立」が保たれる
- 参考: `lindera-sqlite` の既定 yml が持つ `japanese_stop_tags` の除去タグは
  `助詞` / `助動詞` / `接続詞` / `記号`。**§1 の主張がそのまま設定として存在している**

---

# 4. 実装の形 — 2 案

## Route A: `lindera-sqlite` を FTS5 の custom tokenizer として登録

`CREATE VIRTUAL TABLE … tokenize='lindera_tokenizer'`。index 時と query 時に同じ
分割が自動で掛かる。`crate-type` に `rlib` があるので静的リンクでき、`.so` の配布や
`.load` は不要。

**落とす理由:**

- **`.kio` の SQLite が素の `sqlite3` で開けなくなる。**その表に触れた瞬間
  `unknown tokenizer` になる。索引は派生物で再構築可能とはいえ、data sovereignty を
  掲げる製品で「自分のフォルダの中身を標準ツールで読めない」のは実質的な代償である
- 接続を開くすべての経路 (index / search / rebuild / purge / verify) で登録漏れが
  即エラーになる
- 設定が `LINDERA_CONFIG_PATH` 環境変数経由 — folder-local の CLI に環境変数依存は合わない

## Route B: 派生列 + `unicode61` ← **採用**

`chunks` に分かち書き済みの派生列を持ち、`unicode61` の第 2 FTS 表を張る。query 側にも
同じ分割を掛ける。既存の RRF がレーンを束ねる (05 §1.3、実装済み)。

**採る理由:**

- **既に `kio-index/src/search_projection.rs` がある。**NFC 正規化・NUL 除去・Markdown
  escape 解決と**同じ層**であり、分かち書きはその 4 つ目にすぎない
- SQLite ファイルが素のまま読める
- **辞書版を index 側に記録して不一致を検出できる** — §5 の担保がコードの側に置ける
- 環境変数も C ABI も要らない

## 4.1 既存の RRF への差し込み方 — 3 レーンにはしない

`fuse_rrf(text_ranks, vector_ranks, config)` (kio-search/src/rrf.rs) は**2 レーン固定**の
署名である。第 3 引数を足す改造はしない:

- **trigram と語は、どちらも text バックエンドである。**2 本を先に RRF で束ねて 1 本の
  `text_ranks` にしてから `fuse_rrf` に渡す。05 §1.3 の「text + vector」という契約は
  変わらない
- `regrade_vector_rank_globally` と `give_images_their_chunks_text_rank` は
  `text_ranks` を前提に動いている。1 本にまとめて渡せば**これらが無改造で効き続ける**

`fuse_rrf` の署名を N レーンに広げるのは、効果が測れてからでよい。

## 4.2 feature を跨いだ DB の行き来

| 状況 | 何が起きるか |
|---|---|
| feature off のバイナリが on の DB を開く | `text_words` 列と `chunk_word_fts` を**見ないだけ**。SQLite は余分な列を気にしない |
| feature on のバイナリが off の DB を開く | `ensure_schema_on_connection` が列・表・trigger を冪等に足す。既存行の `text_words` は NULL のまま |
| **NULL のまま検索した場合** | 語レーンは 0 件を返し、`fts_scope_search` は `word_ranks.is_empty()` で **primary をそのまま返す**。新しいレーンが埋まるまで、挙動は導入前と同じ |

**どちらの向きにも schema version は要らない。**新しいレーンが要求する再索引を済ませれば
埋まる、というだけである。

---

# 5. 決定性 — 07 §9 との関係 (これが一番危ない)

**分かち書きの出力は辞書のバージョンに依存する。**kio は `chunk_hash` を凍結し、
first-instance-wins で最初の実体を永久固定する (07 §9)。**分かち書き結果が hash に
入る設計にすると、辞書更新が静かに同一性を壊す。**

回避策は既にコードにある。`fts.rs` が繰り返している原則である:

> **This is a derived-index projection only**; the char offsets that evidence resolves
> against remain over the original `row.text`.

- 分かち書きは**派生投影の中だけ**に閉じ込める
- `chunk_hash` / `text_hash` / `byte_start`/`byte_end` / Evidence Pointer には**一切
  入れない**
- 辞書版は tokenizer と同格に扱う。04 §4.1:524 が「tokenizer は CREATE 文に固定で
  埋まるため、切替は FTS の再構築を伴う」と定めているのと同じ扱いにする

そうすれば辞書更新は「再索引」で済み、**同一性の変更には決してならない**。

---

# 6. 供給側の注意 — ビルド時にネットワークを引く

`lindera-ipadic` の `build.rs` は辞書を**ビルド時に取得する**:

```
download_urls: &["https://Lindera.dev/mecab-ipadic-2.7.0-20250920.tar.gz"]
md5_hash: "a95c409f12f1023fce8ef91f991ef042"
```

**依存の重さも実測した** [2026-08-10]:

| | 追加前 | 追加後 |
|---|---|---|
| `Cargo.lock` の crate 数 | **201** | **252** (+51) |
| `getrandom` の版 | 1 | **3** (0.2.17 / 0.3.4 / 0.4.3) |

`rayon` / `httparse` / `rustix` / `simdutf8` / `bytecheck` などが入る。ワークスペースの
Cargo.toml が依存ごとに「Pure Rust, no C build, no transitive deps」と書いてきた
基準からすると、これは**小さくない**。

**実行時間も測った** (同一 session、同一機、feature の on/off だけを変えた):

| suite | off | on | 差 |
|---|---|---|---|
| `step3_p0_contract` (244 件) | 82.93 s | 123.84 s | **+49%** |
| `step4b_p2c_contract` (38 件) | 25.49 s | 36.33 s | **+43%** |

支配的なのは**検索側ではなく索引側**である。chunk 1 個ごとに形態素解析を走らせている
(`index_chunk_with_rowids` の `UPDATE chunks SET text_words`)。検証段階なのでこの
コストは判断材料から外すが、**測らずに外したのではない**ことを記録しておく。
速くする余地はある (バッチ化、あるいは `text` が変わっていない chunk の再解析を省く)
が、効果が要るかどうかが先である。

- **実行時ではなくビルド時。**runtime の offline 性と「API キーなし」は保たれる
- 辞書の版はファイル名 (`20250920`) に入っており、`lindera-ipadic = "5.0.2"` を
  Cargo.lock が固定するので、**§5 の決定性はむしろ扱いやすくなる**
- ただし: **ビルドの信頼境界が第三者ホストまで広がる。**md5 は弱く、この blob は
  Cargo.lock の整合性集合の外にある。オフライン CI では vendoring か cache の事前投入が要る

**だから既定 off の Cargo feature にする。**ベースラインのビルドはネットワークにも
サイズにも触れず、09 §1 の要件は無傷のまま。検証段階に必要なのは「試せること」で
あって「既定になること」ではない。

---

# 7. やってはいけないこと

- **trigram を廃止する。**`G1-01-TOKEN-4827` / `related_images_min_area_ratio` /
  `kio://scope/object/…` / `sha256:6c735bdf…` は形態素解析では扱えない。部分一致と
  typo 耐性は trigram の担当であり、この 2 本は競合ではなく分担である
- **分かち書きを `chunk_hash` に入れる。**§5
- **最初から A/B/C の 3 粒度を入れる。**効かない粒度に重みを付ける作業から始めると、
  何が効いたか分からなくなる。**まず 1 粒度で入れて eval (M3-2/M3-3) で測る**
