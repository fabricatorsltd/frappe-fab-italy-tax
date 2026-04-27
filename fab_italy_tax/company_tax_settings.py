from __future__ import annotations

from typing import Any

import frappe
from erpnext.setup.setup_wizard.operations.taxes_setup import get_or_create_account
from frappe import _
from frappe.utils import cint, cstr, getdate, nowdate

from fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration import (
	EMPLOYEE_COST_SOURCE_MODES,
	VAT_LIQUIDATION_CADENCES,
)

COMPANY_TO_TAX_CONFIGURATION_FIELD_MAP = {
	"fab_itx_enabled": "enabled",
	"fab_itx_vat_liquidation_cadence": "vat_liquidation_cadence",
	"fab_itx_first_managed_period_start_date": "first_managed_period_start_date",
	"fab_itx_settlement_journal_naming_series": "settlement_journal_naming_series",
	"fab_itx_default_tax_payment_mode": "default_tax_payment_mode",
	"fab_itx_vat_output_account": "vat_output_account",
	"fab_itx_vat_input_account": "vat_input_account",
	"fab_itx_vat_payable_account": "vat_payable_account",
	"fab_itx_vat_credit_account": "vat_credit_account",
	"fab_itx_quarterly_interest_account": "quarterly_interest_account",
	"fab_itx_carry_forward_account": "carry_forward_account",
	"fab_itx_include_employee_cost_in_cash_planning": "include_employee_cost_in_cash_planning",
	"fab_itx_employee_cost_source_mode": "employee_cost_source_mode",
}
TAX_CONFIGURATION_TO_COMPANY_FIELD_MAP = {
	value: key for key, value in COMPANY_TO_TAX_CONFIGURATION_FIELD_MAP.items()
}
DEFAULT_TAX_ACCOUNT_SPECS = {
	"vat_output_account": {"account_name": "VAT Output", "root_type": "Liability"},
	"vat_input_account": {"account_name": "VAT Input", "root_type": "Asset"},
	"vat_payable_account": {"account_name": "VAT Payable", "root_type": "Liability"},
	"vat_credit_account": {"account_name": "VAT Credit", "root_type": "Asset"},
	"carry_forward_account": {"account_name": "VAT Credit Carry Forward", "root_type": "Asset"},
}
DEFAULT_QUARTERLY_INTEREST_ACCOUNT_NAME = "Quarterly VAT Interest"
DEFAULT_TAX_PAYMENT_MODE_NAME = "F24 Tax Payment"
DEFAULT_TAX_PAYMENT_MODE_TYPE = "Bank"


def sync_tax_configuration_from_company(document, method: str | None = None) -> None:
	company = cstr(get_document_value(document, "name")).strip()
	if not company:
		return

	payload = build_tax_configuration_payload(document)
	if not should_manage_tax_configuration(document, payload):
		return

	payload = ensure_default_company_tax_setup(document, payload)

	docname = frappe.db.get_value("Italy Tax Configuration", {"company": company})
	if not docname:
		frappe.get_doc({"doctype": "Italy Tax Configuration", **payload}).insert(ignore_permissions=True)
		return

	config = frappe.get_doc("Italy Tax Configuration", docname)
	changed = False
	for fieldname, value in payload.items():
		if fieldname in {"doctype", "company"}:
			continue
		if config.get(fieldname) != value:
			config.set(fieldname, value)
			changed = True

	if changed:
		config.save(ignore_permissions=True)


def ensure_enabled_company_tax_setup() -> None:
	for company in frappe.get_all(
		"Company",
		filters={"country": "Italy", "fab_itx_enabled": 1},
		pluck="name",
	):
		sync_tax_configuration_from_company(frappe.get_doc("Company", company))


def backfill_company_tax_fields() -> None:
	rows = frappe.get_all(
		"Italy Tax Configuration",
		fields=["name", "company", *TAX_CONFIGURATION_TO_COMPANY_FIELD_MAP],
	)
	for row in rows:
		updates = {}
		for config_field, company_field in TAX_CONFIGURATION_TO_COMPANY_FIELD_MAP.items():
			value = row.get(config_field)
			if value in (None, ""):
				continue
			updates[company_field] = value

		if updates:
			frappe.db.set_value("Company", row["company"], updates, update_modified=False)


def sync_company_tax_fields_from_configuration(document, method: str | None = None) -> None:
	company = cstr(get_document_value(document, "company")).strip()
	if not company:
		return

	updates = build_company_updates_from_tax_configuration(document)
	if updates:
		frappe.db.set_value("Company", company, updates, update_modified=False)


