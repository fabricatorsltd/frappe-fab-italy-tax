from __future__ import annotations

from calendar import monthrange
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration import (
	VAT_LIQUIDATION_CADENCES,
	get_document_value,
)

VAT_PERIOD_STATUSES = {"Open", "Draft", "Calculated", "Posted", "Closed", "Cancelled"}


class VATPeriod(Document):
	def validate(self):
		validate_vat_period(self)

	def on_update(self):
		from fab_italy_tax.vat_period_generation import sync_next_vat_period_credit

		sync_next_vat_period_credit(self)

	def calculate_amounts(self):
		from fab_italy_tax.vat_period_calculation import calculate_vat_period

		return calculate_vat_period(self)

	def post_settlement_entry(self):
		from fab_italy_tax.vat_settlement import post_vat_settlement

		return post_vat_settlement(self)

	def generate_next_period(self):
		from fab_italy_tax.vat_period_generation import generate_next_vat_period

		return generate_next_vat_period(self)


def validate_vat_period(document: Any) -> None:
	company = str(get_document_value(document, "company") or "").strip()
	tax_configuration = str(get_document_value(document, "tax_configuration") or "").strip()
	cadence = str(get_document_value(document, "vat_liquidation_cadence") or "").strip()
	status = str(get_document_value(document, "status") or "").strip()
	period_start_date = getdate(get_document_value(document, "period_start_date"))
	period_end_date = getdate(get_document_value(document, "period_end_date"))
	due_date = getdate(get_document_value(document, "due_date"))
	final_payable_amount = flt(get_document_value(document, "final_payable_amount"))
	final_credit_amount = flt(get_document_value(document, "final_credit_amount"))

	if cadence not in VAT_LIQUIDATION_CADENCES:
		frappe.throw(_("VAT Liquidation Cadence must be Monthly or Quarterly."))

	if status not in VAT_PERIOD_STATUSES:
		frappe.throw(_("VAT Period status is not valid."))

	if period_start_date > period_end_date:
		frappe.throw(_("Period Start Date cannot be after Period End Date."))

	if due_date < period_end_date:
		frappe.throw(_("Due Date cannot be earlier than Period End Date."))

	validate_period_shape(cadence, period_start_date, period_end_date)
	validate_configuration_alignment(document, company, tax_configuration, cadence)
	validate_duplicate_period(document, company, tax_configuration, cadence, period_start_date, period_end_date)

	if status in {"Posted", "Closed"} and not get_document_value(document, "linked_settlement_entry"):
		frappe.throw(_("Set Linked Settlement Entry before marking a VAT period as Posted or Closed."))

	if final_payable_amount > 0 and final_credit_amount > 0:
		frappe.throw(_("Final Payable Amount and Final Credit Amount cannot both be positive."))


def validate_period_shape(cadence: str, period_start_date, period_end_date) -> None:
	if cadence == "Monthly":
		if period_start_date.year != period_end_date.year or period_start_date.month != period_end_date.month:
			frappe.throw(_("Monthly VAT periods must stay within a single calendar month."))

		if period_start_date.day != 1:
			frappe.throw(_("Monthly VAT periods must start on the first day of the month."))

		if period_end_date.day != monthrange(period_end_date.year, period_end_date.month)[1]:
			frappe.throw(_("Monthly VAT periods must end on the last day of the month."))
		return

	quarter_start_month = ((period_start_date.month - 1) // 3) * 3 + 1
	quarter_end_month = quarter_start_month + 2
	quarter_end_day = monthrange(period_start_date.year, quarter_end_month)[1]

	if period_start_date.month != quarter_start_month or period_start_date.day != 1:
		frappe.throw(_("Quarterly VAT periods must start on the first day of a calendar quarter."))

	if period_end_date.year != period_start_date.year:
		frappe.throw(_("Quarterly VAT periods cannot span multiple fiscal years."))

	if period_end_date.month != quarter_end_month or period_end_date.day != quarter_end_day:
		frappe.throw(_("Quarterly VAT periods must end on the last day of the calendar quarter."))


def validate_configuration_alignment(document: Any, company: str, tax_configuration: str, cadence: str) -> None:
	if not tax_configuration:
		return

	configuration_company = frappe.get_cached_value("Italy Tax Configuration", tax_configuration, "company")
	if company and configuration_company and configuration_company != company:
		frappe.throw(_("Tax Configuration must belong to the selected company."))

	configuration_cadence = frappe.get_cached_value(
		"Italy Tax Configuration", tax_configuration, "vat_liquidation_cadence"
	)
	if cadence and configuration_cadence and configuration_cadence != cadence:
		frappe.throw(_("VAT Period cadence must match the linked tax configuration."))


def validate_duplicate_period(
	document: Any,
	company: str,
	tax_configuration: str,
	cadence: str,
	period_start_date,
	period_end_date,
) -> None:
	if not company or not tax_configuration or not cadence:
		return

	filters = {
		"company": company,
		"tax_configuration": tax_configuration,
		"vat_liquidation_cadence": cadence,
		"period_start_date": period_start_date,
		"period_end_date": period_end_date,
	}
	current_name = str(get_document_value(document, "name") or "").strip()
	existing_name = frappe.db.get_value("VAT Period", filters, "name")
	if existing_name and existing_name != current_name:
		frappe.throw(_("A VAT Period already exists for the selected company, cadence, and date range."))
