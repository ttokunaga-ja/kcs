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

承認記録には、少なくとも次を残す。

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

- `kcs status` は AI 強化の進捗 (done / pending / paused 件数) と paused の理由 (budget / auth / rate limit) を表示する
- 検索レスポンスは index が部分的なとき `index_status` を返す ([05-runtime.md §1.7](05-runtime.md))

## 1.1 Secrets デフォルト除外 (built-in ignore template)

KCS は secrets 系ファイルの取り込み・オンライン送信事故を防ぐため、built-in の除外テンプレート
を同梱する。パターンは 2 段階に分ける。

**Tier A (デフォルト除外)**: 拡張子・ファイル名から secrets とほぼ確実に判定できるもの。
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
  送信 task は pending のまま保留し、kcs status に表示する。
  対話確認 (kcs index の実行時プロンプト) で一括承認できる。

非一致の新規ファイル:
  従来どおり自動取り込み (デフォルト全管理を維持)。
```

---

# 2. 容量より利便性を優先する

KCS は、容量効率よりも知識を失わないこと、あとから検索・履歴探索・復元できることを優先する。

したがって、全ファイル管理をデフォルトとする方針は維持する。動画・巨大PDF・画像・Officeファイルも、ユーザーが明示的に ignore しない限り管理対象に含める。唯一の例外は secrets 系の built-in デフォルト除外 (§1.1) であり、これは容量ではなく不可逆な漏洩リスクを理由とする。

ただし、プロダクトはこの事実を隠してはならない。

```text
KCS は検索インデックスだけでなく、原本ファイルを content-addressed archive に保存します。
各 `.kcs` が管理するのはその `.kcs` が置かれたフォルダ直下のファイルのみです。
サブフォルダのファイルは (そこに `.kcs` があるか否かに関わらず) 親 `.kcs` は取り込みません。
対象ファイルを含むサブフォルダには子 `.kcs` が作られ、独立したスコープとして管理されます。
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

保存する情報:

```text
scope_id
root_path
kcs_path
participates_in_global_search
approved_at
last_seen_at
effective_ignore_hash
permission_status
```

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

実装前に方針を明示すべき境界:

```text
symlink
hardlink
外部ドライブ
クラウドストレージの placeholder file
権限のないフォルダ
hidden directory
system directory
```

---

# 5. 物理レイアウト統一

内部正本は `.kcs/objects/normalized_units/` (unit object 群 + manifest) に統一する
([03-data-model.md §2.1](03-data-model.md))。全文 Markdown は unit を決定論的に結合した
view (再生成可能な cache) であり正本ではない。

過去メモにある `.kcs/normalized/` は、bootstrap 時の簡略表記または仮想表示パスとして扱う。実装・契約ドキュメントでは、hash ベースの object store を正とする。

```text
truth:
  .kcs/objects/normalized_units/ab/cd/<raw_hash>.<tool_profile_hash>.g<gen>/

materialized view (cache):
  .kcs/objects/normalized/ab/cd/<raw_hash>.<tool_profile_hash>.g<gen>.md

virtual view:
  report.pdf.md
```

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

`purge` は、KCS 管理下の object store、snapshot DAG、index、pack、cache、tombstone、
および KCS 自身のログ (`.kcs/logs/access.jsonl`、`~/.local/share/kcs/logs/` の
events / errors / metrics) から対象ファイル由来の情報を削除する操作である。
ログについては、対象の raw_hash / path / query を含む行の削除またはフィールドマスクを行う。
`redact_logs` デフォルト true (§12.6) の運用では query / path / prompt は元から記録されないため、
実務上のスクラブ対象は主に raw_hash 参照行に限られ軽量である。
purge 自体の実行記録 (`commit_type=purged`、tombstone) は監査可能性のため残す ([05-runtime.md §3.2](05-runtime.md))。

ただし、OS backup、Time Machine、クラウド同期の過去版、外部 export、ユーザーが手動コピーしたファイル、KCS 外のログまでは KCS 単体では保証しない。

