# 01 Positioning

Kio のプロダクト位置づけ・対象ユーザー・差別化・競合分析・MVP スコープ・Phase plan を **正本** として定義する。他ドキュメントが「Kio とは何か」を語る場合、本書を参照する。

> 関連: [02-philosophy.md](02-philosophy.md) (理念) / [09-mvp-scope.md](09-mvp-scope.md) (MVP / Phase / Step) / [10-operations.md](10-operations.md) (横断規約)

---

# 1. ポジショニング (一行で)

```
英: Local-first knowledge archive, powered by frontier AI.
日: データはローカル、計算は最強の AI を使う。
```

二次表現 (補助的な言い換え):

```
英: Evidence-grounded local knowledge archive
日: 原文根拠付きローカル知識アーカイブ
```

Kio は次のいずれでもない:

- 全部入りの "Git for knowledge"
- 個人向け AI 検索ツール (Khoj / AnythingLLM 系)
- OS 級プロダクト
- 企業向けナレッジ基盤
- Knowledge Graph プラットフォーム
- offline-first 原理主義ツール (everything offline)

Kio は次である:

> **ローカルファイルを、過去も含めて、AI と人間が根拠付きで探索できる知識アーカイブ。データの主権はローカルに置きつつ、計算は frontier AI (Mistral OCR / Gemini / Claude / GPT) を含む最強の手段を使う。**

## 1.1 なぜ "local-first" であって "offline-first" ではないか

`local-first` は **データの主権がローカルにある** ことを意味する。`offline-first` は **ネット遮断でも動く** ことを含意する。両者は別物である。

Kio の対象ユーザー (開発者・研究者) の現実のワークフローは、Markdownize や Embedding に Mistral OCR / Gemini / Claude / GPT 等の frontier AI を使うのが既定値である。ここで "everything offline" を強要すると、Perkeep が辿った「思想は近いが日常体験差を出せない」失敗を踏襲する。

Kio の主張は「**原本・履歴・index の保管と主権はあなたのマシンにある / 計算結果 (Markdown, Embedding) もあなたのマシンに残る / 処理のためのファイル内容の送信は明示 opt-in で行い、何を・いつ・どの Adapter へ送ったかを記録する** ([07-adapter-spec.md §3](07-adapter-spec.md))」であり、API 呼び出し自体を禁止することではない。opt-in 後は frontier AI にファイル内容が送信される。これを隠さず、preview で network transmission policy として提示する ([06-cli-spec.md §2](06-cli-spec.md))。完全オフライン運用はローカル LLM Adapter や同梱 deterministic Adapter を選択するユーザーの自由として残るが、それは **デフォルトではない**。

opt-in の単位・寿命・revoke の正本は [07-adapter-spec.md §3](07-adapter-spec.md)。

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

**MVP では一般ユーザー向けではない**。GUI も MVP では持たない (CLI + 構造化出力 `--json` のみ。外部 Agent 向け API は Phase 5 — [09-mvp-scope.md §3.1](09-mvp-scope.md))。広げるのは、上記層で確実に動いてから。

---

# 3. 第一価値命題

最初に売るのは思想ではなく即効的体験差。

> **「探せなかったファイルがすぐ見つかる」**
> **「根拠が死なない」**

最低ライン:

```bash
kio init
kio index --approve      # 取り込み + ベースライン index (初回は preview + 明示承認)
kio search "あの PDF"
kio open <検索結果の pointer>
```

これで価値が成立する状態を MVP の Definition of Done に含める。`kio index` が**初回の**取り込みと検索 index 構築の入口であり (後着の online 成果は batch resume / retry / reindex の finalize が検索対象化する — [05-runtime.md §8.1](05-runtime.md))、成功時に auto snapshot も作られる — 明示 `kio snapshot` は任意。この 4 コマンドは **API キー未設定でも成立する** (同梱 deterministic Adapter によるベースライン index + text 検索。[07-adapter-spec.md §2.1](07-adapter-spec.md))。frontier AI は意味検索・スキャン PDF・画像内テキストへ検索品質を引き上げる推奨 opt-in である。

即効価値と履歴価値は分けて訴求する。

