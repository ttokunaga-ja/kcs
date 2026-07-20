# 05 Runtime

統合元: 旧 `research/hybrid.md` (検索モード) + 旧 `research/commit_snapshot.md` (commit_type, GC, purge) + 一部旧 `research/read_only.md` (検索結果での書き込み境界) + 一部旧 `research/productization_notes.md` (運用)。いずれも正本ではなく、2026-07-18 に docs から撤去 (経緯は git 履歴で参照可)。

---

# 1. 検索

## 1.1 モード

```
text   FTS5 (BM25)         常に利用可能
vector sqlite-vec          embedding 互換性あり時に利用可能
hybrid RRF(text, vector)   両方利用可能時のみ。auto モードがデフォルト
```

`.kcs/config.toml`:

```toml
[search]
default_mode = "auto"            # "auto" | "text" | "vector" | "hybrid"
fail_behavior = "fallback"       # "fallback" | "error" | "warn"
```

`auto` の解決順:

```
--offline 指定 → text fallback (fallback_reason="offline" — 送信自体を行わない短絡。下記)
embedding profile_hash 不一致 → text fallback (KCS-E-SEARCH-VEC-INCOMPAT-001)
embedding 承認なし (下記 consent gate) → text fallback (KCS-E-SEARCH-VEC-UNAUTHORIZED-001)
同一 query が in-flight ([04-pipeline.md §5.4](04-pipeline.md)) → text fallback (fallback_reason="embedding_in_flight")
query embedding 応答が受入検査 ([07-adapter-spec.md §5.3](07-adapter-spec.md)) で contract violation → text fallback (fallback_reason="embedding_contract_violation")
上記のいずれにも該当せず vector のみ利用不能 (index 未構築等の技術的理由) → text
両方利用可能 → hybrid
両方不可 → error (KCS-E-SEARCH-VEC-UNAVAIL-001)
```

解決順の列挙は**判定順序**でもある — 複数条件が同時に成立する場合は先に列挙された行の
`fallback_reason` / error code を採用する (profile 不一致 (INCOMPAT) が承認なし (UNAUTHORIZED) に先行)。
`fail_behavior = "warn"` の挙動は **fallback と同じ結果** (text fallback + `fallback_reason`) に加えて
構造化 warning を stderr / `--json` の `warnings[]` へ出す — exit code も fallback と同じ (error に
しない)。

**query embedding の consent gate**: vector | hybrid の page 1 は query embedding (07 §5.3 の
`input_type: "query"` — sync 呼出) を要し、これは新規送信として [07-adapter-spec.md §3](07-adapter-spec.md)
の opt-in gate の対象である (payload は query 文字列のみで folder 内容を含まない)。**送信可否 =
参加 scope の 1 つ以上に当該 embedding Adapter の active な `approvals[]` 行があり、かつ当該 scope に
明示 revoke (`adapter.policy.allow_network = false` — [07-adapter-spec.md §3](07-adapter-spec.md)) が
ないこと** (`--online` が開くのは未設定の既定閉鎖のみ — 明示 revoke は上書きしない)。承認ゼロ
(かつ `--online` 一時 opt-in なし) の場合、auto / `--hybrid` は text fallback
(`fallback_reason="embedding_not_authorized"`)、`--vector` 明示は KCS-E-SEARCH-VEC-UNAUTHORIZED-001
で error。**ユーザー意思由来の text fallback は `fail_behavior` の対象外である** — `fail_behavior` は技術的
失敗 (INCOMPAT / UNAVAIL 等) への応答方針であり、`embedding_not_authorized` (承認なし) と `offline`
(`--offline` 指定) には適用しない (設定値に関わらず auto / `--hybrid` は常に text fallback、`--vector`
のみ error — §1.2 / [06-cli-spec.md §3](06-cli-spec.md) の `--hybrid` 行の注記も同旨)。一方
**`embedding_in_flight` (同一 query の並行実行 — [04-pipeline.md §5.4](04-pipeline.md)) と
`embedding_contract_violation` (query embedding 応答の受入検査違反 — [07-adapter-spec.md §5.3](07-adapter-spec.md))
は技術的な過渡失敗であり `fail_behavior` の対象**: auto は text fallback、`--hybrid` は fail_behavior に従い、
`--vector` 明示は KCS-E-SEARCH-VEC-UNAVAIL-001 で error。`--online` / `--offline` は他コマンドと
同義の当該実行限りの上書き (07 §3)。**`--offline` 指定時は承認の有無に関わらず query embedding を送信
しない** — auto / `--hybrid` は text fallback (`fallback_reason="offline"`)、`--vector` 明示は
KCS-E-SEARCH-VEC-UNAVAIL-001 で error。課金は
`scope_id='device'` の sync request として縮退 2 相に記帳する ([04-pipeline.md §5.4](04-pipeline.md)
— folder cap 対象外・device cap / per_adapter は通常合算)。

## 1.2 CLI

```bash
kcs search "..."             # auto
kcs search "..." --text      # text only
kcs search "..." --vector    # vector only。失敗時は error
kcs search "..." --hybrid    # hybrid 強制。vector 失敗時は fail_behavior に従う (承認なし・--offline は対象外 — 常に text fallback。embedding_in_flight は対象 — §1.1)
kcs search "..." --no-vector # 明示無効
kcs search "..." [--online|--offline]  # query embedding の一時 opt-in / 当該実行の新規送信禁止 (§1.1 consent gate)
```

## 1.3 RRF (Reciprocal Rank Fusion)

候補取得: text / vector 各バックエンドから検索対象集合 (§1.6) 内の上位 `candidate_depth` 件 (デフォルト
200) を **unique semantic chunk (`scope_id,chunk_hash`) 単位**で取得し、和集合を候補プールとする。
default / `--at` / `--include-deleted` の結果上限は候補プール件数。`--all-history` / `--since` は
MMR/dedup 後に historical aliases を展開するため、最終 hit 数は retained semantic chunks の distinct
`(chunk_hash,path)` binding 数 (history-walk aggregate cap 内) まで増えうる。

```text
RRF_score(c) = w_text / (k + rank_text(c)) + w_vector / (k + rank_vector(c))
default: k = 60, w_text = 1.0, w_vector = 1.0
```

- `rank_*` は各バックエンド内の 1 始まり順位。バックエンド内の同点は chunk_id 昇順で順位を確定する
- **短語 fallback**: query の全 token が 3 文字未満で trigram tokenizer の MATCH が成立しない場合
  (例: 1〜2 文字の日本語 query — MATCH は 0 件になる)、text バックエンドは `chunks.text` への
  **bounded LIKE スキャン** (上限 = `candidate_depth`、instr ベースの部分一致) へ fallback する。
  3 文字以上の token が 1 つでもあれば FTS MATCH を使う — ただし **MATCH 式に渡すのは 3 文字以上の
  token のみ**とし、**3 文字未満の token は同一 bounded query 内の `instr` 条件として LIMIT 前に
  AND 適用する** (trigram は 3 文字未満の phrase を黙って落とすため、混在 query の短語を MATCH に
  含めると条件から脱落する)。**短語 instr 条件は text / vector 両バックエンド共通の eligibility
  述語であり、各バックエンドの候補確定 (candidate_depth 充足前) に適用する** — 和集合・RRF に
  短語欠落候補を入れない (全 token の条件を保ったまま候補確定する)。vector 側の適用形: `chunk_vec` を
  `chunks` へ JOIN して instr 述語を適用した母集合に対し distance 順で LIMIT candidate_depth を確定する
  (brute-force KNN — [10-operations.md §6](10-operations.md)。vec0 の `k =` 構文等、述語適用**前**に
  内部 top-k を確定させる形は用いない — 述語後の候補が痩せて candidate_depth を満たせなくなるため)。
  LIKE fallback の順位も決定的に定める:
  最初の一致位置 (instr) 昇順、同点は chunk_id 昇順。SQL は ORDER BY 確定後に LIMIT candidate_depth
  を適用する (LIMIT 先行で候補集合が非決定になる形は禁止)
- **MATCH 式の生成**: user query を FTS5 構文として解釈しない — token 列を各々二重引用符で囲んだ
  phrase / term の並びとして MATCH 式を機械生成する (token 内の `"` は `""` へ escape。`C++` 等の
  記号語が fts5 syntax error にならない)。FTS5 演算子 (AND / OR / NEAR / `*` 等) の直接指定は
  MVP では提供しない。**tokenization は決定的に固定する**: NFC 正規化後の query を Unicode 空白で
  分割した各非空片が token (長さの単位 = Unicode scalar 数。記号のみの token も phrase として投入可)。
  token が 0 個の query は KCS-E-CONFIG-USAGE-001 (exit 2)
- 片方のバックエンドにしか現れない候補は、現れない側の項を 0 とする
- `RRF_score` の同点は chunk_id 昇順
- text-only / vector-only モードでは fusion せず当該バックエンドの順位をそのまま使う
- 実装規則: `candidate_depth` の上限は rank 計算 (window 関数等) の**入力になる内側段 (サブクエリ)** で
  効かせる。外側の LIMIT では全マッチ行が rank 計算の入力に入り、大ヒット数クエリで実行コストが
  数十倍に膨張する (出典: 旧 `research/folder-history-sqlite-design.md` §18 の実測 — VM step 1,074 → 70,374。2026-07-18 撤去、git 履歴で参照可)

```toml
[search.rrf]
k = 60
w_text = 1.0
w_vector = 1.0
candidate_depth = 200
```

## 1.4 多様化 (MMR / Dedup)

素の RRF だけでは同一原文の隣接 chunk が上位を独占しやすいので、後処理で多様化する。

```toml
[search.diversify]
enabled = true
strategy = "mmr"            # "mmr" | "group_by_raw_hash" | "off"
mmr_lambda = 0.7            # 1.0=relevance only, 0.0=diversity only
max_per_raw_hash = 3
```

MMR 選択則:

```
score(c) = λ * relevance(c) - (1-λ) * max_{c' ∈ selected} similarity(c, c')
similarity = embedding の vector cosine (これのみ。2026-07-03 確定 — embedding が無い場合は
             MMR 自体を適用しないため、代替 similarity は定義しない)
selected = ∅ の初手は similarity 項を 0 とする (= relevance 最高の候補を既定 tie-break 順で
             選ぶ — 実装間で初手が揺れない)
```

適用範囲と決定性:

