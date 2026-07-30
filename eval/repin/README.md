# 改名で動いた凍結 digest を採り直す

`kcs` → `kio` の全面改名にあたり、canonical JSON に入る文字列
(`ARTIFACT_SCHEMA` / `FIXTURE_ID` / `kcs_path_media_type` などのフィールド名) が
動いたため、それを覆う凍結 digest を採り直している。

## 改名は identity だけを動かすわけではない

`persona_v2_source_matched_lifecycle_inventory.py` の `_domain_key` は

```python
raw = b"kio-lifecycle-v1/" + _ascii(domain) + b"/" + _ascii(intent_key)
```

という前置詞で sha256 を取り、それを
`domain-separated-sha256-order-dfs-augmenting-path` 照合の**順序キー**に使う。
前置詞が変われば全ての sha256 が変わり、DFS の探索順が変わり、**どのソースが
どれと照合されるかが変わる**。

その結果、digest だけでなく中身が動く:

```
canonical_bytes         8312760 → 8313318
baseline_aligned_count       13 → 10
language_equal               57 → 54
```

`13` は `persona_v2_query_history_semantic_resolution_feasibility.py` が
`!= 13` で fail させる値、つまり**人が選んで凍結した性質**であって digest の
ような機械的な副産物ではない。

salt だけを `kcs-lifecycle-v1/` に戻し他の改名を全て残すと `13` が復帰するので、
**意味の変化はこの salt 1 つだけが原因**であることが確かめてある。
2026-07-28 の判断で、salt も改名し、動いた性質値を採り直す方針を採った。

## 不変条件 — これが破れたら止める

**salt 下流を除き、`canonical_bytes` は 1 つも動かない。** `kcs` と `kio` は
同じ 3 文字なので canonical JSON の長さは変わらず、digest だけが動く。
**破れたら改名以外の変化が混じった証拠**なので、そのときは digest を差し替えずに
止めること。

この番人は実際に仕事をした — 43 artifact しか測っていなかったときは静かだったが、
81 builder に広げた最初のラウンドで上記の salt を捕まえた。だから salt 下流でも
番人を外さず、**説明のついた artifact だけを名指しで例外にする**。例外が一覧として
見える形でなければ、次に本当の混入が起きたときに気づけない。

もう 1 つの検査: `eval/repin/` 以外で**変更された行はすべて 64 桁 digest を含む**。
含まない行が出たら、それは改名の範囲外の変更である。

```bash
git diff -U0 -- . ':(exclude)eval/repin' | grep -E '^[+-]' \
  | grep -vE '^(\+\+\+|---)' | grep -vE '[0-9a-f]{64}' | wc -l   # 0 であること
```

## 手法 — 推測を入れないこと

一度失敗している。「pin が落ちた → そのモジュールに書かれている 64 桁のどれかが
古い値だろう」と**推測**して差し替えた結果、無関係な上流 pin を潰した
(envelope の digest が coverage catalog の値に化け、27 ファイルへ波及した)。
全て捨てて作り直したのが今の方式である。

正しい対応は **同じ artifact を改名の前後で組んだ出力どうし**として決まる:

- `old` = 改名前に builder が出した digest (`before.json` に採取済み)
- `new` = 改名後に同じ builder が出した digest

`old` がどの pin に書かれているかを知る必要はない。**改名前にテストが通っていた
事実**が、その値を書いている箇所は全てその artifact を指していることを保証する。
だから全域置換が正当化される。

各対応を採用する前に必ず:

1. `bytes` が前後で一致するか (違えば停止)
2. `old` が repo に実在するか (無ければ builder の選択が正本でない — 採用しない)

## 生産者を取りこぼさないこと

`snapshot.py` の列挙は 2 度外していて、そのたびに「解けない残件」に見えていた。

