# fab Italy Tax

Italian tax, VAT, and accounting support for ERPNext.

## Scope

`fab_italy_tax` groups the accounting and compliance helpers that are specific
to the Italian market but independent from SDI transport.

Current responsibilities include:

- company-level Italian tax configuration
- the standard Italian VAT rate registry and generated tax templates
- VAT-period generation and calendar workflows
- tax settlement support
- Italian invoice naming helpers
- Desk workspaces and UI helpers for finance operators

## VAT rate registry

The app seeds an `Italy VAT Rate` record for every rate of the standard
Italian matrix (positive rates, zero rates with their FatturaPA nature code,
reverse charge variants). Each enabled rate generates the matching Sales or
Purchase Taxes and Charges Template on the company VAT accounts; sales rates
also generate an Item Tax Template for per-item overrides, and reverse
charge rates generate the paired add/deduct rows that net to zero. Rates are
disabled, never deleted, so the templates in actual use stay a clean subset
of the matrix. See `docs/specs/vat-rates.md`.

## Documentation

- `docs/operator-guide.md` - setup and day-to-day usage for finance operators
- `docs/specs/` - domain model, workflows, VAT rate registry

## Branches

- `develop`: integration branch for testing against Frappe/ERPNext `develop`
- `version-16`: stable branch for Frappe/ERPNext 16

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/fabricatorsltd/frappe-fab-italy-tax.git --branch version-16
bench --site [site] install-app fab_italy_tax
```

## Contributing

Follow the official Frappe contribution guidelines:

- <https://github.com/frappe/erpnext/wiki/Contribution-Guidelines>

Use the upstream guidance for proposals, coding standards, pull requests, and
documentation updates when contributing to this app.

## Development

```bash
cd apps/fab_italy_tax
pre-commit install
```

Pre-commit is configured for Ruff, ESLint, Prettier, and PyUpgrade.

## License

GNU Affero General Public License v3.0