UI 文言は、過剰な保証を避ける。

```text
推奨:
  KCS 管理下の履歴から完全削除

避ける:
  世界中のすべてのコピーを完全削除
```

`purge` は必ず次を要求する。

```text
影響範囲 preview
理由入力
明示確認
対象 raw / normalized / chunk / embedding / evidence / index の削除
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

- `objects/` 配下の全 CAS object (raw / chunk / tree / commit) の content hash を再計算し、
  保存パス・参照 hash と照合する ([03-data-model.md §8.1](03-data-model.md))
- normalized は content hash を持たない ([03-data-model.md §5](03-data-model.md)) ため hash 検証対象外とし、
  参照整合 (対応する `(raw_hash, tool_profile_hash)` object の実在) のみ確認する
- SQLite index は検証対象外 (破損時は `--rebuild-db` で再構築可能なため)

破損検出時の挙動:

```text
1. working tree に同一ファイルが現存し、再計算 raw_hash が一致
   → re-ingest で object を復元し、commit_type=repaired の commit を記録
     (復元した raw object は GC 対象外、05-runtime.md §2.6)
2. 復元手段なし
   → missing として errors.jsonl に KCS-E-STORE-CORRUPT-001 を記録し、
     影響を受ける commit / Evidence Pointer の一覧を表示
3. exit code: 破損 0 件 または 全件復元 = 0 / missing 残あり = 3
```

MVP では手動実行のみとする。自動定期検証 (スケジューラ連携) は Phase 4+ の論点。

## 7.5.2 バックアップ運用

正式なバックアップ手段は次の 2 つとし、専用コマンドは MVP では追加しない。

```text
1. .kcs ディレクトリごとのコピー (MVP の推奨手段)
   - コピー中に kcs が書き込まないこと (.kcs/.lock 未取得状態) を確認してから行う
   - sqlite.db は repair --rebuild-db で再構築可能なため、最悪 objects/ と refs/ が
     保全されていれば復旧できる

2. kcs export <scope> --to <bundle.kcsz>
   - .kcsz は公開用と同一の bundle 形式で、バックアップにも使える
   - export の実装は Phase 4+ ([09-mvp-scope.md](09-mvp-scope.md))。MVP のバックアップは
     lock 未取得確認 + ディレクトリコピー (手段 1) のみを提供する
   - 復元は kcs import (同じく Phase 4+)
```

復元後は `kcs repair --verify-objects` で整合性を確認する。外部ドライブ・クラウド
ストレージの placeholder file 上の `.kcs` は破損リスクが高いため、§4 の境界方針の確定
までは推奨しない。

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

Adapter は任意コマンド、任意URL、ローカルAPI、オンラインAPIを扱えるため、実行境界を明確にする。

最低限必要な制御:

```text
allow_network
allowed_scope
max_input_bytes
timeout_seconds
redact_logs
store_request_body = false
store_response_body = false
command allowlist / confirmation
secret redaction
```

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
include_neighbors = 1
```

---

# 11. 実装前に埋めるべき仕様

> Phase 1〜3 ([01-positioning.md §6](01-positioning.md)) を着手する前に、少なくとも以下を具体化する。Phase 4-5 の仕様は MVP リリース後に着手する。

以下の仕様は既に正本 spec に統合済みである。着手前に該当節が凍結ゲート ([09-mvp-scope.md §6.2](09-mvp-scope.md)) を通過していることを確認する。

```text
object store / snapshot DAG      → 03-data-model.md
Evidence Pointer schema          → 08-evidence-pointer-spec.md
SQLite schema                    → 03-data-model.md §8
ingest / markdownize / snapshot  → 04-pipeline.md
restore / resume-retry           → 05-runtime.md / 04-pipeline.md §5.7
検索評価規約 / 評価指標定義        → 09-mvp-scope.md §4.3
done criteria                    → 09-mvp-scope.md
```

未統合で実装前に具体化が必要なもの:

