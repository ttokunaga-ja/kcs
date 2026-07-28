```ts
/** Ledger Platform のリリース表記を API 応答用にそろえる。 */
export type ReleaseWindow = {
  product: "orchid-ledger" | "poppy-gateway";
  train: string;
  publishedOn: string;
};

export function formatReleaseWindow(window: ReleaseWindow): string {
  const product = window.product === "orchid-ledger" ? "Orchid Ledger" : "Poppy Gateway";
  return `${product} ${window.train} (${window.publishedOn})`;
}

export function isJulyCutover(window: ReleaseWindow): boolean {
  return window.publishedOn.startsWith("2026-07-");
}
```
