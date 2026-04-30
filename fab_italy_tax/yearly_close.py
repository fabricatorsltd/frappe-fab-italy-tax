from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, flt, getdate

from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions

FULLY_DEDUCTIBLE = "Fully Deductible"
PARTIALLY_DEDUCTIBLE_PERCENTAGE = "Partially Deductible (%)"
PARTIALLY_DEDUCTIBLE_AMOUNT = "Partially Deductible (Amount)"
NON_DEDUCTIBLE = "Non Deductible"
DEDUCTIBILITY_OPTIONS = (
	FULLY_DEDUCTIBLE,
	PARTIALLY_DEDUCTIBLE_PERCENTAGE,
	PARTIALLY_DEDUCTIBLE_AMOUNT,
	NON_DEDUCTIBLE,
)
COMPETENCE_ENTRY_TOKEN = "ITX_COMPETENCE"


def validate_sales_invoice_yearly_close(document: Any, method: str | None = None) -> None:
	validate_invoice_competence_year(document)
	validate_competence_items(document)
	sync_forward_deferred_accounting(document)


def validate_purchase_invoice_yearly_close(document: Any, method: str | None = None) -> None:
	validate_invoice_competence_year(document)
	validate_competence_items(document)
	validate_purchase_deductibility(document)
	sync_forward_deferred_accounting(document)


def sync_invoice_competence_entries(document: Any, method: str | None = None) -> None:
	if cint(get_document_value(document, "docstatus")) != 1:
		return
	if is_prior_year_competence_selected(document):
		create_prior_year_competence_entries(get_document_doctype(document), get_document_name(document))
		return
	cancel_linked_competence_entries(document)


def cancel_linked_competence_entries(document: Any, method: str | None = None) -> None:
	if not get_document_name(document):
		return

	prefix = f"{COMPETENCE_ENTRY_TOKEN}|{get_document_doctype(document)}|{get_document_name(document)}|%"
	for entry_name in frappe.get_all(
		"Journal Entry",
		filters={"user_remark": ["like", prefix]},
		pluck="name",
	):
		entry = frappe.get_doc("Journal Entry", entry_name)
		if entry.docstatus == 1:
			entry.cancel()
		elif entry.docstatus == 0:
			entry.delete(ignore_permissions=True)


def validate_invoice_competence_year(document: Any) -> None:
	posting_date = get_document_posting_date(document)
	if not posting_date:
		return
	invoice_year = get_invoice_year(document)
	allowed_years = get_allowed_competence_years(document)
	selected_year = cstr(get_document_value(document, "fab_itx_competence_year")).strip()
	if not selected_year:
		setattr(document, "fab_itx_competence_year", str(invoice_year))
		return
	if selected_year not in allowed_years:
		frappe.throw(
			_("Competence Year must be either {0} or {1} for this invoice.").format(
				allowed_years[0],
				allowed_years[1],
			)
		)


def validate_competence_items(document: Any) -> None:
	for item in get_document_items(document):
		start_date = get_item_date(item, "fab_itx_competence_start_date")
		end_date = get_item_date(item, "fab_itx_competence_end_date")
		if bool(start_date) != bool(end_date):
			frappe.throw(
				_("Row #{0}: set both Competence Start Date and Competence End Date, or leave both empty.").format(
					get_item_idx(item)
				)
			)
		if start_date and end_date and start_date > end_date:
			frappe.throw(
				_("Row #{0}: Competence Start Date cannot be after Competence End Date.").format(
					get_item_idx(item)
				)
			)


def validate_purchase_deductibility(document: Any) -> None:
	override_mode = get_document_deductibility_override_mode(document)
	if override_mode:
		validate_deductibility_config(
			mode=override_mode,
			percentage=flt(get_document_value(document, "fab_itx_invoice_deductible_percentage")),
			deductible_amount=flt(get_document_value(document, "fab_itx_invoice_deductible_amount")),
			base_amount=get_document_base_amount(document),
			reference_label=_("Invoice deductibility override"),
		)
		normalize_deductibility_fields(
			target=document,
			mode_field="fab_itx_invoice_deductibility_mode",
			percentage_field="fab_itx_invoice_deductible_percentage",
			amount_field="fab_itx_invoice_deductible_amount",
		)
		return

	for item in get_document_items(document):
		mode = get_item_deductibility_mode(item)
		validate_deductibility_config(
			mode=mode,
			percentage=flt(get_item_value(item, "fab_itx_deductible_percentage")),
			deductible_amount=flt(get_item_value(item, "fab_itx_deductible_amount")),
			base_amount=get_item_base_amount(item),
			reference_label=_("Row #{0}").format(get_item_idx(item)),
		)
		normalize_deductibility_fields(
			target=item,
			mode_field="fab_itx_deductibility_mode",
			percentage_field="fab_itx_deductible_percentage",
			amount_field="fab_itx_deductible_amount",
		)


def sync_forward_deferred_accounting(document: Any) -> None:
	posting_date = get_document_posting_date(document)
	if not posting_date:
		return

	for item in get_document_items(document):
		start_date = get_item_date(item, "fab_itx_competence_start_date")
		end_date = get_item_date(item, "fab_itx_competence_end_date")
		if not start_date or not end_date:
			continue
		if start_date < posting_date or end_date <= posting_date:
			continue

		if get_document_doctype(document) == "Sales Invoice":
			setattr(item, "enable_deferred_revenue", 1)
		else:
			setattr(item, "enable_deferred_expense", 1)
		setattr(item, "service_start_date", start_date)
		setattr(item, "service_end_date", end_date)
		setattr(item, "service_stop_date", end_date)