- MMR は候補プールの RRF 上位 `mmr_depth` 件 (デフォルト 100、`candidate_depth` 以下) に対して **1 回だけ** 適用し、並べ替え済みの**確定順序**を得る。`mmr_depth` 以降の候補は RRF 順のまま末尾に接続する
- `relevance(c)` = RRF スコアを **MMR 候補プール内で min-max 正規化した値** ([0,1]。全候補が同スコアなら一律 1.0。2026-07-03 確定、step3a §C の決定性論点解消 — 生の RRF スコア (最大 ~1/k) をそのまま使うと mmr_lambda の意味が損なわれるため)。`similarity` は embedding の cosine。embedding が無い場合 (text-only 検索) は MMR を適用せず RRF 順のままとする (ただし `max_per_raw_hash` の dedup は embedding 非依存であり text-only でも適用する)。**hybrid の候補プールに embedding 未付与、または profile 非互換で cosine を計算できない chunk が 1 件でも混在する場合 (部分 enrichment / §1.8 の profile 不一致 text fallback を含む) も MMR は適用しない** — pairwise similarity が全対で計算できないため。dedup のみ適用し RRF 順で返す。MMR score の同点は RRF 順、さらに同点は immutable `(scope_id,chunk_hash)` の UTF-8 byte order
- `max_per_raw_hash` は alias 展開**前**の unique semantic chunk stream に適用する (ページを跨いで
  raw_hash あたり最大 N semantic chunks)。retained chunk の historical path aliases は provenance 行で
  あり、この上限へ再カウントせず全件を返す
- 入力 (chunk 集合・query・設定) が同じなら確定順序は常に同一 (決定論)。これがページング (§1.5) の前提

```toml
[search.diversify]
# (既存キーに追加)
mmr_depth = 100
```

## 1.5 ページング / カーソル

```bash
kcs search "..." --limit 20
kcs search "..." --limit 20 --offset 20         # 同一 snapshot 内
kcs search "..." --limit 20 --cursor <token>    # snapshot 越し安全
```

ページングは「確定順序 (§1.4) の決定論的再計算」で実現する。cursor に MMR の selected 集合や score は持たない。レスポンスに `next_cursor` を含める。本節の定義は単一 scope 内の sub-cursor であり、複数 scope 横断時の cursor 全体構造 (opaque token、`scope_mode` / `query_hash`) は §1.8 で定義する。

scope ごとの sub-cursor は
`{scope_id, snapshot_commit, index_generation, max_rowid, max_association_rowid, chunking_config_hash, consumed}`。
`index_generation` は **rebuild (`kcs repair --rebuild-db`)・purge・embedding enrichment の finalize・
index / batch finalize で `chunk_fts` の内容が変化した場合・tombstone lifecycle の更新
(retire・再 purge — active-tombstone 判定が検索の可視集合を変えるため、purge の回転と対称。
[§3.5](05-runtime.md))・および GC の shallow 化実行
(`--all-history` cursor の walk 対象が変わる) の、いずれでも新規採番する ULID**
(単調カウンタではない — sqlite.db の `index_metadata` 表 ([04-pipeline.md §4.1](04-pipeline.md)) に保持するため
DB 喪失で数が戻っても、ULID なら旧 cursor が偶然一致して誤受理されることがない。FTS 内容変化でも回転する
理由: FTS5 の bm25() は文書頻度・平均長という**大域統計**を使うため、cursor が chunk 集合を rowid 上限で
固定しても、後発行の追加で既存行の順位自体が変わり得る — 誤った続きを返すより旧 cursor を拒否する)。**回転はそれを引き起こした SQLite 書込 (FTS 内容を変える INSERT / UPDATE / DELETE、purge の行削除等) と同一の SQLite Tx で行う** — 別 Tx にすると、間の crash で旧 cursor が変化後の stream に受理される (file 側の tombstone lifecycle 更新に伴う回転だけは同一 Tx にできないため、§3.5 の lifecycle-epoch カウンタ + 補完規則で crash 窓を閉じる)。**replay 時に現在値と不一致なら
`KCS-E-SEARCH-CURSOR-001` で拒否する** (再検索が正) — rebuild は rowid を再採番し、purge は
append-only 前提を破って行を削除し、後発 embedding は hybrid の候補集合・順位を変えるため、
いずれも旧 cursor の `max_rowid` / `consumed` の意味を失わせる。
token 全体には canonical `time_travel` selector を、`--since` ではさらに
page 1 の `since_cutoff` (UTC ISO8601 + `Z`) も保持する:

- `snapshot_commit`: 当該 scope の検索対象 commit (§1.7 snapshot_at)。2 ページ目以降も同じ commit の tree_entries ([04-pipeline.md §4.5](04-pipeline.md)) で絞る
- `max_rowid`: cursor 発行時点の chunks 最大 rowid。`--all-history` / `--include-deleted` では `rowid <= max_rowid` で chunk 集合を固定する (chunks 行は append-only ([04-pipeline.md §4.1](04-pipeline.md)) なので単調増加)
- `max_association_rowid`: cursor 発行時点の `chunk_config_generations` 最大 association rowid。
  現行 config association も `association_rowid <= max_association_rowid` に固定し、page 1 後に追加された
  association が page 2 の候補へ混入することを防ぐ
- `chunking_config_hash`: page 1 で検索対象にした tree の config (デフォルト = **当該 scope の HEAD tree の値** (移行期間の扱いは [04-pipeline.md §4.6](04-pipeline.md))、時点指定 = 対象 tree の値 — §1.6)。replay 時の対象値と不一致なら拒否する
- `consumed`: alias expansion 後の final result stream で当該 scope から既に返した hit 数 (semantic chunk
  数ではない)。replay は grouped final stream を完全再計算し、scope ごとにこの件数だけ先頭 hit を skip
  するため、page boundary が 1 chunk の alias group 内でも重複/欠落しない
- `since_cutoff`: `--since` の page 1 で一度だけ計算した下限。page 2 以降は現在時刻から再計算しない
- `query_hash` (token 全体に 1 つ、§1.8) が不一致の cursor は `KCS-E-SEARCH-CURSOR-001` で拒否する

2 ページ目以降は同一の候補取得 → RRF (§1.3) → MMR (§1.4) を再計算し、consumed 件を skip して続きを返す。**vector / hybrid の replay は page 1 の query vector を再利用する** — query の再 embedding は行わない (provider の非決定性で候補・順位が変わり、consumed の skip が重複・欠落を生む)。page 1 の正規化済み query vector は参加各 scope の `embeddings` 表 (`target_type='query_cache'` — 正本 [04-pipeline.md §4.3](04-pipeline.md)。query 本文は保存しない) に保持し、その digest (= `query_vector_digest`) を **token の独立 field として保持し、かつ §1.8 の query_hash 構成要素にも含める** (query_hash は一方向 hash であり、replay が読み出す行の鍵は token field 側から得る。vector|hybrid のみ — text mode では field 省略)。replay は参加 scope のいずれかから digest 一致行を読み、どの scope にも無ければ `KCS-E-SEARCH-CURSOR-001` (再検索が正)。**読み出した行は vector BLOB の sha256 を `target_id` (= query_vector_digest) と再照合する** — 不一致は corruption として当該行を削除し、同じく `KCS-E-SEARCH-CURSOR-001` (query_cache は objects 非由来で fsck / rebuild の検証が及ばないため、読出し時が唯一の検査点 — [04-pipeline.md §4.3](04-pipeline.md)。ただし `kcs_format_version` が自己の対応上限より新しい scope では削除を行わず CURSOR-001 へ短絡する — 書込ゼロ規範 [10-operations.md §12.5](10-operations.md))。順序安定性の根拠は SQLite WAL のスナップショット分離**ではなく**、「commit 単位で固定された chunk 集合 + 決定論的な順位計算 + `index_generation` による FTS 内容不変の保証」である。CLI 呼び出しを跨いでも成立する。

`--offset` は cursor の糖衣であり、同じ再現規則で確定順序の `offset` 位置から `limit` 件を返す。**vector|hybrid の `--offset` は単一実行内の slice である** (当該実行が取得した query vector に対する確定順序 — CLI 呼び出しを跨ぐ継続は cursor が正。再 embedding の非決定性は cursor の digest 再利用でのみ回避される)。終端判定は **alias 展開後の final result stream の末尾** — それを超えたら `next_cursor: null` (`--all-history` / `--since` で候補プール末尾を終端にすると最後の alias group を取り残す。default 系は候補プール = final stream で同値)。

## 1.6 Snapshot 越し検索 (`--at`)

```
--at <commit>           指定 commit 時点で indexed だった chunks のみ対象
--at <commit> --vector  指定時点の embedding profile が現在と互換ならOK、
                        非互換なら KCS-E-SEARCH-VEC-INCOMPAT-001
                        (--vector 明示時は fail_behavior に依らず error — §1.2 と同じ。
                         text への fallback は auto / --hybrid のみ)
--all-history           全 commit を横断 (削除済み・移動済み含む)
--include-deleted       現在 working tree に存在しないファイルも対象
--since <duration>      `--since 7d` のように期間指定
```

各モードの検索対象 chunk 集合 (実装規範。schema は [04-pipeline.md §4](04-pipeline.md)):

```text
デフォルト          chunks ⨝ tree_entries(HEAD)     on (raw_hash, tool_profile_hash, gen)
--at <commit>       chunks ⨝ tree_entries(<commit>) on (raw_hash, tool_profile_hash, gen)
--include-deleted   デフォルト集合 ∪ page-1 snapshot tree に存在しない各 logical path について、
                    snapshot の first-parent ancestry でその path を含む newest commit の
                    exact (raw_hash, tool_profile_hash, gen) binding
--all-history       page 1 snapshot HEAD から全 parent edge で到達可能な全 commit の tree binding
                    に現れる chunk 行
--since <duration>  --all-history 集合を chunks.created_at >= now - <duration> で絞る
```

共通フィルタ: `chunk_config_generations` に**対象 tree の `chunking_config_hash`** の association がある chunk のみ
(デフォルト = HEAD tree = 現行値。`--at` は対象 tree の値、`--all-history` / `--include-deleted` は各 binding
tree の値で判定する。v1 tree は config 未記録のため現行値で代替し結果に注記 (**現行値の association が無い場合は、対象 commit の ancestor-or-equal な introduction を持つ association (cursor 継続時は `max_association_rowid` 以下も条件) に限定した上で `chunking_config_hash` の byte 順最小を決定的に代用** — 後発 association で代用値が時間変動しない。候補 0 件は注記つき空集合。HEAD 限定再 chunk 後の履歴 instance を `--at` で全脱落させない) — [04-pipeline.md §4.1, §4.6](04-pipeline.md))。

**HEAD 不在 (初回 auto snapshot 前・snapshot finalize 未完) の scope は index 未完了として扱う** — 検索は当該 scope を `KCS-E-INDEX-REBUILDING-001` で excluded_scopes に計上し (単独 scope なら exit 3)、cursor は発行しない。**SQLite に反映済みでも未公開 (commit / ref 未 publish) の行は返さない** (§8.1 の finalize 耐久順序の crash 窓で、未公開 snapshot の内容を検索に見せない)。この扱いは**bare (--at なし) の現在状態検索など HEAD 依存の解決経路に限る** — 明示 commit・Evidence Pointer 指定の読取・検証 (単一 scope の search `--at <commit>` を含む) は HEAD 非依存に解決する ([08-evidence-pointer-spec.md §3.1](08-evidence-pointer-spec.md)、[06-cli-spec.md §7](06-cli-spec.md))。
purge 済み raw_hash の chunk 行は物理削除済みのため自然に除外される。
**実装規範**: publication / association の時点条件は correlated **EXISTS** (ancestry 判定と
`association_rowid <= cursor.max_association_rowid` を副問い合わせ内に含む) で評価する — 同一
(chunk_id, config) の複数 introduction 行を素の JOIN で結合すると同一 chunk が重複 hit し、
candidate / rank / cursor を歪める。候補集合は ranking 前に (scope_id, chunk_id) で一意にする。

