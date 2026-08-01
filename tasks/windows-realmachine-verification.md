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
#     数が違っても、合計が `git ls-files | Measure-Object` と一致していれば正常

# (c) 実ファイルのバイトが一致すること
Get-FileHash .gitattributes -Algorithm SHA256
Get-FileHash Cargo.toml     -Algorithm SHA256
Get-FileHash docs\README.md -Algorithm SHA256
```

| ファイル | bytes | SHA-256 (小文字で表記。`Get-FileHash` は大文字で出る) |
|---|---:|---|
| `.gitattributes` | 1054 | `f8cf711268dedf72c95c04edd86fe884e4048903fbff42a97d4980836989f347` |
| `Cargo.toml` | 1933 | `d067b66599158b448f4ee534d32bc64fae33fe366d89ae2befb95bf416b4f15e` |
| `docs/README.md` | 10546 | `53d80dbee92b3295129c6a4c6c469da2ac4f025ddf8041f6aa08e3826ae69977` |

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

31 バイナリ / 0 failed / 0 ignored は両日とも同じ。8/2 の 1,418 は 7/31 の 1,412 に
D7 の 6 件 (`http_policy.rs` 3 / `scope.rs` 3、いずれも cfg 無し) が乗った数と一致し、
**差の 26 は 2 つの commit にまたがって動いていない**。これが「増えた 6 件は
Windows でも走った」ことの裏取りである。

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
> この手順一式は 2026-07-31 に macOS で実際に流して、上記の出力になることを確認して
> ある (`search "設計メモ"` は 1 件、`resolved_mode: text`)。**したがって Windows で
> ここが失敗したら、手順の誤りではなく Windows 固有の問題である。**
>
> ただし**次節の 2 つだけは例外**で、Kio ではなく PowerShell 側の問題である。

### ⚠ PowerShell 5.1 で日本語が化ける — Kio の欠陥ではない [2026-08-02 実測]

Windows 実機で上の手順をそのまま流すと、**日本語が壊れて見える経路が 2 つある**。
どちらも Windows PowerShell 5.1 (`powershell.exe`) の文字コード処理であって、
Kio の出力は正しい。切り分けを知らないと Kio の不具合として報告してしまう。

**(1) `.ps1` に落として実行するとパースエラーになる。**
PowerShell 5.1 は **BOM の無い `.ps1` を ANSI コードページ (日本語環境では CP932) として
読む**ため、UTF-8 で保存したスクリプト中の日本語リテラルが壊れ、
`トークン '年' を使用できません` のような構文エラーになる。

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
