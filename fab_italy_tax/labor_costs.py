from __future__ import annotations

from collections import defaultdict
from typing import Any

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, get_first_day, get_last_day, getdate

EMPLOYEE_COST_ENTRY_SOURCE_MODE = "Employee Cost Entries"
DEFAULT_TRAILING_MONTHS = 6
EMPLOYEE_COST_HISTORY_FIELDS = [
	"cost_month",
	"employee",
	"employee_name",
	"employee_identifier",
	"source_type",
	"accrual_journal_entry",
	"gross_monthly_amount",
	"employer_contribution_amount",
	"inail_amount",
	"tfr_accrual_amount",
	"total_company_cost",
	"currency",
]


def get_employee_cost_cash_planning(
	company: str,
	from_month: str,
	to_month: str,
	include_estimates: bool = True,
	trailing_months: int = DEFAULT_TRAILING_MONTHS,
	exclude_posted_entries: bool = False,
) -> list[dict[str, Any]]:
	ensure_employee_cost_cash_planning_enabled(company)
	ensure_employee_cost_entry_support()

	start_month = get_first_day(getdate(from_month))
	end_month = get_first_day(getdate(to_month))
	if start_month > end_month:
		frappe.throw(_("From Month cannot be after To Month."))

	trailing_months = cint(trailing_months)
	if trailing_months < 1:
		frappe.throw(_("Trailing Months must be at least 1."))

	history_rows = frappe.get_all(
		"Employee Cost Entry",
		filters={"company": company, "cost_month": ["<=", end_month]},
		fields=EMPLOYEE_COST_HISTORY_FIELDS,
		order_by="cost_month asc, employee_name asc",
	)
	posted_months: set[str] = set()
	if exclude_posted_entries:
		posted_months = get_submitted_journal_entry_months(history_rows)
		history_rows = exclude_submitted_journal_entry_rows(history_rows)
	actual_rows = [
		row for row in history_rows if start_month <= get_first_day(getdate(row.get("cost_month"))) <= end_month
	]
	actual_monthly_totals = build_actual_monthly_totals(actual_rows)
	currency = frappe.db.get_value("Company", company, "default_currency")

	rows: list[dict[str, Any]] = []
	current_month = start_month
	while current_month <= end_month:
		month_key = current_month.isoformat()
		if month_key in posted_months:
			current_month = add_months(current_month, 1)
			continue
		if month_key in actual_monthly_totals:
			rows.append(build_actual_planning_row(month_key, actual_monthly_totals[month_key], currency))
		elif include_estimates:
			summary = summarize_trailing_history(history_rows, current_month, trailing_months)
			if summary:
				rows.append(build_estimated_planning_row(month_key, summary, currency))

		current_month = add_months(current_month, 1)

	return rows


def exclude_submitted_journal_entry_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
	submitted_entries = get_submitted_journal_entries(rows)
	return [
		row for row in rows if not row.get("accrual_journal_entry") or row["accrual_journal_entry"] not in submitted_entries
	]


def get_submitted_journal_entry_months(rows: list[dict[str, Any]]) -> set[str]:
	submitted_entries = get_submitted_journal_entries(rows)
	return {
		get_first_day(getdate(row.get("cost_month"))).isoformat()
		for row in rows
		if row.get("accrual_journal_entry") and row["accrual_journal_entry"] in submitted_entries
	}


def get_submitted_journal_entries(rows: list[dict[str, Any]]) -> set[str]:
	journal_entries = sorted(
		{row.get("accrual_journal_entry") for row in rows if row.get("accrual_journal_entry")}
	)
	if not journal_entries:
		return set()
	return set(
		frappe.get_all(
			"Journal Entry",
			filters={"name": ["in", journal_entries], "docstatus": 1},
			pluck="name",
		)
	)


def ensure_employee_cost_cash_planning_enabled(company: str) -> None:
	settings = frappe.db.get_value(
		"Company",
		company,
		[
			"fab_itx_include_employee_cost_in_cash_planning",
			"fab_itx_employee_cost_source_mode",
		],
		as_dict=True,
	) or {}
	if not cint(settings.get("fab_itx_include_employee_cost_in_cash_planning")):
		frappe.throw(_("Enable Include Employee Cost in Cash Planning for company {0}.").format(company))

	if settings.get("fab_itx_employee_cost_source_mode") != EMPLOYEE_COST_ENTRY_SOURCE_MODE:
		frappe.throw(
			_("Set Employee Cost Source Mode to {0} for company {1}.").format(
				EMPLOYEE_COST_ENTRY_SOURCE_MODE, company
			)
		)


