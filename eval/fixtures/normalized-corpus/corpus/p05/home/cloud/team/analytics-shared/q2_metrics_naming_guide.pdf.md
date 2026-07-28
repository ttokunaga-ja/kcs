Harborline Commerce | Commercial Intelligence

Shared analytics guide



Harborline Commerce | Commercial Intelligence

Shared analytics guide

CONVENTION 02 | DIMENSIONS



Harborline Commerce | Commercial Intelligence

Shared analytics guide

SHARED CONVENTION | FY2026 Q2



Harborline Commerce | Commercial Intelligence
Shared analytics guide
CONVENTION 01 | MEASURES
Names for measures and rates
Recommended vocabulary
T erm
Use when
Example
gross
Before discounts, returns, or fees
gross_sales_jpy
net
After the documented adjustments
net_sales_jpy
eligible
The denominator is intentionally re-
stricted
eligible_checkout_sessions
completed
The event reached its terminal business
state
completed_orders
rate
A numerator divided by an explicit de-
nominator
checkout_completion_rate
Descriptions travel with the name
Every published measure needs a one-sentence description written for a reviewer who did not build the model.
It should say the population, timing, and material exclusions. For example, a rate is not suﬃciently described by
the word “conversion” alone; the reader must be able to identify the starting population without opening SQL.
Avoid implementation leakage
Warehouse table aliases, temporary campaign labels, and vendor ﬁeld names change more often than metrics
do. Keep those details in model documentation. A semantic name should survive a backend migration without
requiring a dashboard rewrite.
Naming is a contract between the model and its readers
2 / 3


Harborline Commerce | Commercial Intelligence
Shared analytics guide
CONVENTION 02 | DIMENSIONS
Dimensions, dates, and review workﬂow
Dimension names
Use singular names for a single attribute and compound names only when the second word changes the meaning.
Examples include
store_region
sales_channel
, and
product_family
. Avoid abbreviations unless they are
already established in the reporting vocabulary.
Date ﬁelds
business_date
Calendar day used for commercial performance reporting.
order_created_at
Timestamp when an order was ﬁrst submitted.
settlement_date
Date assigned by the payment settlement process.
snapshot_at
Timestamp indicating when a derived table was materialized.
Review checklist
•
Read the name aloud in a dashboard title. If it sounds like a query fragment, simplify it.
•
Conﬁrm that labels and model names use the same core noun.
•
Add a short description before promoting a metric to the shared layer.
•
Record a deﬁnition change in the monthly review notes rather than silently changing an established label.
Harborline Storefront • Q2 reporting conventions
3 / 3


Harborline Commerce | Commercial Intelligence
Shared analytics guide
SHARED CONVENTION | FY2026 Q2
Metrics naming guide
A practical convention for the Harborline Storefront semantic layer
Purpose
Make published metrics recognizable across dashboard tiles, scheduled extracts, and analyst
notebooks. This guide covers names, not business approval.
The basic shape
Use a name that states the measure, population, and grain. Prefer stable nouns over implementation details.
Good
net_sales_daily
checkout_completed_orders
active_stores_month_end
Avoid
sales_v2
final_metric
dashboard_number
Use plural nouns
Counts of entities:
orders
stores
customers
Use unit suﬃxes
Rates and currency:
conversion_rate
net_sales_jpy
Before publishing
1.
Check whether a shared deﬁnition already exists.
2.
State the time basis when it changes the meaning: business date, fulﬁllment date, or settlement date.
3.
Put exclusions in the description, not in an opaque suﬃx.
Maintained by Commercial Intelligence • Shared analytics workspace
1 / 3


# CONVENTION 01 | MEASURES



# Dimensions, dates, and review workflow



# Names for measures and rates



# Metrics naming guide

A practical convention for the Harborline Storefront semantic layer

**Purpose** Make published metrics recognizable across dashboard tiles, scheduled extracts, and analyst notebooks. This guide covers names, not business approval.



## Recommended vocabulary

|  Term | Use when | Example  |
| --- | --- | --- |
|  gross | Before discounts, returns, or fees | gross_sales_jpy  |
|  net | After the documented adjustments | net_sales_jpy  |
|  eligible | The denominator is intentionally restricted | eligible_checkout_sessions  |
|  completed | The event reached its terminal business state | completed_orders  |
|  rate | A numerator divided by an explicit denominator | checkout_completion_rate  |



## Dimension names

Use singular names for a single attribute and compound names only when the second word changes the meaning. Examples include store_region, sales_channel, and product_family. Avoid abbreviations unless they are already established in the reporting vocabulary.



## The basic shape

Use a name that states the measure, population, and grain. Prefer stable nouns over implementation details.

|  **Good** | net_sales_daily, checkout_completed_orders, active_stores_month_end  |
| --- | --- |
|  **Avoid** | sales_v2, final_metric, dashboard_number  |
|  **Use plural nouns** | Counts of entities: orders, stores, customers  |
|  **Use unit suffixes** | Rates and currency: conversion_rate, net_sales_jpy  |



## Date fields

|  business_date | Calendar day used for commercial performance reporting.  |
| --- | --- |
|  order_created_at | Timestamp when an order was first submitted.  |
|  settlement_date | Date assigned by the payment settlement process.  |
|  snapshot_at | Timestamp indicating when a derived table was materialized.  |



## Descriptions travel with the name

Every published measure needs a one-sentence description written for a reviewer who did not build the model. It should say the population, timing, and material exclusions. For example, a rate is not sufficiently described by the word “conversion” alone; the reader must be able to identify the starting population without opening SQL.



## Review checklist

- Read the name aloud in a dashboard title. If it sounds like a query fragment, simplify it.
- Confirm that labels and model names use the same core noun.
- Add a short description before promoting a metric to the shared layer.
- Record a definition change in the monthly review notes rather than silently changing an established label.

Harborline Storefront • Q2 reporting conventions

3 / 3

## Before publishing

1. Check whether a shared definition already exists.
2. State the time basis when it changes the meaning: business date, fulfillment date, or settlement date.
3. Put exclusions in the description, not in an opaque suffix.

Maintained by Commercial Intelligence • Shared analytics workspace

1 / 3

## Avoid implementation leakage

Warehouse table aliases, temporary campaign labels, and vendor field names change more often than metrics do. Keep those details in model documentation. A semantic name should survive a backend migration without requiring a dashboard rewrite.

Naming is a contract between the model and its readers

2 / 3