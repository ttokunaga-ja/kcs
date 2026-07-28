```log
2026-07-13T14:28:15Z operator@incident-shell: kubectl -n checkout-prod get pods -l app=checkout-gateway
NAME                                READY   STATUS    RESTARTS   AGE
checkout-gateway-7bb5c8b8cf-kqv8p   2/2     Running   0          2h
checkout-gateway-7bb5c8b8cf-w2m4d   2/2     Running   0          2h
checkout-gateway-7bb5c8b8cf-zm9nr   2/2     Running   0          2h
2026-07-13T14:31:02Z [warn] route-skew=0.146 region=ap-northeast upstream=orders-edge
2026-07-13T14:36:12Z operator@incident-shell: changectl hold CHG-4821 --reason "regional route imbalance"
change CHG-4821 moved to held
2026-07-13T14:48:05Z operator@incident-shell: gatewayctl disable header-normalization --environment production
rule header-normalization disabled in production
2026-07-13T14:52:44Z [info] deployment checkout-gateway rollout started replicas=12
2026-07-13T15:08:14Z [info] edge-error-rate=0.0031 upstream-p95-ms=462 route-skew=0.041
2026-07-13T15:12:00Z operator@incident-shell: incidentctl update INC-2026-0713 --state monitoring
incident INC-2026-0713 is now monitoring
```
