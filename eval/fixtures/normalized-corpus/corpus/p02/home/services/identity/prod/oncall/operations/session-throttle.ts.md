```ts
type SessionPressure = {
  activeSessions: number;
  authErrorRate: number;
  gatewayHealthy: boolean;
};

export type ThrottleDecision = "open" | "soft-limit" | "hold";

export function decideSessionThrottle(pressure: SessionPressure): ThrottleDecision {
  if (!pressure.gatewayHealthy && pressure.authErrorRate > 0.02) {
    return "hold";
  }

  if (pressure.activeSessions > 42000 || pressure.authErrorRate > 0.01) {
    return "soft-limit";
  }

  return "open";
}

export function retryAfterSeconds(decision: ThrottleDecision): number {
  switch (decision) {
    case "hold":
      return 30;
    case "soft-limit":
      return 5;
    case "open":
      return 0;
  }
}
```
