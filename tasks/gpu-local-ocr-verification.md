# ローカル OCR (Stage 3) の GPU 実機検証 ブリーフ

このファイルはそのまま作業者 (人でもエージェントでも) への指示として読める形にしてある。
実行には **NVIDIA GPU + Linux** が要る。**WSL2 で構わない** — 必要なのは Linux と CUDA
であって Windows 実機ではない。

> **`tasks/windows-realmachine-verification.md` が「WSL は不可」と書いているのは
> あちらの任務についてである。**あちらは *Windows の* clone 挙動を見るので WSL では
> 検証にならない。こちらは逆で、**Linux であることが要件**なので WSL が適格になる。

---

# 任務

**Stage 3 のローカル OCR 経路が、実際の PaddleOCR-VL サーバに対して動くことを確かめ、
コードが「文書から起こした推測」で持っている値を実測へ置き換える。**

## 第 1 回の結果 [2026-08-02/03]

**1 度目の実機接続は済んでいる。**そこで応答 schema が 2 箇所で誤っていることが分かり、
どちらも直して push した (`1feed04` / `1194dba` / `86d4508`、`cargo test`: 1487 passed)。

- **ページは top-level に無い** — `{logId, errorCode, errorMsg, result}` の封筒の中。
  `errorCode` は HTTP 200 に乗って返るので、先に検査しないとサービス側の失敗が
  「ページの無い文書」に化ける
- **図は CommonMark で来ない** — `<div style="text-align: center;"><img src="…"></div>`。
  `![](…)` はどこにも無い
- **`block_order` は全ブロックで `null`** — doc が言う読み順は実在しなかった

**この 3 つを直した結果、正規化後の Markdown のバイト列が変わっている。**
`<img>` は `![](…)` へ、`<div>` は中身を残して除去される。つまり
**第 1 回で OCR 済みの文書は作り直しになる** (`.kio` を消して index し直すこと)。

---

# いま実機に頼む用件はありません [2026-08-09 更新]

**第 4 回・第 5 回とも完了している。**次に GPU が要るのは、下の
「第 5 回の結果」に書いた **`content` 箱の崩れの 2 例目**だけで、
それには**リポジトリに無い入力が要る**ので、いまは頼めることが無い。

| 第 4 回の任務 | 結果 |
|---|---|
| invoice / slide の拒否理由 | **生 HTML で拒否**。`KIO-E-ADAPTER-CONTRACT-001: unit image:0 violates Normalized Markdown v1: raw HTML and autolinks are forbidden`。件数不一致ではない — S3-F の裁定どおりの、初めての「正しい理由での拒否」 |
| アイコン 17 件の扱い | **ノイズと判定**。6 クエリで返った 54 本のうちチャートは 2 本、5 クエリはチャートに 1 度も届かず。→ 面積比で絞る実装を入れた (S3-J) |
| GIF | **422 で拒否**。サイズ・フレーム数・エンコーダに依らず、JPEG/WebP は同形で通る。→ 宣言を足さない (S3-K) |

決定性は**より強い条件で取り直された**: 6 時間の停止とコンテナ再作成をまたいで、
2 日前のコミット済みキャプチャと**バイト等価**。重みの pin も再実測・一致。

> **`related_images` の絞り込みは、現場の提案どおりには実装していない。**
> 提案は `block_label` で `chart` だけ残す案だったが、手元のキャプチャが反証した
> (invoice のただ 1 枚の図は `image` と綴られ、infographic のどちらのチャートより
> 大きい)。面積比に替えた経緯は計画書 S3-J にある。**観測は正しく、規則の一般化
> だけが効かなかった** — 提案者自身が「1 ページの観測なので保証しない」と
> 留保していたとおりだった。

## ✅ 第 5 回の結果 [2026-08-09 実施] — 閾値の根拠は増えなかった

**目的は達していない。**下限を支える材料を採りに行って、**0 件**で戻った。
採った 5 本のうち 4 本は**画像を 1 つも参照しない**ので面積比が定義できず、
閾値テストに足せるものが 1 本も無い。**0.25 は今も上側からしか支えられていない。**

代わりに、これまで 1 本も持っていなかった実測が出た。

