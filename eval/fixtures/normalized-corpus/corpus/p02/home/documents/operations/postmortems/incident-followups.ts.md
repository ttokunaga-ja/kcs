```ts
export type FollowUp = {
  id: string;
  title: string;
  owner: string;
  due: string;
  status: "open" | "in-progress" | "done";
  evidence: string;
};

export const gatewayIncidentFollowUps: readonly FollowUp[] = [
  {
    id: "RE-842",
    title: "Add a regional upstream-selection comparison to the release dashboard",
    owner: "Priya Shah",
    due: "2026-07-22",
    status: "in-progress",
    evidence: "Dashboard review from the checkout gateway event",
  },
  {
    id: "RE-843",
    title: "Page Checkout On-call for sustained route skew",
    owner: "Jules Ortiz",
    due: "2026-07-20",
    status: "open",
    evidence: "Alert contract review",
  },
  {
    id: "RE-844",
    title: "Rehearse the gateway drain path in staging",
    owner: "Mara Chen",
    due: "2026-07-24",
    status: "open",
    evidence: "Change CHG-4821 retrospective",
  },
];

export function outstanding(items: readonly FollowUp[]): FollowUp[] {
  return items.filter((item) => item.status !== "done");
}
```