| 取りこぼし | 原因 | 直し方 |
|---|---|---|
| per-persona の 3 モジュール | 最初の `build_*` を正本と仮定していた | 正本を選ぶのをやめ、全部測る |
| `corpus_input_closure_v3` | `ARTIFACT_KIND = "` を条件にしていたが、複数行で書いている | 同上 |
| `overlay_reservation_layout` | `builders[0]` が origin suite で byte cap に当たる | 同上 |
| renderer / validator contract 16 件 | `*_validator.py` を「テスト側」と誤認して除外。契約側は `CONTRACT_KIND` で `build_renderer_contract` | `contract_snapshot.py` を分け、`PAIR_SPECS` から生産者を引く |
| `device_lane_compositor` | `\(\s*\)` で「引数なし」を判定していたが、`build_device_lane_compositor(envelope_value=None)` は既定値付きで引数なし呼び出しができる | `inspect.signature` で**実際に呼べるか**を訊く |
| per-persona builder 約 26 個 × 20 personas | 引数なしで呼べるものしか測っていなかった | `persona_argument()` で判定し、persona ごとに 1 件として記録 |

**どれも、ソースの見た目からコードの性質を当てにいって外している。** 正規表現で
形を判定する限りこの種の取りこぼしは繰り返す。判定できるものは実行時に訊くこと。

### 座標が 2 つ以上ある 13 個は、今も `snapshot.py` の外にいる

`(persona_id, origin)` / `(persona_id, profile)` / `(persona_id, origin, shard)` を
要求する builder が 13 個ある (`concrete_overlay_membership_package` 3、
`source_inventory_package` 3、`source_semantic_membership_package` 2、
`source_parameter_assignment_package` 2、`lifecycle_effective_membership_reconciliation` 2、
`overlay_reservation_layout` 1)。`snapshot.py` は persona 1 座標までしか展開しない。

**これは検出の穴ではない。** 13 個の凍結値はモジュール側の `_fail` 番か
テスト側の assert で押さえられているので、動けばスイートが赤くなる。穴が開いて
いるのは**修復側** — converge が対応を自動で組めないので、赤が出たら手で採る。

座標の定義域をモジュール横断で一般化してはいけない。shard の序数は
`concrete_overlay` が 0 始まり、`source_inventory` が 1 始まりで、片方を読んで
一般化したときは 60 件の偽の失敗が出た。定義域は必ずそのモジュール自身から引く。

## 圧縮・符号化されたデータの中身には改名が届かない

`persona_v2_core_extension_allocation_manifest.py` は登録簿の投影を
zlib+base64 のソースリテラルとして持っている。その中の
`"artifact_schema":"kcs.persona.pc-format-implementation-registry/v2"` は
**テキスト全域置換でも `git grep kcs` でも見つからない**。producer と
validator の両方に同じ blob があり、両方に残っていた。

見つけ方: ソース内の base64 らしきリテラルを総当りで復号し (必要なら zlib
展開も試し)、中身に `kcs` が無いか探す。`blobscan.py` がそれをやる。
改名の最初にこれを回すべきだった。

直し方: blob を復号 → 文字列を置換 → **JSON として構造が変わっていないこと
を検算** → 再圧縮 → base64 → その blob 自身の pin を実測して更新。
`kcs`/`kio` は同長なので展開後の bytes は変わらない (22,639 のまま)。

## `--allow-fail` は依存の壊れを吸収し、誤った値を焼くことがある

`source_semantic_capacity_axis_catalog::EXPECTED_SHA256` は最初期のコミット
(406528a、"INCOMPLETE. 18 failures and 45 errors remain") で `2bcb84e6…` に
repin されていた。この値は**per-persona builder の fact-graph pin がまだ
壊れている状態**で焼かれたものだった — `_build_state()` は内部で
`_snapshot_fact_graphs()` を呼び、fact-graph の pin 不一致があれば `_fail`
するが、`snapshot.py --allow-fail` はその `_fail` を無害化するので、
**壊れた入力のまま candidate が計算され、それがそのまま「新しい正しい値」
として記録された**。fact-graph の pin (19 件) を後から直したら、この
catalog の candidate はもう一度動いた。

見つかった経緯: per-persona builder を測定対象に含めてもこの catalog は
「不動」(改名前後で digest 一致) と出ていた — 一致していたのではなく、
**両方とも壊れた入力から計算されていたので一致していた**。実際のコードを
直接 import して例外の有無を試すまで気づけなかった。

