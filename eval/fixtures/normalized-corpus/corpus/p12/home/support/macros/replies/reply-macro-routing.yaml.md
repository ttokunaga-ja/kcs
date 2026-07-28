```yaml
version: 1
updated_at: "2026-07-14T15:40:00+09:00"
product: "Harborline Workspace"
default_locale: ja-JP
routes:
  - when:
      category: workspace-switching
      condition: permission-refresh-followed-by-delay
    reply_macro: acknowledge-switching-delay-ja
    owner: support-on-call
    include:
      - reconnect-guidance
      - request-occurrence-time
    exclude:
      - root-cause-commitment
      - configuration-change-request
  - when:
      category: invite-delivery
      condition: duplicate-or-missing-invite
    reply_macro: invite-audit-request-ja
    owner: account-support
    include:
      - audit-window-request
      - recipient-domain-check
    exclude:
      - workspace-switching-workaround
  - when:
      category: attachment-handling
      condition: capture-contains-third-party-identifiers
    reply_macro: attachment-permission-followup-ja
    owner: support-on-call
    include:
      - limited-sharing-explanation
    exclude:
      - attachment-forwarding
review:
  cadence: weekly
  reviewer_group: support-quality
```
