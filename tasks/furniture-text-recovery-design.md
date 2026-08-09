# header / footer / number の本文回収 — 設計

**状態: 設計のみ。実装は未着手。** [2026-08-09]

`markdown.text` が `header` / `footer` / `number` ブロックを落とすため、**認識されている
本文が索引に入らない**。回収するか否かではなく、**どう回収するか**を決める文書である。

---

# 1. 何が落ちているか — 9 キャプチャの実測

`crates/kio-adapter/tests/fixtures/layout-parsing/` の 9 本で、`block_content` を持つのに
`markdown.text` に出ない block は **12 個**。内訳は **furniture 8 / 本文 4**。

| 出所 | 落ちた中身 | 判定 |
|---|---|---|
| `chat-light-avatar-crops` | `Chat` / `Type a message...` | furniture |
| `code-editor-no-crops` | `Ln 1, Col 1 Spaces: 2 UTF-8 LF JavaScript` / `✗ 0 △0 (🔓) 0` / `{ }` | furniture |
| `terminal-dark-no-crops` | `>_ terminal × +` | furniture |
| `infographic-two-charts` (image / pdf 両方) | `Overall Status` / `All critical tokens detected. OCR output is highly s…` | **本文** |
| `seal-crop-uncited` | `回覽` (文書名) / `期限 7/10` | **本文** |

> `table` ラベルは落ちていない。生 HTML の文字列は `markdown.text` に無いが、
> `convert_html_tables_to_gfm` が GFM へ変換して**中身は入っている**。
> 単純な文字列一致で数えると誤検出するので注意。

**認識は成功している。**12 個すべて `block_content` を持ち、中身も正しい
(`回覽` が旧字体で来る点も含めて位置・内容とも合っている)。**欠落は分類の側**で、
本文が `number` や `header` に分類され、その規則で捨てられている。

---

# 2. 軸は存在しない — 候補を 3 つとも実測で潰した

**ラベルは軸にならない。**`footer` が `Type a message...` (furniture) と
`All critical tokens detected…` (本文) の**両方**を持つ。

**位置も軸にならない。**下端の帯が重なる:

| | y 範囲 |
|---|---|
| furniture (chat / code-editor) | 92.4 – 98.3% |
| **本文** (infographic) | **91.3 – 97.0%** |

「余白に近ければ furniture」で切ると `回覽` (14.4%) と `期限 7/10` (77.1%) は救えるが、
**最も実質的な `All critical tokens detected…` を落とし続ける**。

**大きさも軸にならない。**furniture の高さ 3.4–7.3% に対し本文 1.8–5.9%。
`Overall Status` は **12 個中で最小 (1.8%) なのに本文**である。

**ページ間の反復は使えない。**古典的な furniture 検出はこれだが、**入力が単ページ**なので
原理的に成立しない。画像入力である限り今後も使えない。

唯一相関するのは**文書クラス** (UI スクショか文書か) だが、3 対 2 の観測であり、
**索引時に文書クラスは分からない**。

> **だから分類を索引時に確定させてはいけない。**A (落とし続ける) と B (全部本文に混ぜる) は
> 逆方向に見えて、**根拠の無い分類を今決めてしまう**点で同じ誤りである。

---

# 3. 既存機構の調査 — 必要な部品は揃っている

## 3.1 07 §5.2 が先に定めている

- **line 511**: *bbox / page / confidence score は unit metadata に記録する。Evidence Pointer の
  必須 schema には含めない* — レイアウト由来のメタ情報は unit metadata が正式な置き場である
- **line 564** (bbox_annotation): *unit Markdown に入れる。**unit metadata にも同じ
  post-escape strings を保持し**、検索 bytes と Evidence…* — **本文は Markdown、メタは
  metadata という二重持ちが既に前例**である

## 3.2 §5.2.1 は「バイト表現」しか凍結していない

> media 別の変換規約 (何を見出しにするか等) は Adapter 実装の裁量 (tool_profile_hash が識別する)。
> **本節が固定するのはバイト表現の規約のみである。**

**回収は §5.2.1 の仕様変更ではない。**凍結されているのはエンコーディング・見出し記法・
表記法・画像参照・生 HTML 禁止といったバイト表現だけである。

## 3.3 実装の三層が既に動いている

| 層 | 実体 |
|---|---|
| 保存 | `NormalizedUnitObject.metadata: BTreeMap<String, Value>` (`#[serde(default)]`、旧 unit は空 map) |
| 検索時読み出し | `read_instance_figures` が `unit.metadata["images"]` を読む。instance 単位で memo 化 |
| 設定 | `[search] related_images_min_area_ratio` を**クエリ時**に解決 (`main.rs:3877`) |

**縮退の作法も確立している** — 読めなければフィルタせず全部返す:

> *Anything unreadable is simply absent from the result and its caller then keeps the
> unfiltered list: a purged instance, a unit that predates the metadata, or a provider
> that records no boxes are all reasons to **know less, not reasons to hand the Agent less**.*

---

# 4. 設計

**本文は `markdown.text` に入れる。観測は `metadata` に置く。判断は検索時にする。**

