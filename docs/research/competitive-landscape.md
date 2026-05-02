# Competitive Landscape

KCS は隣接領域に多くの先行プロダクトを持つ。「自分だけが新しい」という前提で進めると埋もれる。本章は競合・近接事例を整理し、KCS が **どこで重ならず、どこで学ぶか** を確定する。比較は思想ではなく **ユーザー体験差** を基準にする。

---

# 1. 競合・近接事例

| プロダクト | レイヤー | 主訴求 | KCS との重なり | KCS との非重複 |
| --- | --- | --- | --- | --- |
| **Perkeep** | content-addressed personal storage | open formats / プライバシー / 単一障害点回避 / 永続保存 | content-addressed・ローカル中心・思想 | Markdown 正規化なし、AI 検索なし、Evidence Pointer なし、即効性弱 |
| **git-annex** | 大容量ファイル × Git | 同期・バックアップ・アーカイブ。チェックサム・暗号化 | content-addressed の発想、CLI 中心 | 知識検索なし、Markdown化・Embedding なし |
| **Obsidian + Smart Connections** | ノート vault + ローカル意味検索 | local-first / on-device embedding / vault 内意味検索 | local-first AI 検索、ローカル embedding | vault 内に閉じる。任意ファイル・PDF・履歴 DAG なし |
| **Khoj** | personal AI / second brain | PDF/Markdown/Org/Notion を対象に自然言語検索 / 自己ホスト / 複数 IF | local-first AI 検索、PDF 含む、ローカル運用 | content-addressed archive ではない、Evidence Pointer なし、time-travel なし |
| **AnythingLLM** | local-first AI app | モデル・文書・チャットをローカル。デスクトップ版アカウント不要 | local-first、文書取り込み | チャット中心、CAS や履歴 DAG なし |
| **DEVONthink** | 文書管理アプリ | ローカル AI、文書間関係発見、分類、文書 versioning | ローカル中心、文書管理 | macOS 商用、CAS 中心ではない、Evidence Pointer なし |
| **Microsoft Recall** | 画面 snapshot 検索 | 自然言語検索でタイムラインから過去作業を再発見。ローカル処理 | time-travel 体験 | 画面ベースであってファイルベースではない、ファイル原本に戻れない |
| **Apple Intelligence** | OS 統合 AI | 個人文脈、オンスクリーン認識、オンデバイス + Private Cloud Compute | プライバシー・ローカル処理 | OS ベンダー専属、汎用ローカルアーカイブではない |

---

# 2. Perkeep 失敗分析 (KCS が学ぶべきこと)

Perkeep は思想的に KCS と最も近い (content-addressed、ローカル中心、所有権、永続保存)。にもかかわらず一般化していない。仮説として以下が要因と考える。

```text
- セットアップが技術者向け (server プロセス, blob 概念, importer)
- ユーザー体験が抽象的 (「保存できる」が日常的な体験差に変換されない)
- 既存ファイルシステムとの関係が曖昧 (どちらが正本か分かりにくい)
- 検索・閲覧・整理の即効性が弱い
- "Why now?" の訴求が時代と噛み合わなかった
```

KCS が同じ轍を踏まないための行動原則:

1. **最初の体験を即効的にする**: `kcs init → kcs search "あの PDF" → kcs open` で価値が出る状態。「思想」を最初に売らない。
2. **ファイルシステムとの関係を明示する**: 原本は元の場所にある。`.kcs` は隠しメタデータ。Perkeep のように「全部 blob に持っていく」ことはしない。
3. **content-addressed は手段、Evidence Pointer は目的**: ユーザーに blob/CAS を見せない。見せるのは「根拠が死なない」結果だけ。
4. **既存ワークフローに乗る**: Obsidian vault、Documents、Downloads を **置き換えず横断する**外部アーカイブ層として始める。

---

# 3. KCS が重ならない領域 (差別化の核)

競合製品が満たしていない、KCS だけが提供できる体験は次の **3 点** に絞る。

### 3.1 Evidence Pointer (時間的に安定した根拠)

