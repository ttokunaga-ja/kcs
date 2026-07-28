```yaml
meeting:
  date: 2026-07-14
  group: Product Council
  objective: "Harbor early access の論点を、実装判断と検証判断に分ける"
participants:
  - Harbor Core
  - Research Ops
  - Data Foundations
  - Experience Systems
decisions:
  - topic: "Signal Inbox の初期操作"
    outcome: "手動タグと担当決定を先行する"
    rationale: "利用者の語彙がまだ安定しておらず、推薦の説明責任を持てないため"
    owner: "Harbor Core"
  - topic: "Evidence Link の取り扱い"
    outcome: "確認日と共有範囲を表示する"
    rationale: "引用を残しても、読める人が不明だと引継ぎに使えないため"
    owner: "Research Ops"
open_items:
  - item: "権限差がある根拠の表示方法"
    owner: "Data Foundations"
    review_at: "next technical review"
  - item: "Account Brief の自動補助の範囲"
    owner: "Experience Systems"
    review_at: "after early access observation"
```
