```ts
export type MetricSummary = {
  package: string;
  metric: "ndcg_at_10" | "recall_at_100";
  value: number;
  collectionRevision: string;
};

export function formatMetric(summary: MetricSummary): string {
  return summary.package + " " + summary.metric + "="
    + summary.value.toFixed(3) + " (" + summary.collectionRevision + ")";
}
```