tree entry の `normalize` が省略された commit では、その entry に eligible chunk は 0 件。`--at` /
history projection / include-deleted のいずれも later `latest_normalize_ref` を補完せず、SQLite cached row が
あっても CAS tree の省略を上書きしない ([03-data-model.md §8])。

- `--include-deleted` が加えるのは page-1 snapshot に path が存在しないファイルの**最終版**のみ。
  snapshot HEAD の first-parent を newest-first に辿り、その path を初めて含む tree entry の persisted
  normalize ref を使う。manifest / `files[status=deleted]` は acceleration/cache に限り、page 1 後の
  mutable manifest 変更は cursor の集合を変えない。途中版まで遡るのは `--all-history` の役割
- `--include-deleted` で同じ semantic chunk に snapshot-live binding が 1 件以上あれば live が勝ち、
  その chunk の旧 deleted-path alias は返さない (rename aliases は `--all-history`)。live twins の
  `path_at_commit` は UTF-8 byte order 最小を使う。live binding が 0 件なら、同じ chunk に対応する
  distinct final-deleted `(path,binding_commit)` を §1.7 の post-ranking group expansion で全件返す
- `--all-history` / `--since` の「全 commit」は page 1 の `snapshot_commit` から全 parent edge で
  到達可能な commit に限る。orphan / disconnected tag-only commit は `--at` で明示する。visited set で
  全 parent を辿り、side parent にだけ存在して merge 結果から消えた binding も対象にする。
  **walk 中の shallow 化済み commit (tree 破棄済み — §2.2) は skip し、レスポンスに
  `shallow_skipped` 件数を可視化して partial (exit 3) とする** — 黙って欠落させない
- chunk 行が検索対象になるのは auto snapshot (§8.1 — `kcs index` / batch finalize の成功完了時) 作成後。indexing 途中の chunk はどのモードでも返さない。auto snapshot 作成時に新規 chunk 行へ `first_seen_commit` を刻み、**`chunk_publications` へ `(chunk_id, introduction_commit = 当該 commit)` を追記する** (既存 publication のいずれの子孫でもない tree に同一 chunk が現れた場合も、新しい introduction として追記 — [04-pipeline.md §4.1](04-pipeline.md))。新規の config association も同じ commit を `introduction_commit` として刻む。**初回以外の追加 introduction は chunks.jsonl へ publication event 行として同時に append する** ([03-data-model.md §2](03-data-model.md) — rebuild の正本)
- **時点条件 (正式化)**: デフォルト / `--at` の対象は、上記 join に加えて **`chunk_publications` のいずれかの `introduction_commit` が対象 commit の ancestor-or-equal である chunk に限る** (単一の `first_seen_commit` では incomparable な複数導入 — merge の side 枝・独立 import — を表現できないため、判定は publication relation を参照する。relation 自体は SQLite cache であり commit DAG + tree から決定的に再導出できる — [04-pipeline.md §4.1](04-pipeline.md))。**config association にも同条件を適用する** — `chunk_config_generations` の `introduction_commit` が対象 commit の ancestor-or-equal であること (再 chunk 完了前の時点へ後発 association が遡及出現することを防ぐ)。same-gen partial retry の後着 chunk は tree schema v2/v3 (manifest_hash / chunk_set_hash — [03-data-model.md §8](03-data-model.md)) により新 commit で公開され、この条件が旧 commit への遡及混入を排除する (ancestry 判定は `--at` の到達可能性 walk と同じ)。**`--include-deleted` の補完 binding にも同条件を適用する** (introduction が当該 binding commit の ancestor-or-equal であること — 削除後に完了した後着 chunk の遡及混入を排除)。**`--all-history` は binding ごとに同判定を行う**
- shallow 化済み commit への `--at` の失敗規則は §2.2

History walk の aggregate security bound は exact に次とする (per-object caps に加算):

```text
all-parent DAG walk:   100,000 unique commits / 10,000,000 total tree entries /
                       4 GiB verified commit+tree bytes
first-parent walk:     100,000 commits / 10,000,000 total tree entries /
                       4 GiB verified commit+tree bytes
```

各 walk は counters を独立に持ち、次の object/entry で 1 つでも超える前に停止する。
`--all-history` / `--since` の scope は candidate/alias を部分返却せず
`KCS-E-COMMIT-HISTORY-LIMIT-001` (`excluded_scopes[].reason=history_limit_exceeded`) で失敗し、既存の
multi-scope partial exit 3 / all-failed exit 4 に従う。purge-by-path は all-parent cap、restore-by-path は
first-parent cap を同じ error code で fail-before-mutation/publication する。raw-hash purge と explicit
commit/evidence restore は ancestry walk を必要としない。

過去 snapshot の embedding 再生成は別操作 (`kcs reindex --at`)。

## 1.7 AI Agent レスポンス契約

```json
{
  "query": "認証仕様",
  "requested_mode": "auto",
  "resolved_mode": "text",
  "fallback": true,
  "fallback_reason": "embedding_not_authorized",
  "error_code": "KCS-E-SEARCH-VEC-UNAUTHORIZED-001",
  "diversify": { "strategy": "mmr", "mmr_lambda": 0.7 },
  "paging": { "limit": 20, "next_cursor": "eyJ2IjoxLCJzY29wZXMiOl..." },
  "searched_scopes": [
    { "scope_id": "scope_01J8ZQ...", "scope_path": "/Users/foo/Research/.kcs", "snapshot_at": "sha256:9f2c..." }
  ],
  "excluded_scopes": [],
  "index_status": {
    "enriched_ratio": 0.42,
    "pending_enrichment_tasks": 3120,
    "budget_paused": true
  },
  "results": [
    {
      "chunk_hash": "sha256:...",
      "evidence_pointer": {
        "schema_version": 1,
        "commit": "sha256:9f2c...",
        "tree": "sha256:3f9a...",
        "raw_hash": "sha256:...",
        "tool_profile_hash": "sha256:...",
        "chunk_hash": "sha256:...",
        "path_at_commit": "report.pdf",
        "heading_path": ["認証仕様", "API Token"],
        "byte_start": 1200,
        "byte_end": 1500,
        "scope_id": "scope_01J8ZQ..."
      },
      "evidence_uri": "kcs://scope_01J8ZQ.../sha256:9f2c.../sha256:.../sha256:.../sha256:...",
      "score": 0.87,
      "scope_path": "/Users/foo/Research/.kcs"
    }
  ]
}
```

`evidence_pointer` は [08-evidence-pointer-spec.md §2](08-evidence-pointer-spec.md) の schema を **そのまま** 埋め込む。root (`.kcs`) の信頼は `evidence_pointer.scope_id` を正とし、`results[].scope_path` は解決を高速化する表示・ヒント用の絶対パスである (truth vs cache の不変条件。解決手順は [08-evidence-pointer-spec.md §3.1](08-evidence-pointer-spec.md))。

`evidence_uri` は Evidence Pointer の正規テキスト形 ([08-evidence-pointer-spec.md §2.3](08-evidence-pointer-spec.md)) であり、そのまま `kcs open` / `kcs view` / `kcs evidence verify` の引数に渡せる。

`index_status` は AI 強化 (Markdownize / Embedding) が全対象に行き渡っていないときのみ必須 (`enriched_ratio < 1.0`)。人間向け表示では「AI 強化 42% (budget により一時停止中)」のような 1 行警告に翻訳する。

`snapshot_at` と `evidence_pointer.commit` の決定規則:

- `searched_scopes[].snapshot_at` = 当該 scope の検索対象 commit。デフォルト / `--all-history` / `--include-deleted` では検索時の HEAD commit、`--at` では指定 commit
- `evidence_pointer.commit`: デフォルト / `--at` では検索対象 commit。`--include-deleted` の live chunk は
  snapshot HEAD、削除済み分は final binding を選んだ newest first-parent commit。これにより
  `path_at_commit` は pointer commit の tree に必ず実在する。`--all-history` / `--since` は distinct
  `(chunk_hash,path)` ごとに、全 parent DAG 上の canonical introduction commit を使う。introduction は
 「その commit に binding が存在し、利用可能な全 parent に存在しない」commit。delete/re-add を含む
  複数 introduction のうち別 introduction の descendant でない ancestor-most 集合を作り、1 件ならそれ、
  複数の incomparable 候補なら full commit hash の bytewise 辞書順最小を使う
- `path_at_commit` = `evidence_pointer.commit` の tree における path

`--all-history` / `--since` は同じ chunk の同じ path が複数 commit に現れても 1 hit に畳む一方、rename
で生じた distinct path は別 hit として返す。各 historical alias result は、同じ raw_hash を持つ page-1
snapshot HEAD entry の distinct path を UTF-8 byte order で整列した `current_paths` として持つ
(空なら field を省略)。
raw identity から rename lineage は推測しない。`current_paths` がちょうど 1 件のときだけ compatibility
field `current_path` に同じ値を入れ、identical-byte twins では singular field を省略する。chunk 行自体は
path 非依存で 1 行のまま、path alias は snapshot HEAD から全 parent DAG の tree と snapshot HEAD tree
から導出する。

実装 pipeline は固定する: scope ごとに text/vector を rank → scope 内 RRF し、その rank を cross-scope
merge → global MMR/`max_per_raw_hash` する。pre-alias tie は immutable `(scope_id,chunk_hash)` の UTF-8
byte order とする。その確定 semantic position ごとに historical/deleted aliases を展開し、parent
score/rank をコピーして、group 内を
`(scope_id,chunk_hash,path_at_commit,evidence_pointer.commit)` の UTF-8 byte order で整列してから paginate
する。`scope_path` は display hint なので順序に使わない。alias は MMR cosine competition や
`max_per_raw_hash` へ再投入せず、distinct alias は path/commit により comparator equality にならない。

## 1.8 複数 scope 横断検索 (multi-scope search)

デフォルトの `kcs search` は scope_registry に登録された全 indexed scope を対象とする ([06-cli-spec.md §3](06-cli-spec.md))。各 `.kcs` は独立した index (sqlite.db) を持つため、横断検索は次の実行モデルで行う。

### 対象 scope の列挙

