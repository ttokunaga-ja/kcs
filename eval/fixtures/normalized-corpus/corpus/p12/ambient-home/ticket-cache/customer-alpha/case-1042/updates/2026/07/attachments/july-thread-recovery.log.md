```log
2026-07-08T08:42:11+09:00 INFO  thread-recovery case=HLW-1042 stage=scan message="転記ログを確認" messages=14 attachments=2
2026-07-08T08:42:12+09:00 INFO  thread-recovery case=HLW-1042 stage=dedupe message="重複したメールを除外" retained=13 duplicate_message=mail-8814
2026-07-08T08:42:12+09:00 WARN  thread-recovery case=HLW-1042 stage=ordering message="受信時刻がない行はヘッダー日時を採用" missing_received_at=1
2026-07-08T08:42:13+09:00 INFO  thread-recovery case=HLW-1042 stage=normalize message="会話順に整列" timezone=Asia/Tokyo participants=4
2026-07-08T08:42:13+09:00 INFO  thread-recovery case=HLW-1042 stage=write message="確認用キャッシュを保存" cache_file=conversation-2026-07-08.ndjson
2026-07-08T08:42:13+09:00 INFO  thread-recovery case=HLW-1042 result=completed message="担当者確認待ち" review_flag=message-order
```
