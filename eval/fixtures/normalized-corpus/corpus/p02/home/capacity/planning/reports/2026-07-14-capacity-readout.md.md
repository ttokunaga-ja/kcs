# Q3 Atlas Checkout headroom readout

Prepared for the Reliability Engineering capacity review on 2026-07-14.



## Decision summary

The checkout path has enough steady-state room for the current Q3 demand plan, but the gateway tier should keep one additional worker pool enabled during regional promotions. The 2026-07-13 release showed that a narrow edge imbalance can consume the operational margin before aggregate CPU looks unusual.

| Signal | Recent peak | Planning guardrail | Q3 model |
| --- | ---: | ---: | ---: |
| Completed checkouts / second | 2,840 | 3,600 | 3,180 |
| Gateway CPU per node | 0.62 cores | 0.78 cores | 0.71 cores |
| Queue depth | 420 jobs | 900 jobs | 610 jobs |
| Edge error ratio | 0.34% | 0.80% | 0.46% |



## Assumptions

- The Japan and US traffic curves retain their current offset.
- Cart write volume grows by twelve percent through the final promotion week.
- The payment adapter remains at the present concurrency reservation.
- Cache warm-up is complete before campaign traffic is admitted.



## Follow-up

1. Platform Capacity will reserve the additional gateway pool by 2026-07-22.
2. Checkout On-call will add the regional queue panel to the promotion dashboard.
3. Reliability Engineering will repeat the load replay after the August catalog import.