| 分かったこと | 中身 |
|---|---|
| **暗色テーマのスクショが索引に入らない場合がある** | `g1_code_editor_01` は宣言トークン `G1-01-TOKEN-4827` が **613 KB の応答のどこにも無い**。`markdown.text` にも、どの `block_content` にもである |
| **原因は地色ではない** | 同じ暗色の `g1_terminal_02` は 7 ブロックに割れてトークンを返す。明色の `g1_chat_03` も返る。**極性説は消えた** |
| **原因は「窓全体が 1 つの `content` 箱に潰れたこと」** | その箱は `[0, 5, 1665, 867]` = ページの **99.6% × 92%**。`content` は 9 本中この 1 本にしか出ないラベルである |
| **出荷済み 4 本は健全** | 既存キャプチャは 4 本ともトークンを返す。**この欠落は `code-editor` 固有**で、系統的な問題ではない |
| **`header`/`footer`/`number` は本文から落ちる** | g4 の「期限 7/10」は `block_content` に**正しく認識されている**のに `number` に分類され、`markdown.text` に出ない。認識ではなく**分類の誤り**で、中身は応答内に在るので Kio 側で取り返せる |

**トークン回帰テストを入れた** (`crates/kio-adapter/tests/token_recall.rs`)。
`ground-truth.json` の宣言と実応答を 9 本すべてで突き合わせ、`code-editor` の
失敗を**測定値として**固定する。サービスが改善して戻るようになったら、
テストは「戻るようになった。表を更新せよ」と落ちる。両方向の変化検出器である。

> **`content` 箱の崩れ自体を検出するものは、まだ無い。**いま見ているのは
> 「トークンが消えた」という結果だけで、原因側は測っていない。**規則を書くのは
> 2 例目が採れてから**にする — 1 ページで成立した一般化が次で成立しなかった S3-J と
> 同じ轍になる。g1 族は 3 枚とも採り終えており、**2 例目の入力はリポジトリに無い**。

再現条件は `tasks/artifacts/` に保全した (compose 一式 + digest 固定版)。
**`backend-config.yaml` だけは `docker inspect` から復元できない** — inspect は
マウント先のパスを持つが中身の 789 バイトを持たず、それが無いと 12 GB のカードで
エンジンが起動しない。

## 第 5 回の当初計画 (履歴として残す)

面積比の既定 0.25 は、**インフォグラフィック / 請求書 / スライドの 4 ページ**から
出している。写真・線図・署名・スキャンした報告書の図版は 1 枚も見ていない。
[`real_layout_parsing_captures.rs`](../crates/kio-adapter/tests/real_layout_parsing_captures.rs)
の `the_captures_separate_figures_from_decoration_around_the_shipped_floor` が
この分離を検査しているので、**キャプチャを足せば、閾値が合っているかどうかは
テストが答える**。

頼むとすれば「別の種類の文書を 3〜5 本キャプチャしてコミットする」だけで、
判断は不要になる。入力は**リポジトリ内の合成画像から作ること** — 公開リポジトリ
なので、キャプチャには入力文書の全文と画像がそのまま入る。

**入力は既に揃っている** [2026-08-09 確認]。`experiments/ocr-verification/fixtures/generated-images/`
に 15 枚あり、**足りていないクラスがそのまま入っている**。すべてリポジトリ自身の
合成画像なので、公開リポジトリの制約もクリアしている。

> **「写真が未検証」は誤りである** [2026-08-09 訂正]。既存の `invoice-table.json` の
> 由来は `g4_invoice_photo_03.png` で、**これはクリップボードを斜めから撮った実写**
> (影・被写界深度つき) である。写真という括りは既に 1 枚通っている。未検証なのは
> 下の 3 つで、いずれも**写真かどうかとは別の軸**である。

画像は名前から中身が推測できないので、**開いて確かめたうえで** 3 本選んだ。

| 使う画像 | 実際の中身 | これで何が分かるか |
|---|---|---|
| `g1_code_editor_01.png` | **暗色テーマの VS Code スクショ**。サイドバーのアイコン、ファイルツリー、タブ、ステータスバー。**図版と呼べるものが 1 つも無い** | **下限側。**今のキャプチャ 4 本は全部「図版がある」側なので、**「図版が無いページで何かを誤って図版と呼ばないか」は 1 度も試していない**。地色が暗いのも既存 4 本に無い |
| `g3_whiteboard_flow_02.png` | **物理ホワイトボードの実写**。手描きの角丸四角と矢印、付箋、反射光、下端にマーカーとイレーサー | 手描きは**縁がぼける**ので、矩形前提と面積比がどう振る舞うか。マーカー等の**現実の写り込みが図版扱いされないか** |
| `g4_circular_photo_02.png` | **回覧書の実写** (「circular」は回覧の意で、曲面ではない)。**赤い丸印の押印**、署名欄の表、紙の皺 | 押印は**小さいが意味のある図**で、まさに閾値の境目。ブリーフが挙げていた**「署名」**の実例でもある |

