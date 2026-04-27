from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration import (
	get_document_value,
)

VAT_ADJUSTMENT_TYPES = {
	"Quarterly Interest",
	"Previous Credit Carry Forward",
	"Deductible VAT Correction",
	"Non-deductible VAT Correction",
	"Settlement Correction",
	"Other",
}
VAT_ADJUSTMENT_DIRECTIONS = {
	"Increase Payable",
	"Decrease Payable",
	"Increase Credit",
	"Decrease Credit",
}
LOCKED_VAT_PERIOD_STATUSES = {"Posted", "Closed", "Cancelled"}


class VATAdjustment(Document):
	def validate(self):
		validate_vat_adjustment(self)

	def before_save(self):
		enforce_vat_adjustment_append_only(self)

	def on_trash(self):
		prevent_vat_adjustment_deletion()


def validate_vat_adjustment(document: Any) -> None:
	company = str(get_document_value(document, "company") or "").strip()
	vat_period = str(get_document_value(document, "vat_period") or "").strip()
	adjustment_type = str(get_document_value(document, "adjustment_type") or "").strip()
	direction = str(get_document_value(document, "direction") or "").strip()
	reason = str(get_document_value(document, "reason") or "").strip()
	reference_doctype = str(get_document_value(document, "reference_doctype") or "").strip()
	reference_name = str(get_document_value(document, "reference_name") or "").strip()
	amount = flt(get_document_value(document, "amount"))

	if adjustment_type not in VAT_ADJUSTMENT_TYPES:
		frappe.throw(_("VAT Adjustment Type is not valid."))

	if direction not in VAT_ADJUSTMENT_DIRECTIONS:
		frappe.throw(_("VAT Adjustment Direction is not valid."))

	if amount <= 0:
		frappe.throw(_("VAT Adjustment Amount must be greater than zero."))

	if not reason:
		frappe.throw(_("Set a Reason before saving a VAT Adjustment."))

	validate_reference(reference_doctype, reference_name)
	validate_vat_period_alignment(company, vat_period, adjustment_type, direction)


def validate_reference(reference_doctype: str, reference_name: str) -> None:
	if bool(reference_doctype) != bool(reference_name):
		frappe.throw(_("Set both Reference DocType and Reference Name, or leave both empty."))

	if not reference_doctype:
		return

	if not frappe.db.exists("DocType", reference_doctype):
		frappe.throw(_("Reference DocType does not exist."))

	if not frappe.db.exists(reference_doctype, reference_name):
		frappe.throw(_("Reference Name does not exist for the selected Reference DocType."))


def validate_vat_period_alignment(
	company: str, vat_period: str, adjustment_type: str, direction: str
) -> None:
	if not vat_period:
		return

	if not frappe.db.exists("VAT Period", vat_period):
		frappe.throw(_("VAT Period does not exist."))

	period_company = frappe.get_cached_value("VAT Period", vat_period, "company")
	if company and period_company and company != period_company:
		frappe.throw(_("VAT Adjustment company must match the linked VAT Period company."))

	period_status = frappe.get_cached_value("VAT Period", vat_period, "status")
	if period_status in LOCKED_VAT_PERIOD_STATUSES:
		frappe.throw(_("VAT Adjustments cannot be added to Posted, Closed, or Cancelled VAT Periods."))

	period_cadence = frappe.get_cached_value("VAT Period", vat_period, "vat_liquidation_cadence")
	if adjustment_type == "Quarterly Interest":
		if period_cadence != "Quarterly":
			frappe.throw(_("Quarterly Interest adjustments require a Quarterly VAT Period."))
		if direction != "Increase Payable":
			frappe.throw(_("Quarterly Interest adjustments must use the Increase Payable direction."))

	if adjustment_type == "Previous Credit Carry Forward" and direction not in {
		"Decrease Payable",
		"Increase Credit",
	}:
		frappe.throw(
			_("Previous Credit Carry Forward adjustments must decrease payable VAT or increase VAT credit.")
		)


def enforce_vat_adjustment_append_only(document: Any) -> None:
	is_new = getattr(document, "is_new", None)
	if callable(is_new) and is_new():
		return

	get_old_document = getattr(document, "get_doc_before_save", None)
	if callable(get_old_document) and get_old_document():
		frappe.throw(
			_("VAT Adjustment records are append-only. Add a new adjustment instead of editing history.")
		)


def prevent_vat_adjustment_deletion() -> None:
	frappe.throw(
		_("VAT Adjustment records are append-only. Add a reversing adjustment instead of deleting history.")
	)


def get_vat_adjustment_net_effect(direction: str, amount: Any) -> float:
	value = flt(amount)
	if direction in {"Increase Payable", "Decrease Credit"}:
		return value
	if direction in {"Decrease Payable", "Increase Credit"}:
		return -value
	return 0.0
