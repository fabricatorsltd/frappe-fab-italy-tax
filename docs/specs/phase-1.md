# Phase 1 Scope

## Problem statement

`fab_italy_tax` must provide the Italian accounting and tax layer that ERPNext v16 and `erpnext_italy` do not currently cover in a production-ready way.

The first release should focus on:

- company-scoped **VAT liquidation** with monthly or quarterly cadence
- controlled **VAT settlement** and payable / credit carry-forward handling
- a finance-oriented **cash planning** layer that includes tax deadlines
- optional **employee-cost integration** through HRMS or accounting fallbacks

This app is intentionally separate from `fab_italy_edi`:

- `fab_italy_edi` owns SDI / XML / transport / receipts
- `fab_italy_tax` owns tax periods, settlements, reporting, and finance planning

## Scope

### In scope

- Company-scoped Italian tax configuration
- VAT cadence per company:
  - monthly
  - quarterly
- VAT settlement periods with explicit open / draft / calculated / posted / closed states
- Purchase / sales VAT aggregation from ERPNext accounting data
- Settlement logic for:
  - output VAT
  - input VAT
  - previous credit carry-forward
  - current payable / receivable balance
  - quarterly interest uplift where applicable
- Draft and posted journal entries for VAT settlement
- Operational VAT reports for review before posting
- Tax calendar / due-date visibility for:
  - periodic VAT settlement
  - F24-related payment deadlines
- Cash-planning inputs from:
  - AR / AP due dates
  - bank balances
  - planned VAT payments
  - optional payroll / employee-cost obligations
- Employee-cost visibility through:
  - HRMS payroll integration when installed
  - accounting fallback through salary journal entries when HRMS is absent
- Explicit boundaries and hooks for future integrations with:
  - `fab_italy_edi`
  - `fab_exchange_rate_sync`
  - HRMS

### Out of scope

- Full legal filing automation for Phase 1:
  - LIPE file submission
  - annual VAT return generation
  - direct F24 telematic generation / submission
- Complete Italian chart-of-accounts provisioning
- Full statutory close / bilancio automation
- Payroll engine implementation inside this app
- Replacing ERPNext core treasury or reporting wholesale

## Design principles

1. **Company-scoped behavior**: VAT cadence, accounts, due dates, and carry-forward must be configured per company.
2. **Accounting-first**: settlement must be derived from posted accounting data, not from ad-hoc counters.
3. **Reproducible periods**: every VAT result must be tied to a named period and remain auditable after posting.
4. **Draft before posting**: operators should review computed VAT before any journal entry is created.
5. **No hidden auto-posting**: tax liabilities should never silently hit the ledger without an explicit post action.
6. **ERPNext-native integration**: rely on standard accounts, journal entries, cost centers, payment schedules, and reports where possible.
7. **Layer separation**: tax logic stays here; EDI transport and invoice exchange stay in `fab_italy_edi`.
8. **Behavior-safe fallbacks**: employee-cost planning must still work when HRMS is absent, but with a narrower scope.

## Technical architecture

### Internal modules

- `fab_italy_tax.config`
- `fab_italy_tax.vat`
- `fab_italy_tax.vat.reports`
- `fab_italy_tax.vat.settlement`
- `fab_italy_tax.cashflow`
- `fab_italy_tax.labor_costs`
- `fab_italy_tax.calendar`

### Dependency strategy

- **Required**:
  - ERPNext
- **Optional but supported**:
  - `fab_italy_edi` for invoice-exchange traceability
  - HRMS for payroll-driven employee cost
  - `fab_exchange_rate_sync` for more reliable foreign-currency planning inputs

## Acceptance criteria

Phase 1 is complete when:

1. A company can choose monthly or quarterly VAT cadence in a dedicated tax configuration.
2. The app can generate a VAT period with computed totals derived from posted ledger-backed source documents.
3. Operators can review the breakdown of output VAT, input VAT, prior credit, quarterly interest, and final payable / receivable result.
4. The app can create and post a settlement journal entry using configured liability / credit accounts.
5. Posted settlements remain traceable to their source period and cannot be recalculated silently.
6. The app exposes a usable cash-planning view that combines bank balances, AR / AP due dates, and planned VAT payments.
7. If HRMS is installed, employee-cost obligations can be included in cash planning from payroll data.
8. If HRMS is not installed, the app can still include employee cost from tagged accounting entries or manual planning adjustments.

## Current implementation status

Implemented in the current app scaffold:

- app exists and is installed
- no business logic yet
- no DocTypes yet
- no tax computations yet
- no finance reports yet

## Initial backlog

1. Define the app boundary against `fab_italy_edi`, ERPNext core, and HRMS.
2. Create company-scoped tax configuration.
3. Define VAT period and VAT settlement records.
4. Build VAT aggregation queries and review report.
5. Implement settlement calculation rules for monthly and quarterly companies.
6. Implement draft / post settlement entry flow.
7. Build tax calendar and due-date tracking.
8. Build cash-planning report with VAT obligations.
9. Add employee-cost integration.
10. Add regression coverage and migration hardening.