教訓: `--allow-fail` で測った candidate は、**その artifact 自身が依存する
下流の pin が全て直っている状態でなければ信用できない**。依存関係の末端
(salt の直接の影響を受けるモジュール) から直して、そこに依存する側は
**最後にもう一度、`_fail` を黙らせずに直接呼んで**確かめること。

`realcheck.py` は **1 回では足りない。緑になるまで繰り返す。** 依存 DAG が
ある以上、ある artifact を直せばその下流はその瞬間に動く。実際に 10 件を
直した直後の再検証で 1 件が新たに落ちた — feasibility の bytes を
40,947 → 40,949 にしたことで、それを依存に持つ closure slice の digest が
動いたためである。10 → 1 → 0 と収束させて初めて「全 builder が構築可能」
と言える。

## 赤の件数は破損の件数ではない

最後の取りこぼしがそれを一番はっきり示した。`build_fact_graph(persona_id)` の pin は
**19 件 (p02-p20) がバイト数そのままで digest だけ動いた**状態、つまり改名以外に
理由の無い未再 pin のまま残っていた。だがテストは最初の不一致で fail-fast するので、
**19 件の破損が 2 件のエラーとして見えていた**。

だから「残り N 件」で進捗を測ってはいけない。測るなら、**測定対象の網羅**
(どの builder を測っているか) で測ること。

2 つ目は 44 件のエラーを 1 つの根 (`contributor-text-renderer-contract`) として
まとめて説明していた。**「別々の残件に見えるもの」がひとつの取りこぼしであることが
ある**ので、残件は原因でまとめてから数えること。

契約の正準化はモジュールごとに違う (`raw-image-media` だけ terminal-LF 付き ASCII)。
共通ハッシャで測ると、そこだけ静かに別の値になる。**モジュール自身の
`*_contract_sha256()` で測る**こと。

## 道具は自分の記録を書き換えてはならない

`apply_digests.py` は「追跡下の全テキストファイル」を置換対象にしており、その中に
**`before.json` 自身**が入っていた。ラウンドごとに「改名前の実測値」が「適用後の値」
へ上書きされ、正本が失われていた。同じ builder の記録値がコミットを追うごとに
`47b75b37 → 66d78474 → 9b1fc398 → 0274e649` と動いている。

被害は記録の劣化にとどまらない。`before[X]` が「X の現在値」になると
`before == after` が成立し、**その artifact の対応が見つからなくなる**。ラウンドが
早々に「新規 0」で終わっていたのは収束ではなく、比較対象が消えたためだった。
真の改名前スナップショットを戻した瞬間に 74 対が現れたのは、その 74 件が一度も
再 pin されていなかったからである。

同じ根が検査側にもあった。`in_repo()` は `git grep` で「その digest を pin して
いる箇所があるか」を見るが、`before.json` 自身を数えていた。既に再 pin し終えた
artifact でも改名前の値が記録に残っているので条件を満たし、**幻の対応が立つ**
(74 件の対応が成立して置換対象 0 件、という形で現れた)。

`eval/repin/` は置換対象からも検査対象からも外してある。**道具が自分の記録を
外界についての証拠として扱ってはならない。**

どちらの症状も**進捗が実際より良く見える**方向に出る — 片方は「収束が早い」、
もう片方は「対応が多く採れた」。誤りが望ましい形で現れると気づきにくい。

## 「収束した」は収束の証拠ではない

同じ「新規 0」という嘘には原因が 3 つあった。上の記録破壊がひとつ。ふたつめは、
`converge.py` が当初 `old` を一度使ったら以後その artifact を見ない書き方だったこと。
だが**上流が直れば下流の digest はもう一度動く**。二度目の対応は `old` が適用済み
なので枝刈りされ、ラウンドは「新規 0」と報告して止まる — 対応が無いからではなく、
探すのをやめていたからである。`corpus_input_closure_v3` がこれで round 1 の
中間値のまま残り、46 件のエラーとして現れた。

いまは適用済みの鎖を辿って **いま repo にある値** と対応を取る。ラウンドが
「新規 0」で終わったら、それは**テストが緑であることで裏を取るまで信じない**こと。

