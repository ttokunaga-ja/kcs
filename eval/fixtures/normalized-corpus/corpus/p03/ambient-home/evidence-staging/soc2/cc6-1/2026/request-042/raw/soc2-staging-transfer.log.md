```log
2026-07-18T09:12:07.318+09:00 INFO  transfer.begin job=grc-staging-0718-0912 source=s3://nami-evidence-staging/access-review/july/ destination=archive://trust-evidence/q3/access-review/
2026-07-18T09:12:08.044+09:00 INFO  manifest.read manifest=access-review-2026-07-17.jsonl records=3600 schema=v4
2026-07-18T09:12:08.965+09:00 INFO  replay.crosscheck snapshot_records=3600 replay_records=3600 result=matched
2026-07-18T09:12:09.211+09:00 WARN  label.unresolved subject_group=field-contractor count=14 action=queue_for_manual_mapping
2026-07-18T09:12:10.530+09:00 INFO  object.copy prefix=operator-hub/ copied=18 skipped=0 bytes=483912
2026-07-18T09:12:11.007+09:00 INFO  checksum.verify algorithm=sha256 mismatches=0
2026-07-18T09:12:11.226+09:00 INFO  transfer.complete job=grc-staging-0718-0912 duration_ms=3908 review_lane=trust-engineering
```
