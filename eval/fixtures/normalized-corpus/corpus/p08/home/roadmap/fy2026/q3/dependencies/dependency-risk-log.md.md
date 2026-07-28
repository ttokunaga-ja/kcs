# Dependency risk log

Harbor の Q3 作業は、実装の量より外部チームとの前提合わせに左右される。ここではリスクを完了率ではなく、意思決定に影響する不確実性として残す。

| Dependency | 状態 | 影響 | 次の確認 |
| --- | --- | --- | --- |
| Customer Snapshot API | watching | Account Brief の最新性に影響 | API の更新条件を確認 |
| RBAC review | watching | Evidence Link の見せ方に影響 | 例外ケースを持ち込む |
| Design system tokens | confirmed | empty state の実装速度に影響 | copy の最終レビュー |
| Support coverage | watching | early access の問い合わせ導線に影響 | escalation の dry run |



## 運用メモ

依存が未確定でも、Harbor Core が勝手に仮定して閉じない。A dependency becomes risky when its uncertainty is invisible to the person making the release call.

緩和策は「後で直す」ではなく、どの customer scenario を限定するかまで書く。状況が変わったら、このログと Council の決定記録を同時に更新する。