path ではなく `commit / tree / raw_hash / chunk_hash / span` で根拠を指す。ファイルが移動・削除・上書きされても、KCS の content-addressed object store に原文が残るため、Evidence Pointer は死なない。これは Khoj / Obsidian / Recall いずれも提供していない。

### 3.2 Markdown 正規化を共通中間表現とする

すべてのファイル種別を Normalized Markdown に変換し、人間と AI が同じビューを使う。ただし **Markdown は正本ではなく raw object からの read-only view**。これは DEVONthink 的な「文書管理」と Khoj 的な「AI チャット」の中間に位置する独自レイヤー。

### 3.3 Content-addressed local archive + time-travel search

全ファイルを CAS object として保存し、snapshot DAG を持つ。**削除済み / 過去版 / 移動済みファイルにも検索が届く**。Recall は画面 snapshot だが、KCS はファイル原本に戻れる。Perkeep は CAS だが検索 UX が弱い。Khoj は検索があるが過去版にいけない。

---

# 4. KCS が重なる領域 (=「相互運用」or「乗らない」)

| 領域 | 重なる相手 | KCS のスタンス |
| --- | --- | --- |
| 個人ノート vault | Obsidian | **置き換えない**。Obsidian vault を含む親フォルダに `.kcs` を置く形で共存。Smart Connections が vault 内意味検索を提供しているのに対し、KCS は vault + Documents + Downloads + コードを **横断**する。 |
| AI チャット UX | Khoj, AnythingLLM | **競合しない**。KCS は CLI + 構造化 API を提供し、Khoj/AnythingLLM がそれを呼べる関係を狙う。 |
| 大容量ファイル管理 | git-annex | **対象が違う**。git-annex は同期・バックアップ。KCS は知識検索とEvidence。両立可能。 |
| 画面履歴 | Microsoft Recall, Rewind | **競合しない**。レイヤーが違う (画面 vs ファイル)。 |
| OS 統合 | Apple Intelligence, Windows Copilot | **競合しない**。OS ベンダーは横断アーカイブ層を提供しない。 |

---

# 5. ポジショニングの言語化

採用する一語表現:

```
英: Evidence-grounded local knowledge archive
日: 原文根拠付きローカル知識アーカイブ
```

避けるべき言語:

```
✗ "Git for knowledge"        Git との完全比較に引きずられる。全部入りに見える。
✗ "Personal AI search tool"  Khoj / AnythingLLM と区別できない。
✗ "OS 級プロダクト"            ターゲットとリソースが噛み合わない。
✗ "Knowledge Graph platform" v2 以降の機能を MVP の旗印にしない。
```

---

# 6. ターゲットユーザー (確定)

最初のターゲットは明確に次の層に絞る。

```text
- 大量の PDF・Markdown・コード・画像・研究資料を扱う
- 開発者・研究者・技術者
- Git や CLI に抵抗がない
- ローカルファイルが散らかっている
- AI 検索を試したいが、クラウド丸投げは嫌
```

最初の MVP は **一般ユーザー向けではない**。GUI も MVP では持たない (CLI + 構造化 API のみ)。これは Perkeep の轍を意識した上での判断: 一般ユーザー向けにいきなり広げると、提供価値が霞む。技術者層で「探せなかったファイルがすぐ見つかる」「根拠が死なない」を確立してから広げる。

---

# 7. 第一価値命題

最初に売るのは思想ではなく体験差:

> **「探せなかったファイルがすぐ見つかる」**
> **「根拠が死なない」**

`kcs init → kcs search "あの PDF" → kcs open` の 3 コマンドで成立する状態を MVP の最低ラインにする。

---

# 8. 参考リンク

- Perkeep — https://perkeep.org/
- git-annex — https://git-annex.branchable.com/
- Khoj — https://docs.khoj.dev/
- Smart Connections — https://smartconnections.app/smart-connections/
- DEVONthink — https://www.devontechnologies.com/apps/devonthink/ai
- Microsoft Recall — https://support.microsoft.com/en-us/windows/privacy-and-control-over-your-recall-experience-d404f672-7647-41e5-886c-a3c59680af15
- Apple Intelligence — https://www.apple.com/apple-intelligence
- AnythingLLM — https://anythingllm.com/