- **初日から効く**: 意味検索 (語彙一致しない言い換え・スキャン PDF・画像内テキストに届く) と Evidence Pointer 表示 (意味検索は online Adapter 承認済み構成での Done 条件 — API キー未設定時は text 検索ベースライン)。OS 全文検索 (Spotlight / ripgrep-all) が失敗するクエリで勝つことを Done 条件に含める ([09-mvp-scope.md §4](09-mvp-scope.md))。
- **使うほど効く**: リネーム横断 (M3-2)・削除済み再発見 (M3-3) は snapshot 履歴の蓄積とともに立ち上がる価値であり、導入初日の差別化としては訴求しない。

---

# 4. 差別化の核 (3 点に絞る)

### 4.1 Evidence Pointer

`commit / tree / raw_hash / chunk_hash / span` で根拠を指す。path ではない。ファイル移動・削除・上書きでも根拠は死なない (CAS object store が原文を保持するため。**明示の purge を除く** — [02-philosophy.md §2.4](02-philosophy.md))。

### 4.2 Markdown 正規化を共通中間表現とする

すべてのファイル種別を Normalized Markdown に変換し、人間と AI が同じビューを使う。**Markdown は正本ではなく raw object からの read-only view**。詳細は [03-data-model.md §10](03-data-model.md)。

### 4.3 Content-addressed local archive + time-travel search

全ファイルを CAS object として保存し、snapshot DAG を持つ。削除済み / 過去版 / 移動済みファイルにも検索が届く。

---

# 4.4 競合・近接事例

「自分だけが新しい」という前提で進めると埋もれる。比較は思想ではなく **ユーザー体験差** を基準にする。

| プロダクト | レイヤー | Kio との重なり | Kio との非重複 |
| --- | --- | --- | --- |
| **Perkeep** | content-addressed personal storage | content-addressed・ローカル中心・思想 | Markdown 正規化なし、AI 検索なし、Evidence Pointer なし、即効性弱 |
| **git-annex** | 大容量ファイル × Git | content-addressed の発想、CLI 中心 | 知識検索なし、Markdown化・Embedding なし |
| **Obsidian + Smart Connections** | ノート vault + ローカル意味検索 | local-first AI 検索、ローカル embedding | vault 内に閉じる。任意ファイル・PDF・履歴 DAG なし |
| **Khoj** | personal AI / second brain | local-first AI 検索、PDF 含む | content-addressed archive ではない、Evidence Pointer なし、time-travel なし |
| **AnythingLLM** | local-first AI app | local-first、文書取り込み | チャット中心、CAS や履歴 DAG なし |
| **DEVONthink** | 文書管理アプリ | ローカル中心、文書管理 | macOS 商用、CAS 中心ではない、Evidence Pointer なし |
| **Microsoft Recall** | 画面 snapshot 検索 | time-travel 体験 | 画面ベースであってファイルベースではない、ファイル原本に戻れない |
| **Apple Intelligence** | OS 統合 AI | プライバシー・ローカル処理 | OS ベンダー専属、汎用ローカルアーカイブではない |
| **OS/ローカル全文検索 (Spotlight, Recoll, ripgrep-all)** | ローカル全文検索 | ローカル・即時・無料。「本文の一部から探す」体験の第一代替 | 語彙一致が前提で、言い換え・意味検索に弱い。削除済み・上書き済み・過去版には届かない (現在のファイルシステムのみ)。根拠が path 依存で、移動・リネームで死ぬ。Evidence Pointer なし |
| **NotebookLM** | クラウド型 evidence-grounded QA | citation 付き AI 回答、研究者ユーザー層、無料 | アップロード型でデータ主権がクラウド側。ソースは notebook 単位の手動登録で、ファイルシステム横断・履歴なし。citation は notebook 内参照であり、不変性・time-travel・ローカル原本回帰なし (詳細は下記) |
| **Zotero / Paperless-ngx** | 文書アーカイブ (OCR + 全文検索 + メタデータ) | 研究者の PDF 管理定番、ローカル運用可、OCR 全文検索 | 専用ライブラリへの取り込み型で、任意フォルダの横断ではない。意味検索なし。CAS 履歴なし (削除済み・過去版検索なし)。Evidence Pointer なし |

