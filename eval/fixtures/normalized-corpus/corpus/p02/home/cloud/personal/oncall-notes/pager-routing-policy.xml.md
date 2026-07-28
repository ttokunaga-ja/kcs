```xml
<?xml version="1.0" encoding="UTF-8"?>
<routingPolicy name="checkout-production" version="4">
  <service id="atlas-checkout" displayName="Atlas Checkout">
    <primary team="checkout-oncall" schedule="checkout-primary" />
    <secondary team="reliability-engineering" schedule="reliability-secondary" />
    <escalation afterSeconds="600" target="checkout-duty-manager" />
  </service>
  <rule id="edge-error-rate">
    <match label="component" value="checkout-gateway" />
    <match label="environment" value="production" />
    <route target="checkout-oncall" urgency="high" />
  </rule>
  <rule id="route-skew">
    <match label="signal" value="upstream-selection" />
    <route target="reliability-engineering" urgency="high" />
  </rule>
</routingPolicy>
```