def ensure_default_company_tax_setup(document, payload: dict[str, Any]) -> dict[str, Any]:
	if not cint(payload.get("enabled")):
		return payload

	if normalize_country(get_document_value(document, "country")) != "italy":
		return payload

	company = cstr(payload.get("company")).strip()
	if not company:
		return payload

	updates = build_missing_tax_setup_updates(company, payload.get("vat_liquidation_cadence"), payload)
	if not payload.get("first_managed_period_start_date"):
		updates["first_managed_period_start_date"] = resolve_first_managed_period_start_date(company)
	if not cstr(payload.get("default_tax_payment_mode")).strip():
		updates["default_tax_payment_mode"] = ensure_default_mode_of_payment()

	for fieldname, value in updates.items():
		payload[fieldname] = value

	company_updates = {}
	for fieldname, value in updates.items():
		company_field = TAX_CONFIGURATION_TO_COMPANY_FIELD_MAP.get(fieldname)
		if company_field:
			company_updates[company_field] = value

	if company_updates:
		apply_company_updates(document, company, company_updates)

	return payload


@frappe.whitelist()
def provision_tax_configuration_setup(tax_configuration: str) -> dict[str, Any]:
	document = frappe.get_doc("Italy Tax Configuration", tax_configuration)
	updates = build_missing_configuration_setup_updates(document)
	if not updates:
		return {
			"tax_configuration": tax_configuration,
			"updated_fields": [],
			"message": _("VAT setup is already complete."),
		}

	for fieldname, value in updates.items():
		set_document_value(document, fieldname, value)

	document.save(ignore_permissions=True)
	sync_company_tax_fields_from_configuration(document)
	return {
		"tax_configuration": tax_configuration,
		"updated_fields": sorted(updates),
		"message": _("Provisioned VAT setup for {0}.").format(tax_configuration),
	}


def build_tax_configuration_payload(document) -> dict[str, Any]:
	payload = {
		"doctype": "Italy Tax Configuration",
		"company": cstr(get_document_value(document, "name")).strip(),
	}

	for company_field, config_field in COMPANY_TO_TAX_CONFIGURATION_FIELD_MAP.items():
		value = get_document_value(document, company_field)
		if config_field == "enabled":
			value = cint(value)
		elif config_field == "include_employee_cost_in_cash_planning":
			value = cint(value)
		else:
			value = cstr(value).strip() if isinstance(value, str) else value

		payload[config_field] = value

	payload["vat_liquidation_cadence"] = normalize_cadence(payload.get("vat_liquidation_cadence"))
	payload["employee_cost_source_mode"] = normalize_employee_cost_source_mode(
		payload.get("employee_cost_source_mode")
	)
	return payload


def should_manage_tax_configuration(document, payload: dict[str, Any]) -> bool:
	country = normalize_country(get_document_value(document, "country"))
	if country == "italy":
		return True

	return any(
		value not in (None, "", 0, "0")
		for fieldname, value in payload.items()
		if fieldname not in {"doctype", "company", "vat_liquidation_cadence", "employee_cost_source_mode"}
	)


def build_company_updates_from_tax_configuration(document: Any) -> dict[str, Any]:
	updates: dict[str, Any] = {}
	for config_field, company_field in TAX_CONFIGURATION_TO_COMPANY_FIELD_MAP.items():
		value = get_document_value(document, config_field)
		if config_field in {"enabled", "include_employee_cost_in_cash_planning"}:
			value = cint(value)
		elif isinstance(value, str):
			value = cstr(value).strip()

		updates[company_field] = value
	return updates


def build_missing_configuration_setup_updates(document: Any) -> dict[str, Any]:
	company = cstr(get_document_value(document, "company")).strip()
	if not company:
		frappe.throw(_("Set Company before provisioning VAT setup."))

	cadence = normalize_cadence(get_document_value(document, "vat_liquidation_cadence"))
	current_values = {
		fieldname: get_document_value(document, fieldname)
		for fieldname in {
			*DEFAULT_TAX_ACCOUNT_SPECS,
			"quarterly_interest_account",
			"default_tax_payment_mode",
			"first_managed_period_start_date",
		}
	}
	updates = build_missing_tax_setup_updates(company, cadence, current_values)
	if not current_values.get("first_managed_period_start_date"):
		updates["first_managed_period_start_date"] = resolve_first_managed_period_start_date(company)
	if not cstr(current_values.get("default_tax_payment_mode")).strip():
		updates["default_tax_payment_mode"] = ensure_default_mode_of_payment()
	return updates


