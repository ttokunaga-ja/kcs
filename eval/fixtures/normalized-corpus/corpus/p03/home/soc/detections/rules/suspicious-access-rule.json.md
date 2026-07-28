```json
{
  "rule_id": "suspicious-privileged-access",
  "version": "2026.07.3",
  "owner": "security-operations",
  "status": "enabled",
  "description": "通常と異なるネットワークからの管理者操作を検知し、トリアージキューへ送る。",
  "data_source": "operator_hub_access_events",
  "conditions": {
    "all": [
      { "field": "actor.role", "operator": "in", "value": ["operator_admin", "support_admin"] },
      { "field": "network.trust", "operator": "equals", "value": "unrecognized" },
      { "field": "session.mfa", "operator": "equals", "value": true }
    ]
  },
  "group_by": ["actor.id", "network.source", "session.id"],
  "response": {
    "queue": "soc-triage",
    "severity": "high",
    "include_fields": ["actor.id", "actor.role", "network.source", "request.path", "change.id"]
  },
  "suppression": {
    "requires_change_reference": true,
    "maximum_window_minutes": 45
  }
}
```
