```ts
type Stage = {
  name: string;
  trafficFraction: number;
  observeForSeconds: number;
};

type SignalSnapshot = {
  edgeErrorRate: number;
  upstreamP95Ms: number;
  routeSkew: number;
};

const stages: readonly Stage[] = [
  { name: "single-zone", trafficFraction: 0.02, observeForSeconds: 600 },
  { name: "regional", trafficFraction: 0.05, observeForSeconds: 720 },
  { name: "global", trafficFraction: 0.1, observeForSeconds: 900 },
];

export function shouldHold(snapshot: SignalSnapshot): boolean {
  return (
    snapshot.edgeErrorRate > 0.008 ||
    snapshot.upstreamP95Ms > 780 ||
    snapshot.routeSkew > 0.12
  );
}

export function rolloutPlan(changeId: string): Record<string, unknown> {
  return {
    changeId,
    service: "atlas-checkout",
    component: "checkout-gateway",
    owner: "Reliability Engineering",
    stages,
    rollback: {
      action: "disable header-normalization rule and drain new gateway pods",
      notify: ["checkout-oncall", "reliability-engineering"],
    },
  };
}
```