1. scope_registry から `participates_in_global_search = true` の scope を列挙する
2. `--scope <path>` 単独指定は canonical root_path の**完全一致** (当該 scope のみ — [06-cli-spec.md §3](06-cli-spec.md) の「カレントフォルダのみ」)。`--descendants` 併用時は self + 「`root_path + '/'` を前置に持つ scope」を対象とする (**path-component 境界で判定** — 単純な文字列前方一致は `/work/a` が `/work/ab` に一致するため用いない)。**canonical root_path の算出規則**: CLI 入力を (1) 絶対化 (cwd 基準)、(2) `.` / `..` の lexical 解決、(3) 末尾 separator 除去、(4) symlink 解決 (realpath) の順で正規化する。比較は **byte 単位** (case-folding しない — case-insensitive filesystem では観測された実 path 表記を正とする)。scope_registry の `root_path` も同一規則で保存する ([10-operations.md §3](10-operations.md))
3. 到達不能 / stale な scope (外部ドライブ切断等) は skip し、`excluded_scopes` に理由付きで記録する (検索全体はエラーにしない)

### 実行とマージ

1. scope ごとに独立にクエリを実行する。並列度は min(4, scope 数)、per-scope timeout は 2 秒 (いずれも config で上書き可)
2. scope 内では §1.1〜§1.3 までを実行し、RRF 済み unique semantic chunk 上位 candidate_depth 件を
   候補として返す。§1.4 の MMR/dedup は scope 内でまだ適用しない
3. scope 間の統合は **rank ベース** で行う。各 scope の RRF スコア (rank のみから決まる) をそのまま比較して降順マージする。**BM25 / vector の raw スコアを scope 間で比較・正規化してはならない** (コーパス統計が index ごとに異なり比較不能)。pre-alias 同点は immutable `(scope_id,chunk_hash)` で安定化する
4. diversify (MMR / group_by_raw_hash, §1.4) は統合後の候補列に対して適用する。**multi-scope 検索の
   `[search]` 実効値 (**default_mode** / rrf / diversify / candidate_depth / fail_behavior) は
   user config (device 層) を用いる** — folder 値は `--scope` 単一指定時のみ適用する (scope 間で
   異なる folder 値の統合は定義しない。cursor が bind する実効値 (§1.5) もこの解決に従う —
   **ただし fail_behavior は挙動方針であり確定順序に影響しないため bind / query_hash preimage の
   対象外**)
5. vector / hybrid の横断条件は [03-data-model.md §7](03-data-model.md) に従う。embedding profile が全 scope で一致しない場合、横断部分は text (BM25 rank) のみで統合し、`fallback_reason` に記録する (**`--vector` 明示時は fallback しない** — profile 不一致の scope を KCS-E-SEARCH-VEC-INCOMPAT-001 の excluded_scopes として除外し、全 scope 除外なら error — §1.2 の「失敗時は error」と同じ)。`kcs_format_version` が自己の対応上限より新しい scope も同様に excluded_scopes として除外する (KCS-E-STORE-VERSION-001 を `fallback_reason` に記録・当該 scope へは query_cache を含む一切の書込を行わない — [10-operations.md §12.5](10-operations.md))。**全 scope が STORE-VERSION 除外なら command は KCS-E-STORE-VERSION-001 / exit 8 を返す** (SCOPE-ALL-FAILED (exit 4) より優先 — REBUILDING と同型の昇格、[06-cli-spec.md §7](06-cli-spec.md)。自動化に「新版への更新が必要」を直接伝える)。**全 scope の除外理由が同一 code の場合、command は当該 code とその単独実行時の exit を返す (一般規則)** — VERSION → exit 8・REBUILDING → exit 3・INCOMPAT → exit 8・journal (`KCS-E-PURGE-JOURNAL-ACTIVE-001` — §3.5) → exit 3・DUP → exit 3 (ユーザーの dedupe 後に回復可能 — [08-evidence-pointer-spec.md §4.3](08-evidence-pointer-spec.md) の registry_duplicate = 3 と同一分類)。理由が混在して全 scope 除外となった場合のみ通常の SCOPE-ALL-FAILED (exit 4) とし、個別理由は excluded_scopes[].reason で判別する。embedding 承認の consent gate (§1.1) は**送信 gate であり per-scope の除外条件ではない** — 承認ゼロなら検索全体が text fallback (excluded_scopes には計上しない)。1 つ以上の承認で送信された query vector は profile 互換な全参加 scope の vector 検索に用いる (未承認 scope も含む — 送信は 1 回であり scope 別の再送信は発生しない)

既知の限界: rank ベース統合は、関連文書の乏しい scope の 1 位と強い scope の 1 位を同格に扱う。MVP ではこれを容認する (結果に scope_path が必ず含まれるため判別可能)。scope 間の再ランクは v2 以降の検討事項。

### 設定

```toml
[search.multi_scope]
parallelism = 4                 # 同時にクエリする scope 数の上限
per_scope_timeout_seconds = 2   # 超過 scope は excluded_scopes (reason=timeout)
```

### 部分失敗と exit code

| 状況 | 挙動 | exit code |
| --- | --- | --- |
| 全 scope 成功 | 通常結果 | 0 |
| 一部 scope 失敗 / stale / timeout | 結果を返し `excluded_scopes` に記録 | 3 |
| 全 scope 失敗 (理由混在時 — 除外理由が同一 code なら §1.8 の昇格規則で当該 code の単独時 exit) | エラー (`KCS-E-SEARCH-SCOPE-ALL-FAILED-001`) | 4 |

### レスポンス契約の拡張

単一値の `snapshot_at` は採用せず、次の 2 フィールドを返す (§1.7 の例):

```json
{
  "searched_scopes": [
    { "scope_id": "scope_01J8ZQ...", "scope_path": "/Users/foo/Research/.kcs", "snapshot_at": "sha256:9f2c..." }
  ],
  "excluded_scopes": [
    { "scope_id": "scope_01K3AB...", "scope_path": "/Volumes/ext/Research/.kcs", "reason": "stale" }
  ]
}
```

`snapshot_at` は scope ごとの検索時点 snapshot (commit_hash, [03-data-model.md §8.1](03-data-model.md))。単一 scope 検索 (`--scope .`) でも同形式 (要素 1 個の配列) を返す。これは [06-cli-spec.md §9](06-cli-spec.md) の Agent API 保証 (searched_scopes / excluded_scopes / fallback_reason) と同一の契約である。

### cursor の multi-scope 拡張

§1.5 の cursor を per-scope sub-cursor の合成に拡張する:

```json
{
  "v": 2,
  "scope_mode": "all",
  "query_hash": "sha256:...",
  "query_vector_digest": "sha256:...",
  "time_travel": { "all_history": true, "since": "604800s" },
  "since_cutoff": "2026-07-13T00:00:00Z",
  "excluded_scopes": [],
  "scopes": [
    { "scope_id": "...", "snapshot_commit": "sha256:9f2c...", "max_rowid": 18234,
      "max_association_rowid": 20117, "index_generation": "01J...",
      "chunking_config_hash": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
      "consumed": 40 }
  ]
}
```

`time_travel` は query hash に入る canonical selector object (default のみ field 省略)、`since_cutoff` は
`--since` のときだけ存在する。cursor はこの JSON の JCS と認証 tag を含む signed
base64url opaque token として返す。Step 4 cursor schema は `v=2`; 必須 config/association/selector
binding を持たない legacy `v=1` は `KCS-E-SEARCH-CURSOR-001` で拒否する (cursor は durable artifact ではない)。

- `scope_mode` は検索対象 scope の指定方法 (all / `--scope` / `--descendants`)、`query_hash` は次の正準構成 (per-scope の対象 chunking config binding を含む — §1.5 の対象 config と同一): `"sha256:" + base16(sha256(JCS({ query: <NFC 正規化後のクエリ文字列>, mode: <解決後の実効 mode (text|vector|hybrid)>, chunking_configs: <{scope_id,chunking_config_hash} の scope_id UTF-8 byte order 配列>, scope_mode, scopes: <page 1 または直前 replay で実際に参加する active scope_id の昇順配列>, rrf: <[search.rrf] の実効値 (k / candidate_depth / w_text / w_vector — 変更は確定順序を変えるため cursor 誤用検出の対象)>, diversify: <[search.diversify] の実効値>, query_vector_digest: <実効 mode が vector|hybrid のときのみ — page 1 の query vector の digest ([04-pipeline.md §4.3](04-pipeline.md) の canonical bytes に対する sha256。text mode ではキー省略>, time_travel: <--at/--all-history/--include-deleted/--since の実効値 (未指定キーは省略)> })))`。`limit` / `--offset` / `--cursor` / `--json` は**含めない** (ページング操作で hash が変わってはならない)。いずれも token 全体に 1 つで、別クエリ・別条件・いずれかの scope の別 chunking config での cursor 誤用検出に使う (不一致は `KCS-E-SEARCH-CURSOR-001` で拒否、§1.5)
- page 1 の `scopes` / `chunking_configs` は成功して実際に ranking へ参加した scope だけを含む。
  page-1 `excluded_scopes` は bounded `{scope_id,reason}` として signed token に保持するが active scope や
  query hash の config mapping には入れず、その cursor stream へ後から再参加させない。registry に後から
  現れた scope も入れない
- `snapshot_commit` は当該 scope の検索時点 snapshot (commit_hash)、`max_rowid` / `max_association_rowid`
  は snapshot 時点で index に取り込まれていた chunk / association の上限、`index_generation` は
  page 1 時点の当該 scope の世代 ULID (§1.5 — 不一致は cursor 拒否)、`chunking_config_hash` は
  page 1 の当該 scope の**対象 config** (デフォルト = **当該 scope の HEAD tree の値** (移行期間の
  扱いは [04-pipeline.md §4.6](04-pipeline.md))、時点指定 = 対象 tree の値 —
  §1.5 と同一)、`consumed` は当該 scope から既に返した件数。page 2 で**対象 config** の mapping
  (保存値と再計算値の比較 — current ではなく対象時点の値) が 1 件でも違えば query hash mismatch として
  cursor を拒否する。署名検証後も
  いずれかの field 欠落・型違い・範囲外は cursor error
- cursor 付き呼び出しで selector flag を省略した場合は signed `time_travel` を継承する。1 つでも selector
  flag を再指定した場合は canonicalize 後に token object と完全一致しなければ
  `KCS-E-SEARCH-CURSOR-001`。これにより既存の `search QUERY --cursor TOKEN` は履歴 mode と canonical
  `--since` duration を失わず、同じ selector を明示してもよい
- replay は token の active `scopes` だけを解決する。active scope が unreachable/corrupt/shallow に
  なった場合、global merge/MMR stream を安全に縮退再計算できないため、部分結果や next cursor を返さず
  cause-specific に hard-fail する (unreachable は `KCS-E-SEARCH-CURSOR-001` reason
  `active_scope_unavailable`、shallow は `KCS-E-COMMIT-SHALLOW-001`、store damage は
  `KCS-E-STORE-CORRUPT-001`)。cursor なしの fresh search を案内する。scope move は同じ `scope_id` として
  継続し、config drift も cursor error とする
