```log
2026-07-13T14:22:04Z edge-gw-az2 access request_id=ce8a2f method=POST path=/v2/checkout status=200 upstream=orders-edge-apne1 elapsed_ms=284 route=primary
2026-07-13T14:22:06Z edge-gw-az2 access request_id=ce8a31 method=POST path=/v2/checkout status=200 upstream=orders-edge-apne1 elapsed_ms=301 route=primary
2026-07-13T14:22:09Z edge-gw-az2 access request_id=ce8a44 method=POST path=/v2/checkout status=502 upstream=orders-edge-apne2 elapsed_ms=742 route=primary
2026-07-13T14:22:12Z edge-gw-az2 warn request_id=ce8a52 signal=upstream-selection expected=balanced observed=apne2
2026-07-13T14:22:18Z edge-gw-az2 access request_id=ce8a68 method=POST path=/v2/checkout status=200 upstream=orders-edge-apne2 elapsed_ms=348 route=primary
2026-07-13T14:22:25Z edge-gw-az2 access request_id=ce8a7c method=POST path=/v2/checkout status=200 upstream=orders-edge-apne2 elapsed_ms=366 route=primary
2026-07-13T14:22:33Z edge-gw-az2 info sample_complete requests=6 errors=1 route_skew=0.143
```
