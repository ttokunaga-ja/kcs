```ts
export type AlertRoute = {
  service: "atlas-checkout";
  signal: "edge-error-rate" | "route-skew" | "upstream-latency";
  priority: "high" | "medium";
  recipients: readonly string[];
  runbook: string;
};

export const checkoutAlertRoutes: readonly AlertRoute[] = [
  {
    service: "atlas-checkout",
    signal: "edge-error-rate",
    priority: "high",
    recipients: ["checkout-oncall", "reliability-engineering"],
    runbook: "checkout-edge-errors",
  },
  {
    service: "atlas-checkout",
    signal: "route-skew",
    priority: "high",
    recipients: ["checkout-oncall", "reliability-engineering"],
    runbook: "gateway-route-distribution",
  },
  {
    service: "atlas-checkout",
    signal: "upstream-latency",
    priority: "medium",
    recipients: ["checkout-oncall"],
    runbook: "checkout-upstream-latency",
  },
];

export function contractFor(signal: AlertRoute["signal"]): AlertRoute {
  const route = checkoutAlertRoutes.find((item) => item.signal === signal);
  if (!route) {
    throw new Error(`No checkout alert contract for ${signal}`);
  }
  return route;
}
```
