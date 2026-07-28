# 改名で動いた凍結 digest を採り直す — 未完の作業の引き継ぎ

`kcs` → `kio` の全面改名にあたり、canonical JSON に入る文字列
(`ARTIFACT_SCHEMA` / `FIXTURE_ID` / `kcs_path_media_type` などのフィールド名) が
動いたため、それを覆う凍結 digest を採り直している。**この作業は未完である。**

## 現状

| | |
|---|---:|
| テキストの `kcs` | 0 行 (175 ファイル改名済み) |
| 採り直した digest | **29 対** |
| 残る failures | 18 |
| 残る errors | 45 |

**`canonical_bytes` は 1 つも動いていない。** `kcs` と `kio` は同じ 3 文字なので
canonical JSON の長さは変わらず、digest だけが動く。これは 4 ラウンド全 artifact で
検査済みで、**この不変条件が破れたら改名以外の変化が混じった証拠**なので、
そのときは digest を差し替えずに止めること。

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

## ファイル

| | |
|---|---|
| `snapshot.py` | 全 artifact を組んで `(bytes, sha256)` を記録。改名後は `--allow-fail` |
| `converge.py` | `before.json` を正として、対応の取れた分だけ繰り返し適用 |
| `apply_digests.py` | `old:new` を全域置換 |
| `before.json` | **改名前ツリーでの実測値。これが正本** |
| `applied.json` | 適用済みの 29 対 |

`before.json` は改名前 (`978e874`) のツリーでしか採れない。失うと
`git stash` して採り直すことになるので消さないこと。

## 残作業

### (a) 3 モジュール・44 件

`source_matched_lifecycle_inventory` / `source_parameter_assignment_package` /
`lifecycle_effective_membership_reconciliation`。

`snapshot.py` が **「モジュール内で最初に見つかる `build_*`」を正本と仮定**して
おり、この 6 モジュールでは外れている (`before.json` に `error` が入っている)。
正本 builder を特定して `snapshot.py::artifacts()` を直せば、同じ収束ループで解ける。

### (b) renderer validator 系・12 件

`AssertionError: '<D>' != '<D>'`。テスト内に直接書かれた digest で、artifact 単位の
差分では拾えない。テストログの `A != B` から対応を取り、**どちらが repo に実在するか**で
old/new を判定する方式が有効 (assertEqual の引数順はテストごとに違うので、順序に
依存しない判定が要る)。

### (c) `tasks/` の golden-freeze 記録

約 180 行がコード文字列を凍結 digest と並べて引用している (21 行は同一行)。
(a)(b) が終わって digest が確定してから更新する。

### (d) OCR 検証用 PNG

`experiments/ocr-verification/fixtures/generated-images/*.png` に **"KCS" が画素として
描かれている**。テキスト置換では届かない。画像を再生成すると OCR 期待値の digest が
動くので、別件として扱うこと。

## 進め方

```bash
python3 eval/repin/converge.py                     # 収束ループ
python3 -m unittest $(cat /tmp/wave-modules.txt)   # 残りを測る
```

改名前の値と突き合わせたいときは `git stash` で戻せる。
