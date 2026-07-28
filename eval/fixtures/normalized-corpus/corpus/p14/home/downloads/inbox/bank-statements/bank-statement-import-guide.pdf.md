Shinonome Fulfillment Co., Ltd. | Finance & Accounting

Bank statement reference



Shinonome Fulfillment Co., Ltd. | Finance & Accounting

Bank statement reference



Shinonome Fulfillment Co., Ltd. | Finance & Accounting

Bank statement reference



Shinonome Fulfillment Co., Ltd. | Finance & Accounting Bank statement reference
Bank Statement Import Guide
Monthly close reference for FY2026 Q1 and subsequent cycles
Scope
This guide describes the import and review of bank statements used by the Finance and Accounting team
at Shinonome Fulfillment. It is intended for the operating accounts supporting e-commerce fulfilment, last-mile
delivery and warehouse operations.
Before import
Confirm that the statement file covers a complete bank business day range and that the closing
date matches the review calendar. Save the original file in the restricted inbox folder before opening it in the
reconciliation workbook. Do not rename the bank-delivered file until the source copy is retained.
Check Expected condition
File source Retrieved from the approved banking portal or authenticated bank message.
Period Opening and closing dates align with the month under review.
Account identifier Matches the account register maintained by Treasury.
Currency and format Matches the configured import profile; unexpected fields are reviewed before processing.
Duplicate prevention The source filename, import date and preparer are recorded in the import log.
Security reminder
Store statements only in the designated restricted folder. A working copy may be used for
reconciliation, but it must remain linked to the original source and the prepared output must not contain bank
credentials.
Internal working reference


Shinonome Fulfillment Co., Ltd. | Finance & Accounting Bank statement reference
Cutoff, retention and handoff
Cutoff handling
A transaction appearing after the operational reporting cutoff is not automatically an error.
Determine whether it belongs to the bank statement period, the accounting period, or the next review cycle.
Record the decision with the evidence used, especially when the bank posting date differs from the underlying
service date.
Retention package
For each completed month, retain the original statement, the import log, the reconciliation
output, the exception list and the reviewer confirmation. The reference should permit a future reviewer to identify
who imported the file, when it was imported, and why any unmatched item was resolved or deferred.
Handoff notes
Pending items are discussed at the close review and assigned to Finance, Treasury, Procurement
or the relevant operational owner. Do not carry a vague “to investigate” note into the next month; include the
account, evidence gap, owner and expected follow-up date.
Monthly close checklist
Mark the bank statement control complete only after the working queue agrees with
the documented reconciliation output and all material exceptions have an assigned outcome. Keep the completed
checklist with the Q1 close evidence, not in the downloads inbox.
Internal working reference


Shinonome Fulfillment Co., Ltd. | Finance & Accounting Bank statement reference
Import and reconciliation workflow
1. Prepare the file
Check the delimiter, date convention and account currency. If a bank changes its header
order or adds a new column, stop the import and compare the new layout with the approved profile.
2. Load to the reconciliation queue
Select the period and the account identifier, then upload the untouched
bank source. Record the importer name, timestamp and file reference in the queue log. Rejected rows should be
exported to an exception list rather than repaired directly in the source file.
3. Match transactions
Match recurring vendor payments to the approved supplier register and review unusual
references separately. Payments connected with Shinonome Transport, Mizuho Logistics and Kasumigaseki Data
Center should be checked against the corresponding invoice or contract evidence.
Exception Typical cause Required action
Unmatched payment Reference differs from
invoice
Confirm vendor, service month and approval before clearing.
Duplicate line Bank resend or repeat
import
Retain both source references and reverse only after review.
Unknown fee New bank charge or
service change
Obtain Treasury confirmation and record accounting treat-
ment.
Date mismatch Cutoff falls on a bank
holiday
Link the transaction to the documented close cutoff.
4. Review the outcome
The preparer verifies all exception categories. The reviewer traces a sample of cleared
items back to the statement and source documentation, then records approval in the monthly close checklist.
Internal working reference


## Bank Statement Import Guide

*Monthly close reference for FY2026 Q1 and subsequent cycles*

**Scope** This guide describes the import and review of bank statements used by the Finance and Accounting team at Shinonome Fulfillment. It is intended for the operating accounts supporting e-commerce fulfilment, last-mile delivery and warehouse operations.

**Before import** Confirm that the statement file covers a complete bank business day range and that the closing date matches the review calendar. Save the original file in the restricted inbox folder before opening it in the reconciliation workbook. Do not rename the bank-delivered file until the source copy is retained.

|  Check | Expected condition  |
| --- | --- |
|  File source | Retrieved from the approved banking portal or authenticated bank message.  |
|  Period | Opening and closing dates align with the month under review.  |
|  Account identifier | Matches the account register maintained by Treasury.  |
|  Currency and format | Matches the configured import profile; unexpected fields are reviewed before processing.  |
|  Duplicate prevention | The source filename, import date and preparer are recorded in the import log.  |

**Security reminder** Store statements only in the designated restricted folder. A working copy may be used for reconciliation, but it must remain linked to the original source and the prepared output must not contain bank credentials.

Internal working reference

## Cutoff, retention and handoff

**Cutoff handling** A transaction appearing after the operational reporting cutoff is not automatically an error. Determine whether it belongs to the bank statement period, the accounting period, or the next review cycle. Record the decision with the evidence used, especially when the bank posting date differs from the underlying service date.

**Retention package** For each completed month, retain the original statement, the import log, the reconciliation output, the exception list and the reviewer confirmation. The reference should permit a future reviewer to identify who imported the file, when it was imported, and why any unmatched item was resolved or deferred.

**Handoff notes** Pending items are discussed at the close review and assigned to Finance, Treasury, Procurement or the relevant operational owner. Do not carry a vague “to investigate” note into the next month; include the account, evidence gap, owner and expected follow-up date.

**Monthly close checklist** Mark the bank statement control complete only after the working queue agrees with the documented reconciliation output and all material exceptions have an assigned outcome. Keep the completed checklist with the Q1 close evidence, not in the downloads inbox.

Internal working reference

## Import and reconciliation workflow

**1. Prepare the file** Check the delimiter, date convention and account currency. If a bank changes its header order or adds a new column, stop the import and compare the new layout with the approved profile.

**2. Load to the reconciliation queue** Select the period and the account identifier, then upload the untouched bank source. Record the importer name, timestamp and file reference in the queue log. Rejected rows should be exported to an exception list rather than repaired directly in the source file.

**3. Match transactions** Match recurring vendor payments to the approved supplier register and review unusual references separately. Payments connected with Shinonome Transport, Mizuho Logistics and Kasumigaseki Data Center should be checked against the corresponding invoice or contract evidence.

|  Exception | Typical cause | Required action  |
| --- | --- | --- |
|  Unmatched payment | Reference differs from invoice | Confirm vendor, service month and approval before clearing.  |
|  Duplicate line | Bank resend or repeat import | Retain both source references and reverse only after review.  |
|  Unknown fee | New bank charge or service change | Obtain Treasury confirmation and record accounting treatment.  |
|  Date mismatch | Cutoff falls on a bank holiday | Link the transaction to the documented close cutoff.  |

**4. Review the outcome** The preparer verifies all exception categories. The reviewer traces a sample of cleared items back to the statement and source documentation, then records approval in the monthly close checklist.

Internal working reference