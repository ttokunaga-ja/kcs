# 10 Operations (横断規約と運用)

この文書は、実装・UI・運用へ落とすときに問題になりやすい点を補足する。

> **NOTE (2026-05 改訂)**: ポジショニング・ターゲットユーザー・MVP スコープ・Phase plan は **正本を [01-positioning.md](01-positioning.md) に移した**。本書はその下位の運用ルールを扱う。競合分析は [01-positioning.md §4](01-positioning.md) を参照。

MVP は **「Evidence-grounded local knowledge archive」としての最小完全系** として扱う。「全部入りの Git for knowledge」を目指さない。詳細は [01-positioning.md §5](01-positioning.md)。

---

# 1. 初回スキャン前の承認

KCS はデフォルトで全 indexed scope を検索対象にし、全ファイルを管理対象にする。ただし、初回スキャンでは、対象範囲 preview、除外提案、明示承認を必須にする。

目的はデフォルト全管理を弱めることではない。KCS が単なる検索インデックスではなく、原本を content-addressed object として保存する知識アーカイブであることを、ユーザーが理解したうえで開始するためである。

必須フロー:

```text
kcs init
  ↓
候補 scope を探索
  ↓
対象フォルダ / 推定ファイル数 / 推定容量 / 大容量ファイル / 除外候補を preview
  ↓
.kcsignore / 設定を調整
  ↓
再 preview
  ↓
明示承認
  ↓
raw object 保存、Markdownize、Embedding、index 更新を開始
```

preview では、少なくとも次を表示する。

```text
root path
included scopes
excluded scopes
estimated file count
estimated total bytes
large files
hidden directories
build/cache/vendor candidates
network transmission policy
adapter execution mode
estimated markdownize cost (USD)
estimated embedding cost (USD)
estimated completion under current budget cap
```

コスト概算は、現行 `tool-lock.json` の online Adapter 単価 × 推定ページ数 / トークン数から算出する **桁の目安** であり、保証ではない。概算合計が当月の effective budget cap ([04-pipeline.md §5.4](04-pipeline.md)) を超える場合、preview は承認前に警告し、cap 内での推定完了時期 (月数) とあわせて次の選択肢を提示する。

```text
Estimated AI enrichment cost: ~$210 (markdownize ~$180, embedding ~$30)
Current budget cap: $50/month → estimated completion: 5 months
Options:
  [1] ベースライン index のみで開始 (コスト $0。AI 強化は後から)
  [2] 除外 (.kcsignore) を調整して再 preview
  [3] budget cap を変更
  [4] このまま続行 (cap 到達時に AI 強化タスクは paused)
```

ベースライン index ([07-adapter-spec.md §2.1](07-adapter-spec.md)) は選択肢に依らず先に完了するため、どの選択でも初日の検索は成立する。

除外候補は提案であり、ユーザーの承認なしに自動除外しない。唯一の例外は secrets 系パターン
(§1.1 Tier A) で、これは built-in デフォルト除外として最初から「除外済み」状態で preview に
表示され、取り込むにはユーザーの明示的な解除操作 (対話承認時の個別選択、または .kcsignore の
negation 記述) が必要である。`--yes` はこの解除を行えない ([06-cli-spec.md §2](06-cli-spec.md))。

```text
Suggested exclusions:
  node_modules/     build/cache candidate
  target/           build output candidate
  .git/             VCS internal metadata
  *.tmp             temporary file
  *.cache           cache file
  video.mp4         large file: 8.2GB
```

secrets 系はデフォルト除外・警告として別枠で表示する。

```text
Excluded by default (secrets, Tier A):
  .env              environment file
  .ssh/             SSH keys directory
  cert.pem          private key / certificate

Sensitive candidates (Tier B, 取り込み予定・要確認):
  db_credentials.yaml   filename matches *credentials*
  api_tokens.md         filename matches *token*
```

非対話環境では、承認済み scope または `--yes` / `--approve` のような明示オプションがない限り、`kcs index` は失敗させる。

承認記録には、少なくとも次を残す (**保存先 = `.kcs/scope.json` の `scan_approval` key** — schema 検証
対象 §12.3。adapter 単位の network opt-in 承認 `approvals[]` ([07-adapter-spec.md §3](07-adapter-spec.md))
とは別 key)。

```text
scope_id
root_path
approved_at
actor
approval_method        # interactive | approve | yes
kcs_version
effective_ignore_hash
estimated_file_count
estimated_total_bytes
estimated_markdownize_usd
estimated_embedding_usd
```

承認後の index は二段で進む ([04-pipeline.md §5](04-pipeline.md)): ベースライン index が先に完了し、AI 強化 (Markdownize / Embedding) は budget guardrail の管理下で後段として進む。AI 強化が未完了・paused の間、その状態を隠してはならない。

- `kcs status` は AI 強化の進捗 (done / pending / paused 件数) と paused の理由 (budget / auth / tier_b_approval) を表示する (rate limit は paused ではなく pending + next_retry_at として表示 — [04-pipeline.md §5.2](04-pipeline.md))
- 照合が恒久不能な in-flight Batch job (資格情報喪失等) は **stalled** として表示し続ける。脱出路は
  `kcs batch abandon` のみ (自動では何も変更しない — [04-pipeline.md §5.8](04-pipeline.md))
- 検索レスポンスは index が部分的なとき `index_status` を返す ([05-runtime.md §1.7](05-runtime.md))

## 1.1 Secrets デフォルト除外 (built-in ignore template)

KCS は secrets 系ファイルの取り込み・オンライン送信事故を防ぐため、built-in の除外テンプレート
を同梱する。パターンは 2 段階に分ける。

**Tier A (デフォルト除外)**: 拡張子・ファイル名から secrets とほぼ確実に判定できるもの。
system directory (§4 の走査境界既定) も Tier A 相当の built-in 除外に含め、**OS 別の対象パターンは
built-in template に列挙し、その template の版を `effective_ignore_hash` の入力に含める** (パターン
更新が承認記録の同一性判定に反映されるように)。
初回 preview で「除外済み」として表示され、取り込むには明示解除が必要。

