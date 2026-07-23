# Operator Guide

Day-to-day usage of `fab_italy_tax` for finance operators. For the data
model and design rationale see `docs/specs/`.

## Company setup

All settings live on the Company record, section "Italy Tax":

1. Set the VAT accounts: output, input, payable, credit, carry forward.
   Output and input must be accounts of type Tax; the VAT period
   aggregation reads the general ledger of Tax accounts only, so anything
   posted elsewhere is invisible to the settlement.
2. Pick the liquidation cadence, Monthly or Quarterly. Quarterly companies
   also set the quarterly interest account.
3. Set the first managed period start date. Periods before that date are
   not generated, which is how a mid-year cutover avoids overlapping the
   previous system.
4. Tick "Enable Italy Tax Management". The app maintains the matching
   Italy Tax Configuration record from these fields. Periods are then
   generated on migrate or on demand with the "Generate VAT Periods"
   button on the configuration.

## VAT rates

Open the Italy VAT Rate list. The full standard matrix is already seeded;
enable the rates the company actually uses and leave the rest disabled.
Every enabled rate keeps its Sales or Purchase tax template generated and
current (sales rates also keep an Item Tax Template for per-item
overrides); disabling a rate disables its templates without deleting
history. Do not hand-edit the generated templates: changes belong on the
rate row.

## Invoicing

- Sales and purchase invoices pick up the Italian naming series managed by
  the app.
- Purchase invoice rows carry deductibility fields (fully, partially by
  percent or amount, non deductible). An invoice-level override applies one
  mode to the whole document.
- Rows carry competence date fields when revenue or cost belongs to a
  different period than the posting date.
- The Competence Year field shifts the economic effect of the invoice into
  the prior accounting year: the posting date stays, the app books the
  matching accrual and reversal entries on save (accounts configured in
  the "Italy Year-end Close" section).

## VAT period lifecycle

1. Periods are generated from the enabled configuration following the
   cadence.
2. Calculate: the period aggregates output and input VAT from the posted
   ledger, applies adjustments and prior credit, and stores the source
   breakdown. Status moves to calculated.
3. Review the breakdown; add VAT Adjustment records for corrections that
   must stay visible in the audit trail. Quarterly interest is entered
   here as an adjustment of type Quarterly Interest (the app books it on
   the configured interest account, it does not compute the rate).
4. Post: the app books the settlement journal entry on the configured
   payable or credit account. Status moves to posted; a leftover credit is
   carried into the next period.

## Tax calendar

Periods that end with an amount payable get a VAT Payment calendar event;
the event settles when the period is closed. F24 deadlines are separate
events: with `fab_f24` installed, booking an F24 payment marks the
matching F24 Deadline event as paid.

## Reports

- Company Cash Flow Monitor: bank balances, receivables and payables due,
  planned VAT payments.
- Employee Cost Cash Planning: labor cost obligations, sourced from HRMS
  payroll, tagged accounting entries, manual adjustments, or
  `fab_hr_italy` Employee Cost Entries depending on the configured mode.
- Italian Yearly Balance: year view driven by the competence year handling.

## Troubleshooting

- Settlement shows zero while invoices exist: the tax template rows point
  at accounts that are not of type Tax, or the company VAT accounts are not
  the ones the templates post to. The aggregation also counts sales and
  purchase invoice postings only, so VAT moved by journal entry stays out
  of the automatic totals (book it as a VAT Adjustment instead).
- A period is missing: check the first managed period start date and that
  the configuration is enabled.
