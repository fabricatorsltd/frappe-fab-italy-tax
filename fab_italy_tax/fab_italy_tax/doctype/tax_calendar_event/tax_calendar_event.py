from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, flt

from fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration import (
	get_document_value,
)

TAX_CALENDAR_EVENT_TYPES = {"VAT Settlement", "VAT Payment", "F24 Deadline", "Manual Tax Deadline"}
TAX_CALENDAR_EVENT_STATUSES = {"Planned", "Due", "Settled", "Cancelled"}
TAX_CALENDAR_EVENT_DIRECTIONS = {"Outflow", "Inflow"}


class TaxCalendarEvent(Document):
	def validate(self):
		validate_tax_calendar_event(self)


def validate_tax_calendar_event(document: Any) -> None:
	event_type = cstr(get_document_value(document, "event_type")).strip()
	status = cstr(get_document_value(document, "status")).strip()
	direction = cstr(get_document_value(document, "direction")).strip()
	reference_doctype = cstr(get_document_value(document, "reference_doctype")).strip()
	reference_name = cstr(get_document_value(document, "reference_name")).strip()
	amount = flt(get_document_value(document, "amount"))

	if event_type not in TAX_CALENDAR_EVENT_TYPES:
		frappe.throw(_("Tax Calendar Event Type is not valid."))

	if status not in TAX_CALENDAR_EVENT_STATUSES:
		frappe.throw(_("Tax Calendar Event Status is not valid."))

	if direction not in TAX_CALENDAR_EVENT_DIRECTIONS:
		frappe.throw(_("Tax Calendar Event Direction is not valid."))

	if amount < 0:
		frappe.throw(_("Tax Calendar Event Amount cannot be negative."))

	if bool(reference_doctype) != bool(reference_name):
		frappe.throw(_("Set both Reference DocType and Reference Name, or leave both empty."))

	if reference_doctype and not frappe.db.exists("DocType", reference_doctype):
		frappe.throw(_("Reference DocType does not exist."))

	if reference_doctype and not frappe.db.exists(reference_doctype, reference_name):
		frappe.throw(_("Reference Name does not exist for the selected Reference DocType."))
