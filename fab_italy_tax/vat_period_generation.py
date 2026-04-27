from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.utils import cint, cstr, flt, getdate, nowdate

from fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration import (
	VAT_LIQUIDATION_CADENCES,
	get_document_value,
)

LOCKED_VAT_PERIOD_STATUSES = {"Posted", "Closed", "Cancelled"}


def sync_enabled_tax_configuration_vat_periods() -> None:
	for tax_configuration in frappe.get_all(
		"Italy Tax Configuration", filters={"enabled": 1}, pluck="name"
	):
		generate_missing_vat_periods_for_configuration(tax_configuration)


@frappe.whitelist()
def generate_missing_vat_periods(
	tax_configuration: str, through_date: str | None = None
) -> dict[str, Any]:
	result = generate_missing_vat_periods_for_configuration(tax_configuration, through_date=through_date)
	result["message"] = build_generation_message(
		result["created_periods"], result["existing_periods"], result["target_period_end"]
	)
	return result


@frappe.whitelist()
def generate_next_vat_period(vat_period: str) -> dict[str, Any]:
	document = resolve_vat_period(vat_period)
	period_start_date = getdate(get_document_value(document, "period_start_date"))
	period_end_date = getdate(get_document_value(document, "period_end_date"))
	cadence = cstr(get_document_value(document, "vat_liquidation_cadence")).strip()
	tax_configuration = cstr(get_document_value(document, "tax_configuration")).strip()
	company = cstr(get_document_value(document, "company")).strip()

	if cadence not in VAT_LIQUIDATION_CADENCES:
		frappe.throw(_("VAT Liquidation Cadence must be Monthly or Quarterly."))
	if not tax_configuration:
		frappe.throw(_("Set Tax Configuration before generating the next VAT Period."))

	next_start_date, next_end_date = get_next_period_bounds(period_start_date, period_end_date, cadence)
	existing_name = get_existing_vat_period_name(company, tax_configuration, cadence, next_start_date, next_end_date)
	if existing_name:
		return {
			"period_name": existing_name,
			"created": False,
			"message": _("VAT Period {0} already exists.").format(existing_name),
		}

	created_name = create_vat_period(
		get_tax_configuration(tax_configuration), next_start_date, next_end_date
	)
	return {
		"period_name": created_name,
		"created": True,
		"message": _("Created VAT Period {0}.").format(created_name),
	}


def generate_missing_vat_periods_for_configuration(
	tax_configuration: str | Any, through_date: str | date | None = None
) -> dict[str, Any]:
	configuration = get_tax_configuration(tax_configuration)
	company = cstr(get_document_value(configuration, "company")).strip()
	cadence = cstr(get_document_value(configuration, "vat_liquidation_cadence")).strip()
	first_managed_period_start_raw = get_document_value(configuration, "first_managed_period_start_date")
	enabled = cint(get_document_value(configuration, "enabled"))

	if not enabled:
		frappe.throw(_("Enable the tax configuration before generating VAT periods."))
	if cadence not in VAT_LIQUIDATION_CADENCES:
		frappe.throw(_("VAT Liquidation Cadence must be Monthly or Quarterly."))
	if not company:
		frappe.throw(_("Set Company before generating VAT periods."))
	if not first_managed_period_start_raw:
		frappe.throw(_("Set First Managed Period Start Date before generating VAT periods."))

	first_managed_period_start_date = getdate(first_managed_period_start_raw)
	validate_managed_start_date(first_managed_period_start_date, cadence)
	target_period_end = get_target_period_end(cadence, through_date)
	existing_periods = fetch_existing_vat_periods(company, cstr(get_document_value(configuration, "name")).strip(), cadence)
	existing_by_key = {
		(getdate(row["period_start_date"]), getdate(row["period_end_date"])): row["name"]
		for row in existing_periods
	}

	created_periods: list[str] = []
	existing_period_names: list[str] = []
	period_start_date = first_managed_period_start_date

	while period_start_date <= target_period_end:
		period_end_date = get_period_end_date(period_start_date, cadence)
		period_key = (period_start_date, period_end_date)
		if existing_name := existing_by_key.get(period_key):
			existing_period_names.append(existing_name)
		else:
			created_name = create_vat_period(configuration, period_start_date, period_end_date)
			created_periods.append(created_name)
		period_start_date = get_next_period_start_date(period_start_date, cadence)

	return {
		"tax_configuration": cstr(get_document_value(configuration, "name")).strip(),
		"created_periods": created_periods,
		"existing_periods": existing_period_names,
		"target_period_end": target_period_end.isoformat(),
		"latest_period": (created_periods or existing_period_names or [None])[-1],
	}