- 次ページは各 scope を `snapshot_commit` に固定して再クエリし、cross-scope merge → global MMR → alias 展開まで再計算した**最終 stream 上で** scope ごとの consumed 件を skip して継続する (per-scope の事前 skip は global 選択を変えるため行わない — §1.5 の consumed 定義が正本)。マージは決定的 (RRF スコア降順 + 辞書順 tie-break) なのでページを跨いで再現可能
- cursor 中の `snapshot_commit` が shallow 化済み (tree 破棄) の場合、cursor の再計算は `KCS-E-COMMIT-SHALLOW-001` で失敗する (§2.2)。この場合は cursor なしの再検索を案内する

### 性能目標の前提

M3-1 の p95 < 5 秒 ([09-mvp-scope.md §4.1](09-mvp-scope.md)) は **20 scopes / 合計 10 万 chunk** を前提とする。scope 数が数百を超える構成は MVP の性能保証外とし、`--scope` での絞り込み、または利用頻度の低い scope の `participates_in_global_search = false` 設定を案内する。

# 2. Commit / Snapshot

## 2.1 commit_type 永続 enum

`commit_type` は **永久に変更しない契約**。commit は CAS JSON object であり SQLite に commit 表は
存在しないため ([04-pipeline.md §4.4](04-pipeline.md))、**enum の強制点は commit object の schema
検証 (publication 時の loader)** である。値域 (JSON Schema enum 相当):

```text
commit_type ∈ { 'manual', 'auto', 'imported', 'migrated', 'repaired', 'merged', 'purged' }
```

| type | 用途 | protected | GC policy |
| --- | --- | --- | --- |
| manual | 明示 commit | true | none |
| auto | 自動 snapshot (取り込み完了時 = MVP / 定期 = Phase 4、§8) | false | shallow (個数 / 時間で tree を減衰) |
| imported | 外部 KCS から取り込んだ commit | true | none |
| migrated | format 変換時の中間 commit | false | shallow |
| repaired | repair 操作の中間 commit | false | shallow |
| merged | 共有版マージ (Phase 5+) | true | none |
| purged | 法務・秘匿削除後の commit | true | none |

`semver MAJOR でも値域 bump しない` 契約は他フィールドより強い保証。

## 2.2 GC

> GC (§2.2-2.6) の**実装は Phase 4+** ([09-mvp-scope.md §3.1](09-mvp-scope.md))。MVP (Step 1-4) では GC を実行せず (**定期** auto snapshot・retention 減衰がまだ無く回収対象がほぼ発生しないため — 取り込み完了時の auto snapshot は MVP に存在する: §8.1)、`gc_policy` × `commit_type` の対応 schema のみ Step 1 の設計時から契約として遵守する (§2.6)。

```text
gc_policy(commit_type):
  auto      → shallow   (tiered retention 満了で tree のみ破棄、commit object は残す)
  migrated  → shallow
  repaired  → shallow
  manual    → none
  imported  → none
  merged    → none
  purged    → none
```

**full (commit object の削除) はどの commit_type にも適用しない。** commit object は append-only であり、これを消す操作は KCS に存在しない (purge も commit / tree を書き換えない、§3.5)。

なお `kcs repair --verify-objects` ([10-operations.md §7.5](10-operations.md)) が生成する `repaired` commit は破損 object の再取り込みによる復旧点であり、その復元した raw object は GC 対象外 (§2.6)。したがって commit の tree が shallow 化されても復旧した raw 内容は保持され、object としては実効的に none 相当である。

`shallow` は履歴 DAG の連続性を保つため commit を残し tree のみ破棄する。実行時は
`(commit_hash, tree_hash, gc_policy, shallowed_at)` を持つ non-content receipt
(`.kcs/gc/shallowed/<commit64>`) を**tree 破棄より先に耐久化する** (Phase 4 実装要件) — fsck は
receipt が説明する tree 欠落を正常 (shallow) として扱い、receipt なき欠落を corruption とする
([10-operations.md §7.5.1](10-operations.md)。これが無いと正規 GC と tree の偶発喪失を区別できない)。

`shallow` 後の commit を `kcs view <commit>` した場合:

```text
- メタ情報 (commit_hash, parents, message, timestamp, commit_type) は表示
- tree は "shallow: tree discarded" と表示
- kcs restore <shallow-commit> は KCS-E-COMMIT-SHALLOW-001 で拒否
- kcs diff <a> <b> で片方が shallow なら全ファイル差分は不能と明示
- kcs search --at <shallow-commit> と、shallow 化 commit を snapshot とする
  cursor の再計算も KCS-E-COMMIT-SHALLOW-001 で失敗する (tree 全体を要するため)
- shallow commit を指す Evidence Pointer の解決は失敗しない
  (raw_hash / chunk_hash による直接解決、08-evidence-pointer-spec.md §3.1)
```

## 2.3 GC スケジューリング

GC は独立した常駐プロセスを持たない (§5 プロセスモデル)。実行契機は次の 3 つ:

1. `manual_only` (MVP デフォルト): `kcs gc` の明示実行のみ
2. `after_index` (Phase 4+ の GC 実行系実装後のデフォルト): `kcs index` / `kcs snapshot` の成功終了後、同一プロセス内で `max_runtime_seconds` を上限に実行する。上限到達で中断し、残りは次回に持ち越す (`kcs index` 実行中とは重ならないため I/O / lock 競合が起きない)
3. `on_idle` (Phase 4+): OS スケジューラ委譲の定期 auto snapshot 実行時 (§8)、直近の KCS 書き込み操作から `idle_threshold_seconds` 以上経過していれば便乗実行する

GC 実行系の実装自体は Phase 4+ (§2.6)。config schema は Step 1 の設計時から遵守する。

```toml
[gc]
mode = "manual_only"           # MVP デフォルト。"after_index" (Phase 4+ 実装後のデフォルト) | "on_idle" (Phase 4+)
idle_threshold_seconds = 300   # on_idle 用 (Phase 4+)
max_runtime_seconds = 60
```

## 2.4 Tiered Retention

`commit_type=auto` のみ tiered retention を適用する。retention 満了は **shallow 化 (tree 破棄)** であり commit object の削除ではない (`manual/imported/merged/purged` は tree も常に残す)。
**ref tip 除外**: HEAD・branch・tag が指す commit の tree は、retention 満了でも **shallow 化の対象にしない** — 無変更 scope では auto snapshot が no-op を続け HEAD が古い auto commit に留まり続けるため、除外しないと現在状態の基点 (bare search / restore / cursor) を失う。物理削除の直前にも、ref tip 非該当と「非 shallow commit からの参照ゼロ」を同一 exclusive critical section で再検証する (§2.5):

```toml
[gc.auto_retention]
keep_last_hours    = 24
keep_hourly_days   = 7
keep_daily_weeks   = 4
keep_weekly_months = 6
[gc.derived_retention]
keep_migrated_per_branch = 5
keep_repaired_per_branch = 5
```

## 2.5 並行性 / power-loss 安全性

```
- GC 中の新規 commit 受付は block しない (CoW 風 readonly snapshot 上で走る)。§6 の lock 表が
  `kcs gc` を書き込み系に含めるのは on-demand 実装 (全体 lock 型 — 実装は Phase 4+ の初期形、§2.2) の
  規約 — 本節の並行 GC はその後続であり、導入時に §6 の表を改訂する
- object 物理削除は exclusive lock の短い critical section に限定
- power-loss 中断時は次回起動時に sweep 再開 (.kcs/gc/in_progress マーカーで検出)
```

## 2.6 GC の削除対象 (規範)

GC (tiered retention / `kcs gc --prune-unreachable` を含む) が削除してよいもの:

```text
- tree object (shallow 化対象 commit のもの。**ただし同一 tree hash を非 shallow の commit が参照して
  いる場合は削除しない** — tree は content hash 共有されるため、reachability 確認 (全非 shallow commit
  からの参照 0) が削除の前提)
- SQLite index / FTS など objects/ から再構築可能な cache (例外 = embeddings の
  `target_type='query_cache'` 行 — 復元されず破棄、影響は cursor 拒否のみ [04-pipeline.md §4.3](04-pipeline.md)。
  index を削除すると再構築までの間、
  検索と pointer 解決の 6a/6b 検証は実行不能 — このときの解決は not_found ではなく
  `KCS-E-INDEX-REBUILDING-001` の再構築要求を返す [§6・[08-evidence-pointer-spec.md §3.1](08-evidence-pointer-spec.md)]。
  検証不能を「不在の確定」と混同しない)
- どの commit からも参照されない中間 object (中断した index が残した prepared 等)
```

GC が削除してはならないもの:

```text
- commit object (append-only。§2.2)
- raw object / chunk object — これらを削除する唯一の経路は purge (§3)
- toollock object — 参照する commit object が存在する限り削除不可 (commit は append-only のため実質恒久。
  未公開 finalize 由来の未参照 toollock のみ、全 commit 参照走査の後に回収可)
- manifest object — 参照する tree object が存在する限り削除不可 (削除の唯一の経路は purge。shallow 化で
  未参照になったものの回収は Phase 4 GC の対象 — §2.2 表と同じ tiered retention に従う)
```

raw / chunk を GC 対象外とするのは、Evidence Pointer の永続性契約 ([08-evidence-pointer-spec.md §6](08-evidence-pointer-spec.md)) を「purge されない限り」で成立させるため。ストレージ増は「原則として忘れない」設計の受容済みコスト。

なお GC の実行系 (tiered retention / on_idle / prune) の実装は Phase 4+ ([09-mvp-scope.md](09-mvp-scope.md))。本節の削除対象規範と §2.2 の gc_policy schema は Step 1 の DB / object 設計時から遵守する。tiered retention 導入までの auto commit の蓄積はディスク消費として容認する。

# 3. Purge (法務・秘匿・誤取り込み)

## 3.1 purge と archive の区別

```
archive: 履歴上は残し「現在は使っていない」状態。デフォルト操作。
purge:   履歴から物理的に消す。例外操作。commit_type=purged が記録される。
```

正当事由:

```
- 法令上の削除義務 (個人情報・GDPR の forget 権)
- 機密漏洩への対応 (誤って取り込んだ秘匿文書)
- 著作権・契約上の保持禁止
- 誤取り込みの是正 (取り込むべきでなかった対象 — 秘匿文書に限らない)
```

CLI:

```bash
kcs purge <path|--raw-hash <h>> --reason <legal|privacy|misingest|copyright|other>
# --reason は必須。--yes なしなら確認プロンプト
```

## 3.2 「忘れない」と purge の両立

KCS は「原則として忘れない」が、**purge は「忘れる」のではなく「消した事実を記録して忘れる」操作**。purge 後も:

```
- commit_type = "purged" の新 commit が記録される
- 誰が、いつ、どの正当事由で実行したかを保存
- 監査可能性は維持される (= 透明な忘却)
```