**1 本目が要点である。0.25 という閾値は、今は上側からしか支えられていない。**

`g4_receipt_photo_01.png` は外した。`g4_invoice_photo_03.png` (既存) と
**同じ「印刷物を斜めから撮った写真」で、増える情報が薄い**ためである。
3 本で足りなければ次の候補にする。

閾値を変える必要があればそのとき考える (再索引は要らない)。

> ⚠ **「キャプチャを足せばテストが答える」は、1 本目については成り立たない**
> [2026-08-09 確認]。`the_captures_separate_figures_from_decoration_around_the_shipped_floor`
> は面積比の**分母をそのページの最大の図**に取っていて、
> `boxes.iter().map(area).max().expect("a page with crops")` である。
> `g1_code_editor_01` のように**クロップが 1 つも返らない**応答だと、
> **分母が定義できず panic する**。図版が無いページは、いまのテストの形に
> そもそも収まらない。
>
> なので**テストへ無理に押し込まないこと。**収まらないなら、それ自体が
> 「**閾値の下限は現在の設計では表現できていない**」という発見であり、
> 隠すべきものではない。まず**何が返ってきたか**を報告する。
>
> **キャプチャを置くだけでは検査対象にならない。**このテストは
> `include_str!` の const・`captures` 配列・`FIGURES` の 3 箇所が手書きで、
> `FIGURES` は**どの箱が図でどれが装飾かを人が指定した表**である。
> ファイルを置いて `cargo test` が緑でも、**新しいキャプチャは 1 バイトも
> 読まれていない** — この README がまさに「mock とコードが同意して CI が
> 緑のまま 3 回間違えた」経緯を書いている、その同じ形である。

**急ぐ作業ではない。**閾値を外していても索引は壊れず、`[search]
related_images_min_area_ratio` を 1 行変えれば再索引なしで直る。索引時に何も
捨てていないのはそのためである。

## 環境について 1 つ (Kio の不具合ではない)

