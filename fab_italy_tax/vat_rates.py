from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt

# The full standard Italian VAT matrix. Rows are seeded once and never
# overwritten, so the enabled flags stay under the accountant's control.
# Default enabled = what the Odoo 2025-2026 invoices actually use.
STANDARD_VAT_RATES: tuple[dict[str, Any], ...] = (
	# sales, positive rates
	{"applies_to": "Sales", "rate": 22.0, "enabled": 1, "description": "IVA 22%"},
	{"applies_to": "Sales", "rate": 10.0, "description": "IVA 10%"},
	{"applies_to": "Sales", "rate": 5.0, "description": "IVA 5%"},
	{"applies_to": "Sales", "rate": 4.0, "description": "IVA 4%"},
	# sales, zero rated by Natura
	{"applies_to": "Sales", "rate": 0.0, "nature": "N1", "enabled": 1, "description": "Escluse ex art. 15"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N2.1", "enabled": 1, "description": "Non soggette ex artt. 7-7septies"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N2.2", "description": "Non soggette, altri casi"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N3.1", "enabled": 1, "description": "Non imponibili, esportazioni"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N3.2", "enabled": 1, "description": "Non imponibili, cessioni intra UE"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N3.3", "description": "Non imponibili, cessioni verso San Marino"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N3.4", "description": "Non imponibili, operazioni assimilate"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N3.5", "description": "Non imponibili, lettere di intento"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N3.6", "description": "Non imponibili, altre operazioni"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N4", "description": "Esenti"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N5", "description": "Regime del margine"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N6.1", "description": "Inversione contabile, rottami"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N6.2", "description": "Inversione contabile, oro e argento"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N6.3", "description": "Inversione contabile, subappalto edile"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N6.4", "description": "Inversione contabile, fabbricati"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N6.5", "description": "Inversione contabile, telefoni cellulari"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N6.6", "description": "Inversione contabile, prodotti elettronici"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N6.7", "description": "Inversione contabile, comparto edile"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N6.8", "description": "Inversione contabile, energia"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N6.9", "description": "Inversione contabile, altri casi"},
	{"applies_to": "Sales", "rate": 0.0, "nature": "N7", "description": "IVA assolta in altro stato UE"},
	# purchase, positive rates
	{"applies_to": "Purchase", "rate": 22.0, "enabled": 1, "description": "IVA 22% acquisti"},
	{"applies_to": "Purchase", "rate": 10.0, "enabled": 1, "description": "IVA 10% acquisti"},
	{"applies_to": "Purchase", "rate": 5.0, "description": "IVA 5% acquisti"},
	{"applies_to": "Purchase", "rate": 4.0, "enabled": 1, "description": "IVA 4% acquisti"},
	{"applies_to": "Purchase", "rate": 0.0, "nature": "N2.2", "enabled": 1, "description": "Acquisti non soggetti"},
	# purchase, reverse charge
	{"applies_to": "Purchase", "rate": 22.0, "reverse_charge": 1, "enabled": 1, "description": "Reverse charge 22%"},
	{"applies_to": "Purchase", "rate": 10.0, "reverse_charge": 1, "description": "Reverse charge 10%"},
	{"applies_to": "Purchase", "rate": 22.0, "nature": "N6.7", "reverse_charge": 1, "enabled": 1, "description": "Reverse charge 22% comparto edile"},
	{"applies_to": "Purchase", "rate": 22.0, "nature": "UE", "reverse_charge": 1, "enabled": 1, "description": "Reverse charge 22% acquisti intra UE"},
)


# Maps a natura (N2.1, N3.2, ...) to the core Sales Taxes exemption reason
# Select value, keyed by the code before the dot.
NATURA_EXEMPTION = {
	"N1": "N1-Escluse ex art. 15",
	"N2": "N2-Non Soggette",
	"N3": "N3-Non Imponibili",
	"N4": "N4-Esenti",
	"N5": "N5-Regime del margine / IVA non esposta in fattura",
	"N6": "N6-Inversione Contabile",
	"N7": "N7-IVA assolta in altro stato UE",
}


def exemption_reason_for(nature: str | None) -> str | None:
	if not nature:
		return None
	return NATURA_EXEMPTION.get(nature.split(".")[0])


def build_rate_key(applies_to: str, rate: float, nature: str | None, reverse_charge) -> str:
	parts = ["S" if applies_to == "Sales" else "P"]
	if reverse_charge:
		parts.append("RC")
	parts.append(f"{flt(rate):g}")
	if nature:
		parts.append(nature)
	return "-".join(parts)


def build_template_title(row) -> str:
	parts = ["IVA"]
	if row.reverse_charge:
		parts.append("RC")
	parts.append(f"{flt(row.rate):g}")
	if row.nature:
		parts.append(row.nature)
	return " ".join(parts)


def ensure_standard_vat_rates():
	"""Seed the standard matrix, never touching existing rows.

	Missing rows are added with their default enabled flag; rows the accountant
	already toggled keep whatever state they have.
	"""
	for spec in STANDARD_VAT_RATES:
		key = build_rate_key(
			spec["applies_to"], spec["rate"], spec.get("nature"), spec.get("reverse_charge")
		)
		if frappe.db.exists("Italy VAT Rate", key):
			continue
		frappe.get_doc(
			{
				"doctype": "Italy VAT Rate",
				"applies_to": spec["applies_to"],
				"rate": spec["rate"],
				"nature": spec.get("nature") or "",
				"reverse_charge": spec.get("reverse_charge") or 0,
				"enabled": spec.get("enabled") or 0,
				"description": spec.get("description") or "",
				"seeded": 1,
			}
		).insert(ignore_permissions=True)


def get_vat_companies() -> list[str]:
	"""Companies with both settlement accounts configured, i.e. ready for templates."""
	return frappe.get_all(
		"Company",
		filters={
			"fab_itx_vat_output_account": ["is", "set"],
			"fab_itx_vat_input_account": ["is", "set"],
		},
		pluck="name",
	)


def backfill_exemption_reasons():
	"""Set the exemption reason on already-generated zero-rate natura Sales
	templates; older templates were created without it and fail e-invoicing."""
	companies = get_vat_companies()
	if not companies:
		return
	rates = frappe.get_all(
		"Italy VAT Rate", filters={"applies_to": "Sales", "rate": 0}, fields=["name", "nature"]
	)
	for rate in rates:
		reason = exemption_reason_for(rate.nature)
		if not reason:
			continue
		title = build_template_title(frappe.get_doc("Italy VAT Rate", rate.name))
		for company in companies:
			name = frappe.db.get_value(
				"Sales Taxes and Charges Template", {"title": title, "company": company}, "name"
			)
			if not name:
				continue
			template = frappe.get_doc("Sales Taxes and Charges Template", name)
			changed = False
			for tax in template.taxes:
				if not tax.rate and not tax.get("tax_exemption_reason"):
					tax.tax_exemption_reason = reason
					changed = True
			if changed:
				template.flags.ignore_permissions = True
				template.save()


def sync_vat_rate_templates(company: str | None = None):
	companies = [company] if company else get_vat_companies()
	rows = frappe.get_all("Italy VAT Rate", pluck="name")
	for name in rows:
		row = frappe.get_doc("Italy VAT Rate", name)
		for target in companies:
			sync_templates_for_company(row, target)


def sync_vat_rate_templates_for_rate(row):
	for target in get_vat_companies():
		sync_templates_for_company(row, target)


def sync_templates_for_company(row, company: str):
	if row.applies_to == "Sales":
		ensure_tax_template(row, company, "Sales Taxes and Charges Template")
		ensure_item_tax_template(row, company)
	else:
		ensure_tax_template(row, company, "Purchase Taxes and Charges Template")


def ensure_tax_template(row, company: str, template_doctype: str):
	title = build_template_title(row)
	existing = frappe.db.get_value(template_doctype, {"title": title, "company": company}, "name")

	if not row.enabled:
		# never delete: the template may be referenced by documents
		if existing:
			frappe.db.set_value(template_doctype, existing, "disabled", 1, update_modified=False)
		return

	if existing:
		frappe.db.set_value(template_doctype, existing, "disabled", 0, update_modified=False)
		return

	template = frappe.get_doc(
		{
			"doctype": template_doctype,
			"title": title,
			"company": company,
			"taxes": build_template_taxes(row, company, template_doctype),
		}
	)
	template.insert(ignore_permissions=True)


def build_template_taxes(row, company: str, template_doctype: str) -> list[dict[str, Any]]:
	output_account, input_account = frappe.db.get_value(
		"Company", company, ["fab_itx_vat_output_account", "fab_itx_vat_input_account"]
	)
	description = row.description or build_template_title(row)

	if template_doctype == "Sales Taxes and Charges Template":
		tax = {
			"charge_type": "On Net Total",
			"account_head": output_account,
			"rate": row.rate,
			"description": description,
		}
		# a zero-rate natura line must carry its exemption reason for e-invoicing
		reason = exemption_reason_for(row.nature)
		if reason and not row.rate:
			tax["tax_exemption_reason"] = reason
		return [tax]

	if row.reverse_charge:
		# integrazione: same VAT both as input credit and output debt, net zero
		return [
			{
				"charge_type": "On Net Total",
				"add_deduct_tax": "Add",
				"category": "Total",
				"account_head": input_account,
				"rate": row.rate,
				"description": f"{description} (integrazione IVA a credito)",
			},
			{
				"charge_type": "On Net Total",
				"add_deduct_tax": "Deduct",
				"category": "Total",
				"account_head": output_account,
				"rate": row.rate,
				"description": f"{description} (integrazione IVA a debito)",
			},
		]

	return [
		{
			"charge_type": "On Net Total",
			"add_deduct_tax": "Add",
			"category": "Total",
			"account_head": input_account,
			"rate": row.rate,
			"description": description,
		}
	]


def ensure_item_tax_template(row, company: str):
	"""Item Tax Template for the sales side, so per item overrides and the EDI
	rate resolution (item_tax_template -> tax_rate) keep working."""
	title = build_template_title(row)
	existing = frappe.db.get_value("Item Tax Template", {"title": title, "company": company}, "name")

	if not row.enabled:
		if existing:
			frappe.db.set_value("Item Tax Template", existing, "disabled", 1, update_modified=False)
		return

	if existing:
		frappe.db.set_value("Item Tax Template", existing, "disabled", 0, update_modified=False)
		return

	output_account = frappe.db.get_value("Company", company, "fab_itx_vat_output_account")
	frappe.get_doc(
		{
			"doctype": "Item Tax Template",
			"title": title,
			"company": company,
			"taxes": [{"tax_type": output_account, "tax_rate": row.rate}],
		}
	).insert(ignore_permissions=True)


@frappe.whitelist()
def provision_vat_rates(company: str | None = None):
	frappe.only_for(("System Manager", "Accounts Manager"))
	ensure_standard_vat_rates()
	sync_vat_rate_templates(company=company)