## 3.3 Dead Evidence Pointer のセマンティクス

「Evidence Pointer の不変性」と「法務 purge」の緊張領域。正本は [08-evidence-pointer-spec.md §4](08-evidence-pointer-spec.md)。残未決 (bulk verify スループット — 1 件) は [09-mvp-scope.md §5.3](09-mvp-scope.md)。以下は採用済みセマンティクスの要約。

```text
purge 後の pointer 解決:
1. raw_hash が active な tombstone を持つ → tombstone レスポンス (status = tombstoned)
   {
     "status": "tombstoned",
     "purged_at": "2026-04-25T12:00:00Z",
     "purged_reason": "legal" | "privacy" | "misingest" | ...  (enum の正本 = 08 §4.1),
     "purged_in_commit": "sha256:9f2c...",
     "raw_hash": "sha256:..."
   }
2. raw_hash が完全削除 (--erase-tombstone: public tombstone 記録を残さない) → not_found
   error_code: KCS-E-PURGE-NOT-FOUND-001

検出 API:
kcs evidence verify <pointer> [--strict]
  → status = 6 値 union (alive | tombstoned | not_found | scope_unreachable |
             unverifiable | registry_duplicate — 正本 08 §4.3)
```

## 3.4 purge スコープは `.kcs` 単位

横断 GC を持たないので、purge も **その `.kcs` 内に閉じる**。別 `.kcs` (= ユーザーが意図的に複数フォルダへ配置) に同一 raw_hash がある場合、それは別 purge 操作で消す必要がある。これは将来コスト低下/ローカル LLM 進展前提で容認 ([01-positioning.md](01-positioning.md))。

## 3.5 purge の機構 (何を消し、何を残すか)

purge は **object の物理削除 + default tombstone または内部 erase receipt** であり、
**履歴 DAG の書き換えではない**。

消すもの (対象 raw_hash について、全履歴にわたり):

```text
- raw object 本体 (objects/raw/ab/cd/<raw64>)
- 派生 artifact: prepared / **image** / normalized / chunk / embedding
  (normalized は同一 (raw_hash, tool_profile_hash) 配下の全 gen instance を対象とし、
   **manifest object (objects/manifests/ — 当該 (raw_hash, tool_profile_hash) の全 gen・全確定版) を含む**。
   **共有されうる派生 (prepared / image — content hash 単位で他 raw と共有され得る ([03-data-model.md §1](03-data-model.md)) / embedding — text_hash 単位で他 raw の chunk と共有) は、purge 対象外の
   live 参照が 0 の場合のみ物理削除する** — 無条件削除は非対象文書の検索・再構築を破壊する)
- `~/.cache/kcs/open/<raw_hash digest64>/` の一時展開 dir (存在すれば冪等削除 — [06-cli-spec.md §1.1](06-cli-spec.md))
  (closure の列挙正本 = 当該 (raw_hash, tool_profile_hash) の全 gen manifest。**どの manifest からも
   参照されない orphan prepared / image** (公開前 crash の残骸) は解決経路に乗らず、GC の
   「未参照中間 object」として回収される。**MVP では GC が無いため、削除手段は
   `kcs repair --verify-objects --prune-orphans`** ([10-operations.md §7.5.1](10-operations.md)) —
   purge 完了表示にその旨 (残存可能性と掃除手段) を注記する)
- SQLite の chunks / chunk_config_generations / chunk_publications 行と FTS エントリ。chunk_vec は**対象 chunk_id の行に限定**し、**embeddings 行は object 側と同じく live 参照 0 の場合のみ削除する** (共有 text_hash の行を無条件に消すと、非対象文書の vector 検索が rebuild まで欠ける)。`target_type='query_cache'` の embeddings 行は候補に含めない (文書 lifecycle と無関係 — [04-pipeline.md §4.3](04-pipeline.md)。即時消去したい場合の行削除は常に安全 = 影響は cursor 拒否のみ)
- chunks.jsonl の**対象 chunk_id を参照する creation 行・publication event 行の全部** (append-only の例外 — purge は法務要件の明示例外として行を落とす。書き換えは [04-pipeline.md §1.1](04-pipeline.md) の耐久書込 primitive (temp + rename) に従う)
- 対象 raw_hash に帰属する task の **staging** ([07-adapter-spec.md §8.3](07-adapter-spec.md)) — **task の状態を問わず** (retryable failed の保全 staging を含む。以後の再生成は persist 直前の tombstone 再検査が防ぐ)。**帰属列挙の正本 = `.kcs/staging/` の耐久 descriptor 全走査** ([03-data-model.md §2](03-data-model.md) — tasks.jsonl 非依存。task 記録の喪失後も削除対象を列挙できる)
```

残すもの (不変):

```text
- すべての commit / tree object。commit / tree は書き換えない。
  DAG の再結線・tree entry の削除・連鎖再 hash は行わない。
- tree entry のメタデータ (path, raw_hash)。raw_hash から原文は復元できない。
- tombstone (.kcs/tombstones/ab/cd/<raw64>)。--erase-tombstone 指定時を除く。
- `--erase-tombstone` では fsck 専用の non-content erase receipt
  (`.kcs/purge/erase-receipts/ab/cd/<raw64>`)。public pointer API からは不可視。
```

追加されるもの:

```text
- commit_type=purged の新 commit (purge 実行後の working tree を指す)
```

**working tree の原本には触れない** (KCS はユーザーのファイルを削除しない)。したがって purge の
preview と完了表示は、対象 raw_hash と同一 bytes の原本が working tree に残存する場合に**必ず警告する**:
残存原本は次回 `kcs index` の自動 scan で再取り込みされ、既存 pointer は再び alive になる
([08-evidence-pointer-spec.md §4.2](08-evidence-pointer-spec.md))。恒久的に除外するには原本の削除または
`.kcsignore` への追加が必要である。

**tombstone の退役 (resurrection)**: 同一 raw_hash の raw object が再 publication された場合、その
publication と同一の locked mutation 内で active tombstone を**退役 (retire)** させる — tombstone
レコードの events[] へ `retired` を append する (下記 lifecycle 形式)。**耐久順序**: retire の
append は再 publication の snapshot finalize (§8.1 — chunks.jsonl → SQLite → commit / ref publish)
の**完了後**に行う。間で crash した場合は tombstone が active のまま残る (安全側 — 解決は
tombstoned)。retire append の完了時に index_generation を新規採番する (§1.5 — finalize〜retire 間に
発行された cursor の replay が、退役後の可視集合で別 stream を再計算することを拒否で防ぐ)。
回転は retire append と同一 locked mutation 内で直後に行う。lifecycle 更新の検出は**時刻ではなく
単調カウンタ**で行う: `.kcs/tombstones/lifecycle-epoch` (`.kcs/purge/epoch` と同じ書込規律の単調
カウンタ) を **event append (retire・再 purge・legacy 変換) ごとに同一 lock 下で +1** し、回転の
SQLite Tx は index_metadata の **`last_lifecycle_epoch`** ([04-pipeline.md §4.1](04-pipeline.md)) へ
反映済み counter 値を記録する。append と回転の間で crash した場合は、書き込み系コマンド冒頭の
回復が **counter > last_lifecycle_epoch** を検出して回転を補完する (UTC ms の時刻比較は同一ミリ秒・
時計逆行で補完を見逃すため使わない。`kcs repair --rebuild-db` は完了 Tx で現 counter 値に初期化する
— DEFAULT 0 のままの全件誤検出を防ぐ)。**counter の耐久順序と回復**: counter の +1 (fsync) を
event append より先に行い、**全ての新規 lifecycle event (purged・erased・retired・legacy 変換の
書込) に、その時点の counter 値を `lifecycle_epoch` として必須記録する** (purge の `epoch`
(target_epoch) とは**別 field** — 2 系統のカウンタを混用しない。legacy 行の欠落は可)。
**巻き戻り検出は機械条件のみ**: locked mutation 冒頭で
`counter < max(last_lifecycle_epoch, 全 lifecycle event の lifecycle_epoch 最大値)` (lifecycle_epoch を記録した event が無ければ後者は 0 として評価) なら欠落・不正・
backup 復元による巻き戻りとみなし、**その max + 1 で counter を再作成して無条件で
index_generation を 1 回転する** (取りこぼした可能性のある更新を回転で潰す fail-safe。
「更新痕跡」の判定はこの比較だけで行い、mtime 等の抽象的条件は使わない)。**読取系は冒頭検査で
counter と last_lifecycle_epoch を照合し、不一致 (> だけでなく < も) なら
KCS-E-INDEX-REBUILDING-001 と同じ retryable (exit 3) を返す** — 補完回転は書き込み系のみが行うため、
crash 後最初のコマンドが読取でも旧 cursor を退役後の可視集合へ受理しない (この retryable への自動再試行は仕様として約束しない — 再試行は呼出側の判断)。
次回の locked mutation または fsck が「active tombstone × 同一 raw の ref 到達可能な
再 publication commit **であって、末尾 purged event の `in_commit` を ancestor に持つもの
(= 当該 purge より後の publication)**」を検出したら retired event を補完する (erase receipt の
crash 整合規則と同型。**この因果条件が無いと、再 purge 後も ref に残る過去の resurrection commit を
誤検出して、新しい tombstone を退役させてしまう**)。以後の
open / view / verify / 解決は alive を返す (退役なしには「tombstone 最優先」の解決規則と上記の
「再び alive」が両立しない)。**retired event には `resurrection_commit` (再 publication を刻んだ
commit — §8.1 no-op 例外 (a)) を記録する** — purge 前 commit を指す旧 pointer の解決は、このリンクを
介してのみ新 publication を参照できる ([08-evidence-pointer-spec.md §3.1](08-evidence-pointer-spec.md)
手順 6b。検索の時点条件には影響せず、旧時点への遡及混入は起きない)。purge の監査事実は
commit_type=purged の commit と、削除されず残る purged/retired event 列で追跡できる。
search / open / evidence verify / fsck は同一の **active**-tombstone 判定を共有する。

**purge journal (クラッシュ安全の正本)**: purge は複数ストア (objects / SQLite / chunks.jsonl / logs /
tombstone / commit) を跨ぐ破壊操作のため、**mutation 前に `.kcs/purge/journal` へ対象 closure と
phase を耐久記録し (fsync + atomic rename — [04-pipeline.md §1.1](04-pipeline.md) と同じ書込規律)、
各 phase を冪等に再開できる**ようにする:

```text
journal record = { purge_id (ULID), raw_hash 群, reason, actor, started_at, target_epoch (完了時の epoch 値),
                   marker_kind (tombstone | erase),
                   closure (削除対象の全 object type × hash — 共有派生の live 参照判定の結果を含む),
                   planned_commit (purged commit の canonical bytes — prepared 相で確定し、
                                   tombstone / receipt の purged / erased event の in_commit と
                                   一致する hash を先に固定) }
phase 順序    = prepared (closure 確定・記帳)
              → tombstoned (tombstone / erase receipt を先に耐久化 — 削除より前)
              → deleted (objects / SQLite / chunks.jsonl / logs の冪等削除)
              → committed (commit_type=purged の publication)
              → done: **順序固定** — (1) `.kcs/purge/epoch` を journal の target_epoch へ更新
                (temp 書込 → file fsync → atomic rename → 親 directory fsync)、(2) その後に
                journal を除去 + directory fsync。journal が先に消える実装は、除去〜increment 間の
                crash で「journal 不在 × 旧 epoch」の ABA 窓を作るため禁止
クラッシュ回復 = 次回の書き込み系コマンド冒頭で journal を検出したら、記録 phase から再開する
              (各 phase は再実行安全 — planned_commit を journal から publish するため同一 hash を
              再現でき、時刻の再計算をしない)。journal が active な間の fsck は incomplete (exit 3 —
              [10-operations.md §7.5.1](10-operations.md))。**読み取り系 (status を除く §6 の全読取
              コマンド — search / log / view / inspect / evidence verify / restore / diff / open) は、
              冒頭と「本文・存在情報を返す直前」の 2 点で検査する: 「active journal の不在 **かつ**
              `.kcs/purge/epoch` (単調カウンタ) が開始時と不変」でなければ `KCS-E-PURGE-JOURNAL-ACTIVE-001`
              ([10-operations.md §12.1](10-operations.md)) retryable (exit 3) で拒否する** (2 点目で検出した場合は取得済み結果を破棄する。
              epoch 比較が無いと、高速な purge が 2 点の間に journal 作成〜除去まで完走した場合に
              両検査をすり抜ける — ABA。**epoch ファイルの欠落・不正値も同様に拒否する (fail-closed)** —
              次の locked mutation が journal の target_epoch、journal も無ければ**全 lifecycle
              event に記録された `epoch` の最大値 + 1** (`epoch` を記録した event が皆無なら 1 — event ゼロの store に加え、全行 legacy で epoch 欠落の lifecycle も含む。旧観測値と衝突しない)
              から単調性を回復して再作成する。purge 完了後に epoch ファイルだけ喪失しても恒久
              exit 3 にしない) —
              marker 耐久化後・削除完了前の窓で削除対象の本文を返さないため。読み取り系は lock を
              取らないため、冒頭 1 回の検査では検査後に journal が現れる TOCTOU 窓が残る — 返却直前の
              再検査 (journal / purge epoch / **lifecycle counter** の 3 点 — 順序と比較対象は
              [10-operations.md §3](10-operations.md) の固定順) がこれを閉じる。`kcs status` だけは拒否せず、active journal の存在を状態として
              表示する (クラッシュした purge の回復可視性のため。status は本文を返さない)。
              不可逆な外部副作用を持つ 2 系は検査位置を固定する: restore は private temp へ展開し
              返却直前検査の後に atomic rename で --to へ publish (検出時は temp を削除)、open は
              OS アプリ起動の直前に再検査する (起動後は取消不能 — 検査はそこまでに完了させる)
```

**in-flight 外部実行との整合**: prepared 相で、**当該 scope (purge を実行する `.kcs` の scope_id) の**
対象 raw_hash を入力とする pending / running の外部実行タスク (batch_requests state 0/1 —
`request_kind` = batch / sync の両方。表はデバイスグローバルのため、scope_id 条件が無いと同一 raw を
持つ**別 scope** の実行中 request まで terminal 化・掃除してしまう — purge は `.kcs` 単位) を
abandon 相当で terminal 化し (estimated 記帳 — [04-pipeline.md §5.8](04-pipeline.md))、
provider 上の対応 upload (batch 行のみ) を掃除する。**加えて、対象 raw_hash の terminal だが
`intent_token IS NOT NULL` の行 (残骸掃除未完 — [04-pipeline.md §5.8](04-pipeline.md)) の provider
残骸掃除も同じ prepared 相で完遂する** (これが無いと terminal 化直後の crash が残した機密 upload が
次の batch 系実行まで provider 上に残る)。purge 後に相 3 collect が出力を得た場合は、persist 直前の
tombstone 再検査で破棄する ([04-pipeline.md §5.8](04-pipeline.md) 相 3)。

tombstone を削除より先に耐久化するのは、「対象 object が消えたのに purge の痕跡が無い」状態
(corruption と区別不能な markerless absence) を作らないためである。

tombstone は raw_hash をキーとする **lifecycle レコード** (append-only の events[] 配列) で、CAS object ではないため `objects/` の外に置く。event は `purged` / `retired` の 2 種で、**active 判定 = 末尾 event が `purged` であること** — retire は末尾に `retired` を append し (上書き・削除しない = 退役監査の保全)、再 purge はさらに `purged` を append する。resolver・fsck・再 purge はこの「末尾 event」規則だけを参照する。events を持たない旧 flat 形式は「purged event 1 件」として読み、**次の mutation 時に一回だけ events 形式へ変換する** (legacy)。変換時、5 値 enum ([08-evidence-pointer-spec.md §4.1](08-evidence-pointer-spec.md)) 外の自由文 reason は `other` へ正規化し、原値を optional `legacy_reason` に保全する — 閉 enum は新規書込の規則であり、旧値の読取は other 扱い (表示は原値可・fsck は corruption にせず警告)。**lifecycle レコードの更新 (retire・再 purge・legacy 変換) は `.kcs/.lock` 下で、temp 書込 → file fsync → atomic rename → 親 directory fsync で行う** ([04-pipeline.md §1.1](04-pipeline.md) と同じ規律)。malformed・途中破損 (torn JSON) の record は `KCS-E-STORE-CORRUPT-001` として fail-closed に扱う。
物理 leaf の `<raw64>` は論理 `raw_hash` から `sha256:` を除いた 64 文字の小文字 hex であり、
JSON 内の `raw_hash` は完全な `sha256:<64hex>` を保持する。旧 Unix store の prefixed leaf は
[03-data-model.md §2](03-data-model.md) の検証付き compatibility fallback で解決する。purge 実装時は
canonical / legacy の両 variant が存在する場合に両方を検証し、競合時は fail closed、整合時は両方を削除する。

```json
{
  "raw_hash": "sha256:abc...",
  "events": [
    { "kind": "purged",  "at": "2026-04-25T12:00:00Z", "reason": "legal", "actor": "user",
      "in_commit": "sha256:9f2c...", "epoch": 12, "lifecycle_epoch": 41 },
    { "kind": "retired", "at": "2026-05-01T09:00:00Z", "actor": "user",
      "in_commit": "sha256:1a2b...", "resurrection_commit": "sha256:1a2b...", "lifecycle_epoch": 42 }
  ]
}
```

`--erase-tombstone` は public tombstone を残さない一方、markerless absence と後発 store corruption を
fsck が区別できるよう、同じ digest-only fan-out に次の exact bounded receipt を atomically 保存する。

```json
{
  "schema_version": 2,
  "raw_hash": "sha256:abc...",
  "events": [
    { "kind": "erased",  "at": "2026-04-25T12:00:00Z", "in_commit": "sha256:9f2c...",
      "actor": "user", "reason": "privacy", "epoch": 12, "lifecycle_epoch": 41 },
    { "kind": "retired", "at": "2026-05-01T09:00:00Z", "actor": "user",
      "in_commit": "sha256:1a2b...", "resurrection_commit": "sha256:1a2b...", "lifecycle_epoch": 42 }
  ]
}
```

receipt は path / query / prompt / content を持たず (actor は全 event、**reason (5 値 enum — 非機微 metadata) は purged / erased event** に監査要件として持つ — [02-philosophy.md §2.4](02-philosophy.md) の「どの正当事由で実行したか」を erase 後も保存する。kind 別の必須列挙は [10-operations.md §7.5.1](10-operations.md))、raw_hash は immutable tree に既に残る。**purged / erased
event には当該 purge の `target_epoch` を `epoch` として記録する** (以後の新規 event で必須 —
legacy 行の欠落は可。epoch ファイル喪失時の回復源 — 上記 journal 二重検査の回復規則)。
validity は leaf/raw_hash 一致だけでなく、erased event の `in_commit` が bounded verified CAS 上で
ref-reachable な `commit_type=purged` commit を指し、`at` が canonical UTC かつ commit `created_at` と
一致し、fsck invocation の fixed now より未来でないことを要求する。schema_version ごとの定義に
一致しない field・不一致は store corruption (v1 flat 形式は「erased event 1 件」として読み、
次の mutation で v2 へ locked 変換する — tombstone の legacy 規則と同型。v1 に reason は存在しない
ため変換では `reason: "other"` を合成し legacy 警告として報告する — 新規 erased の 5 値 enum 必須
とは区別。自由文の原値を持つ legacy 変換は従来どおり `legacy_reason` に保存)。
open / view / search / restore / evidence verify / index の resurrection barrier には使わず、fsck だけが
intentional absence の説明に使う。したがって Evidence verify は従来どおり `not_found` で、同一 bytes の
後日 ingest (明示操作に限らず、working tree 残存原本の自動 scan を含む — §3.5 の残存警告) は許可する。**erase receipt も tombstone と同じ lifecycle 形式 (events[]) を持ち、raw object の再 publication 成功時は除去せず `retired` event を append する** — 除去すると erase 済み raw の旧 commit が参照する manifest 欠落を説明するものが消え、fsck の corruption 誤判定と手順 6b の不達を生むため (公開 pointer API に使わない・re-ingest barrier にしない性質は不変)。crash で不整合が残った場合は verified raw object を優先し、次の locked mutation で record を整合させる — **整合の条件は [10-operations.md §7.5.1](10-operations.md) の receipt 整合規則に従う**: 末尾 erased event の `in_commit` を ancestor に持つ ref 到達可能な再 publication commit が存在するときのみ `retired` を append し、commit がまだ無ければ未 finalize の進行状態として保留する (tombstone の補完と同じ因果条件)。

**制約 (明記)**: tree entry の `path` 文字列と `raw_hash` は履歴に残る。ファイル名そのものが秘匿対象であるケース (履歴書き換えが必要) は MVP 非対応。commit / tree の書き換えは content hash の連鎖再計算と無関係ファイルの Evidence Pointer 無効化を伴うため、対応する場合も v2+ の再設計事項とする。

# 4. Restore / Time-travel

## 4.1 Restore

```bash
kcs restore <evidence|path|commit> --to <dir>
```

**安全要件**:

```
- working tree への直接書き戻しは禁止 (--to <dir> 必須)
- 既存ファイル上書きは --force 必須 + 確認プロンプト
- restore は raw object をそのまま展開 (再 Markdownize しない)
- shallow commit からの restore は KCS-E-COMMIT-SHALLOW-001
- purged 対象は KCS-E-PURGE-NOT-FOUND-001 / tombstone
- 展開は検証済み --to ディレクトリの dirfd 配下で no-follow (symlink を辿らない) に行い、
  private temp → atomic rename で publish する。絶対 path・「..」を含む復元エントリは拒否
  (既存 symlink 経由で復元先の外部を上書きさせない)
```

