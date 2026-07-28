```ts
/** 依頼を安全に再試行できる最低限のヘッダを確認する。 */
export type RequestHeaders = Record<string, string | undefined>;

export function missingIdempotencyHeaders(headers: RequestHeaders): string[] {
  const normalized = new Map(Object.entries(headers).map(([key, value]) => [key.toLowerCase(), value]));
  const required = ["idempotency-key", "x-request-id"];
  return required.filter((key) => !normalized.get(key)?.trim());
}

export function hasJsonContentType(headers: RequestHeaders): boolean {
  return (headers["content-type"] ?? headers["Content-Type"] ?? "")
    .toLowerCase()
    .includes("application/json");
}
```
