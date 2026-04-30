# fab Italy Tax

Italian tax, VAT, and accounting support for ERPNext.

## Scope

`fab_italy_tax` groups the accounting and compliance helpers that are specific
to the Italian market but independent from SDI transport.

Current responsibilities include:

- company-level Italian tax configuration
- VAT-period generation and calendar workflows
- tax settlement support
- Italian invoice naming helpers
- Desk workspaces and UI helpers for finance operators

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
