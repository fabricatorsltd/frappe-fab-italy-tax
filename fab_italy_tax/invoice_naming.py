from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, cstr

SALES_INVOICE_SERIES = "FATT/.YYYY./.#####"
SALES_CREDIT_NOTE_SERIES = "NDC/.YYYY./.#####"
PURCHASE_INVOICE_SERIES = "ACQ/.YYYY./.#####"
PURCHASE_CREDIT_NOTE_SERIES = "RACQ/.YYYY./.#####"

SERIES_CONFIG = {
	"Sales Invoice": {
		"default": SALES_INVOICE_SERIES,
		"invoice": SALES_INVOICE_SERIES,
		"return": SALES_CREDIT_NOTE_SERIES,
	},
	"Purchase Invoice": {
		"default": PURCHASE_INVOICE_SERIES,
		"invoice": PURCHASE_INVOICE_SERIES,
		"return": PURCHASE_CREDIT_NOTE_SERIES,
	},
}


def sync_italy_invoice_naming_series() -> None:
	for doctype, config in SERIES_CONFIG.items():
		options = "\n".join([config["invoice"], config["return"]])
		ensure_property_setter(doctype, "naming_series", "options", options)
		ensure_property_setter(doctype, "naming_series", "default", config["default"])


def apply_italy_invoice_naming_series(document: Any, method: str | None = None) -> None:
	doctype = cstr(get_document_value(document, "doctype")).strip()
	config = SERIES_CONFIG.get(doctype)
	if not config:
		return

	company = cstr(get_document_value(document, "company")).strip()
	if not should_manage_italy_series(company):
		return

	if has_persisted_name(document):
		return

	expected_series = config["return"] if cint(get_document_value(document, "is_return")) else config["invoice"]
	current_series = cstr(get_document_value(document, "naming_series")).strip()
	if current_series != expected_series:
		set_document_value(document, "naming_series", expected_series)


def should_manage_italy_series(company: str) -> bool:
	if not company:
		return False

	country = cstr(frappe.get_cached_value("Company", company, "country")).strip().lower()
	if country == "italy":
		return True

	return cint(frappe.get_cached_value("Company", company, "fab_itx_enabled")) == 1


def ensure_property_setter(doctype: str, fieldname: str, property_name: str, value: str) -> None:
	filters = {
		"doc_type": doctype,
		"field_name": fieldname,
		"property": property_name,
	}
	property_setter_name = frappe.db.get_value("Property Setter", filters, "name")
	if property_setter_name:
		current_value = cstr(frappe.db.get_value("Property Setter", property_setter_name, "value"))
		if current_value != value:
			frappe.db.set_value("Property Setter", property_setter_name, "value", value, update_modified=False)
		return

	frappe.make_property_setter(
		{
			"doctype": doctype,
			"doctype_or_field": "DocField",
			"fieldname": fieldname,
			"property": property_name,
			"property_type": "Text" if property_name == "options" else "Data",
			"value": value,
		},
		validate_fields_for_doctype=False,
		module="Fab Italy Tax",
	)


def has_persisted_name(document: Any) -> bool:
	name = cstr(get_document_value(document, "name")).strip()
	if not name:
		return False

	is_new = getattr(document, "is_new", None)
	if callable(is_new):
		return not is_new()

	return not cint(getattr(document, "__islocal", 0))


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