```text
.env
.env.*
*.pem
*.key
*.p12
*.pfx
id_rsa*
id_ecdsa*
id_ed25519*
*.keystore
.ssh/
.gnupg/
.aws/
.kube/config
.docker/config.json
.netrc
.npmrc
.pypirc
*.tfstate
*.tfstate.*
```

**Tier B (警告のみ)**: 名前ベースで機微の可能性があるが誤検出も多いもの。取り込み対象に
含めるが、初回 preview の「機微ファイル候補」欄に列挙してユーザー確認を促す。

```text
*credentials*
*secret*
*token*
*apikey*
*password*
```

規約:

```text
1. テンプレートは KCS 本体に同梱し、バージョンを effective_ignore_hash の入力に含める
2. Tier A の解除は、対話承認時の個別選択 または .kcsignore の negation (!pattern) のみ
3. --yes は Tier A の解除・Tier B 警告のスキップを行えない (06-cli-spec.md §2)
4. テンプレートの追加・変更は本節の更新を伴う (破壊的変更扱い)
```

**承認後に追加されたファイルの扱い**: scope 承認は初回一回だが、承認後にフォルダへ追加された
ファイルが secrets パターンに一致する場合は自動処理を保留する。

```text
Tier A 一致の新規ファイル:
  取り込み自体を保留 (quarantine)。CAS 保存・snapshot への取り込みを行わない。
  kcs status に「取り込み保留 (secrets 候補)」として表示し、
  取り込みには対話確認 または .kcsignore の明示編集を要する。

Tier B 一致の新規ファイル:
  ローカル取り込み (CAS 保存・ローカル index) は行うが、online_api Adapter への
  送信 task は **paused (hold_reason=tier_b_approval — [04-pipeline.md §5.2](04-pipeline.md))**
  として保留し、kcs status に表示する。
  対話確認 (kcs index の実行時プロンプト) で一括承認できる (承認 = paused 解除)。

非一致の新規ファイル:
  従来どおり自動取り込み (デフォルト全管理を維持)。
```

---

# 2. 容量より利便性を優先する

KCS は、容量効率よりも知識を失わないこと、あとから検索・履歴探索・復元できることを優先する。

したがって、全ファイル管理をデフォルトとする方針は維持する。動画・巨大PDF・画像・Officeファイルも、ユーザーが明示的に ignore しない限り管理対象に含める。例外は secrets 系の built-in デフォルト除外 (§1.1 — 不可逆な漏洩リスク) と、§4 の走査境界既定 (system directory / VCS repo root / placeholder 等 — 安全側の既定であり容量目的ではない) のみ。

ただし、プロダクトはこの事実を隠してはならない。

```text
KCS は検索インデックスだけでなく、原本ファイルを content-addressed archive に保存します。
各 `.kcs` が管理するのはその `.kcs` が置かれたフォルダ直下のファイルのみです。
サブフォルダのファイルは (そこに `.kcs` があるか否かに関わらず) 親 `.kcs` は取り込みません。
対象ファイルを含むサブフォルダには子 `.kcs` が作られ、独立したスコープとして管理されます
(§4 の既定により VCS repo root 配下には作られません)。
同じ `.kcs` 内では同じ内容を重複保存しません。
別フォルダの別 `.kcs` に同じ内容のファイルが存在するのは、ユーザーが意図的に複数フォルダへ
同じファイルを配置した場合に限られ、その場合はフォルダ単位の独立性を優先して重複保存します。
```

必要な表示:

```text
推定追加容量
`.kcs` 内 dedup 後の保存見込み
別 `.kcs` 間で重複する可能性のある容量 (ユーザーが複数フォルダへ同じファイルを配置している場合のみ発生)
大容量ファイル一覧
現在の空き容量
ディスク枯渇リスク
除外候補
```

ディスク枯渇が予測される場合、KCS は勝手に対象範囲を狭めない。続行、除外、延期、中断をユーザーに選ばせる。

---

# 3. Scope Registry (= cache only, NOT truth)

KCS は **二層構造** をとる。データ・所有権・権限の **正本は各フォルダ直下の `.kcs`** に閉じる。device-local な scope_registry や将来の global aggregator は **検索キャッシュ・発見補助に過ぎない**。両者を混同しない。

```
truth = folder-local .kcs
  raw object / normalized / chunks / commits / refs
  権限境界 / partial sync / purge / export の単位

cache = scope_registry / aggregator
  検索の探索対象一覧、stale 検出、UI 統合
```

実装では、device-local な scope registry を明確に持つ。

保存先:

```text
~/.local/share/kcs/scope-registry.sqlite
```

schema (本節が正本。2026-07-14 実装準拠で確定):

```sql
CREATE TABLE scopes (
  scope_id TEXT NOT NULL,
  kcs_path TEXT NOT NULL,
  root_path TEXT NOT NULL,
  participates_in_global_search INTEGER NOT NULL DEFAULT 1,
  indexed INTEGER NOT NULL DEFAULT 0,   -- sqlite.db 構築済み (横断検索の対象候補)
  last_seen_at TEXT NOT NULL,
  PRIMARY KEY (scope_id, kcs_path)
);
```

運用規約:

- WAL モード + busy_timeout 5000ms で複数プロセスの書き込みを直列化する
  ([05-runtime.md](05-runtime.md) 同時実行規約)
