```log
2026-07-17T18:02:14.022+09:00 INFO  deploy.start rule=suspicious-privileged-access version=2026.07.3 environment=staging
2026-07-17T18:02:15.408+09:00 INFO  parser.compile source=access-event-v5 result=success
2026-07-17T18:02:16.773+09:00 INFO  test.run rule_set=operator-hub-admin-events expected_alerts=3 observed_alerts=3
2026-07-17T18:02:18.020+09:00 WARN  suppression.review rule=contractor-maintenance-window status=expires_with_change_window
2026-07-17T18:02:20.614+09:00 INFO  deploy.promote rule=suspicious-privileged-access environment=production change=CHG-2026-311
2026-07-17T18:02:21.192+09:00 INFO  audit.write actor=security-operations result=complete
```
