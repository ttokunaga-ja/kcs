```ts
/** 議事録の決定事項から、担当別の follow-up を組み立てる。 */
export type MeetingAction = {
  owner: string;
  summary: string;
  due: string;
  service?: "orchid-ledger" | "poppy-gateway";
};

export function openActions(actions: MeetingAction[], today: string): MeetingAction[] {
  return actions
    .filter((action) => action.due >= today)
    .sort((left, right) => left.due.localeCompare(right.due) || left.owner.localeCompare(right.owner));
}

export function formatAction(action: MeetingAction): string {
  const service = action.service ? ` [${action.service}]` : "";
  return `${action.due} ${action.owner}: ${action.summary}${service}`;
}
```