**Windows 側のビルドは落ちる。**Windows のアプリケーション制御ポリシーが、`target\`
配下に生成された署名の無い `build-script-build` の**実行**をブロックする
(os error 4551)。**WSL 側のビルドは通り、サービスに届くのはそちら**なので、
この任務の実測には影響しない。回避しようとして時間を使わないこと。

> **`--release` 固有ではない。**ここには以前「`cargo build --release` は Windows 側
> だけ失敗する」と書いてあったが、2026-08-09 に **debug でも同じ 4551 で落ちる**ことを
> 実測した (`ref-cast` / `windows_x86_64_gnu`、msvc と gnu の両方で)。
> **「debug なら通る」と読んで Windows 側で粘らないこと** — そこで半日溶ける。
> 経緯は `tasks/windows-realmachine-verification.md` の冒頭にある。

# A〜E の実測 (第 1・2 回)

**第 2 回 [2026-08-03] で A〜E はすべて実測が付いた。**下表は履歴として残す。

> **D の「`block_order` が配列順に縮退する」懸念は `5b0c270` で消えた。**読み順は
> Markdown の参照順そのものになり、各参照が自分の箱を名乗るので、縮退する対象が無い。

| # | 値 | いまの状態 | 誤っていると何が起きるか |
|---|---|---|---|
| **C** | 決定性 | ✅ **一致** (3 ページ × 3 回、差は `.logId` のみ) | 07 §9 の first-instance-wins で**ブレが永久凍結される** |
| **B** | `LOCAL_OCR_MODEL_VERSION_PIN` | ✅ **`sha256:85a479d5…71db`** (単一 safetensors、shard 無し) | 03 §5.1 が要求する重みの sha256 が無い。**採用できない** |
| **D** | 図が 2 つ以上のページ | ✅ **読み順どおり** (上の図が `images[0]`、目視で確認) | `block_order` が図ブロックで null なので配列順に縮退する。読み順と違えば **bbox が入れ替わったまま凍結** |
| **E** | 表がどう来るか | ✅ **HTML `<table>` で来る** → 2026-08-06 から **GFM へ変換して索引する** | 実測を待つ間は拒否していた。変換後も結合セル等は拒否 (下記) |
| A | 応答 schema | ✅ 第 1 回で実測・反映済み | 未知の形が残っていれば `parse_layout_parsing` が弾く |

> **`block_order` は「全ブロック null」ではなかった** (第 1 回の報告の誤り)。
> 散文ブロックには 1,2,3,4 が入り、`header` / `chart` / `figure_title` /
> `vision_footnote` が null である。**図ブロックが常に null** である点は変わらないので、
> `image_block_boxes` が図だけを拾う以上、図の順序が配列順へ縮退する結論も変わらない。

> **末尾 LF が第 2 回の唯一のブロッカーだった。** サービスは散文終わりのページを
> 末尾 LF **0 個**、表終わりを **2 個**で返し、07 §5.2.1 が要求する 1 個にならない。
> `86d4508` で acceptance が fatal になった結果、内容に関係なく全ページが拒否されていた。
> `d66d063` で `normalize_to_markdown_v1` を最後に掛けて解消。**これが直るまで
> E の「HTML だから拒否」は観測できなかった** (LF 違反が先に出るため)。

**C が最も取り返しがつかない。** `/layout-parsing` には `temperature` も `seed` も
渡す口が無く、決定性はサーバ設定の責務である。同一入力が 2 回で違う結果を返すなら、
最初の 1 回がアーカイブの寿命ぶん固定される。

**E は 2026-08-06 に決着した。**当時は「表が HTML で来るなら表を含むページは失敗する。
これは意図した挙動」としていた。**根拠の半分は「PaddleOCR-VL の表が何で来るか未実測」
だったので、キャプチャが入った時点で消えた。**実測した形 — `border=1` / `<tr>` /
`<td style='…'>` だけで、結合セルも `<th>` も入れ子も無い — は **GFM table 記法へ
変換する**ようになった (07 §5 が元から表に定めている形である)。

**その形から外れた表は、今でも変換せず拒否される** (`status: failed` /
`fallback_reason: contract_violation`)。結合セルは GFM に書きようが無く、`<th>` や
入れ子は 1 度も観測されていない。**拒否に出会ったら、それは新しい形を観測したという
ことなので、生の `markdown.text` を添付してほしい。**変換の経緯と規律は計画書 S3-L。

---

# 環境

| | |
|---|---|
| OS | Linux (WSL2 可) |
| GPU | NVIDIA、**CUDA 12.6 以上**をドライバが対応していること |
| Docker | Docker Compose v2 + **NVIDIA Container Toolkit** (WSL2 では別途導入が要る) |
| Kio | **WSL / Linux 側で** clone し `cargo build --release` (Windows 側で建てない — 上記 4551) |

---

# 手順

## 1. PaddleOCR-VL のサービスを起動する

**`paddleocr genai_server` ではない。**あちらは 2 段構成の段 2 (VLM 認識) だけで、
bbox もレイアウトも読み順も返さない。**必ず下記の Compose 版を使うこと。**

```bash
# compose.yaml と .env を取得 (PaddleOCR リポジトリの
# deploy/paddleocr_vl_docker/accelerators/nvidia-gpu/ 配下)
mkdir -p ~/paddleocr-vl && cd ~/paddleocr-vl
# 2 ファイルをここへ置く

docker compose pull      # latest を確実に引く
docker compose up
```

**コンテナは 2 つ**起動する (VLM 推論サービスと Pipeline サービス)。既定ポートは **8080**。
起動完了は次の行で判る:

```
paddleocr-vl-api | INFO:     Uvicorn running on http://0.0.0.0:8080
```

### 疎通確認

```bash
curl -s -X POST http://127.0.0.1:8080/layout-parsing \
  -H 'Content-Type: application/json' \
  -d "{\"file\": \"$(base64 -w0 sample.pdf)\", \"fileType\": 0, \"useLayoutDetection\": true}" \
  | head -c 400
