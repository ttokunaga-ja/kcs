```ts
export type ActionStatus = "open" | "in_progress" | "done" | "blocked";

export interface QbrAction {
  account: "Customer Alpha";
  title: string;
  owner: string;
  dueOn: string;
  status: ActionStatus;
  note?: string;
}

export interface ActionSummary {
  owner: string;
  openCount: number;
  nearestDueOn?: string;
  titles: string[];
}

/** QBR後の対応を担当者ごとにまとめ、定例の確認に使う。 */
export function rollupQbrActions(actions: readonly QbrAction[]): ActionSummary[] {
  const byOwner = new Map<string, QbrAction[]>();

  for (const action of actions) {
    if (action.status === "done") continue;
    const current = byOwner.get(action.owner) ?? [];
    current.push(action);
    byOwner.set(action.owner, current);
  }

  return [...byOwner.entries()]
    .map(([owner, owned]) => {
      const ordered = [...owned].sort((left, right) =>
        left.dueOn.localeCompare(right.dueOn),
      );
      return {
        owner,
        openCount: ordered.length,
        nearestDueOn: ordered[0]?.dueOn,
        titles: ordered.map((action) => action.title),
      };
    })
    .sort((left, right) => left.owner.localeCompare(right.owner, "ja"));
}
```