@frappe.whitelist()
def create_prior_year_competence_entries(doctype: str, name: str, submit: int = 1) -> dict[str, Any]:
	if doctype not in {"Sales Invoice", "Purchase Invoice"}:
		frappe.throw(_("Competence entries are supported only for Sales Invoice and Purchase Invoice."))

	document = frappe.get_doc(doctype, name)
	if document.docstatus != 1:
		frappe.throw(_("Submit the document before creating competence entries."))

	validate_invoice_competence_year(document)
	validate_competence_items(document)
	adjustments = build_competence_adjustments(document)
	if not adjustments:
		return {"entries": [], "message": _("No prior-year competence adjustments are needed for this document.")}

	created_entries: list[str] = []
	reused_entries: list[str] = []
	for adjustment in adjustments:
		for kind in ("accrual", "reversal"):
			entry, was_created = ensure_competence_entry(
				document=document,
				adjustment=adjustment,
				entry_kind=kind,
				submit=bool(cint(submit)),
			)
			if was_created:
				created_entries.append(entry.name)
			else:
				reused_entries.append(entry.name)

	return {
		"entries": created_entries + reused_entries,
		"created_entries": created_entries,
		"reused_entries": reused_entries,
		"message": build_competence_result_message(created_entries=created_entries, reused_entries=reused_entries),
	}


def ensure_competence_entry(
	document,
	adjustment: dict[str, Any],
	entry_kind: str,
	submit: bool,
):
	existing_name = get_existing_competence_entry(
		reference_doctype=document.doctype,
		reference_name=document.name,
		fiscal_year=adjustment["fiscal_year"],
		entry_kind=entry_kind,
	)
	if existing_name:
		return frappe.get_doc("Journal Entry", existing_name), False

	entry = frappe.get_doc(build_competence_journal_entry_payload(document=document, adjustment=adjustment, entry_kind=entry_kind))
	entry.insert(ignore_permissions=True)
	if submit and entry.docstatus == 0:
		entry.submit()
	return entry, True


def build_competence_result_message(created_entries: list[str], reused_entries: list[str]) -> str:
	if created_entries and reused_entries:
		return _("Created {0} competence journal entries and reused {1} existing ones.").format(
			len(created_entries),
			len(reused_entries),
		)
	if created_entries:
		return _("Created {0} competence journal entries.").format(len(created_entries))
	if reused_entries:
		return _("Competence journal entries already existed; reused {0} entries.").format(len(reused_entries))
	return _("No competence journal entries were generated.")


def build_competence_journal_entry_payload(document, adjustment: dict[str, Any], entry_kind: str) -> dict[str, Any]:
	posting_date = adjustment["fiscal_year_end"] if entry_kind == "accrual" else get_document_posting_date(document)
	accounts = []
	for row in adjustment["rows"]:
		accounts.extend(
			build_competence_accounts(
				document_type=document.doctype,
				amount=row["amount"],
				profit_account=row["profit_account"],
				balance_account=adjustment["balance_account"],
				entry_kind=entry_kind,
				dimensions=row["dimensions"],
			)
		)

	return {
		"doctype": "Journal Entry",
		"voucher_type": "Journal Entry",
		"company": document.company,
		"posting_date": posting_date,
		"title": build_competence_entry_title(document=document, fiscal_year=adjustment["fiscal_year"], entry_kind=entry_kind),
		"custom_remark": 1,
		"user_remark": build_competence_entry_token(
			reference_doctype=document.doctype,
			reference_name=document.name,
			fiscal_year=adjustment["fiscal_year"],
			entry_kind=entry_kind,
		),
		"remark": build_competence_entry_remark(document=document, fiscal_year=adjustment["fiscal_year"], entry_kind=entry_kind),
		"accounts": accounts,
	}


def build_competence_accounts(
	document_type: str,
	amount: float,
	profit_account: str,
	balance_account: str,
	entry_kind: str,
	dimensions: dict[str, Any],
) -> list[dict[str, Any]]:
	amount = round(flt(amount), 2)
	if amount <= 0:
		return []

	is_sales = document_type == "Sales Invoice"
	first_line: dict[str, Any] = {**dimensions}
	second_line: dict[str, Any] = {**dimensions}

	if is_sales and entry_kind == "accrual":
		first_line.update({"account": balance_account, "debit_in_account_currency": amount})
		second_line.update({"account": profit_account, "credit_in_account_currency": amount})
	elif is_sales:
		first_line.update({"account": profit_account, "debit_in_account_currency": amount})
		second_line.update({"account": balance_account, "credit_in_account_currency": amount})
	elif entry_kind == "accrual":
		first_line.update({"account": profit_account, "debit_in_account_currency": amount})
		second_line.update({"account": balance_account, "credit_in_account_currency": amount})
	else:
		first_line.update({"account": balance_account, "debit_in_account_currency": amount})
		second_line.update({"account": profit_account, "credit_in_account_currency": amount})

	return [first_line, second_line]


def build_competence_adjustments(document) -> list[dict[str, Any]]:
	header_adjustments = build_header_competence_adjustments(document)
	if header_adjustments:
		return header_adjustments
	return build_prior_year_competence_adjustments_from_items(document)


