```ts
/** 再送キューの設定値を、デプロイ前に軽く検証する。 */
export type RetryPolicy = {
  baseDelayMs: number;
  maxAttempts: number;
  retryableStatuses: number[];
};

export function validateRetryPolicy(policy: RetryPolicy): string[] {
  const issues: string[] = [];
  if (policy.baseDelayMs < 50) issues.push("base delay is too short");
  if (policy.maxAttempts < 1 || policy.maxAttempts > 12) issues.push("attempt count is out of range");
  if (!policy.retryableStatuses.includes(429)) issues.push("rate-limit status is missing");
  return issues;
}

export const defaultRetryPolicy: RetryPolicy = {
  baseDelayMs: 250,
  maxAttempts: 5,
  retryableStatuses: [408, 425, 429, 500, 502, 503],
};
```