みっつめ (2026-07-30 に判明): **空振りした対応が合算の陰に隠れる。**
`apply_digests.py` は `452 pair -> N occurrences in M files` と合算でしか
報告していなかったので、そのうち 1 対が 0 箇所置換でも大きな数が出続けた。
converge は `old` が repo に実在することを確かめてから対応を採るので、直後の
適用が 0 箇所になるのは矛盾であり、**ソースが old でも new でもない第三の値を
持っている**ことを意味する。

その第三の値は `recursive_robustness_lane_catalog` の `c1ae7e10…` だった。
改名前ツリーの pin は `49d6fa26…` (`before.json` の実測と一致、テストは 13 件緑)、
改名後の正しい値は `af73e879…`。`c1ae7e10…` は**改名前ツリーに存在しない** —
早いラウンドが `--allow-fail` 下の候補を焼き、依存を直した後のラウンドが作った
正しい対応は、ソースがもう `49d6fa26…` を含まないので空振りしていた。
どの時点でも正しくなかった値が、コード 2 箇所と `tasks/` 3 文書に残っていた。

いまは対応ごとに件数を数え、0 のものを列挙して 1 を返す。converge 側は
`check=True` を外して報告してから抜ける — 例外で抜けると記録を書く行に
到達せず、当てた対応の記録ごと失われる (それが原因 1 の再来になる)。

**気付いたのはツールではなくテストスイートだった。** 4 時間の CI 走行 1 回を
これに使った。`tasks/` に書かれた digest はテストが押さえていないので、
コード側にも同じ値があるかを併せて確かめること — 今回 79 件のうち 77 件は
コードにもあり、残り 2 件は文書だけだったので個別に実測した。

## 性質値は digest と同じようには直せない

digest の全域置換が正当なのは、64 桁が**ただ一つの artifact を名指す**からである。
数値にはその一意性が無い。salt 下流で動いた値を直したときに踏んだ形は 3 つ:

- **同じリテラルが複数の経路で意味を持つ。** p01 sentinel の `13` は実 fixture と
  合成 snapshot の両方で使われていて、実 fixture に合わせたら合成側の
  `setUpClass` が落ちた。合成データは sentinel を通すために `ordinal <= 13` と
  作られていたので、そちらを追従させるのが筋だった。
- **同じ数に別の形で依存している箇所がある。** sentinel の発火を確かめるテストは
  13 番目の要素 (`[12]`) を壊していた。10 に変えたら壊す位置も `[9]` に動かさないと、
  元から非 aligned な要素を壊すことになり発火しない。
- **巨大な JSON リテラルの中に位置的な値として現れる。** `103433` は受領証 253 行の
  1 行の 4 番目の要素でもあった。今回は同じ行の digest で一意に特定できたが、
  他の artifact のサイズと偶然一致していたら別の行を壊していた。

だから数値は**必ず出現数を数えてから**動かすこと。文脈が一意だと確かめられた
ものだけ (`cumulative_external_projection_bytes` の 17 箇所など) 一括で直す。

種別の見分け方:

| 種別 | 例 | 直し方 |
|---|---|---|
| digest | artifact / contract の sha256 | 全域置換 |
| 観測値 | `EXPECTED_MAX_*`、代表 body の bytes、累積バイト数 | 実測に合わせる。出現数を確認して個別に |
| 選んだ性質 | p01 sentinel の 13/87 | 経路ごとに意味を確かめて 1 箇所ずつ |

## ログから対応を採るときの落とし穴

テスト内に直接書かれた digest (`assertEqual(f(x), "<64 hex>")`) は artifact 単位の
差分では拾えないので、失敗ログの `A != B` から採る。どちらが old かは
**repo に実在するか**で決める (`assertEqual` の引数順はテストごとに違う)。

**ログは必ずいまのツリーで採り直すこと。** 一度 digest を当てた後の repo に古い
ログを当てると、新しい値のほうが repo に実在するので対応が反転し、正しく直した分を
巻き戻す。空撃ちで実際に再現した。`from_test_log.py` が自分でテストを走らせるのは
この取り違えを構造的に不可能にするためで、ログを引数で渡す口はわざと持たせていない。

## 測定範囲 — 正本は CI の 91 モジュール

`eval/test_*.py` は 94 個あり、CI はうち **91 個**を回している
(残り 3 個は改名前ツリーでも組めないため除外されている)。

