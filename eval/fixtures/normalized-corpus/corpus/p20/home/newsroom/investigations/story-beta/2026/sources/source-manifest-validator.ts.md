```ts
type SourceRow = { label: string; origin: string; receivedOn: string };

export function validateSourceRows(rows: SourceRow[]): string[] {
  const issues: string[] = [];
  for (const row of rows) {
    if (!row.label.trim()) issues.push("missing label");
    if (!row.origin.trim()) issues.push(`missing origin for ${row.label}`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(row.receivedOn)) {
      issues.push(`invalid received date for ${row.label}`);
    }
  }
  return issues;
}
```