## 4.2 kcs view (過去版閲覧)

```bash
kcs view <evidence-at-commit-X>
kcs view <path> --at <commit>
```

過去 commit 時点の Markdown を再生成せず、当該 commit の object をそのまま返す (re-Markdownize しない)。unit の完成状態・列挙は、当該 commit の tree entry `normalize.manifest_hash` が指す **manifest object** ([03-data-model.md §2.1](03-data-model.md)) で確定する — same-gen partial retry で作業コピー manifest.json が進んでいても、表示は commit 時点の manifest に従う。

# 5. プロセスモデル (常駐なし)

KCS は **常駐 daemon を持たない**。すべての処理は CLI コマンドのプロセス内で完結する。

- interval 発火 (定期 auto snapshot, Phase 4) は OS スケジューラ (launchd / systemd user timer / Task Scheduler) から CLI を起動する委譲方式とする (§8.2)
- idle 検出 (GC on_idle, Phase 4+) も同様に委譲実行時に判定し、KCS 自身は常駐しない (§2.3)
- 同一 `.kcs` に対する多重起動は `.kcs/.lock` で防止する (§6)

# 6. 並行性 / Locking

```text
.kcs/.lock                     プロセスレベル排他 (書き込み系コマンド全般、下記)
.kcs/index/sqlite.db (WAL)     reader と writer の整合性
```

`.kcs/.lock` を取得するコマンド (書き込み系):

```text
kcs index / kcs snapshot (= kcs commit) / kcs tag (refs/tags-v1 更新) / kcs gc / kcs purge /
kcs repair --rebuild-db / kcs repair --verify-objects / kcs move --accept /
kcs batch resume / kcs batch retry / kcs batch abandon / kcs reindex
```

batch 系と reindex は外部副作用 (upload / job 作成) と batch_requests の状態遷移を伴うため lock 必須
([04-pipeline.md §5.8](04-pipeline.md) — 並行 resume が同一行へ別 intent_token を書くと先行 job が
無記録 in-flight になる)。

規約:

- 読み取り系 (search / log / view / open / inspect / evidence verify / restore / status / diff) は `.kcs/.lock` を取得しない。`kcs index` と `kcs search` の同時実行は許容 (SQLite WAL でリーダーは旧スナップショット)。例外的に `kcs search` は vector|hybrid の page 1 に限り cost-ledger.sqlite の device 行 (`scope_id='device'`) への相 1 / stale 回収・剪定の書込を行うが、これも `.kcs/.lock` の対象外である — device 行はどの scope にも属さず、直列化は cost-ledger 側の `BEGIN IMMEDIATE` Tx が担う ([04-pipeline.md §5.4](04-pipeline.md))
- `.kcs/.lock` を取得できない場合、書き込み系コマンドは**待機せず即座に失敗する**: error code `KCS-E-STORE-LOCKED-001`、exit code 3 (retryable、[06-cli-spec.md §7](06-cli-spec.md))。lock ファイルには保持プロセスの pid と取得時刻を記録し、保持プロセスが存在しない stale lock は次の取得試行時に回収してよい。待機オプション (`--wait <seconds>`) は Phase 4+ 予約
- refs (refs/heads/main, canonical refs/tags-v1/*) の更新は `.kcs/.lock` 保持下で、temp file 書き込み + atomic rename により行う (部分書き込みを外部に見せない)。legacy refs/tags/* は read-only compatibility とする
- `kcs repair --verify-objects` の raw object 復旧と repaired commit publication も、同じ lock の下で private temp + hash 再検証 + atomic publish を使う
- `kcs repair --rebuild-db` 実行中の `kcs search` は、再構築完了までの間旧 sqlite.db (存在すれば) を読むか、`KCS-E-INDEX-REBUILDING-001` を返す。再構築の完了も atomic rename (sqlite.db.tmp → sqlite.db) で切り替える
- scope-registry.sqlite / cost-ledger.sqlite (~/.local/share/kcs/) は WAL モード + busy_timeout (デフォルト 5000ms) で複数プロセスの同時書き込みを直列化する。registry は cache であり ([03-data-model.md §4](03-data-model.md))、破損時は各 `.kcs` の rescan で再構築する (**再構築の入力はユーザーが知る探索 root** — registry 喪失後は `.kcs` の所在一覧も失われるため、各 root での `kcs index` 再実行が再登録を兼ねる。KCS が自力で全ディスクを走査することはしない)。cost-ledger.sqlite は**再構築不可の運用台帳** ([03-data-model.md §4.1](03-data-model.md) / [04-pipeline.md §5.4](04-pipeline.md))
- purge の log scrub と通常 append/rotation は、device logs では `$XDG_DATA_HOME/kcs/logs/scrub.lock`、scope access logs では `.kcs/logs/access.scrub.lock` を共有する。複合 lock 順序は scope store → cost-ledger.sqlite (Tx) → device observability → scope access とし、逆順取得を禁止する。**scope 由来 log の append 順序**: 読取系が対象の path / query / raw_hash を含む行を append する場合、当該 append は scrub lock を保持したまま、2 点検査 (§6 — journal 不在 + epoch 不変) の**最終検査と同一 critical section** で行う — scrub 完了後の再 append で purge の削除 postcondition を破らない。最終検査で拒否した場合の記録には対象 path / query / raw_hash を含めない

# 7. 観測 (Observability)

```
~/.local/share/kcs/logs/
  events.jsonl       重要イベント (commit, gc, purge, schema migration)
  metrics.jsonl      数値メトリクス (デフォルト 1h 間隔の集計に加え、下記の per-search 記録)
  errors.jsonl       error_code 付きの全エラー
.kcs/logs/
  access.jsonl       検索アクセスログ (redact_logs はデフォルト true、10-operations.md §12.6)
```

**検索 latency の per-search 記録** (2026-07-03 追記、step3a §C の解消。北極星 §4.1 の p50/p95/p99 計測の一次データ): `kcs search` は 1 回の実行ごとに metrics.jsonl へ 1 行を追記する。行はログ共通 envelope (必須 `ts, level, code, component, message, context`) に従い、metric 固有フィールドを加える — `{ "ts": <UTC>, "level": "info", "code": "KCS-M-SEARCH-001", "component": "search", "message": "search completed", "metric": "search.latency_ms", "value": <実測 ms>, "context": { "mode": <実効 mode>, "scope_count": <検索した scope 数>, "result_count": <返却件数> } }`。redact_logs 既定 (クエリ本文・path は記録しない) に従う。1h 間隔の集計メトリクスはこの一次データから導出してよい。非エラー行の `code` は `KCS-M-<DOMAIN>-<NNN>` (metric) / `KCS-EV-<DOMAIN>-<NNN>` (event) の名前空間を使う — 形式は [06-cli-spec.md §8](06-cli-spec.md) の error_code と同じ規約 (`KCS-E-` は error 専用)。

各行 JSON 必須フィールド: `ts, level, code, component, message, context`。詳細は [10-operations.md §12.6](10-operations.md)。

# 8. Auto Commit

## 8.1 MVP (Phase 1-3) の snapshot 契機

MVP での snapshot 生成契機は次の 3 つのみ (常駐プロセスは持たない、§5):

1. 明示的 `kcs snapshot` / `kcs commit` (commit_type=manual)
2. `kcs index` の成功完了時に同一プロセス内で auto snapshot を作る (commit_type=auto)。ただし tree_hash が現在の HEAD の tree と一致する場合は commit を作らない (no-op、[03-data-model.md §8.2](03-data-model.md))
3. `kcs batch resume` / `kcs batch retry` / `kcs reindex --force` がオンライン成果 (normalized / chunk) を finalize した成功完了時も同様に auto snapshot を作る ([04-pipeline.md §5.4](04-pipeline.md))。derived 成果の変化は tree entry の `manifest_hash` / tree の `chunking_config_hash` / **tree の `chunk_set_hash` (公開 chunk 集合の digest — chunk のみが後着した finalize でも変わる)** を変えるため (tree schema v2/v3 — [03-data-model.md §8](03-data-model.md))、**tree_hash が実際に変わり、no-op 規則 (tree_hash 一致なら commit を作らない) はそのまま成立する** — これが無いと後着の成果が次回 `kcs index` まで検索対象にならないか、manifest 反映済み snapshot が先行したケースで introduction を刻む commit を作れない (§1.6)

**no-op 規則の例外 (2026-07-18 確定)**: (a) **resurrection finalize** (erase / purge 済み raw の再 ingest) は、同一 bytes の再現で tree_hash・chunk_set_hash が HEAD と一致しても publication commit を作る — retire event と introduction を刻む commit が無いと、復活した chunk を検索対象化できないか旧 introduction へ遡及するため。(b) **no-op 判定は tree_hash に加えて commit の `tool_lock_hash` も比較する** — embedding profile のみの更新でも lock が変われば commit を作る (現行 vector index と HEAD の provenance を一致させる)

**snapshot finalize の耐久順序**: (1) chunks.jsonl へ creation / publication event 行を append + fsync → (2) SQLite 反映 → (3) commit / ref publish。(1) と (3) の間の crash で dangling event 行が残った場合、rebuild はそれを無視し ([04-pipeline.md §5.7](04-pipeline.md) と同一条件 — 生存する creation 行 / chunk object を持たない、**または** introduction commit の **object が store に存在しない**行。commit object が存在するが ref 不達の行 (orphan / disconnected — `--at` の正当対象) は無視しない)、次回 finalize が同内容を冪等に再 append する。chunks.jsonl 末尾の不完全行 (torn tail) は切り詰めて無視する (書込は [04-pipeline.md §1.1](04-pipeline.md) の fsync 規律)

## 8.2 定期 Auto Snapshot (Phase 4 範囲)

```text
- ユーザー操作なし時に一定間隔で auto snapshot を作る (commit_type=auto)
- 実行主体は常駐 daemon ではなく、OS スケジューラ (launchd / systemd user timer /
  Task Scheduler) から起動される CLI とする (§5)。多重起動・kcs index との競合は
  .kcs/.lock で排他する (§6)
- snapshot 対象は indexed scope の現在 working tree
- auto commit は tiered retention で減衰する (§2.4)
- manual commit は auto を吸収しない (auto は tiered retention 満了で shallow 化され tree を失うが — ref tip が指すものは除外 (§2.4) — commit object は履歴 DAG の中間点として残る。§2.2)
- tree_hash 不変なら no-op (§8.1 と同じ)
```

`.kcs/config.toml`:

```toml
[snapshot.auto]                 # Phase 4 (定期 auto snapshot)
enabled = true
interval_seconds = 1800     # 30 分ごと
on_change_threshold = 50    # 50 ファイル以上の変更で即時 snapshot
```