def build_header_competence_adjustments(document) -> list[dict[str, Any]]:
	if not is_prior_year_competence_selected(document):
		return []

	posting_date = get_document_posting_date(document)
	if not posting_date:
		return []

	selected_year = get_selected_competence_year(document)
	target_fiscal_year = get_fiscal_year_for_date(date(selected_year, 12, 31))
	target_fiscal_year_end = getdate(target_fiscal_year["year_end_date"])
	company = frappe.get_doc("Company", document.company)
	balance_account = get_competence_balance_account(document=document, company=company)
	rows = []
	for item in get_document_items(document):
		item_amount = get_item_base_amount(item)
		if item_amount <= 0:
			continue
		rows.append(
			{
				"item_reference": cstr(get_item_value(item, "name")),
				"amount": item_amount,
				"profit_account": get_profit_account(document, item),
				"dimensions": get_item_dimensions(item),
			}
		)
	if not rows:
		return []
	return [
		{
			"fiscal_year": target_fiscal_year["name"],
			"fiscal_year_end": target_fiscal_year_end,
			"balance_account": balance_account,
			"rows": rows,
		}
	]


def build_prior_year_competence_adjustments_from_items(document) -> list[dict[str, Any]]:
	posting_date = get_document_posting_date(document)
	if not posting_date:
		return []

	company = frappe.get_doc("Company", document.company)
	balance_account = get_competence_balance_account(document=document, company=company)
	start_dates = [
		get_item_date(item, "fab_itx_competence_start_date")
		for item in get_document_items(document)
		if get_item_date(item, "fab_itx_competence_start_date")
	]
	if not start_dates:
		return []
	fiscal_years = get_fiscal_years_overlapping(date_filter_end=add_days(posting_date, -1), date_filter_start=min(start_dates))
	grouped: dict[str, dict[str, Any]] = {}

	for item in get_document_items(document):
		start_date = get_item_date(item, "fab_itx_competence_start_date")
		end_date = get_item_date(item, "fab_itx_competence_end_date")
		if not start_date or not end_date or start_date >= posting_date:
			continue

		item_amount = get_item_base_amount(item)
		if item_amount <= 0:
			continue

		for fiscal_year in fiscal_years:
			fiscal_year_start = getdate(fiscal_year["year_start_date"])
			fiscal_year_end = getdate(fiscal_year["year_end_date"])
			if fiscal_year_end >= posting_date:
				continue
			recognized_amount = allocate_amount_to_period(
				amount=item_amount,
				start_date=start_date,
				end_date=end_date,
				period_start=fiscal_year_start,
				period_end=fiscal_year_end,
			)
			if recognized_amount <= 0:
				continue

			adjustment = grouped.setdefault(
				fiscal_year["name"],
				{
					"fiscal_year": fiscal_year["name"],
					"fiscal_year_end": fiscal_year_end,
					"balance_account": balance_account,
					"rows": [],
				},
			)
			adjustment["rows"].append(
				{
					"item_reference": cstr(get_item_value(item, "name")),
					"amount": recognized_amount,
					"profit_account": get_profit_account(document, item),
					"dimensions": get_item_dimensions(item),
				}
			)

	return list(grouped.values())


def get_profit_account(document, item: Any) -> str:
	fieldname = "income_account" if get_document_doctype(document) == "Sales Invoice" else "expense_account"
	account = cstr(get_item_value(item, fieldname)).strip()
	if not account:
		frappe.throw(
			_("Row #{0}: set {1} before creating competence entries.").format(
				get_item_idx(item),
				fieldname.replace("_", " "),
			)
		)
	return account


def get_competence_balance_account(document, company) -> str:
	fieldname = "fab_itx_accrued_revenue_account" if get_document_doctype(document) == "Sales Invoice" else "fab_itx_accrued_expense_account"
	account = cstr(getattr(company, fieldname, "")).strip()
	if not account:
		frappe.throw(
			_("Set {0} on Company {1} before creating competence entries.").format(
				fieldname.replace("_", " "),
				company.name,
			)
		)
	return account


def get_yearly_balance(company: str, fiscal_year: str) -> dict[str, Any]:
	fiscal_year_bounds = get_fiscal_year_bounds(fiscal_year)
	fiscal_year_start = getdate(fiscal_year_bounds["year_start_date"])
	fiscal_year_end = getdate(fiscal_year_bounds["year_end_date"])
	company_doc = frappe.get_doc("Company", company)

	statutory_result = get_statutory_profit_or_loss(company=company, from_date=fiscal_year_start, to_date=fiscal_year_end)
	competence_rows = get_prior_year_competence_rows(company=company, fiscal_year=fiscal_year, fiscal_year_start=fiscal_year_start, fiscal_year_end=fiscal_year_end)
	deductibility_rows = get_purchase_deductibility_rows(company=company, fiscal_year_start=fiscal_year_start, fiscal_year_end=fiscal_year_end)
	closing_stock_value = get_closing_stock_value(company=company, to_date=fiscal_year_end)
	rows = sorted(competence_rows + deductibility_rows + [build_stock_info_row(company_doc, fiscal_year_end, closing_stock_value)], key=row_sort_key)

	pending_competence = sum(flt(row.get("profit_adjustment_amount")) for row in competence_rows if row.get("status") == "Pending")
	non_deductible_addback = sum(flt(row.get("non_deductible_addback")) for row in deductibility_rows)
	fiscal_result = statutory_result + pending_competence + non_deductible_addback
	return {
		"columns": get_yearly_balance_columns(),
		"data": rows,
		"summary": build_yearly_balance_summary(
			company=company_doc,
			statutory_result=statutory_result,
			pending_competence=pending_competence,
			non_deductible_addback=non_deductible_addback,
			fiscal_result=fiscal_result,
			closing_stock_value=closing_stock_value,
		),
	}


