from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from fab_italy_tax.company_tax_settings import (
	backfill_company_tax_fields,
	ensure_enabled_company_tax_setup,
)
from fab_italy_tax.invoice_naming import sync_italy_invoice_naming_series
from fab_italy_tax.tax_calendar import sync_existing_vat_period_tax_calendar_events
from fab_italy_tax.vat_period_generation import sync_enabled_tax_configuration_vat_periods
from fab_italy_tax.yearly_close import backfill_invoice_competence_years


def after_install():
	ensure_custom_fields()
	sync_italy_invoice_naming_series()
	backfill_company_tax_fields()
	backfill_invoice_competence_years()
	ensure_enabled_company_tax_setup()
	sync_enabled_tax_configuration_vat_periods()
	sync_existing_vat_period_tax_calendar_events()
	ensure_standard_vat_rate_registry()


def after_migrate():
	ensure_custom_fields()
	sync_italy_invoice_naming_series()
	backfill_company_tax_fields()
	backfill_invoice_competence_years()
	ensure_enabled_company_tax_setup()
	sync_enabled_tax_configuration_vat_periods()
	sync_existing_vat_period_tax_calendar_events()
	ensure_standard_vat_rate_registry()


def ensure_custom_fields():
	create_custom_fields(get_custom_fields(), update=True)


def get_custom_fields() -> dict[str, list[dict[str, object]]]:
	return {
		"Company": get_company_custom_fields(),
		"Sales Invoice": get_sales_invoice_custom_fields(),
		"Purchase Invoice": get_purchase_invoice_custom_fields(),
		"Sales Invoice Item": get_sales_invoice_item_custom_fields(),
		"Purchase Invoice Item": get_purchase_invoice_item_custom_fields(),
	}


def get_company_custom_fields() -> list[dict[str, object]]:
	return [
		{
			"fieldname": "fab_itx_section",
			"label": "Italy Tax",
			"fieldtype": "Section Break",
			"insert_after": "payment_terms",
		},
		{
			"fieldname": "fab_itx_enabled",
			"label": "Enable Italy Tax Management",
			"fieldtype": "Check",
			"insert_after": "fab_itx_section",
		},
		{
			"fieldname": "fab_itx_vat_liquidation_cadence",
			"label": "VAT Liquidation Cadence",
			"fieldtype": "Select",
			"options": "\nMonthly\nQuarterly",
			"default": "Monthly",
			"insert_after": "fab_itx_enabled",
		},
		{
			"fieldname": "fab_itx_first_managed_period_start_date",
			"label": "First Managed Period Start Date",
			"fieldtype": "Date",
			"insert_after": "fab_itx_vat_liquidation_cadence",
		},
		{
			"fieldname": "fab_itx_column_break_setup",
			"fieldtype": "Column Break",
			"insert_after": "fab_itx_first_managed_period_start_date",
		},
		{
			"fieldname": "fab_itx_settlement_journal_naming_series",
			"label": "Settlement Journal Naming Series",
			"fieldtype": "Data",
			"insert_after": "fab_itx_column_break_setup",
		},
		{
			"fieldname": "fab_itx_default_tax_payment_mode",
			"label": "Default Tax Payment Mode",
			"fieldtype": "Link",
			"options": "Mode of Payment",
			"insert_after": "fab_itx_settlement_journal_naming_series",
		},
		{
			"fieldname": "fab_itx_accounts_section",
			"label": "Italy Tax Settlement Accounts",
			"fieldtype": "Section Break",
			"insert_after": "fab_itx_default_tax_payment_mode",
		},
		{
			"fieldname": "fab_itx_vat_output_account",
			"label": "VAT Output Account",
			"fieldtype": "Link",
			"options": "Account",
			"insert_after": "fab_itx_accounts_section",
		},
		{
			"fieldname": "fab_itx_vat_input_account",
			"label": "VAT Input Account",
			"fieldtype": "Link",
			"options": "Account",
			"insert_after": "fab_itx_vat_output_account",
		},
		{
			"fieldname": "fab_itx_vat_payable_account",
			"label": "VAT Payable Account",
			"fieldtype": "Link",
			"options": "Account",
			"insert_after": "fab_itx_vat_input_account",
		},
		{
			"fieldname": "fab_itx_column_break_accounts",
			"fieldtype": "Column Break",
			"insert_after": "fab_itx_vat_payable_account",
		},
		{
			"fieldname": "fab_itx_vat_credit_account",
			"label": "VAT Credit Account",
			"fieldtype": "Link",
			"options": "Account",
			"insert_after": "fab_itx_column_break_accounts",
		},
		{
			"fieldname": "fab_itx_quarterly_interest_account",
			"label": "Quarterly Interest Account",
			"fieldtype": "Link",
			"options": "Account",
			"depends_on": "eval:doc.fab_itx_vat_liquidation_cadence=='Quarterly'",
			"insert_after": "fab_itx_vat_credit_account",
		},
		{
			"fieldname": "fab_itx_carry_forward_account",
			"label": "Carry Forward Account",
			"fieldtype": "Link",
			"options": "Account",
			"insert_after": "fab_itx_quarterly_interest_account",
		},
		{
			"fieldname": "fab_itx_cash_planning_section",
			"label": "Italy Tax Cash Planning",
			"fieldtype": "Section Break",
			"insert_after": "fab_itx_carry_forward_account",
		},
		{
			"fieldname": "fab_itx_include_employee_cost_in_cash_planning",
			"label": "Include Employee Cost in Cash Planning",
			"fieldtype": "Check",
			"insert_after": "fab_itx_cash_planning_section",
		},
		{
			"fieldname": "fab_itx_employee_cost_source_mode",
			"label": "Employee Cost Source Mode",
			"fieldtype": "Select",
			"options": "\nHRMS Payroll\nAccounting Entries\nManual Adjustments\nEmployee Cost Entries",
			"default": "Accounting Entries",
			"insert_after": "fab_itx_include_employee_cost_in_cash_planning",
		},
		{
			"fieldname": "fab_itx_year_close_section",
			"label": "Italy Year-end Close",
			"fieldtype": "Section Break",
			"insert_after": "fab_itx_employee_cost_source_mode",
		},
		{
			"fieldname": "fab_itx_accrued_revenue_account",
			"label": "Accrued Revenue Account",
			"fieldtype": "Link",
			"options": "Account",
			"insert_after": "fab_itx_year_close_section",
		},
		{
			"fieldname": "fab_itx_accrued_expense_account",
			"label": "Accrued Expense Account",
			"fieldtype": "Link",
			"options": "Account",
			"insert_after": "fab_itx_accrued_revenue_account",
		},
	]


