"""Replace the first level Natura codes on sales tax rows with their sub-code.

SDI has refused a bare N2, N3 or N6 since 1 January 2021. The Italy VAT Rate
registry names the sub-code each generated template stands for, so every row that
still points at one of those templates can be corrected without guessing.

Submitted invoices are deliberately left alone. They are history: their number is
booked, and the ones carried over from Odoo were transmitted by Odoo itself, so
rewriting the tax row here would not change the file the Agenzia delle Entrate
holds. A submitted invoice that has never been transmitted has to be cancelled and
amended anyway, which is what the send time check tells the operator to do.
"""

from __future__ import annotations

import frappe

from fab_italy_tax.install import ensure_tax_exemption_reason_options
from fab_italy_tax.vat_rates import (
	BARE_NATURA_EXEMPTION,
	build_template_title,
	exemption_reason_for,
)

# Documents whose tax rows end up in an e-invoice, with the states worth touching.
# Invoices are booked once submitted, so only their drafts are corrected; the
# selling documents upstream are corrected whatever their state, because
# make_sales_invoice copies their tax rows into the invoice verbatim.
SOURCE_DOCTYPES = {
	"Quotation": [0, 1],
	"Sales Order": [0, 1],
	"Delivery Note": [0, 1],
	"Sales Invoice": [0],
	"POS Invoice": [0],
}


def execute():
	ensure_tax_exemption_reason_options()

	for template, reason in get_template_exemption_reasons().items():
		upgrade_rows({"parenttype": "Sales Taxes and Charges Template", "parent": template}, reason)
		for doctype, docstatuses in SOURCE_DOCTYPES.items():
			parents = frappe.get_all(
				doctype,
				filters={"docstatus": ["in", docstatuses], "taxes_and_charges": template},
				pluck="name",
			)
			if parents:
				upgrade_rows({"parenttype": doctype, "parent": ["in", parents]}, reason)


def get_template_exemption_reasons() -> dict[str, str]:
	"""Generated zero-rate sales templates mapped to the reason their natura calls for."""
	reasons: dict[str, str] = {}
	for rate in frappe.get_all(
		"Italy VAT Rate",
		filters={"applies_to": "Sales", "rate": 0},
		fields=["nature", "rate", "reverse_charge"],
	):
		reason = exemption_reason_for(rate.nature)
		if not reason:
			continue
		title = build_template_title(rate)
		for name in frappe.get_all(
			"Sales Taxes and Charges Template", filters={"title": title}, pluck="name"
		):
			reasons[name] = reason
	return reasons


def upgrade_rows(filters: dict, reason: str):
	bare = BARE_NATURA_EXEMPTION.get(reason.split("-", 1)[0].split(".")[0])
	if not bare:
		return
	rows = frappe.get_all(
		"Sales Taxes and Charges", filters={**filters, "tax_exemption_reason": bare}, pluck="name"
	)
	for row in rows:
		frappe.db.set_value(
			"Sales Taxes and Charges", row, "tax_exemption_reason", reason, update_modified=False
		)
