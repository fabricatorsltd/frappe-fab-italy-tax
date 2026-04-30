from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, get_first_day, getdate

from fab_italy_tax.labor_costs import (
	DEFAULT_TRAILING_MONTHS,
	EMPLOYEE_COST_ENTRY_SOURCE_MODE,
	get_employee_cost_cash_planning,
)

OPENING_BALANCE_EVENT_TYPE = "Opening Balance"
RECEIVABLE_EVENT_TYPE = "Receivable Due"
PAYABLE_EVENT_TYPE = "Payable Due"
EMPLOYEE_COST_EVENT_TYPE = "Employee Cost"
EVENT_TYPE_ORDER = {
	OPENING_BALANCE_EVENT_TYPE: 0,
	RECEIVABLE_EVENT_TYPE: 1,
	PAYABLE_EVENT_TYPE: 2,
	"VAT Payment": 3,
	"VAT Settlement": 4,
	"F24 Deadline": 5,
	"Manual Tax Deadline": 6,
	EMPLOYEE_COST_EVENT_TYPE: 7,
}


def get_company_cash_flow(
	company: str,
	from_date: str,
	to_date: str,
	include_overdue: bool = True,
	include_employee_cost: bool = True,
	trailing_months: int = DEFAULT_TRAILING_MONTHS,
) -> list[dict[str, Any]]:
	start_date = getdate(from_date)
	end_date = getdate(to_date)
	if start_date > end_date:
		frappe.throw(_("From Date cannot be after To Date."))

	company_currency = frappe.db.get_value("Company", company, "default_currency")
	liquid_accounts = get_liquid_account_names(company)
	opening_balance = get_opening_liquid_balance(company, start_date, liquid_accounts)

	rows = [
		build_opening_balance_row(
			start_date=start_date,
			company_currency=company_currency,
			opening_balance=opening_balance,
			liquid_accounts=liquid_accounts,
		)
	]
	rows.extend(
		get_receivable_cash_flow_rows(
			company=company,
			company_currency=company_currency,
			start_date=start_date,
			end_date=end_date,
			include_overdue=include_overdue,
		)
	)
	rows.extend(
		get_payable_cash_flow_rows(
			company=company,
			company_currency=company_currency,
			start_date=start_date,
			end_date=end_date,
			include_overdue=include_overdue,
		)
	)
	rows.extend(
		get_tax_calendar_cash_flow_rows(
			company=company,
			company_currency=company_currency,
			start_date=start_date,
			end_date=end_date,
			include_overdue=include_overdue,
		)
	)
	rows.extend(
		get_employee_cost_cash_flow_rows(
			company=company,
			company_currency=company_currency,
			start_date=start_date,
			end_date=end_date,
			include_employee_cost=include_employee_cost,
			trailing_months=trailing_months,
		)
	)

	return apply_running_balance(sort_cash_flow_rows(rows), opening_balance)


def get_liquid_account_names(company: str) -> list[str]:
	return frappe.get_all(
		"Account",
		filters={
			"company": company,
			"is_group": 0,
			"account_type": ["in", ["Bank", "Cash"]],
		},
		pluck="name",
		order_by="name asc",
	)


def get_opening_liquid_balance(company: str, start_date, liquid_accounts: list[str]) -> float:
	if not liquid_accounts:
		return 0.0

	entries = frappe.get_all(
		"GL Entry",
		filters={
			"company": company,
			"account": ["in", liquid_accounts],
			"is_cancelled": 0,
			"posting_date": ["<", start_date],
		},
		fields=["debit", "credit"],
	)
	return round(sum(flt(row.get("debit")) - flt(row.get("credit")) for row in entries), 2)


def get_receivable_cash_flow_rows(
	company: str,
	company_currency: str | None,
	start_date,
	end_date,
	include_overdue: bool,
) -> list[dict[str, Any]]:
	filters = {
		"company": company,
		"docstatus": 1,
		"is_return": 0,
		"outstanding_amount": [">", 0],
		"due_date": ["<=", end_date] if include_overdue else ["between", [start_date, end_date]],
	}
	documents = frappe.get_all(
		"Sales Invoice",
		filters=filters,
		fields=[
			"name",
			"customer",
			"due_date",
			"outstanding_amount",
			"currency",
			"conversion_rate",
		],
		order_by="due_date asc, name asc",
	)
	return [
		build_party_cash_flow_row(
			document=row,
			company_currency=company_currency,
			start_date=start_date,
			include_overdue=include_overdue,
			event_type=RECEIVABLE_EVENT_TYPE,
			reference_doctype="Sales Invoice",
			party=row.get("customer"),
			direction="Inflow",
		)
		for row in documents
	]


