# Windows 実機での clone・ビルド・動作確認 ブリーフ

このファイルはそのまま作業者 (人でもエージェントでも) への指示として読める形にしてある。
実行には **Windows 実機**が要る。CI では代替できない (理由は下記)。

---

# 任務

**Windows 実機で clone したリポジトリが、Linux / macOS と同じバイトを持ち、
ビルドとテストが通り、`kio` が実際に動くことを確かめる。**

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
`* -text` (一切変換しない) を宣言して塞いだが、**その宣言が実機で効いていることは
まだ実機で確かめられていない。** それがこの任務である。

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
#   → w/lf 1558 / w/-text 15 / w/none 3

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

期待値 (2026-07-31 の CI 実測): **31 バイナリ / 1,412 passed / 0 failed / 0 ignored**。

> macOS では 1,438 passed になる。差の 26 件は `#[cfg(unix)]` のテストで、
> Windows では最初からコンパイルされない。**1,412 と 1,438 の差は異常ではない。**

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

---

# 期待値まとめ

| 検査 | 期待 |
|---|---|
| `core.autocrlf` | 既定 (true) のまま |
| clone 先パス長 | 84 文字以内 |
| `w/crlf` のファイル数 | **0** |
| eol 内訳 | w/lf 1558 / w/-text 15 / w/none 3 |
| 3 ファイルの SHA-256 | 上表と一致 |
| `cargo test --workspace` | 1,412 passed / 0 failed |
| smoke | `init`→`index --preview`→`index --approve --offline`→`search` が完走し、`search` が 1 件以上返す (`fallback: true` は正常) |

---

# 失敗したときに切り分けること

**`w/crlf` が 0 でない、または hash が違う** → `.gitattributes` の `* -text` が効いて
いない。`git check-attr text -- Cargo.toml` を実行して `text: unset` になるか確認し、
結果を報告する。これは**この任務が見つけるために存在する欠陥**なので、詳細に書くこと。

**テスト数が 1,412 と違う** → どのテストが増減したかを名前で報告する。数だけでは
原因が分からない。

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
cargo test:  <n> passed / <n> failed  (期待 1412 / 0)
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
