```ts
/** 設定スニペットをレビュー共有用にマスクする。 */
const SENSITIVE_KEYS = new Set(["authorization", "x-signature", "client_secret", "api_key"]);

export function redactHeaders(headers: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(headers).map(([key, value]) => [
      key,
      SENSITIVE_KEYS.has(key.toLowerCase()) ? "[redacted]" : value,
    ]),
  );
}

export function sanitizeCallbackUrl(rawUrl: string): string {
  const url = new URL(rawUrl);
  url.search = "";
  return url.toString();
}
```
