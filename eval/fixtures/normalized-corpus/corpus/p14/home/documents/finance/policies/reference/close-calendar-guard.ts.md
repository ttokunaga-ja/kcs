```ts
/**
 * 月次締めカレンダーの締切判定。
 * Orion取込前に、担当者が誤って翌月分を混在させないための画面用ロジック。
 */

export type CloseWindow = {
  month: string;
  receiptCutoff: string;
  postingCutoff: string;
  timezone: "Asia/Tokyo";
};

const WINDOWS: readonly CloseWindow[] = [
  {
    month: "2026-01",
    receiptCutoff: "2026-02-03T18:00:00+09:00",
    postingCutoff: "2026-02-05T12:00:00+09:00",
    timezone: "Asia/Tokyo",
  },
  {
    month: "2026-02",
    receiptCutoff: "2026-03-03T18:00:00+09:00",
    postingCutoff: "2026-03-05T12:00:00+09:00",
    timezone: "Asia/Tokyo",
  },
  {
    month: "2026-03",
    receiptCutoff: "2026-04-03T18:00:00+09:00",
    postingCutoff: "2026-04-07T12:00:00+09:00",
    timezone: "Asia/Tokyo",
  },
];

export function findCloseWindow(month: string): CloseWindow {
  const window = WINDOWS.find((candidate) => candidate.month === month);
  if (!window) {
    throw new Error(`締めカレンダーが未登録です: ${month}`);
  }
  return window;
}

export function canPostAt(month: string, at: Date): boolean {
  const { postingCutoff } = findCloseWindow(month);
  return at.getTime() <= new Date(postingCutoff).getTime();
}
```