- upsert は `(scope_id, kcs_path)` を key に行い、`indexed` は単調 (MAX) にのみ更新する
- **stale 登録の退役**: `.kcs` を削除して同じ path で `init` し直すと新しい `scope_id` が採番される
  (scope_id は init 時採番の ULID、[03-data-model.md §2](03-data-model.md))。upsert の直前に、同一
  `kcs_path` で `scope_id` が異なる行を削除する。**逆方向 (scope の移動) も同様に退役する**: 同一
  `scope_id` を新しい `kcs_path` で観測 (再発見) したら、同一 scope_id の旧 path 行を削除する —
  **ただし旧 path がなお到達可能 (存在し有効な `.kcs`) な場合は move と認定せず、削除しない**。
  同一 scope_id の複数 live path は clone 併存であり、**fail-closed で扱う**: global search は当該
  scope_id を skip して `excluded_scopes` に KCS-E-REGISTRY-DUP 系の理由付きで記録し、pointer 解決は
  候補一覧 error とする ([08-evidence-pointer-spec.md §3.1](08-evidence-pointer-spec.md) — purge 状態の
  異なる clone へ黙って解決しない)。どちらを残すかはユーザーの dedupe に委ねる (複製へ新 scope_id を
  発行する fork は Phase 4+ 予約) —
  放置すると default 横断検索が旧 path の stale scope を毎回 skip し恒常的に exit 3 になる。放置すると横断検索が同一文書を dead scope_id 経由で
  二重に返し、その Evidence Pointer は `KCS-E-EVIDENCE-SCOPE-UNREACHABLE-001` で解決不能になる。
  registry は cache なので削除は常に安全 (live scope は自分を再登録する)
- device data dir (`~/.local/share/kcs/`) は owner-only (0700) に制限する (best-effort。非 unix は
  no-op。registry / cost-ledger / logs は利用パターンとスコープ地図を含むため)

`approved_at` / `effective_ignore_hash` / `permission_status` は permission 系 (Phase 4+) の予約であり、
**MVP の schema には含めない** (旧 spec の保存情報リストから 2026-07-14 に分離。追加時は §7.5.3 の
schema 変更規約に従う)。

### 不変条件 (cache vs truth)

```text
1. scope_registry のみを更新して `.kcs` の状態が変わる実装は禁止。
2. scope_registry 喪失は再構築可能 (各 `.kcs` を rescan)。
3. `.kcs` 喪失は復旧不能 (registry には正本データがない)。
4. 検索結果メタには「正本の `.kcs` パス」を必ず含める。
5. raw object の所有権・dedup は scope_registry でグローバル化しない。
   各 `.kcs/objects` 内に閉じる (横断 dedup を諦めた帰結。03-data-model.md §3)。
```

scope registry は共有 `.kcs` の正本ではない。フォルダ移動や外部ドライブ切断時は、`scope.json` の `scope_id` を使って再発見または stale 扱いにする (`folder_id` は同概念の旧称であり廃止)。

---

# 4. フォルダごとの `.kcs` 運用

`.kcs` は基本的に各フォルダに生成される。ただし、空フォルダや未到達フォルダへ先回りして作る必要はない。

推奨:

```text
kcs init は現在フォルダの .kcs だけを作る
kcs index は対象ファイルや子scopeを発見した時点で必要な .kcs を作る
空フォルダには .kcs を作らない
履歴やobjectを持たない .kcs は repair / cleanup で整理可能にする
```

走査境界の既定 (2026-07-18 確定 — いずれも安全側。緩和は config で明示的に行う):

```text
symlink               lstat 基準で検出し、**追跡しない** (skip + status 表示)。scope 外への
                      参照・循環を構造的に排除する
hardlink              通常ファイルとして扱う (同一 inode でも path ごとに別実体 — dedup は
                      content hash が自然に吸収する)
外部ドライブ          mount 済みなら通常フォルダと同じ。unmount 中の path は missing 扱い
                      ([03-data-model.md §8](03-data-model.md) の files status)
クラウド placeholder  内容を hydrate しない (placeholder のまま skip + status 表示 —
                      勝手なダウンロードで帯域・容量を消費しない)
権限のないフォルダ    fail-closed: skip + status 表示 (エラーで走査全体を止めない)
hidden directory      OS の hidden 属性・dotfile は通常どおり対象 (除外は .kcsignore / Tier A で
                      行う — 隠しであることは機微性の根拠にしない)
system directory      built-in ignore (Tier A 相当) に含め既定除外
.kcs 自身             ignore 評価より前に必ず prune (自己再帰の禁止)
VCS リポジトリ root   既定で子 .kcs を生成しない。既存子 .kcs は grandfathered で継続有効 ([03-data-model.md §3](03-data-model.md))
```

---

# 5. 物理レイアウト統一

内部正本は `.kcs/objects/normalized_units/` (unit object 群 + manifest) に統一する
([03-data-model.md §2.1](03-data-model.md))。全文 Markdown は unit を決定論的に結合した
view (再生成可能な cache) であり正本ではない。

過去メモにある `.kcs/normalized/` は、bootstrap 時の簡略表記または仮想表示パスとして扱う。実装・契約ドキュメントでは、hash ベースの object store を正とする。

```text
truth:
  .kcs/objects/normalized_units/ab/cd/<raw64>.<tool64>.g<gen>/

materialized view (cache):
  .kcs/objects/normalized/ab/cd/<raw64>.<tool64>.g<gen>.md

virtual view:
  report.pdf.md
```

`<raw64>` / `<tool64>` は論理 hash (`sha256:<64 lowercase hex>`) の digest 部分のみを使う
canonical physical basename である。Windows で無効な `:` を物理名に含めず、論理 hash、JSON、refs、
Evidence URI の identity は変更しない。新規の物理 object は canonical 名で作成する。

旧 Unix store にある `sha256:` 付き physical leaf/basename は、内容 hash または manifest identity を
照合した compatibility fallback として扱う。要求内容と完全一致すればその場で再利用し、通常の read/index は
canonical への eager migration を行わない。normalized の同一 gen を更新する partial retry は、選択済みの
legacy layout 内で instance/view を置き換えられる。事前の一括変換は不要。canonical / legacy の両方が存在する
場合は両方を検証し、いずれかの不一致または競合を store corruption として fail closed する。これは物理ファイル名の portability correction であり、
object hash 算出・論理 identity の変更や `kcs_format_version` の MAJOR bump ではない
([03-data-model.md §2 / §8.1](03-data-model.md))。

