# Windows 実機での clone・ビルド・動作確認 ブリーフ

このファイルはそのまま作業者 (人でもエージェントでも) への指示として読める形にしてある。
実行には **Windows 実機**が要る。CI では代替できない (理由は下記)。

---

# 任務

**Windows 実機で clone したリポジトリが、Linux / macOS と同じバイトを持ち、
ビルドとテストが通り、`kio` が実際に動くことを確かめる。**

## ✅ 2026-08-02 に実機で完走した

Windows 10.0.26200 / Git 2.53.0 / rustc 1.97.1 (msvc) / `C:\kio` / `core.autocrlf=true`
のまま、`commit c29ecac` で全項目 PASS した。

| | 結果 |
|---|---|
| `w/crlf` | **0** (`core.autocrlf` を触らずに) |
| 3 ファイルの SHA-256 | 一致。`git check-attr text -- Cargo.toml` → `text: unset` |
| `cargo build` / `cargo test` | 成功 / **1,418 passed / 0 failed** (31 バイナリ) |
| smoke | `init`→`index --preview`→`index --approve --offline`→`search` 完走。1 件ヒット |

**`.gitattributes` の `* -text` は実機で効いている。** 任務の目的は達成済みなので、
以降この手順を回すのは**回帰確認**である。新規の検証としてもう一度やる必要はない。

その過程で見つかった 2 つの落とし穴 (どちらも Kio ではなく PowerShell 側) は
§4 の後に追記してある。**日本語が化けて見えても Kio の不具合ではない。**

