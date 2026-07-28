```log
2026-07-18T08:43:11.107+09:00 INFO  session.open workspace=grc-q3-readiness operator=keiko.s view=access-review-register
2026-07-18T08:43:14.772+09:00 INFO  export.loaded source=operator-hub-q2-access-review rows=3600 checksum=verified
2026-07-18T08:43:17.091+09:00 INFO  filter.applied field=account_type value=privileged result_rows=126
2026-07-18T08:43:22.402+09:00 WARN  reference.missing ticket=GRC-426 field=reviewer_note action=mark_for_follow_up
2026-07-18T08:43:29.615+09:00 INFO  comparison.complete left=snapshot right=replay unmatched=0
2026-07-18T08:43:37.908+09:00 INFO  annotation.saved subject=GRC-426 visibility=team-only
2026-07-18T08:44:01.274+09:00 INFO  session.idle workspace=grc-q3-readiness timeout_seconds=900
```