```

`layoutParsingResults` が返れば正しい口に繋がっている。

## 2. 【A】生の応答を 1 本記録する — **最優先**

これがこの任務でいちばん価値のある成果物である。**コードが持っている schema は
実物を見ていない。**

```bash
# 図を 1 つ以上含む 1 ページの PDF か画像を用意する (図が無いと bbox 経路が通らない)
curl -s -X POST http://127.0.0.1:8080/layout-parsing \
  -H 'Content-Type: application/json' \
  -d "{\"file\": \"$(base64 -w0 figure-page.png)\", \"fileType\": 1, \"useLayoutDetection\": true}" \
  > /tmp/layout-parsing-raw.json

python3 - <<'PY'
import json
d = json.load(open('/tmp/layout-parsing-raw.json'))
r = d['layoutParsingResults'][0]
print('top-level keys      :', sorted(d))
print('result keys         :', sorted(r))
print('markdown keys       :', sorted(r.get('markdown', {})))
blocks = r.get('prunedResult', {}).get('parsing_res_list', [])
print('block count         :', len(blocks))
print('block keys          :', sorted(blocks[0]) if blocks else '(none)')
print('block_labels        :', sorted({b.get('block_label') for b in blocks}))
print('sample block_bbox   :', [b.get('block_bbox') for b in blocks][:3])
print('markdown.images keys:', list((r.get('markdown') or {}).get('images') or {})[:3])
PY
```

**確認すべき点** (コードが前提にしていること):

- `layoutParsingResults[]` が配列で、画像なら要素 1、PDF ならページ数
- 各要素に `prunedResult.parsing_res_list[]` と `markdown.text` / `markdown.images`
- ブロックに `block_label` / `block_bbox` / `block_order`
- **`block_bbox` が `[x0,y0,x1,y1]` の 4 要素で、絶対ピクセル**であること
  (0–1000 の正規化なら**コードは全部の bbox を左上隅に置く**)
- `markdown.images` のキーが `markdown.text` 中の `![](...)` の**参照先と一致**すること
- 図ブロックの `block_label` が実際に何か
  (コードは `image` / `figure` / `chart` / `table` / `seal` を図として扱う)

**ずれていたら `/tmp/layout-parsing-raw.json` をそのまま報告に添付すること。**
推測で直さない。

> **ずれていなくても添付してほしい。**2026-08-03 時点で、リポジトリには実応答の
> キャプチャが 1 本も無い。mock はサービスに 3 回続けて食い違い
> (封筒 / 図の綴り / 末尾 LF)、**3 回とも CI は緑のまま**だった — mock とコードが
> 互いに同意し、サービスだけが両方と食い違っていたためである。
>
> 現在の防御は `kio-pipeline` の
> `every_measured_service_shape_produces_v1_markdown_or_a_named_refusal` で、
> **実測された応答形を並べた表**になっている。効くが、**表に無い形については
> 何も言えない。**実キャプチャが 1 本入れば、表の代わりにそれを再生できる。
> 数百 KB でも構わないので、**成功した回の生 JSON をそのまま**送ってほしい
> (画像 base64 が大きければ `markdown.images` の値だけ切り詰めて、
> **切り詰めたと明記**すること — 切り詰めを黙ってやると、また別の
> 「サービスと違う形の fixture」になる)。

## 3. 【C】決定性を確かめる — **取り返しがつかないので必ず**

```bash
for i in 1 2; do
  curl -s -X POST http://127.0.0.1:8080/layout-parsing \
    -H 'Content-Type: application/json' \
    -d "{\"file\": \"$(base64 -w0 figure-page.png)\", \"fileType\": 1, \"useLayoutDetection\": true}" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['layoutParsingResults'][0]['markdown']['text'])" \
    > /tmp/det-$i.txt
