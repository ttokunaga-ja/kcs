```yaml
project: Cedar
owner_team: Applied Foundations
package: model-beta
role: robust baseline
collection_revision: cedar-docs-r12
required_checks:
  - evaluator_can_load_judge_set
  - duplicate_suppression_enabled
  - tokenizer_checksum_matches
  - rollback_bundle_present
promotion:
  allowed: false
  rationale: retain the baseline while the candidate review remains open
```
