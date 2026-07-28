```ts
export type LeaderboardRow = {
  package: "model-alpha" | "model-beta";
  metric: string;
  value: number;
};

export function candidateMinusBaseline(rows: LeaderboardRow[]): number {
  const values = new Map(rows.map((row) => [row.package, row.value]));
  const candidate = values.get("model-alpha");
  const baseline = values.get("model-beta");
  if (candidate === undefined || baseline === undefined) {
    throw new Error("Cedar comparison requires candidate and baseline rows");
  }
  return candidate - baseline;
}
```