done
diff /tmp/det-1.txt /tmp/det-2.txt && echo "DETERMINISTIC" || echo "NON-DETERMINISTIC"
```

**`NON-DETERMINISTIC` なら、そこで止めて報告すること。**採用してはいけない。
差分の中身 (数文字か、段落ごと違うか) も書く。

## 4. 【B】重みの sha256 を採る

03 §5.1 は「重みファイルの sha256」を要求する。タグ名ではない。

```bash
# コンテナ内のモデル配置を探す
docker compose exec paddleocr-vl-api sh -c 'find / -name "*.safetensors" 2>/dev/null | head'
# 見つかったパスに対して
docker compose exec paddleocr-vl-api sh -c 'sha256sum <見つかったパス>'
```

複数ファイルに分かれている (shard) 場合は **03 §5.1 の shard 集約規約**に従う。
コンテナ内で見つからなければ、Hugging Face から同 revision を落として採ってもよい —
**その場合はどの repo / revision から採ったかを必ず報告に書くこと。**

あわせて**モデル名と revision** を記録する:

```bash
docker compose exec paddleocr-vl-api sh -c 'cat /path/to/config.json' | head -20
```

## 5. Kio を実サーバに繋いで end-to-end

```bash
# ~/.config/kio/tools.toml
[markdown.paddleocr_vl_local]
kind  = "offline_api"
url   = "http://127.0.0.1:8080"   # 末尾の /layout-parsing は不要。loopback リテラルのみ
model = "PaddleOCR-VL-0.9B"       # 実際に動いている名前に合わせる (接頭辞 PaddleOCR-VL で照合)
```

**第 1 回で作った `.kio` は使い回さないこと。**正規化後のバイト列が変わっており、
07 §9 の first-instance-wins は最初の結果を保持するので、古い索引の上で index し直しても
新しい正規化は反映されない。`rm -rf .kio` するか、新しいディレクトリで始める。

```bash
rm -rf /tmp/kio-ocr && mkdir -p /tmp/kio-ocr && cd /tmp/kio-ocr
cp <スキャン PDF (テキストレイヤ無し)> ./scan.pdf
kio init
kio index --approve --offline     # --offline でよい。07 §3 が offline_api を止めない
kio search "<PDF 中の語>"
```

**PDF は 3 種類ほしい** (別々に index して構わない):

| | 何を測るか |
|---|---|
| 図が 1 つのページ | 第 1 回の再現 + `related_images[]` |
| **図が 2 つ以上のページ** | 読み順。`block_order` が全 null なので配列順に落ちる |
| **表を含むページ** | ✅ 実測済 — HTML `<table>` で来て、GFM へ変換され索引される (S3-L) |

**期待**:

- `kio index` **1 回**で完結する (`batch resume` は要らない)
- `.kio/tasks.jsonl` の当該行が `status: done` / `fallback_reason: local_adapter_done`
- `output_ref` が **normalized instance のオブジェクトパス**
  (`offline:paddleocr_vl_local` は実行前のプレースホルダで、成功時に生成物のパスへ
  置き換わる。失敗時は `offline:` のまま残る。online 経路も同じ挙動 —
  `main.rs` の `latest_online_instance_for_path` の doc 参照。
  `online:` が残っていたら配線が誤っている)
- `kio search` が PDF の本文で引ける
- ledger に行が増えない: `sqlite3 ~/.local/share/kio/ledger.db 'select count(*) from cost_ledger'` が 0

図を含む PDF なら追加で:

- `.kio/objects/image/` に画像オブジェクトが出来ている
- **`kio search` の結果に `related_images[]` が載っている**、かつ
  `kio open <その image_uri>` が `status: opened` を返す。
  これが W2 の契約そのものなので、ここを見ること。
  **normalized Markdown に `kio://` が入っていることを代理チェックにしない** —
  URI が「在る」ことと、それを読む側が「読める」ことは別で、
  2026-08-02 の検証では前者だけ真になり後者が偽だった
  (`<img src="kio://…">` を `extract_related_images` が見なかった)
- unit metadata の `images[].bbox` が**実際の図の位置**と合っている
  (上流に「PDF crop と `block_bbox` が合わない」報告があるため、**目視で 1 つ確認**)
- 図が **2 つ以上**あるページを 1 枚は通すこと。`block_order` は実測で全 null なので
  複数図では配列順に縮退する。ここが読み順と食い違うと bbox が入れ替わったまま
  07 §9 で永久凍結される — 現状これを測ったページが無い

> ~~**表を含むページも 1 枚通し、生の `markdown.text` を添付してください。**~~
> **✅ 済 — もう頼む必要はありません。**invoice と slide のキャプチャがどちらも表を
> 持っており、リポジトリに入っています。実測が付いたので **2026-08-06 から表は
> GFM table 記法へ変換して索引します** (S3-L)。以前ここに書いていた「表を含むページは
> 失敗します」はもう当てはまりません。
> **結合セル・`<th>`・入れ子など観測していない形だけは今も拒否**されるので、
> `contract_violation` に出会ったらそれは新しい形の観測です — 生の `markdown.text` を
> 添付してください。

---

# 余力があれば — 独立した 2 件

## U7: image/text 同一空間の数値一致

