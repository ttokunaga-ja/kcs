# Atlas Checkout alternate-route checklist

Use this checklist when edge routing must be deliberately moved away from the normal gateway path during a production event.



## Before changing traffic

- Confirm the incident channel has an active Checkout On-call owner.
- Capture the current edge error ratio, upstream latency, and regional route distribution.
- Pause unrelated production changes affecting checkout, payments, or the edge.
- Verify that the alternate route has healthy capacity in each serving region.



## During the change

1. Apply the route adjustment to one region first.
2. Watch the regional dashboard and the checkout success panel together.
3. Record each control-plane action in the incident timeline.
4. Stop if customer errors or upstream selection diverge from the operating band.



## After stabilization

- Keep the incident in monitoring until two consecutive dashboard checks are normal.
- Save a trace sample and the gateway pod log tail with the incident notes.
- Hand off any unfinished review work to Reliability Engineering.
