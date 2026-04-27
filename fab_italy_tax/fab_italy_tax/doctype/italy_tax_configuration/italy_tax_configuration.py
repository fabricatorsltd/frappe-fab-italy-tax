from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr

VAT_LIQUIDATION_CADENCES = {"Monthly", "Quarterly"}
EMPLOYEE_COST_SOURCE_MODES = {"HRMS Payroll", "Accounting Entries", "Manual Adjustments"}
MANDATORY_ACCOUNT_FIELDS = {
	"vat_output_account": _("VAT Output Account"),
	"vat_input_account": _("VAT Input Account"),
	"vat_payable_account": _("VAT Payable Account"),
	"vat_credit_account": _("VAT Credit Account"),
}
OPTIONAL_ACCOUNT_FIELDS = {
	"quarterly_interest_account": _("Quarterly Interest Account"),
	"carry_forward_account": _("Carry Forward Account"),
}


class ItalyTaxConfiguration(Document):
	def validate(self):
		validate_italy_tax_configuration(self)


def validate_italy_tax_configuration(document: Any) -> None:
	company = cstr(get_document_value(document, "company")).strip()
	cadence = cstr(get_document_value(document, "vat_liquidation_cadence")).strip()
	employee_cost_source_mode = cstr(get_document_value(document, "employee_cost_source_mode")).strip()
	enabled = cint(get_document_value(document, "enabled"))
	include_employee_cost = cint(get_document_value(document, "include_employee_cost_in_cash_planning"))

	if cadence not in VAT_LIQUIDATION_CADENCES:
		frappe.throw(_("VAT Liquidation Cadence must be Monthly or Quarterly."))

	if employee_cost_source_mode and employee_cost_source_mode not in EMPLOYEE_COST_SOURCE_MODES:
		frappe.throw(_("Employee Cost Source Mode is not valid."))

	if include_employee_cost and not employee_cost_source_mode:
		frappe.throw(_("Set an Employee Cost Source Mode before enabling employee-cost cash planning."))

	if not enabled:
		validate_account_companies(document, company)
		return

	if not get_document_value(document, "first_managed_period_start_date"):
		frappe.throw(_("Set First Managed Period Start Date before enabling the tax configuration."))

	for fieldname, label in MANDATORY_ACCOUNT_FIELDS.items():
		if not cstr(get_document_value(document, fieldname)).strip():
			frappe.throw(_("Set {0} before enabling the tax configuration.").format(label))

	if cadence == "Quarterly" and not cstr(get_document_value(document, "quarterly_interest_account")).strip():
		frappe.throw(_("Set Quarterly Interest Account before enabling quarterly VAT liquidation."))

	validate_account_companies(document, company)


def validate_account_companies(document: Any, company: str) -> None:
	if not company:
		return

	account_fields = {**MANDATORY_ACCOUNT_FIELDS, **OPTIONAL_ACCOUNT_FIELDS}
	for fieldname, label in account_fields.items():
		account = cstr(get_document_value(document, fieldname)).strip()
		if not account:
			continue

		account_company = frappe.get_cached_value("Account", account, "company")
		if account_company and account_company != company:
			frappe.throw(_("{0} must belong to company {1}.").format(label, company))


def get_document_value(document: Any, fieldname: str) -> Any:
	getter = getattr(document, "get", None)
	if callable(getter):
		return getter(fieldname)
	return getattr(document, fieldname, None)