一時期 24 モジュールだけを流して残件を数えていたが、これは**スイートの 26%**でしかなく、
しかも重い cold build 系に偏っていた。軽い側にこそテスト内リテラルが多い。
残件を数えるときは CI のリストを正本にすること。

```bash
grep -oE "eval\.test_[a-z0-9_]+" .github/workflows/ci.yml | sort -u > /tmp/ci-modules.txt
```

## ファイル

| | |
|---|---|
| `snapshot.py` | artifact を組んで `(bytes, sha256)` を記録。改名後は `--allow-fail` |
| `contract_snapshot.py` | renderer / validator contract 16 件を同じ形で記録 |
| `converge.py` | `before.json` を正として、対応の取れた分だけ繰り返し適用 |
| `from_test_log.py` | テストを走らせ、失敗ログからテスト内リテラルの対応を採る |
| `realcheck.py` | `--allow-fail` 抜きで builder を直接呼ぶ。**収束宣言の前に必ず回す** |
| `blobscan.py` | base64/zlib リテラルを展開して `kcs` 残存を探す。**改名の最初に回す** |
| `apply_digests.py` | `old:new` を全域置換 |
| `before.json` | **改名前ツリーでの実測値。これが正本** |
| `applied.json` | 適用済みの対応 |

`before.json` は改名前 (`978e874`) のツリーでしか採れない。失うと採り直しになるので
消さないこと。改名前ツリーは `git archive 978e874 eval | tar -x -C /tmp/pre` で復元できる。

## 進め方

```bash
python3 eval/repin/converge.py                       # artifact の収束ループ
python3 eval/repin/from_test_log.py \
  --modules /tmp/ci-modules.txt --log /tmp/wave.log --out /tmp/pairs.txt
python3 eval/repin/apply_digests.py $(cat /tmp/pairs.txt)
```

`from_test_log.py` を当てた後は同じモジュールを流し直すこと。対応が反転していれば
元の失敗に戻るので、この再実行が反転も捕まえる。

## 済んでいること

- テキストの `kcs` は 0 行 (175 ファイル改名済み)。残る 19 箇所はこのディレクトリの
  散文と、値が動いた理由を書いた 2 つのコメントで、改名作業そのものを説明して
  いるので旧名を残すのが正しい。符号化されたデータの中も `blobscan.py` で 0 件、
  未追跡ファイルも 0 件、`kiokio` のような全域置換の事故痕も 0 件。
- 2026-07-31 時点で **CI 91 モジュールと `cargo test --workspace` が緑**。
  最後の CI 全体走行 (1218 tests / 4h02m) が出した 3 件はこの 2 系統だった:
  - `recursive_robustness_lane_catalog` の `c1ae7e10…` — どの時点でも正しくなかった
    値。上の「空振りした対応が合算の陰に隠れる」を参照。`af73e879…` に直して 13 件緑。
  - `semantic_projection_complete_inventory` の `EXPECTED_CLASS_BYTES` 2 件 —
    salt 下流の性質値。`effective-source-membership` -89、
    `query-independent-lifecycle-fact-rendition-rules` +1 で正味 -88。12 件緑。
- `tasks/` に改名が新しく書き込んだ digest 79 個は全件裏を取った。77 個はコード側にも
  あり緑のスイートが押さえている。2 個は文書にしかないので builder を直接呼んで
  実測し一致を確認した (`fact_membership[p01]` 4,519 / `history_intent[p01]` 14,657)。
- OCR 検証用 PNG の画素に描かれていた "KCS" は `90c9983` で 2 枚とも再生成済み、
  ground truth は `b8eefe4` で画素に合わせ直し済み。画像 digest を pin している
  箇所は 15 枚すべてについて 0 件で、OCR 出力は gitignore なので凍結値は動かない。
- `tasks/` に出る 127 個の digest のうち 103 個は `eval/crates/docs` にも現れるので
  全域置換で追随する。残る 24 個は `tasks/` にしか無く、改名前の実測値
  (`before.json` / 契約 16 件) のどれとも一致しないため、取り残された pin ではなく
  過去の測定の記録である。
