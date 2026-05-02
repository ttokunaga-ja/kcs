# Positioning, MVP Scope, Phase Plan

KCS のプロダクト位置づけ・対象ユーザー・MVP スコープ・実装フェーズを **正本** として定義する。他のドキュメントが「KCS とは何か」を語る場合、本書を参照する。

> 関連: [競合分析](competitive-landscape.md), [プロダクト化メモ](productization_notes.md), [理念](philosophy.md)

---

# 1. ポジショニング (一行で)

```
英: Evidence-grounded local knowledge archive
日: 原文根拠付きローカル知識アーカイブ
```

KCS は次のいずれでもない:

- 全部入りの "Git for knowledge"
- 個人向け AI 検索ツール (Khoj / AnythingLLM 系)
- OS 級プロダクト
- 企業向けナレッジ基盤
- Knowledge Graph プラットフォーム

KCS は次である:

> **ローカルファイルを、過去も含めて、AI と人間が根拠付きで探索できる知識アーカイブ。**

---

# 2. ターゲットユーザー (最初の顧客)

最初のターゲットは明確に絞る。

```text
- 大量の PDF・Markdown・コード・画像・研究資料を扱う
- 開発者・研究者・技術者
- Git や CLI に抵抗がない
- ローカルファイルが散らかっている
- AI 検索を試したいが、クラウド丸投げは嫌
```

**MVP では一般ユーザー向けではない**。GUI も MVP では持たない (CLI + 構造化 API のみ)。広げるのは、上記層で確実に動いてから。

---

# 3. 第一価値命題

最初に売るのは思想ではなく即効的体験差。

> **「探せなかったファイルがすぐ見つかる」**
> **「根拠が死なない」**

最低ライン:

```bash
kcs init
kcs snapshot
kcs search "あの PDF"
kcs open
```

これで価値が成立する状態を MVP の Definition of Done に含める。

---

# 4. 差別化の核 (3 点に絞る)

### 4.1 Evidence Pointer

`commit / tree / raw_hash / chunk_hash / span` で根拠を指す。path ではない。ファイル移動・削除・上書きでも根拠は死なない (CAS object store が原文を保持するため)。

### 4.2 Markdown 正規化を共通中間表現とする

すべてのファイル種別を Normalized Markdown に変換し、人間と AI が同じビューを使う。**Markdown は正本ではなく raw object からの read-only view**。詳細は [read_only.md](read_only.md), [hash.md](hash.md)。

### 4.3 Content-addressed local archive + time-travel search

全ファイルを CAS object として保存し、snapshot DAG を持つ。削除済み / 過去版 / 移動済みファイルにも検索が届く。

---

# 5. MVP スコープ (絞り込み)

KCS は要素が多すぎるので、MVP では **一次・二次** を厳格に分ける。

### 5.1 MVP に含める (Phase 1〜3)

```text
content-addressed raw object 保存
Normalized Markdown (incremental Markdownize 含む)
chunk
Embedding
FTS (FTS5 外部 content + trigram tokenizer)
Hybrid search
Evidence Pointer
snapshot DAG (commit / tree)
restore
time-travel search (--at)
```

### 5.2 MVP で捨てる (v2 以降に倒す)

```text
完全な Knowledge Graph (node/edge 自動生成)
複雑な Agent navigation (neighbors, beam search 等)
GUI
クラウド共有・修正提案・workspace 概念
pack/delta 圧縮
高度な分類器の自動移動 (auto_organize は提案表示のみ)
```

これらが「設計に存在しない」のではなく、**MVP の旗印にしない**ということ。設計検討は research ドキュメント上で続けてよいが、Phase 4-5 のラベルを付ける。

---

# 6. Phase Plan (実装順)

```
Phase 1: Evidence 基盤
  - raw object 保存
  - normalized markdown 生成 (incremental 含む)
  - chunk 生成
  - Evidence Pointer

Phase 2: 検索
  - FTS5
  - sqlite-vec
  - hybrid search (paging / MMR)

Phase 3: 履歴
  - tree
  - commit / snapshot object
  - restore
  - --at / --all-history

Phase 4: 自動化
  - auto snapshot
  - Downloads watch
  - inbox
  - classification suggestion (提案のみ)

Phase 5: Agent
  - agent API
  - navigation
  - neighbors
  - node / edge
```

各 Phase は前 Phase に依存する。Phase 1 が動かないうちに Phase 4-5 を深掘りしない。

---

# 7. 二層構造: truth と cache

データ・所有権・権限の正本は **各フォルダ直下の `.kcs`** に閉じる。device-local な `scope_registry` や将来の global aggregator は **検索キャッシュ・発見補助** に過ぎない。

```
truth = folder-local .kcs
  - raw object / normalized / chunks / commits / refs
  - 権限境界 / partial sync / purge / export の単位

cache = scope_registry / aggregator
  - 検索の探索対象一覧
  - stale 検出
  - UI 統合
```

ルール:

- aggregator のみを更新して `.kcs` の状態が変わる実装は禁止。
- aggregator 喪失は再構築可能 (各 `.kcs` を rescan)。`.kcs` 喪失は復旧不能。
- 検索結果メタには「正本の `.kcs` パス」を必ず含める。

---

# 8. 既存ワークフローとの関係

KCS は既存ツールを置き換えない。**横断する**外部アーカイブ層として始める。

| 既存ワークフロー | KCS の関係 |
| --- | --- |
| Obsidian vault | vault を含む親フォルダに `.kcs`。vault 内検索は Smart Connections に任せ、KCS は vault + Documents + Downloads + コードを横断。 |
| Git リポジトリ | リポジトリ自体には `.kcs` を置かない (Git に管理される)。リポジトリ群を含む親フォルダに `.kcs` で横断検索。 |
| 既存ファイル整理 | Documents / Downloads など散らかった領域を整理せず、横断検索と Evidence で「整理しなくても見つかる」体験を提供。 |
| Khoj / AnythingLLM | KCS の構造化 API を呼ぶ関係を狙う。チャット UX は彼らに任せる。 |

---

# 9. ポジショニングを揺さぶる発言禁止リスト

ドキュメント・README・ピッチでは、以下のフレーズを使わない。

```
✗ "Git for knowledge"
✗ "全部入りのナレッジ管理"
✗ "個人 AI アシスタント"
✗ "OS 級"
✗ "Knowledge Graph for personal data"
✗ "Notion / Obsidian キラー"
```

採用する語:

```
✓ Evidence-grounded local knowledge archive
✓ 原文根拠付きローカル知識アーカイブ
✓ time-travel knowledge navigation (履歴特性を語るとき)
✓ Evidence Pointer (技術用語として)
```

---

# 10. このドキュメントの更新方針

ポジショニングは頻繁に変えない。MVP リリース → 一次ユーザー検証 → 拡張判断、の**節目でのみ更新**する。揺らぎは ADR で記録し、本書は「現時点の確定版」を保つ。