> ⚠ **os error 4551 でビルドが落ちる機がある。**Windows のアプリケーション制御
> ポリシーが、`target\` 配下に生成された**署名の無い `build-script-build` の実行**を
> ブロックする。cargo はビルドスクリプトを*コンパイル*できていて*実行*だけが拒否される
> ので、`could not execute process ... (never executed)` という形で出る。
>
> | 実測 | プロファイル | 落ちた crate |
> |---|---|---|
> | 2026-08-05 | `--release` | `sqlite-vec-*` |
> | 2026-08-09 (別機) | **debug** | `ref-cast` / `windows_x86_64_gnu` |
>
> **ここには以前「`--release` に固有」と書いてあったが、それは誤りだった。**
> 8/9 の機は debug でも落ちる。固有なのはプロファイルではなく**その機のポリシー**で、
> msvc でも gnu でも変わらない。8/2 の実績機が debug で通っているのは、その機に
> ポリシーが掛かっていないというだけである。
>
> **Kio の不具合ではない。**同じ機の WSL 側では通る。ポリシーは管理者にしか変えられず、
> Smart App Control は Windows 11 では**一度切ると再インストールなしには戻せない**ので、
> **ビルドを目的にしているのでない限り迂回に時間を使わないこと。**

## ⛔ 2026-08-06 → 08-09 — 別機での試行。バイト検査は合格、ビルドは不可

`a282165` で `crates/kio-adapter/tests/fixtures/layout-parsing/` に実キャプチャ 4 本が
入った。下記「なぜ CI では足りないのか」の但し書き —**改行に敏感な fixture を足した
ときは CI が緑でも実機で回すこと**— に該当するので回帰確認を始め、**バイト検査までを
終えた**。ビルドとテストはこの機のアプリケーション制御ポリシーに阻まれて完走できず、
**8/2 の実績機へ差し戻した**。

実機は 8/2 とは**別の機械**である。Git 2.55.0.windows.3 / `core.autocrlf=true`
(既定のまま、触っていない) / リポジトリは `%USERPROFILE%\dev\github.com\ttokunaga-ja\kio`
(実長 45 文字で、§0 の 84 文字の予算内)。`C:\kio` は存在しない。

### 済み — バイト検査 PASS。再実行不要

計測用に **Git for Windows で別クローンを作った** (`%USERPROFILE%\Desktop\kio-verify`)。
既存チェックアウトの作業ツリーは WSL の git が pull で書いたので、**そのまま測っても
Git for Windows の変換を検査したことにならない**。別クローンはそのための措置である。

| 検査 | 結果 |
|---|---|
| `git ls-files --eol` (layout-parsing) | `README.md` = `i/lf w/lf attr/-text`、JSON 4 本 = `i/none w/none attr/-text`。**`w/crlf` は無し** |
| `git check-attr text -- …/invoice-table.json` | `text: unset` |
| `.gitattributes` SHA-256 | `f8cf7112…6989f347` — §2 の参照表と**一致** |
| `Cargo.toml` SHA-256 | `d067b665…16b4f15e` — **一致** |
| `docs/README.md` SHA-256 | `53d80dbe…6ae69977` — **一致** |
| Windows clone と WSL 作業ツリーのバイト比較 | 3 ファイルとも**同一ハッシュ** |

`.gitattributes` の `* -text` は `a282165` でも効いている。

### 2026-08-09 — この機では完走できなかった

この機には **Rust が入っていなかった**ので入れた。

- `winget install --id rustlang.rustup --source winget --accept-package-agreements`
  → rustup 1.29.0 / **rustc・cargo 1.97.1 (c980f4866 2026-06-30)** / 既定 `stable-x86_64-pc-windows-msvc`
- `winget install --id microsoft.visualstudio.2022.buildtools --source winget --accept-package-agreements`
  → **Build Tools 2022 17.14.37 (July 2026)。ワークロードは未選択のまま**

rustup が `warn: installing msvc toolchain without its prerequisites` を出す。
**`link.exe` と Windows SDK が無いので、この状態の `cargo build` はリンクで落ちる。**
`ring` / `sqlite-vec` / `libsqlite3-sys` が C をビルドするため避けて通れない。
VS Code が入っていることは関係しない — あれはエディタで、リンカも SDK も持たない。

> `winget` は初回に msstore ソースの規約同意を求め、断ると全体が止まる。
> `--source winget` を明示すれば同意なしで通る。

ここで C++ ワークロード (数 GB) を入れる代わりに **GNU ツールチェーンで迂回**しようと
して 3 つ踏んだ。**1 と 2 は解決し、3 で止まった。**

**(1) `rustup default …-gnu` が効かない — 犯人は `rust-toolchain.toml`**

リポジトリ直下の `rust-toolchain.toml` はホストトリプルを書いていない。

```toml
[toolchain]
channel = "stable"
```

この形は **rustup の default-host 経由で解決される**。だから
`rustup default stable-x86_64-pc-windows-gnu` を打ってもリポジトリ内では上書きされ、
`cargo build` は msvc のまま `error: linker link.exe not found` で落ち続ける。効くのは

```powershell
rustup set default-host x86_64-pc-windows-gnu
```

だけである。`rustup show` が
`active because: overridden by '...\rust-toolchain.toml'` かつ
`name: stable-x86_64-pc-windows-gnu` になれば正しい。**msvc で行くなら無関係だが、
GNU に振ろうとした人は必ずここで時間を溶かす。**

**(2) `error: error calling dlltool 'dlltool.exe': program not found`**

`windows-sys` / `getrandom` の `raw-dylib` が windows-gnu では `dlltool` を要求する。
rustup の `rust-mingw` コンポーネントはリンカを持つが **`dlltool` も `gcc` も持たない**。
MSYS2 で解決した。

```powershell
winget install --id MSYS2.MSYS2 --source winget --accept-package-agreements
C:\msys64\usr\bin\pacman.exe --sync --refresh --noconfirm mingw-w64-ucrt-x86_64-toolchain
```

→ `gcc 16.1.0` / `GNU Binutils 2.47.20260726`。**リンカ側の問題はこれで全部消えた。**

**(3) os error 4551 — ここで打ち切った**

`C:\msys64\ucrt64.exe` のシェルから `cargo build --workspace --locked` を回すと、
`quote` / `syn` / `ring` / `windows-sys` など多数が通った先で止まる。

```
error: failed to run custom build command for `ref-cast v1.0.25`
Caused by:
  could not execute process ...\target\debug\build\ref-cast-*\build-script-build (never executed)
Caused by:
  アクセスが拒否されました。 (os error 4551)
