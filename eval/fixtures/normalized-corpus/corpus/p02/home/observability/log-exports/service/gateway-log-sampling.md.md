# Gateway log sampling notes



## Purpose

This export recipe was used to validate the Atlas Checkout gateway route after
the 2026-07-13 patch incident. It samples request logs by route, status class,
and upstream pool without collecting payment payloads.



## Sampling rules

- Use the gateway request ID and route label as the join keys.
- Keep only timestamps, route, status, upstream pool, and latency bucket.
- Read a short window before the route change and a matching window after it.
- Compare request volume and failures against the checkout completion panel.



## Handling

Store temporary exports in the incident staging area and remove them after the
post-incident review. The Rust helper emits aggregate route counts suitable for
an attachment to the operations record.
