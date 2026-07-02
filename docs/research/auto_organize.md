# Auto Organize Research Notes

> Status: reviewed
> Canonical refs: none yet. Phase 4+ concept.

---

# 位置づけ

自動整理は MVP 必須ではない。Phase 4+ で、KCS の index / embedding / folder profile を使って分類候補を出す構想。

Agent がなくても成立する。Agent は理由説明や複雑な再編に効くが、基礎はローカル検索・類似度・履歴で足りる。

# 基本フロー

```text
new file
  → markdownize
  → index / embedding
  → folder profile と比較
  → move / tag candidate を inbox に出す
  → user accept / reject
  → feedback を保存
```

# folder profile

```text
Folder Profile =
  embedding centroid
  frequent keywords
  heading list
  MIME distribution
  recent accepted moves
```

embedding profile が違うものは混ぜない。`(dimensions, distance, modality, profile_hash)` ごとに subprofile を持つ。

# score

```text
semantic_similarity: cosine を [0,1] に変換
keyword_overlap:    Jaccard
file_type_match:    MIME distribution match
recency:            exp(-days_since_last_match / tau)

score = 0.50 * semantic_similarity
      + 0.20 * keyword_overlap
      + 0.20 * file_type_match
      + 0.10 * recency
```

# threshold

```text
score >= 0.85:
  auto-mode 時のみ自動移動候補。それ以外は top suggestion。

0.65 <= score < 0.85:
  提案として表示。

score < 0.65:
  表示しない。
```

# feedback

```text
accept / reject を保存する。
precision@1 と recall@3 を見る。
reject された file-folder pair は一定時間 negative cache。
移動直後は再提案を抑制してループを避ける。
```

# CLI 案

```bash
kcs inbox
kcs move --accept <id>
kcs move --reject <id>
```

# MVP へ混ぜない理由

北極星シナリオ 3 つに直接必要ではない。基盤ができた後に、Downloads watch / inbox / auto snapshot と一緒に扱う。