def ensure_employee_cost_entry_support() -> None:
	if not frappe.db.exists("DocType", "Employee Cost Entry"):
		frappe.throw(
			_("Install and migrate fab_hr_italy before using Employee Cost Entries cash planning.")
		)


def build_actual_monthly_totals(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
	monthly_totals: defaultdict[str, dict[str, Any]] = defaultdict(
		lambda: {
			"gross_monthly_amount": 0.0,
			"employer_contribution_amount": 0.0,
			"inail_amount": 0.0,
			"tfr_accrual_amount": 0.0,
			"total_company_cost": 0.0,
			"employees": set(),
			"source_types": set(),
		}
	)
	for row in rows:
		month_key = get_first_day(getdate(row.get("cost_month"))).isoformat()
		monthly_totals[month_key]["gross_monthly_amount"] += flt(row.get("gross_monthly_amount"))
		monthly_totals[month_key]["employer_contribution_amount"] += flt(
			row.get("employer_contribution_amount")
		)
		monthly_totals[month_key]["inail_amount"] += flt(row.get("inail_amount"))
		monthly_totals[month_key]["tfr_accrual_amount"] += flt(row.get("tfr_accrual_amount"))
		monthly_totals[month_key]["total_company_cost"] += flt(row.get("total_company_cost"))
		employee_key = row.get("employee_identifier") or row.get("employee") or row.get("employee_name")
		if employee_key:
			monthly_totals[month_key]["employees"].add(employee_key)
		if row.get("source_type"):
			monthly_totals[month_key]["source_types"].add(row["source_type"])

	return dict(monthly_totals)


def build_actual_planning_row(month_key: str, totals: dict[str, Any], currency: str | None) -> dict[str, Any]:
	return {
		"planning_month": month_key,
		"planning_month_label": format_month_label(month_key),
		"due_date": get_last_day(month_key),
		"planning_type": _("Actual"),
		"source_detail": ", ".join(sorted(totals["source_types"])) or EMPLOYEE_COST_ENTRY_SOURCE_MODE,
		"employee_count": len(totals["employees"]),
		"gross_monthly_amount": round(flt(totals["gross_monthly_amount"]), 2),
		"employer_contribution_amount": round(flt(totals["employer_contribution_amount"]), 2),
		"employer_insurance_amount": round(flt(totals["inail_amount"]), 2),
		"tfr_accrual_amount": round(flt(totals["tfr_accrual_amount"]), 2),
		"total_company_cost": round(flt(totals["total_company_cost"]), 2),
		"currency": currency,
	}


def build_estimated_planning_row(
	month_key: str, summary: dict[str, Any], currency: str | None
) -> dict[str, Any]:
	return {
		"planning_month": month_key,
		"planning_month_label": format_month_label(month_key),
		"due_date": get_last_day(month_key),
		"planning_type": _("Estimated"),
		"source_detail": _("Estimated from last {0} months").format(summary["month_count"]),
		"employee_count": summary["average_monthly_headcount"],
		"gross_monthly_amount": round(flt(summary["average_monthly_gross_monthly_amount"]), 2),
		"employer_contribution_amount": round(
			flt(summary["average_monthly_employer_contribution_amount"]), 2
		),
		"employer_insurance_amount": round(flt(summary["average_monthly_employer_insurance_amount"]), 2),
		"tfr_accrual_amount": round(flt(summary["average_monthly_tfr_accrual_amount"]), 2),
		"total_company_cost": round(flt(summary["average_monthly_total_company_cost"]), 2),
		"currency": currency,
	}


def summarize_trailing_history(
	history_rows: list[dict[str, Any]], planning_month, trailing_months: int
) -> dict[str, Any] | None:
	relevant_rows = [
		row
		for row in history_rows
		if get_first_day(getdate(row.get("cost_month"))) < get_first_day(getdate(planning_month))
	]
	if not relevant_rows:
		return None

	selected_months: list[str] = []
	seen_months: set[str] = set()
	for row in reversed(relevant_rows):
		month_key = get_first_day(getdate(row.get("cost_month"))).isoformat()
		if month_key in seen_months:
			continue
		seen_months.add(month_key)
		selected_months.append(month_key)
		if len(selected_months) >= trailing_months:
			break

	selected_rows = [
		row
		for row in relevant_rows
		if get_first_day(getdate(row.get("cost_month"))).isoformat() in set(selected_months)
	]
	if not selected_rows:
		return None

	from fab_hr_italy.company_costing import serialize_employee_cost_history_summary, summarize_employee_cost_history

	return serialize_employee_cost_history_summary(summarize_employee_cost_history(selected_rows))


def format_month_label(value: Any) -> str:
	return get_first_day(getdate(value)).strftime("%m-%Y")
