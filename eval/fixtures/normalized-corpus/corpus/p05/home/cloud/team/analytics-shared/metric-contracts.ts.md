```ts
export type MetricContract = {
  metricKey: string;
  grain: string[];
  owner: "sales" | "operations" | "product";
  refreshByJst: string;
  nullableDimensions: string[];
};

export const commercialContracts: MetricContract[] = [
  {
    metricKey: "recognized_net_sales",
    grain: ["business_date", "market_code", "channel"],
    owner: "sales",
    refreshByJst: "06:30",
    nullableDimensions: ["campaign_family"],
  },
  {
    metricKey: "fulfillment_margin",
    grain: ["business_date", "fulfillment_node", "carrier_service"],
    owner: "operations",
    refreshByJst: "07:15",
    nullableDimensions: ["carrier_service"],
  },
];

export function missingDimensions(contract: MetricContract, fields: string[]): string[] {
  const available = new Set(fields);
  return contract.grain.filter((field) => !available.has(field));
}

// 共有 dashboard は contract を参照して、粒度の省略を早めに検知する。
```