def get_yearly_balance_columns() -> list[dict[str, Any]]:
	return [
		{"fieldname": "section", "label": _("Section"), "fieldtype": "Data", "width": 120},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "reference_doctype", "label": _("Reference DocType"), "fieldtype": "Data", "width": 120},
		{"fieldname": "reference_name", "label": _("Reference Name"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 160},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "party", "label": _("Party"), "fieldtype": "Data", "width": 180},
		{"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "competence_year", "label": _("Competence Year"), "fieldtype": "Data", "width": 110},
		{"fieldname": "competence_start_date", "label": _("Competence Start"), "fieldtype": "Date", "width": 120},
		{"fieldname": "competence_end_date", "label": _("Competence End"), "fieldtype": "Date", "width": 120},
		{"fieldname": "base_amount", "label": _("Document Amount"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "recognized_amount", "label": _("Year Amount"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "profit_adjustment_amount", "label": _("Profit Adjustment"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "deductible_amount", "label": _("Deductible Amount"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "non_deductible_addback", "label": _("Non-deductible Add-back"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "stock_value", "label": _("Stock Value"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "note", "label": _("Note"), "fieldtype": "Data", "width": 260},
	]


def build_yearly_balance_summary(
	company,
	statutory_result: float,
	pending_competence: float,
	non_deductible_addback: float,
	fiscal_result: float,
	closing_stock_value: float,
) -> list[dict[str, Any]]:
	stock_label = _("Closing Stock Value (already in GL)") if cint(company.enable_perpetual_inventory) else _("Closing Stock Value")
	return [
		{
			"label": _("Statutory Profit / Loss"),
			"value": statutory_result,
			"datatype": "Currency",
			"currency": company.default_currency,
			"indicator": "Green" if statutory_result >= 0 else "Red",
		},
		{
			"label": _("Pending Competence Adjustment"),
			"value": pending_competence,
			"datatype": "Currency",
			"currency": company.default_currency,
			"indicator": "Orange" if pending_competence else "Green",
		},
		{
			"label": _("Non-deductible Add-back"),
			"value": non_deductible_addback,
			"datatype": "Currency",
			"currency": company.default_currency,
			"indicator": "Orange" if non_deductible_addback else "Blue",
		},
		{
			"label": _("Fiscal Result After Adjustments"),
			"value": fiscal_result,
			"datatype": "Currency",
			"currency": company.default_currency,
			"indicator": "Green" if fiscal_result >= 0 else "Red",
		},
		{
			"label": stock_label,
			"value": closing_stock_value,
			"datatype": "Currency",
			"currency": company.default_currency,
			"indicator": "Blue",
		},
	]


def get_prior_year_competence_rows(
	company: str,
	fiscal_year: str,
	fiscal_year_start: date,
	fiscal_year_end: date,
) -> list[dict[str, Any]]:
	rows = get_header_competence_rows(
		company=company,
		fiscal_year=fiscal_year,
		fiscal_year_end=fiscal_year_end,
	)
	rows.extend(
		get_item_level_competence_rows(
			company=company,
			fiscal_year=fiscal_year,
			fiscal_year_start=fiscal_year_start,
			fiscal_year_end=fiscal_year_end,
		)
	)
	return rows


def get_header_competence_rows(
	company: str,
	fiscal_year: str,
	fiscal_year_end: date,
) -> list[dict[str, Any]]:
	rows: list[dict[str, Any]] = []
	target_year = str(fiscal_year_end.year)
	for doctype, child_table, party_field, profit_sign in (
		("Sales Invoice", "Sales Invoice Item", "customer", 1),
		("Purchase Invoice", "Purchase Invoice Item", "supplier", -1),
	):
		query = f"""
			select
				parent_doc.name as reference_name,
				parent_doc.posting_date,
				parent_doc.{party_field} as party,
				parent_doc.fab_itx_competence_year,
				child_doc.item_code,
				child_doc.base_net_amount,
				child_doc.net_amount,
				child_doc.amount
			from `tab{child_table}` child_doc
			inner join `tab{doctype}` parent_doc on parent_doc.name = child_doc.parent
			where parent_doc.docstatus = 1
				and parent_doc.company = %(company)s
				and parent_doc.posting_date > %(fiscal_year_end)s
				and parent_doc.fab_itx_competence_year = %(target_year)s
			order by parent_doc.posting_date, parent_doc.name, child_doc.idx
		"""
		for result in frappe.db.sql(
			query,
			{"company": company, "fiscal_year_end": fiscal_year_end, "target_year": target_year},
			as_dict=True,
		):
			entry_exists = bool(
				get_existing_competence_entry(
					reference_doctype=doctype,
					reference_name=result.reference_name,
					fiscal_year=fiscal_year,
					entry_kind="accrual",
				)
			)
			amount = get_result_line_amount(result)
			rows.append(
				{
					"section": "Competence",
					"status": "Posted" if entry_exists else "Pending",
					"reference_doctype": doctype,
					"reference_name": result.reference_name,
					"item_code": result.item_code,
					"party": result.party,
					"posting_date": result.posting_date,
					"competence_year": target_year,
					"competence_start_date": None,
					"competence_end_date": None,
					"base_amount": amount,
					"recognized_amount": amount,
					"profit_adjustment_amount": round(profit_sign * amount, 2),
					"deductible_amount": 0.0,
					"non_deductible_addback": 0.0,
					"stock_value": 0.0,
					"note": _("Prior-year competence from the invoice-level Competence Year field."),
				}
			)
	return rows


def get_item_level_competence_rows(
	company: str,
	fiscal_year: str,
	fiscal_year_start: date,
	fiscal_year_end: date,
) -> list[dict[str, Any]]:
	rows: list[dict[str, Any]] = []
	for doctype, child_table, account_field, party_field, profit_sign in (
		("Sales Invoice", "Sales Invoice Item", "income_account", "customer", 1),
		("Purchase Invoice", "Purchase Invoice Item", "expense_account", "supplier", -1),
	):
		query = f"""
			select
				parent_doc.name as reference_name,
				parent_doc.posting_date,
				parent_doc.{party_field} as party,
				parent_doc.fab_itx_competence_year,
				child_doc.name as item_row_name,
				child_doc.item_code,
				child_doc.{account_field} as profit_account,
				child_doc.base_net_amount,
				child_doc.net_amount,
				child_doc.amount,
				child_doc.fab_itx_competence_start_date,
				child_doc.fab_itx_competence_end_date
			from `tab{child_table}` child_doc
			inner join `tab{doctype}` parent_doc on parent_doc.name = child_doc.parent
			where parent_doc.docstatus = 1
				and parent_doc.company = %(company)s
				and parent_doc.posting_date > %(fiscal_year_end)s
				and child_doc.fab_itx_competence_start_date is not null
				and child_doc.fab_itx_competence_end_date is not null
				and child_doc.fab_itx_competence_start_date <= %(fiscal_year_end)s
				and child_doc.fab_itx_competence_end_date >= %(fiscal_year_start)s
			order by parent_doc.posting_date, parent_doc.name, child_doc.idx
		"""
		for result in frappe.db.sql(
			query,
			{"company": company, "fiscal_year_start": fiscal_year_start, "fiscal_year_end": fiscal_year_end},
			as_dict=True,
		):
			posting_year = getdate(result.posting_date).year
			selected_year = cstr(result.fab_itx_competence_year).strip()
			if selected_year and selected_year != str(posting_year):
				continue
			recognized_amount = allocate_amount_to_period(
				amount=get_result_line_amount(result),
				start_date=getdate(result.fab_itx_competence_start_date),
				end_date=getdate(result.fab_itx_competence_end_date),
				period_start=fiscal_year_start,
				period_end=fiscal_year_end,
			)
			if recognized_amount <= 0:
				continue
			entry_exists = bool(
				get_existing_competence_entry(
					reference_doctype=doctype,
					reference_name=result.reference_name,
					fiscal_year=fiscal_year,
					entry_kind="accrual",
				)
			)
			rows.append(
				{
					"section": "Competence",
					"status": "Posted" if entry_exists else "Pending",
					"reference_doctype": doctype,
					"reference_name": result.reference_name,
					"item_code": result.item_code,
					"party": result.party,
					"posting_date": result.posting_date,
					"competence_year": selected_year or str(posting_year),
					"competence_start_date": result.fab_itx_competence_start_date,
					"competence_end_date": result.fab_itx_competence_end_date,
					"base_amount": get_result_line_amount(result),
					"recognized_amount": recognized_amount,
					"profit_adjustment_amount": round(profit_sign * recognized_amount, 2),
					"deductible_amount": 0.0,
					"non_deductible_addback": 0.0,
					"stock_value": 0.0,
					"note": _("Prior-year competence from a document posted after the fiscal year close."),
				}
			)
	return rows


def get_purchase_deductibility_rows(company: str, fiscal_year_start: date, fiscal_year_end: date) -> list[dict[str, Any]]:
	query = """
		select
			parent_doc.name as reference_name,
			parent_doc.posting_date,
			parent_doc.supplier as party,
			parent_doc.fab_itx_competence_year,
			child_doc.item_code,
			child_doc.base_net_amount,
			child_doc.net_amount,
			child_doc.amount,
			child_doc.fab_itx_competence_start_date,
			child_doc.fab_itx_competence_end_date,
			parent_doc.fab_itx_invoice_deductibility_mode,
			parent_doc.fab_itx_invoice_deductible_percentage,
			parent_doc.fab_itx_invoice_deductible_amount,
			child_doc.fab_itx_deductibility_mode,
			child_doc.fab_itx_deductible_percentage,
			child_doc.fab_itx_deductible_amount
		from `tabPurchase Invoice Item` child_doc
		inner join `tabPurchase Invoice` parent_doc on parent_doc.name = child_doc.parent
		where parent_doc.docstatus = 1
			and parent_doc.company = %(company)s
			and (
				parent_doc.posting_date between %(fiscal_year_start)s and %(fiscal_year_end)s
				or parent_doc.fab_itx_competence_year = %(target_year)s
				or (
					child_doc.fab_itx_competence_start_date is not null
					and child_doc.fab_itx_competence_end_date is not null
					and child_doc.fab_itx_competence_start_date <= %(fiscal_year_end)s
					and child_doc.fab_itx_competence_end_date >= %(fiscal_year_start)s
				)
			)
		order by parent_doc.posting_date, parent_doc.name, child_doc.idx
	"""
	rows: list[dict[str, Any]] = []
	results = frappe.db.sql(
		query,
		{
			"company": company,
			"fiscal_year_start": fiscal_year_start,
			"fiscal_year_end": fiscal_year_end,
			"target_year": str(fiscal_year_end.year),
		},
		as_dict=True,
	)
	invoice_totals: dict[str, float] = defaultdict(float)
	for result in results:
		invoice_totals[result.reference_name] += get_result_line_amount(result)
	for result in results:
		recognized_amount = get_result_line_amount(result)
		posting_year = getdate(result.posting_date).year
		selected_year = cstr(result.fab_itx_competence_year).strip()
		if selected_year and selected_year == str(fiscal_year_end.year) and selected_year != str(posting_year):
			recognized_amount = get_result_line_amount(result)
		elif result.fab_itx_competence_start_date and result.fab_itx_competence_end_date:
			recognized_amount = allocate_amount_to_period(
				amount=recognized_amount,
				start_date=getdate(result.fab_itx_competence_start_date),
				end_date=getdate(result.fab_itx_competence_end_date),
				period_start=fiscal_year_start,
				period_end=fiscal_year_end,
			)
		elif not (fiscal_year_start <= getdate(result.posting_date) <= fiscal_year_end):
			recognized_amount = 0.0
		if recognized_amount <= 0:
			continue

		deductibility_ratio = get_result_deductibility_ratio(
			result,
			invoice_total_amount=invoice_totals.get(result.reference_name, 0.0),
		)
		deductible_amount = round(recognized_amount * deductibility_ratio, 2)
		non_deductible_addback = round(recognized_amount - deductible_amount, 2)
		if non_deductible_addback <= 0:
			continue
		rows.append(
			{
				"section": "Deductibility",
				"status": "Fiscal",
				"reference_doctype": "Purchase Invoice",
				"reference_name": result.reference_name,
				"item_code": result.item_code,
				"party": result.party,
				"posting_date": result.posting_date,
				"competence_year": selected_year or str(posting_year),
				"competence_start_date": result.fab_itx_competence_start_date,
				"competence_end_date": result.fab_itx_competence_end_date,
				"base_amount": get_result_line_amount(result),
				"recognized_amount": recognized_amount,
				"profit_adjustment_amount": 0.0,
				"deductible_amount": deductible_amount,
				"non_deductible_addback": non_deductible_addback,
				"stock_value": 0.0,
				"note": _(
					"Deductibility reclassification for the fiscal result."
				)
				if not cstr(result.fab_itx_invoice_deductibility_mode).strip()
				else _("Deductibility reclassification using the invoice-level override."),
			}
		)
	return rows


def build_stock_info_row(company_doc, fiscal_year_end: date, stock_value: float) -> dict[str, Any]:
	perpetual_note = _("Perpetual inventory is enabled, so warehouse value is already reflected in the statutory GL.")
	if not cint(company_doc.enable_perpetual_inventory):
		perpetual_note = _("Perpetual inventory is disabled, so warehouse value should be reviewed before closing.")
	return {
		"section": "Stock",
		"status": "Info",
		"reference_doctype": "Company",
		"reference_name": company_doc.name,
		"item_code": "",
		"party": "",
		"posting_date": fiscal_year_end,
		"competence_year": "",
		"competence_start_date": None,
		"competence_end_date": None,
		"base_amount": 0.0,
		"recognized_amount": 0.0,
		"profit_adjustment_amount": 0.0,
		"deductible_amount": 0.0,
		"non_deductible_addback": 0.0,
		"stock_value": stock_value,
		"note": _("{0} Valuation method: {1}.").format(perpetual_note, company_doc.valuation_method or _("not set")),
	}


def row_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
	return (
		0 if row.get("section") == "Competence" else 1 if row.get("section") == "Deductibility" else 2,
		cstr(row.get("posting_date")),
		cstr(row.get("reference_name")),
		cstr(row.get("item_code")),
	)


def get_statutory_profit_or_loss(company: str, from_date: date, to_date: date) -> float:
	rows = frappe.db.sql(
		"""
		select account.root_type, sum(gl.debit) as debit, sum(gl.credit) as credit
		from `tabGL Entry` gl
		inner join `tabAccount` account on account.name = gl.account
		where gl.company = %s
			and gl.is_cancelled = 0
			and gl.posting_date between %s and %s
			and account.report_type = 'Profit and Loss'
		group by account.root_type
		""",
		(company, from_date, to_date),
		as_dict=True,
	)
	income_total = sum(flt(row.credit) - flt(row.debit) for row in rows if row.root_type == "Income")
	expense_total = sum(flt(row.debit) - flt(row.credit) for row in rows if row.root_type == "Expense")
	return round(income_total - expense_total, 2)


def get_closing_stock_value(company: str, to_date: date) -> float:
	rows = frappe.db.sql(
		"""
		select item_code, warehouse, stock_value
		from `tabStock Ledger Entry`
		where company = %s
			and is_cancelled = 0
			and posting_date <= %s
		order by item_code, warehouse, posting_date desc, posting_time desc, creation desc
		""",
		(company, to_date),
		as_dict=True,
	)
	seen: set[tuple[str, str]] = set()
	total = 0.0
	for row in rows:
		key = (cstr(row.item_code), cstr(row.warehouse))
		if key in seen:
			continue
		seen.add(key)
		total += flt(row.stock_value)
	return round(total, 2)


def get_invoice_year(document: Any) -> int:
	posting_date = get_document_posting_date(document)
	if not posting_date:
		return 0
	return posting_date.year


def get_allowed_competence_years(document: Any) -> list[str]:
	invoice_year = get_invoice_year(document)
	return [str(invoice_year), str(invoice_year - 1)]


def get_selected_competence_year(document: Any) -> int:
	selected_year = cstr(get_document_value(document, "fab_itx_competence_year")).strip()
	if selected_year:
		return cint(selected_year)
	return get_invoice_year(document)


def is_prior_year_competence_selected(document: Any) -> bool:
	invoice_year = get_invoice_year(document)
	selected_year = get_selected_competence_year(document)
	return bool(invoice_year and selected_year == invoice_year - 1)


def backfill_invoice_competence_years() -> None:
	for doctype in ("Sales Invoice", "Purchase Invoice"):
		for row in frappe.db.sql(
			f"""
			select name, posting_date
			from `tab{doctype}`
			where posting_date is not null
				and ifnull(fab_itx_competence_year, '') = ''
			""",
			as_dict=True,
		):
			frappe.db.set_value(
				doctype,
				row.name,
				"fab_itx_competence_year",
				str(getdate(row.posting_date).year),
				update_modified=False,
			)


def get_fiscal_year_bounds(fiscal_year: str) -> dict[str, Any]:
	row = frappe.db.get_value(
		"Fiscal Year",
		fiscal_year,
		["name", "year_start_date", "year_end_date"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Fiscal Year {0} was not found.").format(fiscal_year))
	return row


def get_fiscal_year_for_date(value: date) -> dict[str, Any]:
	rows = frappe.db.sql(
		"""
		select name, year_start_date, year_end_date
		from `tabFiscal Year`
		where year_start_date <= %s and year_end_date >= %s
		order by year_start_date desc
		limit 1
		""",
		(value, value),
		as_dict=True,
	)
	if not rows:
		frappe.throw(_("No Fiscal Year covers {0}.").format(value))
	return rows[0]


def get_fiscal_years_overlapping(date_filter_start: date, date_filter_end: date) -> list[dict[str, Any]]:
	return frappe.db.sql(
		"""
		select name, year_start_date, year_end_date
		from `tabFiscal Year`
		where year_start_date <= %s and year_end_date >= %s
		order by year_start_date asc
		""",
		(date_filter_end, date_filter_start),
		as_dict=True,
	)


def get_existing_competence_entry(
	reference_doctype: str,
	reference_name: str,
	fiscal_year: str,
	entry_kind: str,
) -> str | None:
	return frappe.db.get_value(
		"Journal Entry",
		{
			"user_remark": build_competence_entry_token(
				reference_doctype=reference_doctype,
				reference_name=reference_name,
				fiscal_year=fiscal_year,
				entry_kind=entry_kind,
			),
			"docstatus": ["<", 2],
		},
		"name",
	)


def build_competence_entry_token(
	reference_doctype: str,
	reference_name: str,
	fiscal_year: str,
	entry_kind: str,
) -> str:
	return f"{COMPETENCE_ENTRY_TOKEN}|{reference_doctype}|{reference_name}|{fiscal_year}|{entry_kind}"


def build_competence_entry_title(document, fiscal_year: str, entry_kind: str) -> str:
	action = _("Accrual") if entry_kind == "accrual" else _("Reversal")
	return _("Italian Competence {0} {1} {2}").format(action, fiscal_year, document.name)


def build_competence_entry_remark(document, fiscal_year: str, entry_kind: str) -> str:
	action = _("accrual") if entry_kind == "accrual" else _("reversal")
	return _("Italian competence {0} for {1} {2} in fiscal year {3}.").format(
		action,
		document.doctype,
		document.name,
		fiscal_year,
	)


def get_item_dimensions(item: Any) -> dict[str, Any]:
	dimensions = {}
	for fieldname in ("cost_center", "project", *get_accounting_dimensions()):
		value = get_item_value(item, fieldname)
		if value:
			dimensions[fieldname] = value
	return dimensions


def get_deductibility_ratio(item: Any) -> float:
	return get_deductibility_ratio_from_values(
		mode=get_item_deductibility_mode(item),
		percentage=flt(get_item_value(item, "fab_itx_deductible_percentage")),
		deductible_amount=flt(get_item_value(item, "fab_itx_deductible_amount")),
		base_amount=get_item_base_amount(item),
	)


def get_deductibility_ratio_from_values(
	mode: str,
	percentage: float,
	deductible_amount: float,
	base_amount: float,
) -> float:
	mode = cstr(mode).strip() or FULLY_DEDUCTIBLE
	if mode == NON_DEDUCTIBLE:
		return 0.0
	if mode == PARTIALLY_DEDUCTIBLE_PERCENTAGE:
		return min(max(flt(percentage) / 100.0, 0.0), 1.0)
	if mode == PARTIALLY_DEDUCTIBLE_AMOUNT:
		if not base_amount:
			return 0.0
		return min(max(flt(deductible_amount) / base_amount, 0.0), 1.0)
	return 1.0


def get_result_deductibility_ratio(result: Any, invoice_total_amount: float = 0.0) -> float:
	override_mode = cstr(getattr(result, "fab_itx_invoice_deductibility_mode", "")).strip()
	if override_mode:
		return get_deductibility_ratio_from_values(
			mode=override_mode,
			percentage=flt(getattr(result, "fab_itx_invoice_deductible_percentage", 0.0)),
			deductible_amount=flt(getattr(result, "fab_itx_invoice_deductible_amount", 0.0)),
			base_amount=invoice_total_amount,
		)
	return get_deductibility_ratio_from_values(
		mode=cstr(result.fab_itx_deductibility_mode).strip() or FULLY_DEDUCTIBLE,
		percentage=flt(result.fab_itx_deductible_percentage),
		deductible_amount=flt(result.fab_itx_deductible_amount),
		base_amount=get_result_line_amount(result),
	)


def get_item_deductibility_mode(item: Any) -> str:
	return cstr(get_item_value(item, "fab_itx_deductibility_mode")).strip() or FULLY_DEDUCTIBLE


def get_document_deductibility_override_mode(document: Any) -> str:
	return cstr(get_document_value(document, "fab_itx_invoice_deductibility_mode")).strip()


def get_document_base_amount(document: Any) -> float:
	return round(sum(get_item_base_amount(item) for item in get_document_items(document)), 2)


def validate_deductibility_config(
	mode: str,
	percentage: float,
	deductible_amount: float,
	base_amount: float,
	reference_label: str,
) -> None:
	if mode not in DEDUCTIBILITY_OPTIONS:
		frappe.throw(_("{0}: Deductibility Mode is not valid.").format(reference_label))
	if mode == PARTIALLY_DEDUCTIBLE_PERCENTAGE and (percentage <= 0 or percentage > 100):
		frappe.throw(_("{0}: Deductible Percentage must be between 0 and 100.").format(reference_label))
	if mode == PARTIALLY_DEDUCTIBLE_AMOUNT:
		if deductible_amount <= 0:
			frappe.throw(_("{0}: Deductible Amount must be greater than zero.").format(reference_label))
		if base_amount and deductible_amount - base_amount > 0.02:
			frappe.throw(_("{0}: Deductible Amount cannot exceed the amount in scope.").format(reference_label))


def normalize_deductibility_fields(
	target: Any,
	mode_field: str,
	percentage_field: str,
	amount_field: str,
) -> None:
	mode = cstr(getattr(target, mode_field, "")).strip()
	if mode == PARTIALLY_DEDUCTIBLE_PERCENTAGE:
		setattr(target, amount_field, 0)
	elif mode == PARTIALLY_DEDUCTIBLE_AMOUNT:
		setattr(target, percentage_field, 0)
	elif mode in {FULLY_DEDUCTIBLE, NON_DEDUCTIBLE}:
		setattr(target, percentage_field, 0)
		setattr(target, amount_field, 0)


def get_item_base_amount(item: Any) -> float:
	for fieldname in ("base_net_amount", "net_amount", "base_amount", "amount"):
		value = abs(flt(get_item_value(item, fieldname)))
		if value:
			return round(value, 2)
	return round(abs(flt(get_item_value(item, "qty")) * flt(get_item_value(item, "rate"))), 2)


def get_result_line_amount(result: Any) -> float:
	for fieldname in ("base_net_amount", "net_amount", "amount"):
		value = abs(flt(getattr(result, fieldname, 0)))
		if value:
			return round(value, 2)
	return 0.0


def allocate_amount_to_period(
	amount: float,
	start_date: date,
	end_date: date,
	period_start: date,
	period_end: date,
) -> float:
	start_date = getdate(start_date)
	end_date = getdate(end_date)
	period_start = getdate(period_start)
	period_end = getdate(period_end)
	if start_date > end_date or period_start > period_end:
		return 0.0
	overlap_start = max(start_date, period_start)
	overlap_end = min(end_date, period_end)
	if overlap_start > overlap_end:
		return 0.0
	total_days = (end_date - start_date).days + 1
	overlap_days = (overlap_end - overlap_start).days + 1
	return round(flt(amount) * overlap_days / total_days, 2)


def get_document_items(document: Any) -> list[Any]:
	items = get_document_value(document, "items")
	return list(items or [])


def get_document_posting_date(document: Any) -> date | None:
	value = get_document_value(document, "posting_date")
	return getdate(value) if value else None


def get_document_name(document: Any) -> str:
	return cstr(get_document_value(document, "name")).strip()


def get_document_doctype(document: Any) -> str:
	return cstr(get_document_value(document, "doctype")).strip()


def get_document_value(document: Any, fieldname: str) -> Any:
	getter = getattr(document, "get", None)
	if callable(getter):
		return getter(fieldname)
	return getattr(document, fieldname, None)


def get_item_value(item: Any, fieldname: str) -> Any:
	getter = getattr(item, "get", None)
	if callable(getter):
		return getter(fieldname)
	return getattr(item, fieldname, None)


def get_item_date(item: Any, fieldname: str) -> date | None:
	value = get_item_value(item, fieldname)
	return getdate(value) if value else None


def get_item_idx(item: Any) -> int:
	return cint(get_item_value(item, "idx")) or 0
