# Domain Model

## Core DocTypes

### Italy Tax Configuration

Company-scoped configuration for Italian tax and finance behavior.

Key fields:

- company
- enabled flag
- VAT cadence:
  - `monthly`
  - `quarterly`
- first managed period start date
- settlement journal series
- VAT output account
- VAT input account
- VAT payable account
- VAT credit account
- quarterly interest account
- carry-forward account
- default tax payment mode
- include payroll in cash planning
- employee-cost source mode:
  - `hrms_payroll`
  - `accounting_entries`
  - `manual_adjustments`

Rules:

- one active configuration per company
- account references must belong to the configured company
- cadence drives VAT period generation rules

### VAT Period

Canonical record for one VAT reporting period for a company.

Key fields:

- company
- tax configuration
- fiscal year
- cadence
- period label
- period start date
- period end date
- due date
- status:
  - `open`
  - `draft`
  - `calculated`
  - `posted`
  - `closed`
- previous credit brought forward
- output VAT total
- input VAT total
- deductible VAT adjustments
- non-deductible VAT adjustments
- quarterly interest amount
- final payable amount
- final credit amount
- linked settlement entry

Rules:

- one VAT period per `(company, start_date, end_date, cadence)`
- posted periods must be immutable except for explicit corrective workflow
- every computed amount must be reproducible from source data plus stored manual adjustments

### VAT Adjustment

Append-only manual adjustment lines tied to a VAT period.

Key fields:

- parent VAT period
- adjustment type
- direction:
  - `increase_payable`
  - `decrease_payable`
  - `increase_credit`
  - `decrease_credit`
- reason
- amount
- reference doctype / name
- notes

Rules:

- adjustments are explicit, never implied
- adjustments must be included in audit output for the period

### VAT Source Summary

Materialized or computed review rows that explain where a VAT total came from.

Key fields:

- parent VAT period
- source type:
  - `sales_invoice`
  - `purchase_invoice`
  - `journal_entry`
  - `adjustment`
- voucher type / voucher no
- posting date
- tax account
- tax rate
- taxable amount
- tax amount
- recoverability classification
- note

Rules:

- serves operator review and audit traceability
- may be recomputed from ledger / source documents before posting

### Tax Calendar Event

Tracks upcoming fiscal obligations that matter for treasury and operations.

Key fields:

- company
- event type:
  - `vat_settlement`
  - `vat_payment`
  - `f24_deadline`
  - `manual_tax_deadline`
- reference doctype / name
- event date
- amount
- status
- notes

### Cash Planning Adjustment

Manual future cash event that ERPNext does not derive automatically.

Key fields:

- company
- event date
- direction:
  - `inflow`
  - `outflow`
- category:
  - `tax`
  - `payroll`
  - `treasury`
  - `other`
- amount
- description
- reference doctype / name

### Labor Cost Snapshot

Optional normalized snapshot of employee-cost obligations for planning and reporting.

Key fields:

- company
- period start / end
- source mode
- source reference
- employee
- department
- cost center
- project
- gross amount
- employer contribution amount
- total employer cost

Rules:

- source data may come from HRMS payroll, accounting entries, or manual adjustments
- the snapshot is for planning / allocation visibility, not for replacing payroll records

## ERPNext integration

### Standard records reused

- `Company`
- `Account`
- `Journal Entry`
- `Journal Entry Account`
- `Sales Invoice`
- `Purchase Invoice`
- `Payment Entry`
- `Bank Transaction`
- `GL Entry`
- `Cost Center`
- `Project`

### Optional integration records

- HRMS payroll records if HRMS is installed
- `EDI Document` from `fab_italy_edi` for invoice-traceability drilldown

## State model

### VAT Period states

- `open`
- `draft`
- `calculated`
- `posted`
- `closed`
- `cancelled`

### Tax Calendar Event states

- `planned`
- `due`
- `settled`
- `cancelled`

## Security and storage rules

- Period calculations and adjustments must be traceable by user and timestamp.
- Posted settlement references must never be overwritten silently.
- Sensitive payroll-derived values should respect document permissions and source-app restrictions.
- Optional HRMS integration must degrade safely when HRMS is absent.
