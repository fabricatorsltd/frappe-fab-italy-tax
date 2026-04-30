from __future__ import annotations

import frappe
from frappe import _

from fab_italy_tax.yearly_close import get_yearly_balance


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)
	result = get_yearly_balance(company=filters.company, fiscal_year=filters.fiscal_year)
	return result["columns"], result["data"], None, None, result["summary"]


def validate_filters(filters) -> None:
	if not filters.get("company"):
		frappe.throw(_("Select a Company first."))
	if not filters.get("fiscal_year"):
		frappe.throw(_("Select a Fiscal Year first."))

