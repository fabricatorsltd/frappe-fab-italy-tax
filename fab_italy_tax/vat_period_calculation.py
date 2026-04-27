from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration import (
	get_document_value,
)
from fab_italy_tax.fab_italy_tax.doctype.vat_adjustment.vat_adjustment import (
	LOCKED_VAT_PERIOD_STATUSES,
	get_vat_adjustment_net_effect,
)

SALES_VAT_SOURCE_DOCTYPES = {"Sales Invoice"}
PURCHASE_VAT_SOURCE_DOCTYPES = {"Purchase Invoice"}


def calculate_vat_period(vat_period: str | Any) -> dict[str, float]:
	document = resolve_vat_period(vat_period)
	status = str(get_document_value(document, "status") or "").strip()
	if status in LOCKED_VAT_PERIOD_STATUSES:
		frappe.throw(_("VAT Periods in status Posted, Closed, or Cancelled cannot be recalculated."))

	gl_entries = fetch_period_gl_entries(document)
	adjustments = fetch_period_adjustments(str(get_document_value(document, "name") or ""))
	results = build_vat_period_totals(document, gl_entries, adjustments)
	apply_calculation_results(document, results)
	return results


def resolve_vat_period(vat_period: str | Any):
	if isinstance(vat_period, str):
		return frappe.get_doc("VAT Period", vat_period)
	return vat_period


def fetch_period_gl_entries(document: Any) -> list[dict[str, Any]]:
	return frappe.get_all(
		"GL Entry",
		filters={
			"company": get_document_value(document, "company"),
			"is_cancelled": 0,
			"posting_date": (
				"between",
				[
					get_document_value(document, "period_start_date"),
					get_document_value(document, "period_end_date"),
				],
			),
		},
		fields=["account", "debit", "credit", "voucher_type", "voucher_no"],
	)


def fetch_period_adjustments(vat_period_name: str) -> list[dict[str, Any]]:
	if not vat_period_name:
		return []

	return frappe.get_all(
		"VAT Adjustment",
		filters={"vat_period": vat_period_name},
		fields=[
			"name",
			"adjustment_type",
			"direction",
			"amount",
			"reason",
			"reference_doctype",
			"reference_name",
		],
		order_by="creation asc",
	)


def build_vat_period_totals(
	document: Any,
	gl_entries: list[dict[str, Any]],
	adjustments: list[dict[str, Any]],
) -> dict[str, float]:
	previous_credit_brought_forward = flt(get_document_value(document, "previous_credit_brought_forward"))
	tax_accounts = get_tax_account_names(row.get("account") for row in gl_entries)
	output_vat_total = round_amount(
		sum(
			flt(row.get("credit")) - flt(row.get("debit"))
			for row in gl_entries
			if is_output_vat_entry(row, tax_accounts)
		)
	)
	input_vat_total = round_amount(
		sum(
			flt(row.get("debit")) - flt(row.get("credit"))
			for row in gl_entries
			if is_input_vat_entry(row, tax_accounts)
		)
	)
	quarterly_interest_amount = round_amount(
		sum(
			flt(row.get("amount"))
			for row in adjustments
			if row.get("adjustment_type") == "Quarterly Interest"
		)
	)
	adjustment_net_effect = round_amount(
		sum(
			get_vat_adjustment_net_effect(str(row.get("direction") or "").strip(), row.get("amount"))
			for row in adjustments
		)
	)
	net_due_amount = round_amount(
		output_vat_total - input_vat_total - previous_credit_brought_forward + adjustment_net_effect
	)

	return {
		"output_vat_total": output_vat_total,
		"input_vat_total": input_vat_total,
		"quarterly_interest_amount": quarterly_interest_amount,
		"final_payable_amount": round_amount(max(net_due_amount, 0)),
		"final_credit_amount": round_amount(max(-net_due_amount, 0)),
	}


def get_tax_account_names(account_names) -> set[str]:
	names = sorted({str(account or "").strip() for account in account_names if str(account or "").strip()})
	if not names:
		return set()

	return set(
		frappe.get_all(
			"Account",
			filters={"name": ("in", names), "account_type": "Tax"},
			pluck="name",
		)
	)


def is_output_vat_entry(row: dict[str, Any], tax_accounts: set[str]) -> bool:
	return (
		str(row.get("account") or "").strip() in tax_accounts
		and str(row.get("voucher_type") or "").strip() in SALES_VAT_SOURCE_DOCTYPES
	)


def is_input_vat_entry(row: dict[str, Any], tax_accounts: set[str]) -> bool:
	return (
		str(row.get("account") or "").strip() in tax_accounts
		and str(row.get("voucher_type") or "").strip() in PURCHASE_VAT_SOURCE_DOCTYPES
	)


def apply_calculation_results(document: Any, results: dict[str, float]) -> None:
	for fieldname, value in results.items():
		set_document_value(document, fieldname, value)

	set_document_value(document, "status", "Calculated")

	save = getattr(document, "save", None)
	if callable(save):
		save(ignore_permissions=True)


def set_document_value(document: Any, fieldname: str, value: Any) -> None:
	setter = getattr(document, "set", None)
	if callable(setter):
		setter(fieldname, value)
		return

	if isinstance(document, dict):
		document[fieldname] = value
		return

	setattr(document, fieldname, value)


def round_amount(value: Any) -> float:
	return round(flt(value), 2)
