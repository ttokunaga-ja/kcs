```ts
export type CapaNotice = {
  recordNo: string;
  product: "Nagi B2";
  owner: string;
  nextReview: string;
  note: string;
};

export function buildNotice(owner: string): CapaNotice {
  return {
    recordNo: "NC-26-074",
    product: "Nagi B2",
    owner,
    nextReview: "2026-07-24",
    note: "Use the revised first-piece confirmation before extending the change.",
  };
}
```
