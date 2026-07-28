Harborline Commerce | Commercial Intelligence

Export package reference

EXPORT PACKAGE REFERENCE | FY2026 Q2



Harborline Commerce | Commercial Intelligence

Export package reference

FIELD MAP | SUMMARY BLOCK



Harborline Commerce | Commercial Intelligence

Export package reference

RECONCILIATION FLOW | CLOSE ROUTINE



Harborline Commerce | Commercial Intelligence
Export package reference
EXPORT PACKAGE REFERENCE | FY2026 Q2
Vendor settlement layout
Field guide for Harborline Storefront reconciliation extracts
Scope
This reference describes the analyst-facing export used to review settlement totals before the
monthly close. It is not a vendor interface speciﬁcation.
File anatomy
The package is organized as a compact header, a daily summary block, and transaction-level support rows.
Each export must be readable without a separate schema lookup, so column labels favor business language
over source-system abbreviations.
Header block
Reporting period, source refresh timestamp, currency, and extract owner.
Summary block
Daily settlement totals by payment provider and sales channel.
Support rows
Adjustment category, reference key, original amount, and reconciled amount.
Layout principles
1.
Keep one commercial concept per column.
2.
Place signed adjustments beside the original amount, not in a distant appendix.
3.
Preserve provider reference keys exactly as delivered so the operations team can trace a question.
Commercial Intelligence • Reconciliation reference
1 / 3


Harborline Commerce | Commercial Intelligence
Export package reference
FIELD MAP | SUMMARY BLOCK
Required reporting ﬁelds
Columns used in review
Column
Format
Review use
settlement_date
ISO calendar date
Aligns provider activity to the reconciliation calendar.
provider_name
T ext label
Separates payment partner totals.
sales_channel
Controlled label
Allows comparison with storefront reporting.
gross_amount_jpy
Currency
Starting amount before fees and adjustments.
fee_amount_jpy
Signed currency
Charges retained by the provider.
net_settled_jpy
Currency
Amount expected in the settlement statement.
adjustment_reason
T ext label
Explains refund, correction, or timing movement.
Presentation rules
Amounts are exported as numeric ﬁelds, not formatted strings. Display formatting belongs in the review sheet
so downstream checks can distinguish a zero from a missing value. A negative adjustment uses the accounting
sign and never parentheses in the raw extract.
Use the same date basis across the summary and support rows
2 / 3


Harborline Commerce | Commercial Intelligence
Export package reference
RECONCILIATION FLOW | CLOSE ROUTINE
How analysts use the package
Review sequence
1.
Compare the summary block to the daily storefront ledger at the same settlement date.
2.
Investigate material movements by provider before grouping them into a monthly explanation.
3.
Use support rows to distinguish processing fees from customer refunds and operational corrections.
4.
Mark unresolved timing diﬀerences for follow-up; do not force a balancing entry in the export.
Hand-oﬀ notes
When a layout change is needed, retain the existing columns for one close cycle and document the new ﬁeld
in the shared analytics guide. The export should remain stable enough for recurring reviewers while allowing an
explicit migration path for data operations.
Practical check
The total of support rows should explain the diﬀerence between gross activity and the
amount expected from the payment provider. If it does not, ﬁrst verify the reporting window and late-
arriving adjustments.
Harborline Storefront • Monthly settlement review
3 / 3


# Required reporting fields



# How analysts use the package



# Vendor settlement layout

Field guide for Harborline Storefront reconciliation extracts

**Scope** This reference describes the analyst-facing export used to review settlement totals before the monthly close. It is not a vendor interface specification.



## Columns used in review

|  Column | Format | Review use  |
| --- | --- | --- |
|  settlement_date | ISO calendar date | Aligns provider activity to the reconciliation calendar.  |
|  provider_name | Text label | Separates payment partner totals.  |
|  sales_channel | Controlled label | Allows comparison with storefront reporting.  |
|  gross_amount_jpy | Currency | Starting amount before fees and adjustments.  |
|  fee_amount_jpy | Signed currency | Charges retained by the provider.  |
|  net_settled_jpy | Currency | Amount expected in the settlement statement.  |
|  adjustment_reason | Text label | Explains refund, correction, or timing movement.  |



## Review sequence

1. Compare the summary block to the daily storefront ledger at the same settlement date.
2. Investigate material movements by provider before grouping them into a monthly explanation.
3. Use support rows to distinguish processing fees from customer refunds and operational corrections.
4. Mark unresolved timing differences for follow-up; do not force a balancing entry in the export.



## File anatomy

The package is organized as a compact header, a daily summary block, and transaction-level support rows. Each export must be readable without a separate schema lookup, so column labels favor business language over source-system abbreviations.

|  **Header block** | Reporting period, source refresh timestamp, currency, and extract owner.  |
| --- | --- |
|  **Summary block** | Daily settlement totals by payment provider and sales channel.  |
|  **Support rows** | Adjustment category, reference key, original amount, and reconciled amount.  |



## Hand-off notes

When a layout change is needed, retain the existing columns for one close cycle and document the new field in the shared analytics guide. The export should remain stable enough for recurring reviewers while allowing an explicit migration path for data operations.

**Practical check** The total of support rows should explain the difference between gross activity and the amount expected from the payment provider. If it does not, first verify the reporting window and late-arriving adjustments.

Harborline Storefront • Monthly settlement review

3 / 3

## Presentation rules

Amounts are exported as numeric fields, not formatted strings. Display formatting belongs in the review sheet so downstream checks can distinguish a zero from a missing value. A negative adjustment uses the accounting sign and never parentheses in the raw extract.

Use the same date basis across the summary and support rows

2 / 3

## Layout principles

1. Keep one commercial concept per column.
2. Place signed adjustments beside the original amount, not in a distant appendix.
3. Preserve provider reference keys exactly as delivered so the operations team can trace a question.

Commercial Intelligence • Reconciliation reference

1 / 3