---

# 6. 検索バックエンド統一

MVP の標準全文検索バックエンドは SQLite FTS5 とする。Vector は sqlite-vec を標準とする。

Tantivy など他の BM25 / full-text backend は将来候補として扱い、採用する場合は本書を更新する (破壊的変更扱い)。

> **リスク注記 (sqlite-vec)**: sqlite-vec は v0 系で API 未安定、ANN index を持たない全件 brute-force KNN であり、成熟度リスクがある。M3-1 の性能目標 (20 scopes / 合計 10 万 chunk で p95 < 5 秒、[09-mvp-scope.md §4.1](09-mvp-scope.md)) は brute-force で達成可能な規模であり、text fallback ([05-runtime.md §1.1](05-runtime.md)) と本節の Future 差し替え経路が設計済みのため、MVP では標準として維持する。Step 3 の最初のタスクとして (1) 使用する sqlite-vec のバージョンを pin し、(2) 合計 10 万 chunk 規模での brute-force レイテンシ計測 spike を行う。目標未達の場合も MVP では対応せず、Future バックエンドの採用判断材料として記録する。

```text
MVP:
  MetadataStore = SQLite
  TextSearchBackend = SQLite FTS5
  VectorSearchBackend = sqlite-vec

Future:
  Tantivy
  LanceDB
  Qdrant
  PostgreSQL + pgvector
```

---

# 7. Purge の保証範囲

`purge` は、KCS 管理下の object store (本文 bytes と派生 artifact — manifest object 含む)、index、pack、cache (`~/.cache/kcs/open/` の一時展開を含む — [05-runtime.md §3.5](05-runtime.md))、
および KCS 自身のログ (`.kcs/logs/access.jsonl`、`~/.local/share/kcs/logs/` の
events / errors / metrics) から対象ファイル由来の情報を削除する操作である。
**snapshot DAG (commit / tree object) は書き換えない** — tree entry のメタデータ (path, raw_hash) は
履歴に残る (正本 [05-runtime.md §3.5](05-runtime.md)。完全な履歴書き換えは v2+/Phase 4+ —
[06-cli-spec.md §6](06-cli-spec.md))。
ログについては、対象の raw_hash / path / query を含む行の削除またはフィールドマスクを行う。
`redact_logs` デフォルト true (§12.6) の運用では query / path / prompt は元から記録されないため、
実務上のスクラブ対象は主に raw_hash 参照行に限られ軽量である。
purge 自体の実行記録 (`commit_type=purged`、tombstone) は監査可能性のため残す ([05-runtime.md §3.2](05-runtime.md))。

ただし、OS backup、Time Machine、クラウド同期の過去版、外部 export、ユーザーが手動コピーしたファイル、KCS 外のログまでは KCS 単体では保証しない。

UI 文言は、過剰な保証を避ける。

```text
推奨:
  KCS 管理下の本文と派生物を全履歴から削除 (ファイル名と存在の記録は履歴に残ります)

避ける:
  世界中のすべてのコピーを完全削除
```

`purge` は必ず次を要求する。

```text
影響範囲 preview
理由入力
明示確認
対象の削除 (raw / prepared / image / normalized / chunk / embedding — 共有派生は live 参照 0 のみ、
  SQLite 行 (chunks / chunk_config_generations / chunk_vec / embeddings / FTS) と chunks.jsonl 行を含む。
  正本一覧は [05-runtime.md §3.5](05-runtime.md))
pack / cache / index rebuild
KCS 自身のログのスクラブ (該当行の削除またはマスク) と、その完了有無の結果表示
復元不能な最小 tombstone
```

---

# 7.5 `.kcs` の整合性検証とバックアップ

「`.kcs` 喪失は復旧不能」(§3 不変条件 3) である以上、破損の検出手段とバックアップ手順を
仕様として持つ。

## 7.5.1 kcs repair --verify-objects (fsck 相当)

```bash
kcs repair --verify-objects
```

- `objects/` 配下の全 CAS object (raw / prepared / image / chunk / embedding / manifest / tree / commit) を [03-data-model.md §8.1](03-data-model.md) の per-type algorithm で検証し (embedding は vector 長・有限値・vector digest も — 03 §8.1)、
  保存パス・参照 hash と照合する。chunk は object bytes の content hash ではなく semantic identity hash
  と fan-out key、さらに exact `text` / `text_hash` / normalized span を照合する
  ([03-data-model.md §8.1](03-data-model.md))
- normalized の unit bytes は content hash を持たない ([03-data-model.md §5](03-data-model.md)) ため hash 検証対象外とし、
  参照整合 (対応する `(raw_hash, tool_profile_hash)` object の実在) のみ確認する。**manifest object
  (objects/manifests/ — [03-data-model.md §2.1](03-data-model.md)) は content-addressed であり再 hash 検証の対象**:
  各 tree entry の `normalize.manifest_hash` が実在する manifest object を指すこと (**tombstone / erase
  receipt が説明する purge 済み raw の entry を除く** — 下記 dead terminal 規則。purge は manifest object を
  削除するが tree は書き換えないため、この例外なしには正規 purge 直後の store が必ず corruption になる)、
  HEAD tree の entry については作業コピー manifest.json の canonical JCS hash が一致することも検査する
  (不一致 = 破損ではなく「**未 finalize の進行状態**」として incomplete (exit 3) — manifest finalize と
  次回 snapshot の間のクラッシュ窓で正常に生じる。次回 index / batch resume が同期する。corruption と
  するのは manifest object 自体の再 hash 不一致のみ)
- SQLite index は検証対象外 (破損時は `--rebuild-db` で再構築可能なため)

破損検出時の挙動:

```text
1. working tree に同一ファイルが現存し、再計算 raw_hash が一致
   → re-ingest で object を復元し、commit_type=repaired の commit を記録
     (復元した raw object は GC 対象外、05-runtime.md §2.6)
2. 復元手段なし
   → missing として errors.jsonl に KCS-E-STORE-CORRUPT-001 を記録し、
     影響を受ける commit hash の bounded 一覧と
     `external_pointers_may_be_affected=true` を表示する。Evidence Pointer は self-contained で
     registry がないため、存在しない pointer 一覧を推測・捏造しない
3. exit code: 破損 0 件 または 全件復元 = 0 / missing 残あり = 3
```

purge との整合: validated tombstone または fsck-only erase receipt が説明する missing raw とその derived
(chunk・**当該 (raw_hash, tool_profile_hash) 配下の manifest object**) は正常な dead terminal として数え、
corruption にしない。**tree 欠落**は `.kcs/gc/shallowed/<commit64>` receipt が説明する場合のみ正常
(shallow — [05-runtime.md §2.2](05-runtime.md))、receipt なき欠落は corruption。receipt-covered bytes は working copy から
自動復元しない。receipt は public pointer API と re-ingest barrier には使わない。purge journal が active
なら incomplete exit 3。marker 無し missing は ordinary store corruption、malformed / identity-conflicting
receipt も corruption とする。verified raw と stale receipt が共存する場合は raw を正として locked repair
完了時に receipt を除去する。

erase receipt の validation は strict schema/leaf identity に加え、`purged_in_commit` が bounded verified
CAS で ref-reachable な `commit_type=purged` commit を指すこと、`erased_at` が canonical UTC でその
commit の `created_at` と一致し、invocation の fixed now より未来でないことを必須とする。

MVP では手動実行のみとする。自動定期検証 (スケジューラ連携) は Phase 4+ の論点。

## 7.5.2 バックアップ運用

正式なバックアップ手段は次の 2 つとし、専用コマンドは MVP では追加しない。

```text
1. .kcs ディレクトリごとのコピー (MVP の推奨手段)
   - コピー中に kcs が書き込まないこと (.kcs/.lock 未取得状態) を確認してから行う。
     **注意: この確認は check-then-act であり、確認とコピーの間の書き込みまでは防げない** —
     コピー中に kcs コマンドを実行しないことがユーザー前提。厳密な原子性が必要なら
     filesystem スナップショット (APFS/btrfs 等) 上でコピーする。復元後は
     `kcs repair --verify-objects` (§7.5.1) を必ず実行して整合を確認する
   - sqlite.db は repair --rebuild-db で再構築可能。ただし**最低保全集合は objects/ と refs/ では
     なく、[03-data-model.md §4.1](03-data-model.md) の truth 区分の全行** (scope.json / config /
     tool-lock / tombstones + erase receipts / chunks.jsonl / access.jsonl を含む) — これらは
     いずれも喪失時復旧不能である
   - **デバイスグローバルの cost-ledger.sqlite は `.kcs` コピーに含まれない** — 別途
     `sqlite3 cost-ledger.sqlite ".backup <dest>"` (WAL-safe) でバックアップし、復元後は
     §5.8 の回復 (reconcile) が完了するまで新規 Batch 投入を行わない ([04-pipeline.md §5.4](04-pipeline.md))

2. kcs export <scope> --to <bundle.kcsz>
   - .kcsz は公開用と同一の bundle 形式で、バックアップにも使える
   - export の実装は Phase 4+ ([09-mvp-scope.md](09-mvp-scope.md))。MVP のバックアップは
     lock 未取得確認 + ディレクトリコピー (手段 1) のみを提供する
   - 復元は kcs import (同じく Phase 4+)
```

復元後は `kcs repair --verify-objects` で整合性を確認する。外部ドライブ・クラウド
ストレージの placeholder file 上の `.kcs` は破損リスクが高いため、§4 の境界方針の確定
までは推奨しない。

## 7.5.3 SQLite schema 変更の規約 (rebuild vs in-place migration)

sqlite.db / scope-registry.sqlite は正本から再構築可能な cache である ([03-data-model.md §4.1](03-data-model.md))。
したがって schema 変更のデフォルト経路は **migration を書かず再構築する** こと
(sqlite.db は `kcs repair --rebuild-db`、registry は各 `.kcs` の rescan)。

**`cost-ledger.sqlite` はこのデフォルトの対象外** — 再構築不可の運用台帳 (課金記録 + in-flight Batch
intent、[04-pipeline.md §5.4](04-pipeline.md)) であり、schema 変更は常に下記の in-place migration
要件に従う (既存行の保全が必須。旧 JSONL 3 ファイル構成からの移行も同要件で一度だけ行う —
追加列は NULL / DEFAULT で backfill)。

例外として in-place migration を書いてよいのは次の場合のみ:

```text
1. append-only データの保全が必要な場合
   例: chunks 行は time-travel 検索の実体 (04-pipeline.md §4.1) で、rebuild は履歴 commit の
   再展開を伴い高価。旧 `chunks.chunking_config_hash` 列 → `chunk_config_generations` relation
   への分離 (Step 3) は in-place migration とした (実装済みの先例)
2. 起動のたびに全再構築するのが非現実的な大規模 store
```

in-place migration の要件:

```text
- 冪等であること。旧形状の検出は表 / 列の存在検査で行い、再実行しても結果が変わらない
- 全体を単一 savepoint で包み、失敗時は rollback して torn state を残さない
- 移行後に FTS 等の導出インデックスを rebuild する
```

`PRAGMA user_version` による schema version 管理は MVP では**採用しない** (旧形状の判別は存在検査で
足りる)。存在検査で表現できない互換性判断が必要になった時点で導入を再検討する。

---

# 8. commit_type の固定 enum について

現在の正本では、`commit_type` を `manual / auto / imported / migrated / repaired / merged / purged` の7種に閉じる方針である。

この方針を採用する場合でも、実装では以下を守る。

```text
type に混ぜない情報は actor / source / trigger / metadata に逃がす
metadata には schema_version を持たせる
未知 type を読んだ場合の error message を明確にする
新 type が必要に見える場合は、まず既存 type + metadata で表現できないか確認する
```

