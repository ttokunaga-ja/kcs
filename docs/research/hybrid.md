# Hybrid Search Research Notes

> Status: integrated
> Canonical refs: [../05-runtime.md](../05-runtime.md), [../06-cli-spec.md](../06-cli-spec.md)

---

# 結論

デフォルト検索は `auto`。vector が使えるなら hybrid、使えなければ text に fallback する。

```text
auto:
  FTS5 + vector が使える → hybrid
  vector 不可             → text

text:
  FTS5 のみ

vector:
  vector のみ。不可なら error

hybrid:
  FTS5 + vector。不可時の fallback は設定で制御
```

# fallback

```text
kcs search:
  text fallback 可。warning を返す。

kcs search --text:
  常に text。

kcs search --vector:
  vector 不可なら error。

kcs search --hybrid:
  設定に従い fallback または error。
```

fallback は黙って行わず、CLI / JSON response / observability log に残す。

# fusion

FTS5 と vector の結果は RRF (Reciprocal Rank Fusion) を基本に統合する。score の絶対値を直接混ぜない。

```text
final_rank = RRF(text_rank, vector_rank)
```

# diversity

検索結果は MMR / dedup を使って、同一 raw、同一 chunk、近すぎる semantic_fingerprint の重複を抑える。

# cursor

ページング cursor は opaque にし、対象 snapshot と last position を含める。

```text
cursor = opaque(snapshot_id, last_score, last_chunk_id)
```

index 更新があっても同じ snapshot 内では順序が安定する。

# `--at`

`--at <commit>` は指定 snapshot 時点で存在した chunk を検索する。過去 snapshot の embedding profile が現在と互換しない場合、vector は使わず text fallback または error。

# Agent response

検索結果には Agent が引用検証できる情報を含める。

```text
chunk_id
score
mode_used
fallback_reason
evidence_pointer
snapshot_at
source_path
span
```

# 正本へ移した内容

```text
search runtime / fallback / cursor    → 05-runtime.md
CLI flags                             → 06-cli-spec.md
Evidence Pointer response             → 08-evidence-pointer-spec.md
```
