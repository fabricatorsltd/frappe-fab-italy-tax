from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate, getdate

from fab_italy_tax.cashflow import get_company_cash_flow
from fab_italy_tax.labor_costs import DEFAULT_TRAILING_MONTHS


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)
	data = get_company_cash_flow(
		company=filters.company,
		from_date=filters.from_date,
		to_date=filters.to_date,
		include_overdue=bool(cint(filters.get("include_overdue", 1))),
		include_employee_cost=bool(cint(filters.get("include_employee_cost", 1))),
		trailing_months=cint(filters.get("trailing_months") or DEFAULT_TRAILING_MONTHS),
	)
	return get_columns(), data, None, build_chart_data(data), build_report_summary(data)


def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Select a Company first."))
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("Set both From Date and To Date."))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date."))


def get_columns():
	return [
		{
			"fieldname": "event_date",
			"label": _("Event Date"),
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"fieldname": "event_type",
			"label": _("Event Type"),
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"fieldname": "status",
			"label": _("Status"),
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"fieldname": "party",
			"label": _("Party"),
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"fieldname": "source_detail",
			"label": _("Source Detail"),
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"fieldname": "reference_doctype",
			"label": _("Reference DocType"),
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"fieldname": "reference_name",
			"label": _("Reference Name"),
			"fieldtype": "Dynamic Link",
			"options": "reference_doctype",
			"width": 160,
		},
		{
			"fieldname": "source_amount",
			"label": _("Document Amount"),
			"fieldtype": "Currency",
			"options": "source_currency",
			"width": 130,
		},
		{
			"fieldname": "source_currency",
			"label": _("Document Currency"),
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"fieldname": "inflow_amount",
			"label": _("Inflow Amount"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"fieldname": "outflow_amount",
			"label": _("Outflow Amount"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"fieldname": "projected_balance",
			"label": _("Projected Balance"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
	]


def build_chart_data(rows):
	if not rows:
		return None

	daily_totals = defaultdict(lambda: {"inflow_amount": 0.0, "outflow_amount": 0.0, "projected_balance": 0.0})
	for row in rows:
		date_key = getdate(row.get("event_date"))
		daily_totals[date_key]["inflow_amount"] += flt(row.get("inflow_amount"))
		daily_totals[date_key]["outflow_amount"] += flt(row.get("outflow_amount"))
		daily_totals[date_key]["projected_balance"] = flt(row.get("projected_balance"))

	ordered_dates = sorted(daily_totals)
	return {
		"data": {
			"labels": [formatdate(date_value) for date_value in ordered_dates],
			"datasets": [
				{
					"name": _("Projected Balance"),
					"values": [round(daily_totals[date_value]["projected_balance"], 2) for date_value in ordered_dates],
				},
				{
					"name": _("Planned Inflows"),
					"values": [round(daily_totals[date_value]["inflow_amount"], 2) for date_value in ordered_dates],
				},
				{
					"name": _("Planned Outflows"),
					"values": [round(daily_totals[date_value]["outflow_amount"], 2) for date_value in ordered_dates],
				},
			],
		},
		"type": "line",
		"colors": ["#2490ef", "#2ecc71", "#e74c3c"],
	}


def build_report_summary(rows):
	if not rows:
		return None

	currency = rows[0].get("currency")
	opening_balance = flt(rows[0].get("projected_balance"))
	total_inflows = sum(flt(row.get("inflow_amount")) for row in rows)
	total_outflows = sum(flt(row.get("outflow_amount")) for row in rows)
	closing_balance = flt(rows[-1].get("projected_balance"))
	return [
		{
			"value": opening_balance,
			"indicator": "Blue",
			"label": _("Opening Liquid Balance"),
			"datatype": "Currency",
			"currency": currency,
		},
		{
			"value": total_inflows,
			"indicator": "Green",
			"label": _("Planned Inflows"),
			"datatype": "Currency",
			"currency": currency,
		},
		{
			"value": total_outflows,
			"indicator": "Red",
			"label": _("Planned Outflows"),
			"datatype": "Currency",
			"currency": currency,
		},
		{
			"value": closing_balance,
			"indicator": "Orange" if closing_balance < 0 else "Blue",
			"label": _("Projected Closing Balance"),
			"datatype": "Currency",
			"currency": currency,
		},
	]
