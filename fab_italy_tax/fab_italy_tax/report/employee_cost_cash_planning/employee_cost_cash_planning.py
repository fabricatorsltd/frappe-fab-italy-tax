from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt, get_first_day, getdate

from fab_italy_tax.labor_costs import DEFAULT_TRAILING_MONTHS, get_employee_cost_cash_planning


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)
	data = get_employee_cost_cash_planning(
		company=filters.company,
		from_month=filters.from_month,
		to_month=filters.to_month,
		include_estimates=bool(cint(filters.get("include_estimates", 1))),
		trailing_months=cint(filters.get("trailing_months") or DEFAULT_TRAILING_MONTHS),
	)
	return get_columns(), data, None, build_chart_data(data), build_report_summary(data)


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Select a Company first."))
	if not filters.get("from_month") or not filters.get("to_month"):
		frappe.throw(_("Set both From Month and To Month."))
	if get_first_day(getdate(filters.from_month)) > get_first_day(getdate(filters.to_month)):
		frappe.throw(_("From Month cannot be after To Month."))


def get_columns():
	return [
		{
			"fieldname": "planning_month_label",
			"label": _("Reference Month"),
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"fieldname": "due_date",
			"label": _("Due Date"),
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"fieldname": "planning_type",
			"label": _("Planning Type"),
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"fieldname": "source_detail",
			"label": _("Source Detail"),
			"fieldtype": "Data",
			"width": 170,
		},
		{
			"fieldname": "employee_count",
			"label": _("Employee Count"),
			"fieldtype": "Float",
			"precision": 1,
			"width": 110,
		},
		{
			"fieldname": "gross_monthly_amount",
			"label": _("Gross Pay"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"fieldname": "employer_contribution_amount",
			"label": _("Employer Contributions"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"fieldname": "employer_insurance_amount",
			"label": _("Employer Insurance"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{
			"fieldname": "tfr_accrual_amount",
			"label": _("TFR Accrual"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"fieldname": "total_company_cost",
			"label": _("Total Company Cost"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
	]


def build_chart_data(rows):
	if not rows:
		return None

	return {
		"data": {
			"labels": [row["planning_month_label"] for row in rows],
			"datasets": [
				{
					"name": _("Total Company Cost"),
					"values": [flt(row.get("total_company_cost"), 2) for row in rows],
				},
				{
					"name": _("Gross Pay"),
					"values": [flt(row.get("gross_monthly_amount"), 2) for row in rows],
				},
			],
		},
		"type": "line",
		"colors": ["#2490ef", "#8e44ad"],
	}


def build_report_summary(rows):
	if not rows:
		return None

	currency = rows[0].get("currency")
	return [
		{
			"value": sum(flt(row.get("total_company_cost")) for row in rows),
			"indicator": "Blue",
			"label": _("Planned Total Company Cost"),
			"datatype": "Currency",
			"currency": currency,
		},
		{
			"value": sum(flt(row.get("gross_monthly_amount")) for row in rows),
			"indicator": "Green",
			"label": _("Planned Gross Pay"),
			"datatype": "Currency",
			"currency": currency,
		},
		{
			"value": sum(1 for row in rows if row.get("planning_type") == _("Actual")),
			"indicator": "Grey",
			"label": _("Actual Months"),
			"datatype": "Int",
		},
		{
			"value": sum(1 for row in rows if row.get("planning_type") == _("Estimated")),
			"indicator": "Orange",
			"label": _("Estimated Months"),
			"datatype": "Int",
		},
	]