def get_sales_invoice_item_custom_fields() -> list[dict[str, object]]:
	return [
		{
			"fieldname": "fab_itx_competence_start_date",
			"label": "Competence Start Date",
			"fieldtype": "Date",
			"allow_on_submit": 1,
			"insert_after": "service_end_date",
		},
		{
			"fieldname": "fab_itx_competence_end_date",
			"label": "Competence End Date",
			"fieldtype": "Date",
			"allow_on_submit": 1,
			"insert_after": "fab_itx_competence_start_date",
		},
	]


def get_purchase_invoice_item_custom_fields() -> list[dict[str, object]]:
	return [
		{
			"fieldname": "fab_itx_competence_start_date",
			"label": "Competence Start Date",
			"fieldtype": "Date",
			"allow_on_submit": 1,
			"insert_after": "service_end_date",
		},
		{
			"fieldname": "fab_itx_competence_end_date",
			"label": "Competence End Date",
			"fieldtype": "Date",
			"allow_on_submit": 1,
			"insert_after": "fab_itx_competence_start_date",
		},
		{
			"fieldname": "fab_itx_deductibility_mode",
			"label": "Deductibility Mode",
			"fieldtype": "Select",
			"options": "\nFully Deductible\nPartially Deductible (%)\nPartially Deductible (Amount)\nNon Deductible",
			"default": "Fully Deductible",
			"allow_on_submit": 1,
			"in_list_view": 1,
			"columns": 2,
			"insert_after": "fab_itx_competence_end_date",
		},
		{
			"fieldname": "fab_itx_deductible_percentage",
			"label": "Deductible Percentage",
			"fieldtype": "Percent",
			"allow_on_submit": 1,
			"in_list_view": 1,
			"columns": 1,
			"depends_on": "eval:doc.fab_itx_deductibility_mode=='Partially Deductible (%)'",
			"insert_after": "fab_itx_deductibility_mode",
		},
		{
			"fieldname": "fab_itx_deductible_amount",
			"label": "Deductible Amount",
			"fieldtype": "Currency",
			"allow_on_submit": 1,
			"in_list_view": 1,
			"columns": 1,
			"depends_on": "eval:doc.fab_itx_deductibility_mode=='Partially Deductible (Amount)'",
			"insert_after": "fab_itx_deductible_percentage",
		},
	]


def get_sales_invoice_custom_fields() -> list[dict[str, object]]:
	return [build_competence_year_custom_field(insert_after="due_date")]


def get_purchase_invoice_custom_fields() -> list[dict[str, object]]:
	return [
		build_competence_year_custom_field(insert_after="due_date"),
		{
			"fieldname": "fab_itx_invoice_deductibility_mode",
			"label": "Invoice Deductibility Override",
			"fieldtype": "Select",
			"options": "\nFully Deductible\nPartially Deductible (%)\nPartially Deductible (Amount)\nNon Deductible",
			"description": "When set, overrides line-level deductibility for the whole invoice.",
			"allow_on_submit": 1,
			"insert_after": "fab_itx_competence_year",
		},
		{
			"fieldname": "fab_itx_invoice_deductible_percentage",
			"label": "Invoice Deductible Percentage",
			"fieldtype": "Percent",
			"allow_on_submit": 1,
			"depends_on": "eval:doc.fab_itx_invoice_deductibility_mode=='Partially Deductible (%)'",
			"insert_after": "fab_itx_invoice_deductibility_mode",
		},
		{
			"fieldname": "fab_itx_invoice_deductible_amount",
			"label": "Invoice Deductible Amount",
			"fieldtype": "Currency",
			"allow_on_submit": 1,
			"depends_on": "eval:doc.fab_itx_invoice_deductibility_mode=='Partially Deductible (Amount)'",
			"insert_after": "fab_itx_invoice_deductible_percentage",
		},
	]


def build_competence_year_custom_field(insert_after: str) -> dict[str, object]:
	return {
		"fieldname": "fab_itx_competence_year",
		"label": "Competence Year",
		"fieldtype": "Select",
		"description": "Set the accounting competence year. Selecting invoice year minus 1 creates or restores the prior-year competence accrual automatically on save.",
		"allow_on_submit": 1,
		"insert_after": insert_after,
	}

def ensure_standard_vat_rate_registry():
	# doctype may not be synced yet on fresh installs before migrate
	if not frappe.db.exists("DocType", "Italy VAT Rate"):
		return
	from fab_italy_tax.vat_rates import ensure_standard_vat_rates, sync_vat_rate_templates

	ensure_standard_vat_rates()
	sync_vat_rate_templates()