将来、実運用で固定 enum が強すぎると判明した場合は、既存の互換性を壊さない migration plan を本書および 05-runtime.md に明記する。

---

# 9. local-first と同期構想の分離

MVP は単一端末・local-first を優先する。同期、共有版、Web修正提案、複数ユーザー権限は将来構想であり、MVP の CLI / core 仕様へ混ぜすぎない。

推奨:

```text
MVP文書:
  local object store
  local snapshot
  local search
  local restore
  local purge

将来同期文書:
  共有版
  Web修正提案
  権限
  同期競合
```

---

# 10. Adapter セキュリティ

R23 の Markdownize / Embedding Adapter は KCS 同梱の built-in target のみを実行し、
任意コマンドや任意 URL への差し替えは受理しない。ローカルAPIや外部プロセスを扱う
dispatcher は将来仕様であり、実装時には現行の入力・送信境界に加えて command 境界も
明確にする。

最低限必要な制御:

```text
allow_network
allowed_scope
max_input_bytes
timeout_seconds
redact_logs
store_request_body = false
store_response_body = false
secret redaction
```

将来の外部 Adapter dispatcher には、上記に加えて `command allowlist / confirmation` を
必須とする。これは現行 built-in target に任意コマンド実行能力があることを意味しない。

これらの policy の強制モデル (宣言 + 監査であって sandbox 保証ではないこと) は
[07-adapter-spec.md §7.1](07-adapter-spec.md) を正本とする。

オンライン Adapter は、明示 opt-in なしにファイル内容を送信してはならない。opt-in の
単位 (scope × adapter)・寿命・revoke は [07-adapter-spec.md §3](07-adapter-spec.md) を
正本とする。初回スキャン preview でも、network transmission policy を表示する。

---

# 10.5 Incremental Markdownize (要件)

ファイルが更新された場合、Markdownize (OCR を含む) Adapter には **新 raw だけでなく、旧 raw + 旧 normalized Markdown + 変更ヒント** をセットで渡し、変更が軽微なら Adapter が部分更新を返す方式を採用する。MVP〜v1 のプロダクト要件として確定する。

目的:

```text
1. LLM API コスト抑制 (04-pipeline.md §5.4 の cost guardrail と整合)
2. 全文再生成による表記ゆれ・見出し変動を抑制
   → unit_key / chunk / Evidence Pointer の安定性向上
3. 変わっていない unit の再 Markdownize 呼び出しを完全排除
   (embedding は text_hash 一致による再利用で抑制する, 04-pipeline.md §5.5)
```

実装責務の分担:

```text
KCS:
  - 変更検出 (raw_hash 変化 + unit_mapping による変化率算出, 04-pipeline.md §2.2)
  - 発動条件の判定 (capability / 閾値 / 連続回数)
  - Adapter への入力組み立て (旧 raw, 旧 Markdown, hints)
  - Adapter からの fallback_to_full 受信時の full 再投入
  - normalization_run への mode/parent_run_id/changed_unit_keys の記録

Markdownize Adapter:
  - capabilities = ["incremental_update"] の宣言
  - incremental 入力を受け取って updated_units / unchanged_unit_keys を返す
  - 軽微でないと判断したら fallback_to_full=true を返す
```

Adapter が `incremental_update` capability を宣言しない場合は、KCS は常に full モードで Adapter を呼ぶ。これにより既存 Adapter との後方互換が保たれる。

詳細仕様: [04-pipeline.md §2, §3](04-pipeline.md), [07-adapter-spec.md §8](07-adapter-spec.md)

設定上書き例 (`.kcs/config.toml`):

```toml
[markdownize.incremental]
enabled = true
threshold = 0.30
max_consecutive = 5
```

---

# 11. 実装前に埋めるべき仕様

> Phase 1〜3 ([01-positioning.md §6](01-positioning.md)) を着手する前に、少なくとも以下を具体化する。Phase 4-5 の仕様は MVP リリース後に着手する。

以下の仕様は既に正本 spec に統合済みである。着手前に該当節が凍結ゲート ([09-mvp-scope.md §6.2](09-mvp-scope.md)) を通過していることを確認する。

```text
object store / snapshot DAG      → 03-data-model.md
Evidence Pointer schema          → 08-evidence-pointer-spec.md
永続ストア一覧 (SQLite/file 境界) → 03-data-model.md §4.1
SQLite schema (index / registry) → 04-pipeline.md §4 / 10-operations.md §3
object / manifest schema         → 03-data-model.md §8
ingest / markdownize / snapshot  → 04-pipeline.md
restore / resume-retry           → 05-runtime.md / 04-pipeline.md §5.7
検索評価規約 / 評価指標定義        → 09-mvp-scope.md §4.3
done criteria                    → 09-mvp-scope.md
```

未統合で実装前に具体化が必要なもの:

```text
.kcsignore spec                  → 03-data-model.md §11.1 に追記済み (2026-07-03)
Normalized Markdown 形式 spec     → 07-adapter-spec.md §5.2.1 に最小凍結済み (2026-07-18)
```

特に object hash 算出、Evidence Pointer、Normalized Markdown の決定性、purge 後の到達不能性は、実装後に変えると互換性コストが高い。

---

# 12. 横断規約 (cross-cutting contracts)

複数のドキュメントで部分的に触れられている規約事項を一元化する。各個別ドキュメントの記述はこの章を **正本** として参照する。

## 12.1 エラーコード namespace

すべての error は `KCS-E-<DOMAIN>-<SUBDOMAIN>-<NNN>` 形式の **error_code** を持つ。`error_kind` などのフリーテキストはユーザー向け表示専用で、機械判定には `error_code` を使う。