def get_payable_cash_flow_rows(
	company: str,
	company_currency: str | None,
	start_date,
	end_date,
	include_overdue: bool,
) -> list[dict[str, Any]]:
	filters = {
		"company": company,
		"docstatus": 1,
		"is_return": 0,
		"outstanding_amount": [">", 0],
		"due_date": ["<=", end_date] if include_overdue else ["between", [start_date, end_date]],
	}
	documents = frappe.get_all(
		"Purchase Invoice",
		filters=filters,
		fields=[
			"name",
			"supplier",
			"due_date",
			"outstanding_amount",
			"currency",
			"conversion_rate",
		],
		order_by="due_date asc, name asc",
	)
	return [
		build_party_cash_flow_row(
			document=row,
			company_currency=company_currency,
			start_date=start_date,
			include_overdue=include_overdue,
			event_type=PAYABLE_EVENT_TYPE,
			reference_doctype="Purchase Invoice",
			party=row.get("supplier"),
			direction="Outflow",
		)
		for row in documents
	]


def get_tax_calendar_cash_flow_rows(
	company: str,
	company_currency: str | None,
	start_date,
	end_date,
	include_overdue: bool,
) -> list[dict[str, Any]]:
	filters = {
		"company": company,
		"status": ["not in", ["Cancelled", "Settled"]],
		"event_date": ["<=", end_date] if include_overdue else ["between", [start_date, end_date]],
	}
	events = frappe.get_all(
		"Tax Calendar Event",
		filters=filters,
		fields=[
			"name",
			"event_type",
			"event_date",
			"amount",
			"direction",
			"status",
			"payment_mode",
			"reference_doctype",
			"reference_name",
			"notes",
		],
		order_by="event_date asc, name asc",
	)
	rows: list[dict[str, Any]] = []
	for event in events:
		original_date = getdate(event.get("event_date"))
		event_date = normalize_event_date(original_date, start_date, include_overdue)
		if not event_date:
			continue

		amount = round(flt(event.get("amount")), 2)
		status = _("Overdue") if include_overdue and original_date < start_date else cstr(event.get("status"))
		source_detail = cstr(event.get("payment_mode")).strip() or cstr(event.get("notes")).strip()
		rows.append(
			build_cash_flow_row(
				event_date=event_date,
				event_type=event.get("event_type"),
				status=translate_status(status),
				party="",
				source_detail=source_detail,
				reference_doctype=event.get("reference_doctype"),
				reference_name=event.get("reference_name"),
				source_amount=amount,
				source_currency=company_currency,
				inflow_amount=amount if event.get("direction") == "Inflow" else 0.0,
				outflow_amount=amount if event.get("direction") != "Inflow" else 0.0,
				currency=company_currency,
			)
		)
	return rows


def get_employee_cost_cash_flow_rows(
	company: str,
	company_currency: str | None,
	start_date,
	end_date,
	include_employee_cost: bool,
	trailing_months: int,
) -> list[dict[str, Any]]:
	if not include_employee_cost:
		return []

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
		return []

	source_mode = settings.get("fab_itx_employee_cost_source_mode")
	if source_mode != EMPLOYEE_COST_ENTRY_SOURCE_MODE:
		frappe.throw(
			_("Employee Cost Source Mode {0} is not yet supported in Company Cash Flow Monitor.").format(
				source_mode or _("Not set")
			)
		)

	if not frappe.db.exists("DocType", "Employee Cost Entry"):
		frappe.throw(_("Install and migrate fab_hr_italy before including employee cost in company cash flow."))

	planning_rows = get_employee_cost_cash_planning(
		company=company,
		from_month=get_first_day(start_date),
		to_month=get_first_day(end_date),
		include_estimates=True,
		trailing_months=trailing_months,
		exclude_posted_entries=True,
	)
	return [
		build_cash_flow_row(
			event_date=row.get("due_date"),
			event_type=EMPLOYEE_COST_EVENT_TYPE,
			status=row.get("planning_type"),
			party="",
			source_detail=row.get("source_detail"),
			reference_doctype="",
			reference_name="",
			source_amount=row.get("total_company_cost"),
			source_currency=company_currency,
			inflow_amount=0.0,
			outflow_amount=row.get("total_company_cost"),
			currency=company_currency,
		)
		for row in planning_rows
		if start_date <= getdate(row.get("due_date")) <= end_date
	]


