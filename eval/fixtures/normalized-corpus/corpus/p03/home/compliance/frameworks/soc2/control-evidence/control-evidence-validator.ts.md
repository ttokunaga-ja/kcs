```ts
/** SOC 2 証跡の提出前チェック。数値評価ではなく、必要な紐付けの欠落を返す。 */

export type EvidenceItem = {
  control: string;
  system: string;
  collectedAt: string;
  sourceUri: string;
  reviewer?: string;
  status: "ready" | "needs-review" | "rejected";
};

export type EvidenceIssue = {
  sourceUri: string;
  message: string;
};

const supportedControls = new Set(["CC6.1", "CC7.2", "CC8.1"]);

export function validateEvidence(items: ReadonlyArray<EvidenceItem>): EvidenceIssue[] {
  const issues: EvidenceIssue[] = [];
  const seen = new Set<string>();

  for (const item of items) {
    const key = `${item.control}:${item.sourceUri}`;
    if (seen.has(key)) {
      issues.push({ sourceUri: item.sourceUri, message: "同じ証跡が重複しています" });
    }
    seen.add(key);

    if (!supportedControls.has(item.control)) {
      issues.push({ sourceUri: item.sourceUri, message: `対象外のコントロール: ${item.control}` });
    }
    if (!item.system.trim()) {
      issues.push({ sourceUri: item.sourceUri, message: "対象システムが未設定です" });
    }
    if (!/^\d{4}-\d{2}-\d{2}T/.test(item.collectedAt)) {
      issues.push({ sourceUri: item.sourceUri, message: "取得時刻は ISO 8601 で指定してください" });
    }
    if (item.status === "ready" && !item.reviewer?.trim()) {
      issues.push({ sourceUri: item.sourceUri, message: "提出準備完了には確認者が必要です" });
    }
  }

  return issues;
}

export function groupByControl(items: ReadonlyArray<EvidenceItem>): Map<string, EvidenceItem[]> {
  return items.reduce((groups, item) => {
    const existing = groups.get(item.control) ?? [];
    existing.push(item);
    groups.set(item.control, existing);
    return groups;
  }, new Map<string, EvidenceItem[]>());
}
```