```
Adapter  ─ header/footer/number の block_content を markdown.text へ入れる
         └ metadata["blocks"] に、全ブロックの block_label・bbox・byte span を記録
                │
Index    ─ 通常どおり chunk 化・Evidence Pointer 発行・embedding
                │            (本文が markdown に在るので全部そのまま届く)
                │
Search   ─ 既定では何もしない。metadata["blocks"] は在るので、
           除外 / 降格 / snippet 整形へはいつでも再索引なしで移れる
```

> **キー名は `furniture` ではなく `blocks` である。**当初 `furniture` と書いていたが、
> それは**この設計が「下せない」と結論した分類を、キー名に焼き付ける**ものだった。
> 「provider が `footer` と綴った」は**観測**、「これは furniture だ」は**判断**である。
> metadata に保存するのは観測だけにする — `token_recall` の `blocks` / `widest` 列を
> assert せず表示だけに留めたのと同じ規律である。
>
> **落ちたものだけでなく全ブロックを記録する。**落ちた 12 個だけを選んで保存することが
> 既に「落ちたか否か」という分類の固定になる。副次的な利得として、`content` 箱の崩れ
> (`code-editor` の 91%) も検索時にこの metadata から計算できるようになり、
> **いま `token_recall` が表示しているだけの数字が、索引側からも辿れる**ようになる。

## 4.1 なぜ本文を markdown に入れるのか

**私が最初に懸念したのは「markdown の外に置くと chunk / Evidence Pointer / embedding が
届かない」ことだった。**入れれば届く。metadata に置くのは**分類だけ**で、本文ではない。
これが 3.1 の line 564 が既に採っている形である。

## 4.2 検索時に何ができるか

byte span を持つので、少なくとも次が選べる:

- **除外**: furniture だけで構成された chunk を結果から落とす
- **降格**: ランキング上の重みを下げる
- **snippet 整形**: 返す抜粋から furniture span を落とす (本文は索引に残したまま)
- **そのまま**: 何もしない

**どれを既定にするかは、この設計では決めない。**決めるのは「決められる状態にすること」である。

---

# 5. コスト

**再索引が要る。**本文が増えれば `markdown.text` のバイトが変わり、chunk 境界と
chunk_hash が変わる。07 §9 first-instance-wins により**既存の索引は古い内容のまま凍る**ので、
回収を効かせるには再索引が必要である。

これは**回収するどの案でも同じ**であり、C 固有のコストではない。A (現状維持) だけが
このコストを持たないが、その代わり本文を落とし続ける。

**仕様互換のコストは無い** (3.2)。`tool_profile_hash` は出力が変われば当然変わるので、
世代判定は自動的に正しく動く。

---

# 6. 決定 [2026-08-09]

**検証段階なので、再索引コストと後方互換は判断材料から外して決めた。**

| # | 決定 | 理由 |
|---|---|---|
| 1 | **`metadata["blocks"]` に全ブロックを provider のラベルのまま** | 観測と判断を分ける。§4 の但し書きを参照 |
| 2 | **検索時の既定は「何もしない」** | 実運用コーパスがまだ無く、ノイズの実害を観測していない。**いまフィルタを既定にすると、その害がどれほどかを永久に測れない。**本文が索引に入るという回収の目的は、これだけで達成される |
| 3 | **回収は `header` / `footer` / `number` の 3 ラベル** | 9 キャプチャで落ちていると実測できた範囲に限る。測った範囲と実装範囲を一致させる |
| 4 | **回帰は `token_recall` に列を足す** | manifest 駆動・ディレクトリ走査・`include_str!` ゼロの機構と、「置いただけで読まれないキャプチャは失敗になる」保証がそのまま効く |

**2 について、比率で決めなかった。**落ちている 12 個は furniture 8 / 本文 4 だが、
本文 4 のうち 2 個は infographic の image / pdf で**同一文書**である。文書単位では
**3 件中 2 件で本文が落ちている**。どちらの数え方を採るかで印象が逆になる程度の根拠しか
無いので、**根拠が足りないことを理由に「決めない」を選んだ**。

**3 の残件。**「認識されたが markdown に出ない全部」を拾う案は原理的には一貫しているが、
`table` が罠になる — 生 HTML の文字列は `markdown.text` に無いのに
`convert_html_tables_to_gfm` が中身を入れているので、単純な不在判定では**二重挿入**する。
広げるなら変換経路を持つラベルの除外リストが要る。**いまは広げない。**

---

# 7. やってはいけないこと

- **1 例で分類規則を書く。**§2 のとおり軸は存在しない。`seal-crop-uncited.json` 1 本を見て
  「`number` は本文」と決めると、`code-editor` の `{ }` が本文になる
- **索引時に furniture を捨てる。**捨てた判断は再索引でしか取り消せない。
  `related_images_min_area_ratio` が索引時に何も捨てていないのはこのためである
- **§5.2.1 のバイト表現を変える。**回収は本文の中身の話であって、
  エンコーディング・見出し記法・表記法の話ではない