```text
DOMAIN:
  BATCH    バッチ処理 (markdownize / embedding / etc.)
  INDEX    インデックス更新
  SEARCH   検索 (FTS / vector / hybrid)
  COMMIT   commit / snapshot / restore
  GC       garbage collection
  PURGE    purge 操作
  EVIDENCE Evidence Pointer 解決 / verify / retarget
  SYNC     同期・共有 (v2 予約。MVP では発行しない)
  ADAPTER  Adapter ロード・実行
  EMBED    embedding profile / modality 検証 (KCS-E-EMBED-MODALITY-001 — [03-data-model.md §7](03-data-model.md))
  CONFIG   config / schema / 設定
  STORE    object store / fs IO
  AUTH     認証・認可
```

例: `KCS-E-BATCH-NET-001`, `KCS-E-SEARCH-VEC-INCOMPAT-001`, `KCS-E-SEARCH-VEC-UNAVAIL-001`, `KCS-E-COMMIT-SHALLOW-001`, `KCS-E-PURGE-NOT-FOUND-001`, `KCS-E-STORE-PATH-001`, `KCS-E-STORE-CORRUPT-001`, `KCS-E-SEARCH-SCOPE-ALL-FAILED-001`, `KCS-E-SEARCH-CURSOR-001`, `KCS-E-INDEX-REBUILDING-001`, `KCS-E-EVIDENCE-SCOPE-UNREACHABLE-001`, `KCS-E-EVIDENCE-RETARGET-AMBIG-001`, `KCS-E-ADAPTER-CONTRACT-001`。各 code の定義箇所は該当 spec (06-cli-spec.md §8 に一覧と参照先) を参照。

各 spec が定義した個別エラー (04-pipeline.md / 05-runtime.md / 06-cli-spec.md 等) はこの namespace に従う。新規 code 追加は本書および該当 spec の更新を伴う (破壊的変更扱い)。

## 12.2 CLI exit code

KCS のすべての CLI コマンドは以下の exit code を返す。

```text
0   成功 / 全 up_to_date
1   汎用 failure (詳細不明)
2   invalid usage / config 不正 / schema validation 失敗
3   retryable な失敗が残っている (部分成功・全体 retryable を含む — [06-cli-spec.md §7](06-cli-spec.md))
4   全失敗 permanent
5   auth_error (user action 必要)
6   budget_exceeded により paused
7   user 中断 (SIGINT/SIGTERM)
8   incompatible profile / format version
9   confirm 拒否 (purge 等の確認プロンプトで no)
```

スクリプト連携はこれらを参照する。コマンド固有の補足は各 sub-command が docstring に明記する。

dead pointer (tombstoned / not_found) は `4`、**scope_unreachable のみは retryable の `3`** (再接続・registry 再登録で回復可能 — [08-evidence-pointer-spec.md §4.3](08-evidence-pointer-spec.md))、tool_profile 不一致による chunk 解決不能は `8` に割り当てる (詳細: [06-cli-spec.md §7](06-cli-spec.md))。

## 12.3 設定ファイル schema validation

すべての設定ファイルは JSON Schema (TOML は JSON 等価表現に変換して同 schema で validate) を持ち、CLI 起動時に schema-driven validation を行う。schema は KCS 本体に同梱する。

```text
~/.config/kcs/tools.toml          → schemas/tools.schema.json
~/.config/kcs/config.toml         → schemas/user-config.schema.json
.kcs/config.toml                  → schemas/folder-config.schema.json
.kcs/scope.json                   → schemas/scope.schema.json
.kcs/tool-lock.json               → schemas/tool-lock.schema.json
.kcs/manifest.json (簡易管理時)    → schemas/manifest.schema.json
```

validation 失敗は exit code 2 で停止し、`KCS-E-CONFIG-SCHEMA-NNN` を返す。schema は semver で版管理し、breaking change は migration を要求 (§12.5)。

`scope.schema.json` は少なくとも次の key を定義する: `scope_id` (required)・子 `.kcs` リンク ([03-data-model.md §2](03-data-model.md))・`scan_approval` (optional — §1 の取り込み承認記録。required field は §1 の記録一覧と一致)・`approvals[]` (optional — adapter 単位の network opt-in。要素の required field = scope_id / tool_id / execution_mode / tool_profile_hash / approved_at / approval_method — [07-adapter-spec.md §3](07-adapter-spec.md))。**未知 key は schema error** (fail-closed)。両 key を欠く旧 scope.json は valid であり、欠落 = 当該承認なしとして扱う (migration 不要の後方互換)。

`user-config.schema.json` は device cap (`[budget]`、[04-pipeline.md §5.4](04-pipeline.md)) を含む。

## 12.4 時刻・タイムゾーン

すべての永続データ (commit timestamps, normalization_runs, access_events, snapshot lineage 等) の時刻は **UTC ISO8601 拡張形式 + suffix `Z`** に固定する。**例外 = SQLite ストアの内部時刻列** (cost-ledger.sqlite の recorded_at / job_create_started_at / completed_at / created_at — [04-pipeline.md §5.4](04-pipeline.md)): SQL での比較・期限演算のため **UTC epoch ミリ秒の INTEGER** を正とする (JSON / JSONL / UI 境界へ出す際に ISO8601+Z へ変換する)。

```text
正:   2026-04-25T12:00:00Z
正:   2026-04-25T12:00:00.123456Z
誤:   2026-04-25T12:00:00      (TZ 欠落)
誤:   2026-04-25T12:00:00+09:00 (local 表記)
```

ユーザー向け UI 表示時のみ local TZ に変換する。snapshot lineage の順序判定は UTC タイムスタンプを使い、Lamport/HLC 系の論理時計は v0 では採用しない (採用判断は v2 の同期設計で別途。経緯: 旧 research/synchronization.md — git 履歴)。

## 12.5 semver / 互換性 promise

KCS が公開する識別子は次のいずれかの semver 軸を持つ。

