```ts
export type SemanticField = {
  key: string;
  labelJa: string;
  grain: readonly string[];
  description: string;
};

export const fields: readonly SemanticField[] = [
  {
    key: "recognized_net_sales",
    labelJa: "確定純売上",
    grain: ["business_date", "market_code", "channel"],
    description: "会計確定後の売上。取消は確定日で反映する。",
  },
  {
    key: "active_buyers",
    labelJa: "アクティブ購入者",
    grain: ["business_date", "channel"],
    description: "対象日に少なくとも一度注文したユニーク buyer。",
  },
];

export function getField(key: string): SemanticField {
  const field = fields.find((candidate) => candidate.key === key);
  if (!field) throw new Error(`Unknown semantic field: ${key}`);
  return field;
}
```