参考: Perkeep https://perkeep.org/ / git-annex https://git-annex.branchable.com/ / Khoj https://docs.khoj.dev/ / Smart Connections https://smartconnections.app/smart-connections/ / DEVONthink https://www.devontechnologies.com/apps/devonthink/ai / Recall https://support.microsoft.com/en-us/windows/privacy-and-control-over-your-recall-experience-d404f672-7647-41e5-886c-a3c59680af15 / Apple Intelligence https://www.apple.com/apple-intelligence / AnythingLLM https://anythingllm.com/ / Recoll https://www.recoll.org/ / ripgrep-all https://github.com/phiresky/ripgrep-all / NotebookLM https://notebooklm.google.com/ / Zotero https://www.zotero.org/ / Paperless-ngx https://docs.paperless-ngx.com/

## 4.4.1 NotebookLM との差別化 — citation と Evidence Pointer は別物

NotebookLM の citation は「notebook にアップロード済みのソース内の該当箇所への参照」であり、クラウド上のコーパスに閉じる。Evidence Pointer は `commit / tree / raw_hash / chunk_hash / span` で根拠を不変に固定するため、次の 4 点で体験が異なる: (1) **不変性** — 原本のリネーム・移動・削除・上書き後も pointer は死なない。citation はソースを削除すれば消える。(2) **time-travel** — 過去の任意 snapshot 時点の内容を指せる。(3) **ローカル原本回帰** — `kio open` で OS 規定アプリの原本そのものに戻れる。citation の終点はクラウド上のビューア。(4) **任意フォルダ横断** — アップロード操作なしに、手元の全 indexed scope (過去版・削除済み含む) を対象にする。NotebookLM は「選んだソースに質問する」体験、Kio は「持っている全ファイルから根拠を掘り出し、その根拠を固定する」体験であり、併用可能 (Kio で見つけた原本を NotebookLM に投入する使い方は妨げない)。

# 4.5 Perkeep 失敗分析 (Kio が学ぶべきこと)

Perkeep は思想的に Kio と最も近い (content-addressed、ローカル中心、所有権、永続保存)。にもかかわらず一般化していない。仮説:

```
- セットアップが技術者向け (server プロセス, blob 概念, importer)
- ユーザー体験が抽象的 (「保存できる」が日常的な体験差に変換されない)
- 既存ファイルシステムとの関係が曖昧 (どちらが正本か分かりにくい)
- 検索・閲覧・整理の即効性が弱い
- "Why now?" の訴求が時代と噛み合わなかった
```

Kio が同じ轍を踏まないための行動原則:

1. **最初の体験を即効的にする**: `kio init → kio index --approve → kio search "あの PDF" → kio open <pointer>` で価値が出る状態。「思想」を最初に売らない。
2. **ファイルシステムとの関係を明示**: 原本は元の場所にある。`.kio` は原本を置き換えない隠しアーカイブ層 (CAS コピー + metadata — 容量は原本相当 + 派生を見込む)。Perkeep のように「blob store を原本の置き場にする」ことはしない。
3. **content-addressed は手段、Evidence Pointer は目的**: ユーザーに blob/CAS を見せない。見せるのは「根拠が死なない」結果だけ。
4. **既存ワークフローに乗る**: Obsidian vault / Documents / Downloads を **置き換えず横断する** 外部アーカイブ層として始める (詳細 §8)。

# 4.6 重なる領域 = 相互運用 / 乗らない

| 領域 | 重なる相手 | Kio のスタンス |
| --- | --- | --- |
| 個人ノート vault | Obsidian | **置き換えない**。vault を含む親フォルダに `.kio`。vault 内検索は Smart Connections に任せ、Kio は vault + Documents + Downloads + コードを横断 |
| AI チャット UX | Khoj, AnythingLLM | **競合しない**。Kio は CLI + 構造化 API を提供し、Khoj/AnythingLLM がそれを呼べる関係を狙う |
| 大容量ファイル管理 | git-annex | **対象が違う**。git-annex は同期・バックアップ。Kio は知識検索と Evidence。両立可能 |
| 画面履歴 | Microsoft Recall, Rewind | **競合しない**。レイヤーが違う (画面 vs ファイル) |
| OS 統合 | Apple Intelligence, Windows Copilot | **競合しない**。OS ベンダーは横断アーカイブ層を提供しない |
| 文書アーカイブ | Zotero, Paperless-ngx | **置き換えない**。Zotero ライブラリ等を含む親フォルダに `.kio` を置き、専用アーカイブの外にあるファイルも含めて横断する |

