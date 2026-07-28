```json
{
  "project": "Cedar",
  "owner_team": "Applied Foundations",
  "package": "model-beta",
  "role": "robust baseline",
  "collection_revision": "cedar-docs-r12",
  "tokenizer_checksum": "c8e1b6d4",
  "evaluation": {
    "judge_set": "editorial-holdout-v5",
    "duplicate_suppression": true,
    "metrics": [
      "ndcg_at_10",
      "recall_at_100"
    ]
  },
  "release_policy": "retain as rollback target during candidate review"
}
```