def build_missing_tax_setup_updates(
	company: str, cadence: Any, current_values: dict[str, Any]
) -> dict[str, Any]:
	updates: dict[str, Any] = {}
	for fieldname, account_spec in DEFAULT_TAX_ACCOUNT_SPECS.items():
		if cstr(current_values.get(fieldname)).strip():
			continue
		updates[fieldname] = ensure_default_tax_account(company, **account_spec)

	if normalize_cadence(cadence) == "Quarterly" and not cstr(
		current_values.get("quarterly_interest_account")
	).strip():
		updates["quarterly_interest_account"] = ensure_default_expense_account(
			company, DEFAULT_QUARTERLY_INTEREST_ACCOUNT_NAME
		)

	return updates


def ensure_default_tax_account(company: str, *, account_name: str, root_type: str) -> str:
	account = get_or_create_account(
		company,
		{
			"account_name": account_name,
			"root_type": root_type,
		},
	)
	return account.name


def ensure_default_expense_account(company: str, account_name: str) -> str:
	existing = frappe.db.get_value(
		"Account",
		{"company": company, "root_type": "Expense", "account_name": account_name},
		"name",
	)
	if existing:
		return existing

	parent_account = get_default_expense_parent(company)
	account = frappe.get_doc(
		{
			"doctype": "Account",
			"company": company,
			"account_name": account_name,
			"parent_account": parent_account,
			"report_type": "Profit and Loss",
			"root_type": "Expense",
			"is_group": 0,
		}
	)
	account.flags.ignore_links = True
	account.flags.ignore_validate = True
	account.insert(ignore_permissions=True, ignore_mandatory=True, ignore_if_duplicate=True)
	return account.name


def ensure_default_mode_of_payment() -> str:
	existing = frappe.db.get_value("Mode of Payment", DEFAULT_TAX_PAYMENT_MODE_NAME, "name")
	if existing:
		return existing

	mode = frappe.get_doc(
		{
			"doctype": "Mode of Payment",
			"mode_of_payment": DEFAULT_TAX_PAYMENT_MODE_NAME,
			"type": DEFAULT_TAX_PAYMENT_MODE_TYPE,
			"enabled": 1,
		}
	)
	mode.insert(ignore_permissions=True)
	return mode.name


def resolve_first_managed_period_start_date(company: str):
	default_fiscal_year = frappe.db.get_value("Company", company, "default_fiscal_year")
	if default_fiscal_year:
		year_start_date = frappe.db.get_value("Fiscal Year", default_fiscal_year, "year_start_date")
		if year_start_date:
			return year_start_date

	current_year_start = frappe.db.get_value(
		"Fiscal Year",
		{
			"year_start_date": ("<=", nowdate()),
			"year_end_date": (">=", nowdate()),
		},
		"year_start_date",
		order_by="year_start_date desc",
	)
	if current_year_start:
		return current_year_start

	today = getdate(nowdate())
	return today.replace(month=1, day=1)


def get_default_expense_parent(company: str) -> str:
	parent_account = frappe.db.get_value(
		"Account",
		{"company": company, "root_type": "Expense", "account_name": "Indirect Expenses", "is_group": 1},
		"name",
	)
	if parent_account:
		return parent_account

	root_accounts = frappe.get_all(
		"Account",
		filters={
			"company": company,
			"root_type": "Expense",
			"is_group": 1,
			"report_type": "Profit and Loss",
			"parent_account": ("is", "not set"),
		},
		pluck="name",
		limit=1,
	)
	if root_accounts:
		return root_accounts[0]

	frappe.throw(f"Could not determine an expense parent account for company {company}.")


def apply_company_updates(document: Any, company: str, updates: dict[str, Any]) -> None:
	frappe.db.set_value("Company", company, updates, update_modified=False)
	for fieldname, value in updates.items():
		set_document_value(document, fieldname, value)


def normalize_cadence(value: Any) -> str:
	text = cstr(value).strip()
	if text in VAT_LIQUIDATION_CADENCES:
		return text
	return "Monthly"


def normalize_employee_cost_source_mode(value: Any) -> str:
	text = cstr(value).strip()
	if text in EMPLOYEE_COST_SOURCE_MODES:
		return text
	return "Accounting Entries"


def normalize_country(value: Any) -> str:
	return cstr(value).strip().lower()


def get_document_value(document: Any, fieldname: str) -> Any:
	getter = getattr(document, "get", None)
	if callable(getter):
		return getter(fieldname)
	return getattr(document, fieldname, None)


def set_document_value(document: Any, fieldname: str, value: Any) -> None:
	setter = getattr(document, "set", None)
	if callable(setter):
		setter(fieldname, value)
		return
	if isinstance(document, dict):
		document[fieldname] = value
		return
	setattr(document, fieldname, value)