def build_party_cash_flow_row(
	document: dict[str, Any],
	company_currency: str | None,
	start_date,
	include_overdue: bool,
	event_type: str,
	reference_doctype: str,
	party: str | None,
	direction: str,
) -> dict[str, Any]:
	start_date = getdate(start_date)
	original_date = getdate(document.get("due_date"))
	event_date = normalize_event_date(original_date, start_date, include_overdue)
	amount = convert_to_company_currency(
		amount=document.get("outstanding_amount"),
		document_currency=document.get("currency"),
		company_currency=company_currency,
		conversion_rate=document.get("conversion_rate"),
	)
	return build_cash_flow_row(
		event_date=event_date,
		event_type=event_type,
		status=_("Overdue") if include_overdue and original_date < start_date else _("Due"),
		party=party,
		source_detail=_("Original due date: {0}").format(original_date.isoformat())
		if include_overdue and original_date < start_date
		else "",
		reference_doctype=reference_doctype,
		reference_name=document.get("name"),
		source_amount=document.get("outstanding_amount"),
		source_currency=document.get("currency"),
		inflow_amount=amount if direction == "Inflow" else 0.0,
		outflow_amount=amount if direction == "Outflow" else 0.0,
		currency=company_currency,
	)


def build_opening_balance_row(
	start_date,
	company_currency: str | None,
	opening_balance: float,
	liquid_accounts: list[str],
) -> dict[str, Any]:
	account_count = len(liquid_accounts)
	return build_cash_flow_row(
		event_date=start_date,
		event_type=OPENING_BALANCE_EVENT_TYPE,
		status=_("Actual"),
		party="",
		source_detail=_("Opening liquid balance from {0} account(s).").format(account_count)
		if account_count
		else _("No liquid accounts found."),
		reference_doctype="",
		reference_name="",
		source_amount=opening_balance,
		source_currency=company_currency,
		inflow_amount=0.0,
		outflow_amount=0.0,
		currency=company_currency,
	)


def build_cash_flow_row(
	event_date,
	event_type: str | None,
	status: str | None,
	party: str | None,
	source_detail: str | None,
	reference_doctype: str | None,
	reference_name: str | None,
	source_amount: Any,
	source_currency: str | None,
	inflow_amount: Any,
	outflow_amount: Any,
	currency: str | None,
) -> dict[str, Any]:
	return {
		"event_date": getdate(event_date),
		"event_type": translate_event_type(event_type),
		"event_sort_order": EVENT_TYPE_ORDER.get(cstr(event_type).strip(), 99),
		"status": cstr(status).strip(),
		"party": cstr(party).strip(),
		"source_detail": cstr(source_detail).strip(),
		"reference_doctype": cstr(reference_doctype).strip(),
		"reference_name": cstr(reference_name).strip(),
		"source_amount": round(flt(source_amount), 2),
		"source_currency": cstr(source_currency).strip(),
		"inflow_amount": round(flt(inflow_amount), 2),
		"outflow_amount": round(flt(outflow_amount), 2),
		"currency": cstr(currency).strip(),
		"projected_balance": 0.0,
	}


def normalize_event_date(original_date, start_date, include_overdue: bool):
	start_date = getdate(start_date)
	if original_date < start_date:
		return start_date if include_overdue else None
	return original_date


def convert_to_company_currency(
	amount: Any,
	document_currency: str | None,
	company_currency: str | None,
	conversion_rate: Any,
) -> float:
	if cstr(document_currency).strip() in {"", cstr(company_currency).strip()}:
		return round(flt(amount), 2)
	rate = flt(conversion_rate)
	if not rate:
		frappe.throw(_("Missing conversion rate for currency {0}.").format(document_currency))
	return round(flt(amount) * rate, 2)


def sort_cash_flow_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
	return sorted(
		rows,
		key=lambda row: (
			getdate(row.get("event_date")),
			row.get("event_sort_order", EVENT_TYPE_ORDER.get(row.get("event_type"), 99)),
			row.get("reference_doctype") or "",
			row.get("reference_name") or "",
		),
	)


def apply_running_balance(rows: list[dict[str, Any]], opening_balance: float) -> list[dict[str, Any]]:
	running_balance = round(flt(opening_balance), 2)
	for index, row in enumerate(rows):
		if index == 0 and (
			row.get("event_sort_order") == EVENT_TYPE_ORDER[OPENING_BALANCE_EVENT_TYPE]
			or row.get("event_type") == OPENING_BALANCE_EVENT_TYPE
		):
			row["projected_balance"] = running_balance
			continue
		running_balance = round(
			running_balance + flt(row.get("inflow_amount")) - flt(row.get("outflow_amount")),
			2,
		)
		row["projected_balance"] = running_balance
	return rows


def translate_event_type(event_type: str | None) -> str:
	key = cstr(event_type).strip()
	if not key:
		return ""
	return _(key)


def translate_status(status: str | None) -> str:
	key = cstr(status).strip()
	if not key:
		return ""
	return _(key)
