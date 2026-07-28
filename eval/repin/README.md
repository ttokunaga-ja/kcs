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
| per-persona の 3 モジュール | `ARTIFACT_KIND` を条件にしていたが、この 3 つは持たず `build_*_suite_descriptor` で pin する | suite descriptor があればそれを正本とする |
| renderer / validator contract 16 件 | `*_validator.py` を「テスト側」と誤認して除外。契約側は `CONTRACT_KIND` で `build_renderer_contract` | `contract_snapshot.py` を分け、`PAIR_SPECS` から生産者を引く |

2 つ目は 44 件のエラーを 1 つの根 (`contributor-text-renderer-contract`) として
まとめて説明していた。**「別々の残件に見えるもの」がひとつの取りこぼしであることが
ある**ので、残件は原因でまとめてから数えること。

契約の正準化はモジュールごとに違う (`raw-image-media` だけ terminal-LF 付き ASCII)。
共通ハッシャで測ると、そこだけ静かに別の値になる。**モジュール自身の
`*_contract_sha256()` で測る**こと。

## 「収束した」は収束の証拠ではない

`converge.py` は当初 `old` を一度使ったら以後その artifact を見ない書き方だった。
だが**上流が直れば下流の digest はもう一度動く**。二度目の対応は `old` が適用済み
なので枝刈りされ、ラウンドは「新規 0」と報告して止まる — 対応が無いからではなく、
探すのをやめていたからである。`corpus_input_closure_v3` がこれで round 1 の
中間値のまま残り、46 件のエラーとして現れた。

いまは適用済みの鎖を辿って **いま repo にある値** と対応を取る。ラウンドが
「新規 0」で終わったら、それは**テストが緑であることで裏を取るまで信じない**こと。

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

- テキストの `kcs` は 0 行 (175 ファイル改名済み)。残る 6 箇所はこのディレクトリの
  散文とコメントで、改名作業そのものを説明しているので旧名を残すのが正しい。
- OCR 検証用 PNG の画素に描かれていた "KCS" は `90c9983` で 2 枚とも再生成済み、
  ground truth は `b8eefe4` で画素に合わせ直し済み。画像 digest を pin している
  箇所は 15 枚すべてについて 0 件で、OCR 出力は gitignore なので凍結値は動かない。
- `tasks/` に出る 127 個の digest のうち 103 個は `eval/crates/docs` にも現れるので
  全域置換で追随する。残る 24 個は `tasks/` にしか無く、改名前の実測値
  (`before.json` / 契約 16 件) のどれとも一致しないため、取り残された pin ではなく
  過去の測定の記録である。
