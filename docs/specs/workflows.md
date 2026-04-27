# Workflows

## VAT settlement workflow

### Period generation

1. Operator configures `Italy Tax Configuration` for a company.
2. The app generates the next VAT period based on configured cadence:
   - monthly companies get one period per month
   - quarterly companies get one period per quarter
3. The generated period receives:
   - period dates
   - due date
   - previous credit carried forward if applicable

### Calculation

1. Operator opens a VAT period in `open` or `draft` state.
2. The app aggregates source data from posted accounting records.
3. The app computes:
   - output VAT
   - input VAT
   - adjustments
   - quarterly interest where applicable
   - final payable or credit
4. The app stores the calculation snapshot and source summary rows.
5. Period moves to `calculated`.

### Review and posting

1. Operator reviews source breakdown and manual adjustments.
2. Operator posts settlement.
3. The app creates a settlement `Journal Entry`.
4. The period stores the linked journal entry and moves to `posted`.
5. When fully settled / locked, the period can move to `closed`.

## Monthly vs quarterly company workflow

### Monthly company

- one VAT period per calendar month
- no quarterly interest uplift
- due-date logic follows monthly cadence

### Quarterly company

- one VAT period per calendar quarter
- quarterly interest is computed according to configured rules
- due-date logic follows quarterly cadence

The app must keep cadence at company level, not at invoice or user level.

## Carry-forward workflow

1. A posted VAT period ends with either:
   - payable amount
   - credit amount
2. If credit remains, the next generated period receives it as prior credit brought forward.
3. Carry-forward must remain explicit on both periods for audit traceability.

## Manual adjustment workflow

1. Operator adds one or more `VAT Adjustment` rows.
2. Each row requires:
   - amount
   - direction
   - reason
3. Recalculation includes the adjustments.
4. Adjustments remain append-only history for the period.

## Cash-planning workflow

1. Operator opens the cash-planning report for a company and date horizon.
2. The app combines:
   - current bank / cash balances
   - AR due dates
   - AP due dates
   - planned VAT obligations from VAT periods / tax calendar
   - optional payroll / labor-cost obligations
   - manual cash planning adjustments
3. The app presents future inflows / outflows grouped by date and category.
4. Operators can add manual adjustments when a cash event is known but not yet represented in ERPNext documents.

## Employee-cost integration workflow

### With HRMS installed

1. The app reads payroll-derived employer cost for the selected period.
2. Costs are grouped by:
   - employee
   - department
   - cost center
   - project where available
3. The result feeds:
   - cash planning
   - cost-center visibility
   - project / service profitability support

### Without HRMS

1. The app falls back to salary-related accounting entries or manual planning adjustments.
2. Costs can still be included in cash planning and cost-center reporting, but with less detail.

## Integration boundary workflow

### `fab_italy_edi`

- provides invoice transport / receipt data
- may be used for drilldown or operational traceability
- does not own VAT settlement logic

### ERPNext core

- remains the system of record for:
  - ledgers
  - invoices
  - journal entries
  - payments
  - bank reconciliation

### HRMS

- provides payroll truth when installed
- remains the owner of payroll documents and computations
- `fab_italy_tax` consumes the resulting cost information for planning and reporting

## Manual operator actions

Operators must be able to:

- generate the next VAT period
- recalculate an unposted period
- add and review manual adjustments
- post settlement entry
- inspect the source breakdown of a calculated period
- mark tax calendar items as settled
- add cash-planning adjustments

## Reporting expectations

Phase 1 reporting should expose:

- VAT period overview by company
- payable vs credit trend
- detailed review of one VAT period
- upcoming tax deadlines
- cash projection including tax obligations
- optional employee-cost contribution to upcoming outflows
