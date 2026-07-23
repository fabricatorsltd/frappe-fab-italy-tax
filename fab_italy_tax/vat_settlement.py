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
)
from fab_italy_tax.vat_period_calculation import calculate_vat_period, resolve_vat_period, set_document_value


def post_vat_settlement(vat_period: str | Any):
	document = resolve_vat_period(vat_period)
	status = str(get_document_value(document, "status") or "").strip()
	if status in LOCKED_VAT_PERIOD_STATUSES:
		frappe.throw(_("VAT Periods in status Posted, Closed, or Cancelled cannot post a settlement entry."))

	if get_document_value(document, "linked_settlement_entry"):
		frappe.throw(_("This VAT Period already has a Linked Settlement Entry."))

	calculate_vat_period(document)
	configuration = get_tax_configuration(document)
	accounts = build_settlement_accounts(document, configuration)
	if not accounts:
		frappe.throw(_("VAT Period has no amounts to settle."))

	entry = frappe.new_doc("Journal Entry")
	entry.voucher_type = "Journal Entry"
	entry.company = get_document_value(document, "company")
	entry.posting_date = get_document_value(document, "due_date") or get_document_value(
		document, "period_end_date"
	)
	entry.user_remark = build_settlement_remark(document)
	for account_row in accounts:
		entry.append("accounts", account_row)

	naming_series = str(get_document_value(configuration, "settlement_journal_naming_series") or "").strip()
	if naming_series:
		entry.naming_series = naming_series

	entry.insert(ignore_permissions=True)
	entry.submit()

	set_document_value(document, "linked_settlement_entry", getattr(entry, "name", None))
	set_document_value(document, "status", "Posted")

	save = getattr(document, "save", None)
	if callable(save):
		save(ignore_permissions=True)

	return entry


def get_tax_configuration(document: Any):
	return frappe.get_doc(
		"Italy Tax Configuration",
		str(get_document_value(document, "tax_configuration") or "").strip(),
	)


def build_settlement_accounts(document: Any, configuration: Any) -> list[dict[str, Any]]:
	output_vat_total = require_non_negative_amount(
		_("Output VAT Total"), flt(get_document_value(document, "output_vat_total"))
	)
	input_vat_total = require_non_negative_amount(
		_("Input VAT Total"), flt(get_document_value(document, "input_vat_total"))
	)
	previous_credit_brought_forward = require_non_negative_amount(
		_("Previous Credit Brought Forward"),
		flt(get_document_value(document, "previous_credit_brought_forward")),
	)
	quarterly_interest_amount = require_non_negative_amount(
		_("Quarterly Interest Amount"), flt(get_document_value(document, "quarterly_interest_amount"))
	)
	final_payable_amount = require_non_negative_amount(
		_("Final Payable Amount"), flt(get_document_value(document, "final_payable_amount"))
	)
	final_credit_amount = require_non_negative_amount(
		_("Final Credit Amount"), flt(get_document_value(document, "final_credit_amount"))
	)

	accounts: list[dict[str, Any]] = []
	append_account_row(
		accounts,
		require_configuration_account(configuration, "vat_output_account", _("VAT Output Account")),
		debit=output_vat_total,
	)
	append_account_row(
		accounts,
		require_configuration_account(configuration, "vat_input_account", _("VAT Input Account")),
		credit=input_vat_total,
	)

	if previous_credit_brought_forward:
		append_account_row(
			accounts,
			require_configuration_account(
				configuration, "carry_forward_account", _("Carry Forward Account")
			),
			credit=previous_credit_brought_forward,
		)

	if quarterly_interest_amount:
		append_account_row(
			accounts,
			require_configuration_account(
				configuration, "quarterly_interest_account", _("Quarterly Interest Account")
			),
			debit=quarterly_interest_amount,
		)

	if final_payable_amount:
		append_account_row(
			accounts,
			require_configuration_account(configuration, "vat_payable_account", _("VAT Payable Account")),
			credit=final_payable_amount,
		)

	if final_credit_amount:
		append_account_row(
			accounts,
			require_configuration_account(configuration, "vat_credit_account", _("VAT Credit Account")),
			debit=final_credit_amount,
		)

	total_debit = round_amount(sum(flt(row.get("debit_in_account_currency")) for row in accounts))
	total_credit = round_amount(sum(flt(row.get("credit_in_account_currency")) for row in accounts))
	if total_debit != total_credit:
		frappe.throw(_("VAT settlement entry is not balanced. Recalculate the VAT Period before posting."))

	return accounts


def append_account_row(
	accounts: list[dict[str, Any]], account: str, debit: float = 0.0, credit: float = 0.0
) -> None:
	debit_amount = round_amount(debit)
	credit_amount = round_amount(credit)
	if not debit_amount and not credit_amount:
		return

	accounts.append(
		{
			"account": account,
			"debit_in_account_currency": debit_amount,
			"credit_in_account_currency": credit_amount,
		}
	)


def require_configuration_account(configuration: Any, fieldname: str, label: str) -> str:
	account = str(get_document_value(configuration, fieldname) or "").strip()
	if not account:
		frappe.throw(_("Set {0} on the linked tax configuration before posting VAT settlement.").format(label))
	return account


def require_non_negative_amount(label: str, amount: float) -> float:
	if amount < 0:
		frappe.throw(_("{0} cannot be negative when posting VAT settlement.").format(label))
	return round_amount(amount)


def build_settlement_remark(document: Any) -> str:
	period_label = str(get_document_value(document, "period_label") or "").strip()
	period_reference = period_label or str(get_document_value(document, "name") or "").strip()
	return _("VAT settlement for {0}").format(period_reference)


def round_amount(value: Any) -> float:
	return round(flt(value), 2)
