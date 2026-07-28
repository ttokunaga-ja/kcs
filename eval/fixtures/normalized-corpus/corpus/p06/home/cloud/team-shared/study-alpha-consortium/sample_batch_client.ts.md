```ts
export type BatchReceipt = { batchId: string; receivedAt: string; records: number; checksum: string };

export async function fetchBatchReceipt(batchId: string): Promise<BatchReceipt> {
  const url = "/api/assay-batches/" + encodeURIComponent(batchId) + "/receipt";
  const response = await fetch(url);
  if (!response.ok) throw new Error("receipt request failed: " + response.status);
  return (await response.json()) as BatchReceipt;
}

export function isComplete(receipt: BatchReceipt): boolean {
  return receipt.records > 0 && receipt.checksum.length === 64;
}
```
