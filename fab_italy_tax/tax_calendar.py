from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr, flt, getdate, nowdate

from fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration import (
	get_document_value,
)

VAT_PAYMENT_EVENT_TYPE = "VAT Payment"


def sync_existing_vat_period_tax_calendar_events() -> None:
	for vat_period in frappe.get_all("VAT Period", pluck="name"):
		sync_vat_period_tax_calendar_event(vat_period)


def sync_vat_period_tax_calendar_event(document: Any, method: str | None = None) -> str | None:
	vat_period = resolve_vat_period(document)
	vat_period_name = cstr(get_document_value(vat_period, "name")).strip()
	if not vat_period_name:
		return None

	event_name = get_vat_payment_calendar_event_name(vat_period_name)
	payload = build_vat_payment_calendar_event_payload(vat_period)
	if not payload and not event_name:
		return None

	if event_name:
		event = frappe.get_doc("Tax Calendar Event", event_name)
	else:
		event = frappe.new_doc("Tax Calendar Event")

	if payload:
		apply_values(event, payload)
	else:
		apply_values(event, build_cancelled_vat_payment_event_payload(vat_period))

	if event_name:
		event.save(ignore_permissions=True)
	else:
		event.insert(ignore_permissions=True)

	return cstr(getattr(event, "name", "")).strip() or None


@frappe.whitelist()
def get_vat_payment_calendar_event(vat_period: str) -> dict[str, Any] | None:
	event_name = get_vat_payment_calendar_event_name(vat_period)
	if not event_name:
		return None

	return frappe.db.get_value(
		"Tax Calendar Event",
		event_name,
		["name", "event_date", "amount", "status", "direction"],
		as_dict=True,
	)


def resolve_vat_period(document: Any):
	if isinstance(document, str):
		return frappe.get_doc("VAT Period", document)
	return document


def get_vat_payment_calendar_event_name(vat_period_name: str) -> str | None:
	return frappe.db.get_value(
		"Tax Calendar Event",
		{
			"reference_doctype": "VAT Period",
			"reference_name": vat_period_name,
			"event_type": VAT_PAYMENT_EVENT_TYPE,
		},
		"name",
	)


def build_vat_payment_calendar_event_payload(vat_period: Any) -> dict[str, Any] | None:
	status = cstr(get_document_value(vat_period, "status")).strip()
	if status == "Cancelled":
		return build_cancelled_vat_payment_event_payload(vat_period)

	final_payable_amount = round_amount(get_document_value(vat_period, "final_payable_amount"))
	if final_payable_amount <= 0:
		return None

	label = get_vat_period_label(vat_period)
	return {
		"company": get_document_value(vat_period, "company"),
		"event_type": VAT_PAYMENT_EVENT_TYPE,
		"reference_doctype": "VAT Period",
		"reference_name": get_document_value(vat_period, "name"),
		"event_date": get_document_value(vat_period, "due_date")
		or get_document_value(vat_period, "period_end_date"),
		"amount": final_payable_amount,
		"direction": "Outflow",
		"status": resolve_vat_payment_event_status(vat_period),
		"payment_mode": get_tax_payment_mode(vat_period),
		"linked_journal_entry": get_document_value(vat_period, "linked_settlement_entry"),
		"notes": _("VAT payment due for {0}.").format(label),
	}


def build_cancelled_vat_payment_event_payload(vat_period: Any) -> dict[str, Any]:
	return {
		"company": get_document_value(vat_period, "company"),
		"event_type": VAT_PAYMENT_EVENT_TYPE,
		"reference_doctype": "VAT Period",
		"reference_name": get_document_value(vat_period, "name"),
		"event_date": get_document_value(vat_period, "due_date")
		or get_document_value(vat_period, "period_end_date"),
		"amount": 0.0,
		"direction": "Outflow",
		"status": "Cancelled",
		"payment_mode": get_tax_payment_mode(vat_period),
		"linked_journal_entry": get_document_value(vat_period, "linked_settlement_entry"),
		"notes": _("VAT payment was cancelled or is no longer due for this period."),
	}


def resolve_vat_payment_event_status(vat_period: Any) -> str:
	status = cstr(get_document_value(vat_period, "status")).strip()
	if status == "Closed":
		return "Settled"

	due_date = get_document_value(vat_period, "due_date")
	if due_date and getdate(due_date) <= getdate(nowdate()):
		return "Due"
	return "Planned"


def get_tax_payment_mode(vat_period: Any) -> str | None:
	tax_configuration = cstr(get_document_value(vat_period, "tax_configuration")).strip()
	if not tax_configuration:
		return None
	return frappe.get_cached_value("Italy Tax Configuration", tax_configuration, "default_tax_payment_mode")


def get_vat_period_label(vat_period: Any) -> str:
	period_label = cstr(get_document_value(vat_period, "period_label")).strip()
	if period_label:
		return period_label
	return cstr(get_document_value(vat_period, "name")).strip()


def apply_values(document: Any, values: dict[str, Any]) -> None:
	for fieldname, value in values.items():
		setter = getattr(document, "set", None)
		if callable(setter):
			setter(fieldname, value)
			continue
		setattr(document, fieldname, value)


def round_amount(value: Any) -> float:
	return round(flt(value), 2)