```

**ツールチェーンの問題ではない** — 冒頭の 4551 の但し書きを参照。**debug でも起きる。**
回避はポリシーの無効化か管理者による除外設定で、どちらも Kio の検証のために踏み込む
話ではない。

> **4551 が出なかった機との違いは、まだ特定できていない。**8/9 に完走した実績機の
> clone 先は `C:\kio` で**ユーザープロファイル配下ではない**。app-control ポリシーは
> ユーザー書き込み可能なパスにスコープされることが多いので、**パスが効いている**という
> 仮説は立つ。ただし 8/9 に止まった機にポリシーが掛かっているかを測っていないので、
> 「機の違い」なのか「パスの違い」なのかは**区別がついていない**。
> 4551 に当たったら、機を替える前に **`C:\` 直下の短いパスへ clone し直して 1 回試す**
> 価値はある。それで通れば仮説が確かめられ、通らなければ機の問題である。

## ✅ 2026-08-09 — 実績機 (`C:\kio`) で完走。回帰確認は終わり

`eb54f0e` で全項目 PASS した。**この回帰確認は閉じてよい。**

| | 結果 |
|---|---|
| `w/crlf` | **0** (`core.autocrlf=true` のまま。system の gitconfig 由来で global / local は未設定) |
| eol 内訳 | `w/lf 1570 / w/-text 15 / w/none 7` = 1592 = tracked 1592 |
| 7 ファイルの SHA-256 | **全一致** (§2 の参照表。JSON 4 本は生バイトの CR も 0) |
| `cargo build` | 成功 (exit 0 / 17.98s。`Cargo.lock` が動いていないので依存は 8/2 を再利用) |
| `cargo test` | **1,488 passed / 0 failed / 0 ignored** (34 バイナリ) |
| macOS 対照 | **1,514 passed** (34 バイナリ) — 差 26 で 3 点目も一致 |
| smoke | `init`→`index --preview`→`index --approve --offline`→`search`→`status` 完走。1 件ヒット |
| `os error 4551` | 出ていない |

**格納側も見た。**入力は BOM 付き CRLF (`Out-File -Encoding utf8`) だが、
`chunks.jsonl` の本文は **CR=0 / BOM=0 / 末尾 U+000A**。BOM も CRLF も正しく落ちている。
`.gitattributes` の `* -text` と合わせて、**この任務が守ろうとしている正規化は
入口から出口まで通っている**。

その過程で §4 の 2 項に実測を足した (BOM 無し `.ps1` が**黙って**壊れる件、
`search` の `--json` は pretty/compact の違いでしかない件)。どちらも 8/9 に踏んで
切り分けたものである。

---

# なぜ CI では足りないのか — ここが任務の核心

`windows-security-r23` (GitHub Actions / windows-latest) は 2026-07-31 時点で
**31 バイナリ / 1,412 passed / 0 failed** で緑である。それでも実機確認が要るのは、
**CI が構造的に検出できない欠陥が 1 種類あるから**である。

Git for Windows は既定で `core.autocrlf=true` であり、clone 時に LF テキストを
CRLF へ変換する。**Kio はファイルのバイト列そのものが identity** (CAS の hash) なので、
変換されると fixture の digest が Linux / macOS と食い違う。しかも壊れ方は原因から
遠い場所に出る。

GitHub の ubuntu / windows ランナーはこの変換をしない設定で走るため、**CI は何度
緑になってもこの問題について何も言わない**。2026-07-31 に `.gitattributes` へ
`* -text` (一切変換しない) を宣言して塞ぎ、**2026-08-02 に実機で効いていることを
確かめた** (上記)。

**この構造は今後も変わらない。** `.gitattributes` を触ったとき、あるいは
バイナリ / 改行に敏感な fixture を足したときは、CI が緑でも実機で回すこと。
CI がこの欠陥を見つけてくれることは、これからも無い。

---

# 環境

| | |
|---|---|
| OS | Windows 10 / 11 実機 (VM 可。WSL は**不可** — WSL は Linux なので検証にならない) |
| Git | Git for Windows (既定設定のまま。**`core.autocrlf` を触らないこと**) |
| Rust | stable (`rustup default stable`)。MSRV は 1.86 |
| ビルド | MSVC toolchain (Visual Studio Build Tools の C++ ワークロード) |

**`core.autocrlf` を明示的に false にしてはいけない。** 既定のまま走らせるのが検証の
目的である。既に false にしてある機械なら、`git config --global core.autocrlf true` に
戻してから clone すること (何を設定したかは報告に書く)。

---

# 手順

## 0. clone 先を選ぶ (先に決めること)

リポジトリ内の最長パスは **175 文字**:

```
eval/fixtures/normalized-corpus/corpus/p18/ambient-home/plm-cache/product-alpha/changes/eco-0042/attachments/supplier-alpha/certificates/supplier-audit-attachment-brief.pdf.md
```

Windows の `MAX_PATH` は 260 文字なので、**clone 先のパスは 84 文字以内**に収める。

```
260 - 175 - 1 (NUL) = 84
```

`C:\kio` のような浅い場所を推奨する。OneDrive 配下や
`C:\Users\<長い名前>\Documents\projects\...` は容易に超える。
超えた場合の症状は「clone は成功するのに一部ファイルが無い / チェックアウトに失敗する」で、
CRLF の問題と紛らわしいので**先に潰しておく**。

## 1. clone

```powershell
git config --get core.autocrlf     # 値を報告に書く (既定は true)
git clone https://github.com/ttokunaga-ja/kio.git C:\kio
cd C:\kio
```

## 2. バイト検査 — **これが本題**

```powershell
# (a) 作業ツリーに CRLF のファイルが 1 つも無いこと
git ls-files --eol | Select-String "w/crlf" | Measure-Object | Select-Object -ExpandProperty Count
#   → 0 でなければならない

