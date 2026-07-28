# Production gateway module change - 2026-07-12



## Change summary

The Atlas Checkout gateway module was updated to make the edge target group
explicit and to keep the canary listener rule separate from the default route.
The work was prepared by Reliability Engineering for the July production
window.



## Intended behavior

- The checkout edge target group receives the default production route.
- A low-weight listener rule remains available for a controlled canary.
- Health-check settings stay in the shared gateway module and are not copied
  into the checkout service configuration.
- Rollback is a Terraform state change plus listener-rule verification, not a
  service deployment.



## Review note

The plan was reviewed on 2026-07-12. During the following incident review, the
team agreed to retain the module layout and improve the handoff checklist for
gateway changes.