`eval/u7/README.md` の手順。**vLLM で `Qwen/Qwen3-VL-Embedding-2B` を立て**、
参照実装 (torch + transformers) と突き合わせる。

```bash
vllm serve Qwen/Qwen3-VL-Embedding-2B --runner pooling
python3 eval/u7/u7_same_space.py \
  --base-url http://127.0.0.1:8000 \
  --model Qwen/Qwen3-VL-Embedding-2B \
  --out eval/u7/results/u7-same-space.json
```

**llama.cpp 経路を採るなら必須。**vLLM は公式サポートなので優先度は下がる。
判定は**モダリティごと・最小値**で出る。`reason: harness-suspect` が出たら
image の数字は読まないこと (参照側の問題である)。

## V3b の 2 回目 JSON

`eval/v3/V3B-PROMPT.md` の手順で V3b を 2 回走らせ、**2 回目の JSON を必ず保存する**
(成果物は `eval/v3/results/`)。
前回は出力先が消えて記録が残らず、決定性の主張が記録されていない stdout に
依存している。

---

# 報告フォーマット

```
## 環境
GPU <型番> / ドライバ <version> / CUDA <version> / WSL2: <はい|いいえ>
PaddleOCR-VL イメージタグ: <API> / <VLM>

## 1. 起動
docker compose up: <成功|失敗>
/layout-parsing 疎通: <成功|失敗>

## 2. 応答 schema  ← 最重要
layoutParsingResults: <あり|なし>   要素数: <n>
parsing_res_list:     <あり|なし>   block 数: <n>
block キー:           <列挙>
block_label の実際の値: <列挙>
block_bbox:           <4 要素か> / <絶対ピクセルか正規化か> / 実例 <[...]>
markdown.images のキーと ![](...) の参照先: <一致|不一致>
コードの前提とのずれ: <無し | 具体的に>
（ずれがあれば raw JSON を添付）

## 3. 決定性
2 回の diff: <一致|不一致>
不一致なら差分の性質: <...>

## 4. 重みの pin
model_version_pin: sha256:<...>
採取元: <コンテナ内パス | HF repo + revision>
shard 数: <n>
モデル名 / revision: <...>

## 5. Kio end-to-end
index 1 回で完結: <はい|いいえ>
task status / fallback_reason / output_ref: <...>
search がヒット: <はい|いいえ>
ledger 行数: <n>  (期待 0)
画像オブジェクト: <n>
related_images[] の要素数: <n>   ← W2 の契約。ここが 0 なら図は繋がっていない
kio open <image_uri>: <opened|失敗>
bbox の目視確認: <合っている|ずれている>
図が 2 つ以上のページ: <通した (読み順 合っている|入れ替わっている) | 用意できず>
表を含むページ: <通った | contract_violation で失敗 | 用意できず>
  ※ 通るのが今の期待。失敗したら観測していない表の形なので、生 markdown.text を添付
  失敗した場合の生 markdown.text: <添付>

## 判定
Stage 3 のローカル OCR 経路は実サーバで成立する: <はい|いいえ>
採用可否 (決定性 + pin が揃ったか): <可|不可>
成立しない場合、何が足りないか
```

---

# やってはいけないこと

- **`paddleocr genai_server` の `/v1` を使う** — 段 2 だけで bbox が返らない。
  上流も OpenAI クライアントでの直接利用を明示的に非推奨としている
- **決定性が確認できていないのに採用へ進む** — 07 §9 でブレが永久凍結される
- **重みの digest を測らずに書き換える** — 2026-08-03 の実測値をテストが凍結している。
  値を動かすなら重みが変わったということなので、定数を編集して済ませないこと
- **応答が想定と違ったとき、推測でコードを直す** — raw JSON を添付して報告すること。
  schema はコードの前提そのもので、当てずっぽうで直すと mock だけが通る状態になる
- `url` に loopback リテラル以外を書く (D1 違反、`KIO-E-CONFIG-OFFLINE-URL-001`)
- **手元にある実文書をキャプチャしてコミットする** — **このリポジトリは公開である**。
  `layout-parsing` のキャプチャには**入力文書の全文と画像がそのまま入る**ので、
  コミットした時点で公開されたのと同じである。入力は
  `experiments/ocr-verification/fixtures/generated-images/` の合成画像に限ること。
  「1 枚だけ」「社外秘ではない」も**取り消せないので駄目**である