# (b) eol の内訳が Linux/macOS と一致すること
git ls-files --eol | ForEach-Object { ($_ -split '\s+')[1] } | Group-Object | Select-Object Count,Name
#   → 判定は「w/crlf の行が存在しないこと」だけ。内訳の絶対数はファイルが
#     増減すれば当然動くので、合否ではない。
#     参考値 2026-07-31: w/lf 1558 / w/-text 15 / w/none 3  (tracked 1576)
#     参考値 2026-08-02: w/lf 1564 / w/-text 15 / w/none 3  (tracked 1582)
#     参考値 2026-08-09: w/lf 1570 / w/-text 15 / w/none 7  (tracked 1592)
#     数が違っても、合計が `git ls-files | Measure-Object` と一致していれば正常

# (c) 実ファイルのバイトが一致すること
Get-FileHash .gitattributes -Algorithm SHA256
Get-FileHash Cargo.toml     -Algorithm SHA256
Get-FileHash docs\README.md -Algorithm SHA256
Get-FileHash (Get-ChildItem crates\kio-adapter\tests\fixtures\layout-parsing\*.json) -Algorithm SHA256
```

| ファイル | bytes | SHA-256 (小文字で表記。`Get-FileHash` は大文字で出る) |
|---|---:|---|
| `.gitattributes` | 1054 | `f8cf711268dedf72c95c04edd86fe884e4048903fbff42a97d4980836989f347` |
| `Cargo.toml` | 1933 | `d067b66599158b448f4ee534d32bc64fae33fe366d89ae2befb95bf416b4f15e` |
| `docs/README.md` | 10546 | `53d80dbee92b3295129c6a4c6c469da2ac4f025ddf8041f6aa08e3826ae69977` |
| `…/layout-parsing/invoice-table.json` | 1117633 | `1ebec4b66a8fdf439cf3fb5307673dc4a3bdf56aec171258aa320d336cca0b8f` |
| `…/layout-parsing/slide-single-figure.json` | 1285842 | `1013ea29ebf0713f63cf76dfd1a8662cee8767c61370ccce7d7f71b8ae0c6023` |
| `…/layout-parsing/infographic-two-charts.json` | 1472174 | `337a12b90833642c8f3015c408edafbdff6d1a5d5e9f3fa87ef0037ad45ad2a1` |
| `…/layout-parsing/infographic-two-charts-as-pdf.json` | 1279343 | `2a635f3dbc3540a38e2adbcfd0a5304e295dbb75545465630a7f5201ef157ee2` |

> **上 3 ファイルは汎用のカナリアで、下 4 本が今の検証対象そのものである。**
> `layout-parsing` の JSON は `a282165` で入った実キャプチャで、**改行に敏感である**
> がゆえにこの回帰確認の引き金になった。参照値は `1074644` 時点の macOS 実測。
> 上 3 ファイルの hash は `028b7f7` の値だが `1074644` でも変わっていない。

> **`git status` は検出器にならない。** 変換が起きていても status はクリーンに見える
> (Git が比較時に正規化して戻すため)。作業ツリーの実バイトを見る (a)(c) が要る。

> **`w/` を見ること。`i/` ではない。** `git ls-files --eol` は 2 列出す。`i/` は
> オブジェクトストアの中身なので、**どの OS からでも同じ結果になり CI でも見える**
> (2026-08-02 時点で `i/crlf` は 0)。`w/` は clone が作業ツリーへ書いた実バイトで、
> **`core.autocrlf` が効くのはこちらだけ**である。つまり `i/crlf` = 0 は
> 「CRLF を commit していない」ことしか言わず、この任務が問うている
> 「clone が CRLF に変換していない」ことは `w/crlf` = 0 でしか分からない。

> **上表の hash は commit `028b7f7` 時点の値である。** これらのファイルが後日変更されれば
> 当然ずれるので、**hash が違ったら「CRLF 変換が起きた」と即断せず、まず
> `git log -1 --format=%H -- <file>` でその後に変更されていないかを見ること。**
> (a) の `w/crlf` = 0 と、下記の `git check-attr text -- Cargo.toml` → `text: unset` は
> ファイル内容に依存しないので、**そちらが主検査**である。hash は裏取り。

## 3. ビルドとテスト

```powershell
cargo build --workspace --locked
cargo test --workspace --all-targets --locked
```

**判定は `0 failed` である。** passed の数は裏取りであって合否ではない —
テストが増えれば当然増える。

| 日付 | commit | Windows | macOS | 差 | 出所 |
|---|---|---:|---:|---:|---|
| 2026-07-31 | `028b7f7` | 1,412 | 1,438 | 26 | CI (両 job とも同一コマンド) |
| 2026-08-02 | `c29ecac` | **1,418** | 1,444 | 26 | Windows 実機 / macOS 手元 |
| 2026-08-09 | `eb54f0e` | **1,488** | 1,514 | 26 | Windows 実機 / macOS 手元 |

0 failed / 0 ignored は 3 回とも同じ。バイナリ数は 7/31・8/2 が 31、8/9 は **34**
(下記の新規 `tests/*.rs` 3 本ぶん) で、Windows と macOS で常に同数である。

> **Linux は macOS より 1 多い。**`s6_non_utf8_filename_is_skipped_with_warning`
> (`crates/kio-cli/tests/contract_cli.rs`) が `#[cfg(target_os = "linux")]` で、
> macOS/APFS は非 UTF-8 のファイル名をファイルシステムが拒むため**そのバイト列を
> 作ることすらできない**からである。2026-08-09 実測: macOS 1,516 / Linux 1,517。
> GPU 機 (WSL2) の報告はこちらの系列なので、**macOS と 1 ずれるのが正常**である。

**差 26 は 3 点で動いていない。**これが効くのは、Windows 側の数が正しいかを
macOS から独立に言えるからである。8/9 は Windows 1,488 を測ったあと macOS を回して
1,514 — 予測 (1,488 + 26) と一致した。**片側だけ測って「増えたから正常」と
言わないこと。**差が 26 から動いたときは `#[cfg]` の付き方が変わったサインである。

8/2 の 1,418 は 7/31 の 1,412 に
D7 の 6 件 (`http_policy.rs` 3 / `scope.rs` 3、いずれも cfg 無し) が乗った数と一致する。
これが「増えた 6 件は Windows でも走った」ことの裏取りである。

8/9 の +70 も同じやり方で名寄せした。`c29ecac..eb54f0e` の diff で追加された
`#[test]` / `#[tokio::test]` の**正味が 70** で、passed の増分と一致する。

| ファイル | 追加 |
|---|---:|
| `crates/kio-adapter/src/local_ocr_markdownize.rs` | 43 |
| `crates/kio-cli/tests/step5_local_ocr.rs` | 11 |
| `crates/kio-adapter/tests/real_layout_parsing_captures.rs` | 7 |
| `crates/kio-adapter/src/tool_lock.rs` | 4 |
| `crates/kio-cli/tests/step5_local_ocr_secrets.rs` | 2 |
| `crates/kio-index/src/chunking.rs` | 2 |
| `crates/kio-pipeline/src/markdownize.rs` | 1 |
| **計** | **70** |

削除は 0 なので、**Windows で丸ごとコンパイルされていないモジュールは無い**と言える。
数え方の裏取り: このリポジトリに `rstest` / `test_case` / `proptest` の類は 1 つも無いので、
上の 2 属性を数えれば取りこぼしが出ない。

> **eol 内訳も同じ名寄せができる。**8/9 は `w/none` +4 / `w/lf` +6 / 計 +10 で、
> `c29ecac..eb54f0e` の**追加ファイルがちょうど 10 本 (JSON 4 / テキスト 6)** と
> 種別まで一致した。合計だけ合わせても再現しない一致なので、**内訳が動いたときは
> 追加ファイルの種別と突き合わせる**とよい。

> **差の 26 は「`#[cfg(unix)]` のテスト数」ではなく差し引きである。**
> `#[cfg(unix)]` / `#[cfg(not(windows))]` のテストが Windows で消える一方、
> `#[cfg(windows)]` のテスト (`windows_known_profile_is_an_absolute_fallback`、
> `home_and_xdg_unset_use_windows_profile_without_cwd_device_state` など) が
> 逆に増える。**26 という数だけを見て `cfg(unix)` を数えても合わない。**
> 数が合わないときに見るべきは差ではなく、下記のとおり**名前**である。

## 4. 実際に動かす (テストが通ることと、動くことは別)

適当な作業用ディレクトリに、テキストファイルを数本置いて試す。

```powershell
mkdir C:\kio-smoke ; cd C:\kio-smoke
"Kio は履歴を保つローカル検索です" | Out-File -Encoding utf8 note-01.md
"2026 年 7 月の設計メモ。埋め込みは後段。"  | Out-File -Encoding utf8 note-02.md

C:\kio\target\debug\kio.exe init
C:\kio\target\debug\kio.exe index --preview
C:\kio\target\debug\kio.exe index --approve --offline
C:\kio\target\debug\kio.exe search "設計メモ"
C:\kio\target\debug\kio.exe status
```

`--offline` を付けるのは、外部 adapter (OCR / embedding) を呼ばずに text 検索だけで
end-to-end を成立させるためである。**承認行も課金も発生しない。**

見るべきこと:

- `init` が `.kio` を作る (`initialized` と出る)
- `index --preview` が `preview` を返し、**何も送らない**
- `index --approve --offline` が `indexed` で完走する
- `search` が **1 件以上**返す
- `status` が投入した 2 ファイルを列挙する
- パス表示に `\` と `/` の混在で壊れた形が出ていない

> **`--json` を付けると `resolved_mode: "text"` / `fallback: true` が出るが、これは正常
> である。** 既定の `auto` は hybrid を試みてから text へ落ちる設計で、この smoke には
> embedding adapter を設定していないので落ちるのが正しい。**`fallback: true` を故障と
> 読まないこと。**
>
> ただし上の書き方は誤解を招くので補足する。**`search` は `--json` を付けなくても
> JSON を出す。**`print_output` (`crates/kio-cli/src/main.rs`) は `text` / `status` /
> `commits` / `changes` / `files` を持つペイロードだけプレーンテキストに描画し、
> **それ以外は `to_string_pretty` に落ちる**。`search` の応答は `results` なので
> 該当せず、`--json` の有無は **pretty か compact かの違いにしかならない**
> (8/9 実測: 無し 1053 B / 有り 842 B、どちらも JSON)。`view` / `status` / `log` /
> `diff` には本物のプレーンテキスト出力があるので、**この話は `search` 固有**である。
>
> この手順一式は 2026-07-31 に macOS で実際に流して、上記の出力になることを確認して
> ある (`search "設計メモ"` は 1 件、`resolved_mode: text`)。**したがって Windows で
> ここが失敗したら、手順の誤りではなく Windows 固有の問題である。**
>
> ただし**次節の 2 つだけは例外**で、Kio ではなく PowerShell 側の問題である。

### ⚠ PowerShell 5.1 で日本語が化ける — Kio の欠陥ではない [2026-08-02 / 08-09 実測]

Windows 実機で上の手順をそのまま流すと、**日本語が壊れて見える経路が 2 つある**。
どちらも Windows PowerShell 5.1 (`powershell.exe`) の文字コード処理であって、
Kio の出力は正しい。切り分けを知らないと Kio の不具合として報告してしまう。

**(1) BOM 無しの `.ps1` は日本語リテラルが壊れる。エラーになるとは限らない。**
PowerShell 5.1 は **BOM の無い `.ps1` を ANSI コードページ (日本語環境では CP932) として
読む**ため、UTF-8 で保存したスクリプト中の日本語リテラルが壊れる。**症状は 2 通りあり、
どちらが出るかは壊れたバイトが有効なトークンになるかどうかで決まる。**

| | 症状 | 危険度 |
|---|---|---|
| 構文として壊れた | `トークン '年' を使用できません` で**止まる** [8/2 実測] | 気付く |
| 文字列として通った | **エラーにならず、壊れた引数がそのまま `kio.exe` に渡る** [8/9 実測] | **気付かない** |

後者が厄介である。8/9 に実際に出たのは:

```
query echoed : 險ｭ險医Γ繝｢                        ← kio.exe が受け取った引数
query cps    : U+96AA U+FF6D U+96AA U+533B …
results count: 0
```

`險ｭ險医Γ繝｢` は 設計メモ の CP932 誤読そのもので、**`search` は 0 件を返す**。
これは Kio の検索が壊れているのと**画面上まったく区別がつかない**。同じスクリプトに
BOM を付けるだけで `設計メモ` (U+8A2D U+8A08 U+30E1 U+30E2) が渡り、1 件返る。

> **`search` が 0 件だったら、Kio を疑う前にまず引数を echo すること。**
> スクリプトの BOM 有無で結果が変わるなら、それは Kio ではなく PowerShell である。

- 対処: `.ps1` を **UTF-8 BOM 付き**で保存する。または PowerShell 7 (`pwsh`) を使う
  (7 以降は BOM 無し UTF-8 が既定)。コマンドを対話的に貼って実行する分には起きない

**(2) `kio.exe` の出力をパイプ・リダイレクトすると mojibake になる。**
PowerShell 5.1 は**ネイティブプロセスの stdout をコンソールコードページで
デコードし直す**。Kio は UTF-8 を書くので、CP932 として解釈された時点で壊れ、
`Out-File` で書き戻しても復元しない。実際に観測した snippet:

```
'2026 蟷ｴ 7 譛医・險ｭ險医Γ繝｢縲ょ沂繧∬ｾｼ縺ｿ縺ｯ蠕梧ｮｵ縲・n'   ← PowerShell 経由
'2026 年 7 月の設計メモ。埋め込みは後段。\n'                ← 実際の Kio の出力
```

- 対処: `cmd` / Git Bash から `kio.exe … --json > out.json` と**直接リダイレクト**する
  (バイトが素通りする)。PowerShell を使うなら
  `[Console]::OutputEncoding = [Text.Encoding]::UTF8` を先に設定する

**Kio かどうかの切り分け方** — 表示ではなく**格納された本文**を見る:

```bash
# .kio に入った本文が正しければ、化けているのは表示経路だけである
python3 -c "import json;[print(repr(json.loads(l)['text'][:40])) for l in open('.kio/index/chunks.jsonl',encoding='utf-8')]"
```

2026-08-02 の Windows 実機ではこれが
`'2026 年 7 月の設計メモ。埋め込みは後段。\n'` と正しく、**UTF-8 BOM も正しく
剥がされていた**。直接リダイレクトした `--json` の snippet も同じく正しい。
**したがって「PowerShell の画面や `Out-File` の結果が化けている」ことは
Kio の不具合の根拠にならない。**格納側を確認してから報告すること。

---

# 期待値まとめ

| 検査 | 期待 |
|---|---|
| `core.autocrlf` | 既定 (true) のまま |
| clone 先パス長 | 84 文字以内 |
| `w/crlf` のファイル数 | **0** ← これが合否 |
| eol 内訳 | 合計が tracked 数と一致 (2026-08-02: w/lf 1564 / w/-text 15 / w/none 3 = 1582)。絶対数は合否ではない |
| 3 ファイルの SHA-256 | 上表と一致 |
| `cargo test --workspace` | **0 failed** ← これが合否 (2026-08-02: 1,418 passed) |
| smoke | `init`→`index --preview`→`index --approve --offline`→`search` が完走し、`search` が 1 件以上返す (`fallback: true` は正常) |

---

# 失敗したときに切り分けること

**`w/crlf` が 0 でない、または hash が違う** → `.gitattributes` の `* -text` が効いて
いない。`git check-attr text -- Cargo.toml` を実行して `text: unset` になるか確認し、
結果を報告する。これは**この任務が見つけるために存在する欠陥**なので、詳細に書くこと。

**テスト数が上表と違う** → 落ちていないなら、まず**それが正常**である可能性を疑う
(このリポジトリは動いており、テストは増える)。そのうえで `cargo test -- --list` の
差分を**名前で**報告する。数だけでは、テストが増えたのか、Windows で丸ごと
コンパイルされていないモジュールがあるのか区別できない。

**特定のテストだけ落ちる** → 落ちたテスト名・エラーコード・panic 位置をそのまま報告する。
2026-07-31 に直したのは `KIO-E-STORE-IO-001` (directory fsync) とパス区切りの 2 系統なので、
**それ以外の症状なら新種**である。

**ビルドが通らない** → C++ Build Tools と `link.exe` の有無を先に確認する。
`sqlite-vec` / `ring` / `libsqlite3-sys` は C をビルドするので MSVC が要る。

---

# 報告フォーマット

```
## 環境
Windows <version> / Git <version> / rustc <version> / clone 先 <path> (<n> 文字)
core.autocrlf: <値>

## バイト検査
w/crlf: <n>          eol 内訳: w/lf <n> / w/-text <n> / w/none <n>
.gitattributes  <hash>  一致: <はい|いいえ>
Cargo.toml      <hash>  一致: <はい|いいえ>
docs/README.md  <hash>  一致: <はい|いいえ>

## ビルド / テスト
cargo build: <成功|失敗>
cargo test:  <n> passed / <n> failed  (合否は failed=0。passed は 2026-08-02 に 1418)
落ちたテスト: <名前を列挙、無ければ「なし」>

## smoke
init / index --preview / index --approve --offline / search: <各 成功|失敗>
search が引いたもの: <結果>

## 判定
Windows 実機で clone・ビルド・動作が成立する: <はい|いいえ>
成立しない場合、何が足りないか
```

---

# やってはいけないこと

- **`core.autocrlf` を false にして「通った」と報告する** — 既定で通ることが任務である
- **WSL で実行する** — WSL は Linux であり、この任務が探している問題は起きない
- テストが落ちたときに `--exclude` や `--ignored` で回避して緑にする
- 失敗を「環境のせい」で片付ける。**再現手順と実際の出力を書く**こと。
  2026-07-31 の 4 件は「Windows だから仕方ない」ではなく 1 関数の欠陥だった
- smoke で `--offline` を外す (外部 adapter を呼ぶと承認と課金の話が混ざる)
- **os error 4551 を通すためにアプリケーション制御ポリシーを切る** — 管理者の領分であり、
  Smart App Control は Windows 11 では**一度切ると再インストールなしには戻せない**。
  4551 に当たったら**その機を諦めて別の実機に移る**のが正しい (2026-08-09 はそうした)