```text
.kcsignore spec                  → 03-data-model.md へ追記予定
Normalized Markdown 形式 spec     → 07-adapter-spec.md へ追記予定
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
3   一部失敗 (retryable 残あり)
4   全失敗 permanent
5   auth_error (user action 必要)
6   budget_exceeded により paused
7   user 中断 (SIGINT/SIGTERM)
8   incompatible profile / format version
9   confirm 拒否 (purge 等の確認プロンプトで no)
```

スクリプト連携はこれらを参照する。コマンド固有の補足は各 sub-command が docstring に明記する。

dead pointer (tombstoned / not_found / scope_unreachable) は `4`、tool_profile 不一致による chunk 解決不能は `8` に割り当てる (詳細: [06-cli-spec.md §7](06-cli-spec.md))。

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

`user-config.schema.json` は device cap (`[budget]`、[04-pipeline.md §5.4](04-pipeline.md)) を含む。

## 12.4 時刻・タイムゾーン

すべての永続データ (commit timestamps, normalization_runs, access_events, snapshot lineage 等) の時刻は **UTC ISO8601 拡張形式 + suffix `Z`** に固定する。

```text
正:   2026-04-25T12:00:00Z
正:   2026-04-25T12:00:00.123456Z
誤:   2026-04-25T12:00:00      (TZ 欠落)
誤:   2026-04-25T12:00:00+09:00 (local 表記)
```

ユーザー向け UI 表示時のみ local TZ に変換する。snapshot lineage の順序判定は UTC タイムスタンプを使い、Lamport/HLC 系の論理時計は v0 では採用しない (採用判断は v2 の同期設計で別途。経緯: research/synchronization.md — 正本ではない)。

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

**Adapter 入出力の `spec_version` bump 規約**: `tool-lock.json` の `spec_version` および Adapter 入出力 schema ([04-pipeline.md §3.1](04-pipeline.md)) の `spec_version` は単調増加の整数とする。bump するのは、フィールドの削除・必須化・意味変更など**旧 Adapter が誤動作しうる変更のみ** (MAJOR 相当。該当 spec と CHANGELOG への明示記載必須)。optional フィールドの追加では bump せず、代わりに Adapter は未知フィールドを無視しなければならない (MUST ignore unknown fields)。不一致時の挙動は分業する: Adapter 側は `invalid_input` として失敗し ([07-adapter-spec.md §8.1](07-adapter-spec.md))、KCS 側は当該 Adapter を `incremental_update` capability なしとみなして full モードで呼び直す ([07-adapter-spec.md §8.4](07-adapter-spec.md))。この full fallback により、`spec_version` の bump が index の停止を引き起こさないことを保証する。

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
code      error_code または event_code
component batch | search | commit | gc | ...
message   人間可読な短文
context   任意の JSON object (tool_profile_hash, commit_hash, file_id 等)
```

ログのローテーションは日次、保持は 30 日 (config 上書き可)。`redact_logs` の
デフォルトは **true** であり、`[adapter.policy]` に限らず observability ログ
(events / metrics / errors) と access.jsonl の全域に適用される。true の場合、
`context` の `query`, `path`, `prompt` 等の機微フィールドをマスクする。
false への変更は明示設定のみで行える。

## 12.7 命名リネーム表 (旧 → 新)

過去メモから現行設計への移行で発生した renaming を一覧化する。実装者はこの表を grep して旧称残置を排除する。

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
.kcs/normalized/<path>.md        | .kcs/objects/normalized_units/ab/cd/<raw>.<tool>.g<gen>/ (正本) | research/kcs.md §11
unit_id                          | unit_key / unit_ref                 | 03-data-model.md §2.1
last_indexed_git_commit          | (廃止: Git 連携は持たない)             | research/kcs.md §10
output_hash (in normalization_runs) | (廃止)                            | research/hash.md §3
```

## 12.8 推奨 Reading Path

Reading Path の正本は [README.md §1](README.md)。docs/ 直下のファイル名の数字プレフィックスがそのまま読む順番であり、本書で別の順序を定義しない。