def create_vat_period(configuration: Any, period_start_date: date, period_end_date: date) -> str:
	company = cstr(get_document_value(configuration, "company")).strip()
	cadence = cstr(get_document_value(configuration, "vat_liquidation_cadence")).strip()
	doc = frappe.get_doc(
		{
			"doctype": "VAT Period",
			"company": company,
			"tax_configuration": cstr(get_document_value(configuration, "name")).strip(),
			"fiscal_year": resolve_fiscal_year(company, period_end_date),
			"vat_liquidation_cadence": cadence,
			"period_label": build_period_label(period_start_date, cadence),
			"status": "Open",
			"period_start_date": period_start_date,
			"period_end_date": period_end_date,
			"due_date": get_due_date(period_end_date, cadence),
			"previous_credit_brought_forward": get_previous_credit_amount(
				company,
				cstr(get_document_value(configuration, "name")).strip(),
				cadence,
				period_start_date,
			),
		}
	)
	doc.insert(ignore_permissions=True)
	return cstr(getattr(doc, "name", "")).strip()


def sync_next_vat_period_credit(document: Any) -> None:
	status = cstr(get_document_value(document, "status")).strip()
	if status == "Cancelled":
		return

	next_period_name = get_next_existing_vat_period_name(document)
	if not next_period_name:
		return

	next_period_status = cstr(frappe.get_cached_value("VAT Period", next_period_name, "status")).strip()
	if next_period_status not in {"Open", "Draft"}:
		return

	next_credit = round_amount(get_document_value(document, "final_credit_amount"))
	current_brought_forward = round_amount(
		frappe.get_cached_value("VAT Period", next_period_name, "previous_credit_brought_forward")
	)
	if current_brought_forward == next_credit:
		return

	frappe.db.set_value(
		"VAT Period",
		next_period_name,
		"previous_credit_brought_forward",
		next_credit,
		update_modified=False,
	)


def get_next_existing_vat_period_name(document: Any) -> str | None:
	return frappe.db.get_value(
		"VAT Period",
		{
			"company": get_document_value(document, "company"),
			"tax_configuration": get_document_value(document, "tax_configuration"),
			"vat_liquidation_cadence": get_document_value(document, "vat_liquidation_cadence"),
			"period_start_date": (">", get_document_value(document, "period_start_date")),
		},
		"name",
		order_by="period_start_date asc",
	)


def get_previous_credit_amount(
	company: str, tax_configuration: str, cadence: str, period_start_date: date
) -> float:
	previous_period = frappe.get_all(
		"VAT Period",
		filters={
			"company": company,
			"tax_configuration": tax_configuration,
			"vat_liquidation_cadence": cadence,
			"period_end_date": ("<", period_start_date),
			"status": ("!=", "Cancelled"),
		},
		fields=["final_credit_amount"],
		order_by="period_end_date desc",
		limit=1,
	)
	if not previous_period:
		return 0.0
	return round_amount(previous_period[0].get("final_credit_amount"))


def fetch_existing_vat_periods(company: str, tax_configuration: str, cadence: str) -> list[dict[str, Any]]:
	return frappe.get_all(
		"VAT Period",
		filters={
			"company": company,
			"tax_configuration": tax_configuration,
			"vat_liquidation_cadence": cadence,
		},
		fields=["name", "period_start_date", "period_end_date"],
		order_by="period_start_date asc",
	)