---

# 5. MVP スコープ (絞り込み)

Kio は要素が多すぎるので、MVP では **一次・二次** を厳格に分ける。

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

これらが「設計に存在しない」のではなく、**MVP の旗印にしない**ということ。設計検討の経緯は git history で辿り、将来仕様は正本 spec 内で Phase 4-5 のラベルを付けて扱う (旧 research ドキュメントは 2026-07-18 に撤去 — README §5)。

---

# 6. Phase Plan (価値の柱の区分 — 実装順ではない。実装順の正本は [09-mvp-scope.md §3](09-mvp-scope.md) の Step 計画 / README §2)

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
  - 定期 auto snapshot (取り込み完了時の auto snapshot は MVP — 05-runtime.md §8.1)
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

データ・所有権・権限の正本は **各フォルダ直下の `.kio`** に閉じる。device-local な `scope_registry` と global aggregator は **検索キャッシュ** に過ぎない。device-global の例外は **cost-ledger.sqlite** (再構築不可の運用台帳 — cache ではない、[03-data-model.md §4.1](03-data-model.md))。

```
truth = folder-local .kio
  - raw object / normalized / chunks / commits / refs
  - 権限境界 / partial sync / purge / export の単位

cache = scope_registry
  - 検索の探索対象一覧 / stale 検出
cache = aggregator
  - 全 scope の live chunk 集合を複製した device-level read replica
  - 横断検索の採点・候補選択、権限状態の横断投影
```

ルール:

- scope_registry / aggregator のみを更新して `.kio` の状態が変わる実装は禁止。
- scope_registry / aggregator 喪失は再構築可能 (各 `.kio` を rescan)。`.kio` 喪失は復旧不能。
- 検索結果メタには「正本の `.kio` パス」を必ず含める。
- **aggregator は安全性判定の最終権限を持たない** — 結果を返す scope は live `.kio` で再確認する
  ([05-runtime.md §1.8](05-runtime.md))。**権限の書き込みは常に `.kio` へ行う**。

---

# 8. 既存ワークフローとの関係

Kio は既存ツールを置き換えない。**横断する**外部アーカイブ層として始める。

| 既存ワークフロー | Kio の関係 |
| --- | --- |
| Obsidian vault | vault を含む親フォルダに `.kio`。vault 内検索は Smart Connections に任せ、Kio は vault + Documents + Downloads + コードを横断。 |
| Git リポジトリ | リポジトリ自体には `.kio` を置かない (Git に管理される)。`kio index` は VCS repo root 配下に既定で子 `.kio` を作らないため、**リポジトリ内のコードは既定では検索対象外** — コードも対象にするには `[scope] index_vcs_repos = true` の明示 opt-in ([03-data-model.md §3](03-data-model.md))。検索が横断するのは repo 外のファイルと他 scope である (横断検索は scope_registry 経由の全 scope 検索であり、親 `.kio` 自体は直下のみ管理 — 03 §3)。 |
| 既存ファイル整理 | Documents / Downloads など散らかった領域を整理せず、横断検索と Evidence で「整理しなくても見つかる」体験を提供。 |
| Khoj / AnythingLLM | Kio の構造化 API を呼ぶ関係を狙う。チャット UX は彼らに任せる。 |

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
✗ "offline-first"           (誤解を招く。"local-first" を使う)
✗ "private AI" / "機密 AI"  (中心軸ではない)
✗ "データはあなたのマシンから出ない"  (デフォルト構成 (frontier AI) では偽。「保管と主権はローカル」と言い換える)
```

採用する語:

```
✓ Local-first knowledge archive, powered by frontier AI.   (core)
✓ データはローカル、計算は最強の AI を使う。                  (core 日)
✓ local-first                                                (データ主権の語として)
✓ Evidence-grounded local knowledge archive                  (二次表現)
✓ 原文根拠付きローカル知識アーカイブ                            (二次表現)
✓ time-travel knowledge navigation                           (履歴特性を語るとき)
✓ Evidence Pointer                                           (技術用語として)
```


---

# 10. このドキュメントの更新方針

ポジショニングは頻繁に変えない。MVP リリース → 一次ユーザー検証 → 拡張判断、の**節目でのみ更新**する。本書は「現時点の確定版」を保つ。揺らぎは git history で追える。