```text
kcs_format_version       .kcs ディレクトリ全体のフォーマットバージョン (03-data-model.md §2)
tool_lock_spec_version   tool-lock.json の schema バージョン (07-adapter-spec.md)
profile_hash_spec        tool_profile_hash の計算規約バージョン (03-data-model.md)
schema_version_<name>    各 config schema の semver
adapter_io_spec_version  Adapter 入出力 schema (incremental Markdownize 含む) の spec_version
                         (07-adapter-spec.md §8 / 04-pipeline.md §3.1)
```

ルール:

```text
MAJOR bump:
  - 既存データの非互換破壊。migration 必須。
  - 該当 spec と CHANGELOG への明示記載が必要。
  - 既存ユーザーは旧バージョンの read-only モード または migrate のいずれかを選択。

MINOR bump:
  - 新フィールド追加 (default 値で旧データを補える場合)
  - 既存値の意味は不変。

PATCH bump:
  - typo / コメント修正レベル。意味変更なし。
```

**tree schema v2/v3 (2026-07-18 確定)**: tree entry へ `normalize.manifest_hash`、tree object へ
`chunking_config_hash` (v2) と `chunk_set_hash` (v3 — 公開 chunk 集合の digest) を追加した
([03-data-model.md §8](03-data-model.md)) — hash/identity 規約の変更だが、
[08-evidence-pointer-spec.md §8](08-evidence-pointer-spec.md) の 2026-07 改訂と同じく
**実装・store 公開前の schema 確定であり MAJOR bump ではない**。既存 dev store の v1/v2 tree
(該当フィールド欠落) は legacy として読取可 (欠落 = 旧 semantics)。Step 1-2 実装の tree hashing は
v2/v3 対応の rework が必要 ([09-mvp-scope.md](09-mvp-scope.md))。

**Adapter 入出力の `spec_version` bump 規約**: `tool-lock.json` の `spec_version` および Adapter 入出力 schema ([04-pipeline.md §3.1](04-pipeline.md)) の `spec_version` は単調増加の整数とする。bump するのは、フィールドの削除・必須化・意味変更など**旧 Adapter が誤動作しうる変更のみ** (MAJOR 相当。該当 spec と CHANGELOG への明示記載必須)。optional フィールドの追加では bump せず、代わりに Adapter は未知フィールドを無視しなければならない (MUST ignore unknown fields)。不一致時の挙動は分業する: Adapter 側は `invalid_input` として失敗する ([07-adapter-spec.md §8.1](07-adapter-spec.md))。**full fallback が有効なのは incremental capability だけが非互換な場合に限る** — spec_version 自体の非互換は full で呼び直しても同じ拒否を再生するため、当該 online Adapter のタスクを failed permanent (Adapter 更新が必要) とし、同梱 deterministic Adapter のベースラインは影響なく継続する ([07-adapter-spec.md §8.1](07-adapter-spec.md) と同旨)。index 全体の停止を引き起こさないという保証は、このベースライン継続が担う。

`commit_type` の値域 ([05-runtime.md §2](05-runtime.md)) のみは「永久に変更しない契約」として MAJOR bump も発動しない約束をしている。これは一般 semver 規約より強い保証である。

## 12.6 観測 (observability)

`logs/access.jsonl` 以外に、以下の構造化ログを `~/.local/share/kcs/logs/` に出す。

```text
events.jsonl       重要イベント (commit, gc, purge, schema migration)
metrics.jsonl      数値メトリクス (任意の interval、デフォルト1時間に1行)
errors.jsonl       error_code 付きの全エラー
```

各行 JSON で次のフィールドを必須とする:

```text
ts        UTC ISO8601 (§12.4)
level     debug | info | warn | error
code      error_code (KCS-E-) / event_code (KCS-EV-) / metric_code (KCS-M- — [05-runtime.md §7](05-runtime.md))
component batch | search | commit | gc | ...
message   人間可読な短文
context   任意の JSON object (tool_profile_hash, commit_hash, raw_hash, scope_id 等 — file_id は廃止済み識別子のため使わない)
```

ログのローテーションは日次、保持は 30 日 (config 上書き可)。`redact_logs` の
デフォルトは **true** であり、`[adapter.policy]` に限らず observability ログ
(events / metrics / errors) と access.jsonl の全域に適用される。true の場合、
`context` の `query`, `path`, `prompt` 等の機微フィールドをマスクする。
false への変更は明示設定のみで行える。

## 12.7 命名リネーム表 (旧 → 新)

過去メモから現行設計への移行で発生した renaming を一覧化する。実装者はこの表を grep して旧称残置を排除する。
(出所列の research/*.md は 2026-07-18 に docs から撤去済み — git 履歴で参照可)

```text
旧称                            | 現行                                | 出所
-------------------------------- | ----------------------------------- | ----
folder.json                      | scope.json                          | research/kcs.md §6
folder_id                        | scope_id                            | 10-operations.md §3
normalized_hash                  | (廃止)                               | research/hash.md §9
canonical_text_hash              | (廃止)                               | research/diff.md §8
canonical_hash                   | (廃止)                               | research/diff.md §17
markdown_hash                    | (廃止)                               | research/diff.md §3
Normalized-Hash: <Markdown header> | Tool-Profile-Hash: <Markdown header> | research/read_only.md §2
.kcs/normalized/<path>.md        | .kcs/objects/normalized_units/ab/cd/<raw64>.<tool64>.g<gen>/ (正本) | research/kcs.md §11
unit_id                          | unit_key / unit_ref                 | 03-data-model.md §2.1
last_indexed_git_commit          | (廃止: Git 連携は持たない)             | research/kcs.md §10
output_hash (in normalization_runs) | (廃止)                            | research/hash.md §3
cost-ledger.jsonl (+ -reservations / -reclaimed / .lock) | cost-ledger.sqlite (cost_ledger / batch_requests の 2 表) | 04-pipeline.md §5.4
```

## 12.8 推奨 Reading Path

Reading Path の正本は [README.md §1](README.md)。docs/ 直下のファイル名の数字プレフィックスがそのまま読む順番であり、本書で別の順序を定義しない。
