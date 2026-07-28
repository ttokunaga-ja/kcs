```ts
/**
 * GRC 共用スペースから参照するコントロール担当の軽量レジストリ。
 * 正式な組織情報は People Directory が正本で、ここは証跡依頼時の振り分け用。
 */

export type ControlOwner = {
  control: string;
  primary: string;
  backup: string;
  serviceBoundary: string;
  evidenceCadence: "monthly" | "quarterly" | "on-demand";
};

const registry: ReadonlyArray<ControlOwner> = [
  {
    control: "CC6.1",
    primary: "trust-engineering@nami-grid.example",
    backup: "identity-platform@nami-grid.example",
    serviceBoundary: "Operator Hub production access",
    evidenceCadence: "monthly",
  },
  {
    control: "CC7.2",
    primary: "security-operations@nami-grid.example",
    backup: "platform-reliability@nami-grid.example",
    serviceBoundary: "Grid Console detection response",
    evidenceCadence: "monthly",
  },
  {
    control: "CC8.1",
    primary: "release-assurance@nami-grid.example",
    backup: "service-owners@nami-grid.example",
    serviceBoundary: "production change approvals",
    evidenceCadence: "quarterly",
  },
];

export function ownerFor(control: string): ControlOwner | undefined {
  return registry.find((entry) => entry.control.toLowerCase() === control.toLowerCase());
}

export function ownersForService(serviceBoundary: string): ReadonlyArray<ControlOwner> {
  return registry.filter((entry) => entry.serviceBoundary === serviceBoundary);
}

export function formatRoutingLine(control: string): string {
  const owner = ownerFor(control);
  if (!owner) return `${control}: routing not registered`;
  return `${owner.control}: ${owner.primary} (backup: ${owner.backup})`;
}
```
