# VAT Rate Registry

## Purpose

Give every site the full standard Italian VAT matrix as data, with an
enabled flag per rate, so the tax templates in actual use are generated and
consistent instead of hand-built. Operators toggle rates; the app owns the
template shape.

## Italy VAT Rate

One record per rate of the standard matrix.

Key fields:

- applies_to: `Sales` or `Purchase`
- rate (percent)
- nature (FatturaPA N code for zero rated rows, e.g. `N1`, `N2.1`, `N3.1`, `N6.7`)
- reverse_charge flag (purchase only)
- description
- enabled flag

Rules:

- the rate key `S|P`[-`RC`]-`rate`[-`nature`] (e.g. `S-22`, `P-RC-22-N6.7`)
  is unique across the matrix
- reverse charge rows are purchase only
- seeded on install and migrate; existing rows are never overwritten, so
  operator toggles survive updates
- rows are disabled, never deleted

## Template generation

Each enabled rate generates the matching template on the company accounts
configured in `Italy Tax Configuration`:

- sales rates: one Sales Taxes and Charges Template row on the VAT output
  account
- purchase rates: one Purchase Taxes and Charges Template row (add) on the
  VAT input account
- reverse charge rates: paired rows, add on the VAT input account and
  deduct on the VAT output account, netting to zero while feeding both VAT
  registers
- sales rates: an Item Tax Template as well, for per-item overrides and
  EDI rate resolution
- zero rated rows carry the nature code into the template title

Disabling a rate disables its templates; nothing is deleted. Generation is
idempotent and runs on install, migrate, and when a rate row changes.

## Default enabled set

All rows are seeded disabled except the set in real use, so a fresh site
starts with a clean template list. The default enabled set covers standard
sales 22 percent, the common zero rated sales natures, purchase 22/10/4
percent, purchase zero rated N2.2, and the reverse charge 22 percent
variants (domestic, N6.7, intra EU).

## Constraints

- template rows must point at accounts of type Tax, or the VAT period
  aggregation will not see the posted amounts
- rates are data, not code: renting the suite to another company only
  requires a different enabled subset, not a fork