def get_existing_vat_period_name(
	company: str, tax_configuration: str, cadence: str, period_start_date: date, period_end_date: date
) -> str | None:
	return frappe.db.get_value(
		"VAT Period",
		{
			"company": company,
			"tax_configuration": tax_configuration,
			"vat_liquidation_cadence": cadence,
			"period_start_date": period_start_date,
			"period_end_date": period_end_date,
		},
		"name",
	)


def get_target_period_end(cadence: str, through_date: str | date | None = None) -> date:
	anchor_date = getdate(through_date or nowdate())
	return get_period_end_date(get_period_start_date(anchor_date, cadence), cadence)


def get_next_period_bounds(period_start_date: date, period_end_date: date, cadence: str) -> tuple[date, date]:
	next_start_date = get_next_period_start_date(period_start_date, cadence)
	return next_start_date, get_period_end_date(next_start_date, cadence)


def get_next_period_start_date(period_start_date: date, cadence: str) -> date:
	if cadence == "Monthly":
		if period_start_date.month == 12:
			return date(period_start_date.year + 1, 1, 1)
		return date(period_start_date.year, period_start_date.month + 1, 1)

	quarter_start_month = ((period_start_date.month - 1) // 3) * 3 + 1
	next_quarter_start_month = quarter_start_month + 3
	if next_quarter_start_month > 12:
		return date(period_start_date.year + 1, next_quarter_start_month - 12, 1)
	return date(period_start_date.year, next_quarter_start_month, 1)


def get_period_start_date(anchor_date: date, cadence: str) -> date:
	if cadence == "Monthly":
		return date(anchor_date.year, anchor_date.month, 1)
	quarter_start_month = ((anchor_date.month - 1) // 3) * 3 + 1
	return date(anchor_date.year, quarter_start_month, 1)


def get_period_end_date(period_start_date: date, cadence: str) -> date:
	if cadence == "Monthly":
		return date(
			period_start_date.year,
			period_start_date.month,
			monthrange(period_start_date.year, period_start_date.month)[1],
		)

	quarter_end_month = period_start_date.month + 2
	return date(
		period_start_date.year,
		quarter_end_month,
		monthrange(period_start_date.year, quarter_end_month)[1],
	)


def get_due_date(period_end_date: date, cadence: str) -> date:
	months_to_add = 1 if cadence == "Monthly" else 2
	due_year = period_end_date.year + ((period_end_date.month - 1 + months_to_add) // 12)
	due_month = ((period_end_date.month - 1 + months_to_add) % 12) + 1
	due_day = 20 if due_month == 8 else 16
	return date(due_year, due_month, due_day)


def build_period_label(period_start_date: date, cadence: str) -> str:
	if cadence == "Monthly":
		return period_start_date.strftime("%m/%Y")
	quarter = ((period_start_date.month - 1) // 3) + 1
	return f"Q{quarter} {period_start_date.year}"


def resolve_fiscal_year(company: str, period_end_date: date) -> str | None:
	fiscal_year = get_fiscal_year(date=period_end_date, company=company, raise_on_missing=False)
	if not fiscal_year:
		return None
	return fiscal_year[0]


def validate_managed_start_date(first_managed_period_start_date: date, cadence: str) -> None:
	expected_start_date = get_period_start_date(first_managed_period_start_date, cadence)
	if first_managed_period_start_date != expected_start_date:
		frappe.throw(
			_("First Managed Period Start Date must match the start of a {0} VAT period.").format(
				cadence.lower()
			)
		)


def build_generation_message(
	created_periods: list[str], existing_periods: list[str], target_period_end: str
) -> str:
	if created_periods:
		return _("Generated {0} VAT period(s) through {1}.").format(
			len(created_periods), target_period_end
		)
	if existing_periods:
		return _("VAT periods already exist through {0}.").format(target_period_end)
	return _("No VAT periods were generated.")


def get_tax_configuration(tax_configuration: str | Any):
	if isinstance(tax_configuration, str):
		return frappe.get_doc("Italy Tax Configuration", tax_configuration)
	return tax_configuration


def resolve_vat_period(vat_period: str | Any):
	if isinstance(vat_period, str):
		return frappe.get_doc("VAT Period", vat_period)
	return vat_period


def round_amount(value: Any) -> float:
	return round(flt(value), 2)
