from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from frappe.exceptions import ValidationError

from fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period import validate_vat_period


def raise_validation_error(message):
	raise ValidationError(str(message))


def build_document(**overrides):
	defaults = {
		"company": "Fabricators",
		"tax_configuration": "Fabricators",
		"vat_liquidation_cadence": "Monthly",
		"status": "Open",
		"period_start_date": "2026-01-01",
		"period_end_date": "2026-01-31",
		"due_date": "2026-02-16",
		"linked_settlement_entry": None,
		"final_payable_amount": 0,
		"final_credit_amount": 0,
	}
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


class TestVATPeriod(unittest.TestCase):
	def test_valid_monthly_period_passes(self):
		document = build_document()

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe.throw",
				side_effect=raise_validation_error,
			),
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe.db.get_value",
				return_value=None,
			),
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe.get_cached_value",
				side_effect=lambda doctype, name, fieldname: "Fabricators"
				if fieldname == "company"
				else "Monthly",
			),
		):
			validate_vat_period(document)

	def test_monthly_period_must_cover_single_month(self):
		document = build_document(period_end_date="2026-02-01")

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe.throw",
				side_effect=raise_validation_error,
			),
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe.db.get_value",
				return_value=None,
			),
			self.assertRaisesRegex(ValidationError, "single calendar month"),
		):
			validate_vat_period(document)

	def test_valid_quarterly_period_passes(self):
		document = build_document(
			vat_liquidation_cadence="Quarterly",
			period_start_date="2026-04-01",
			period_end_date="2026-06-30",
			due_date="2026-08-20",
		)

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe.throw",
				side_effect=raise_validation_error,
			),
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe.db.get_value",
				return_value=None,
			),
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe.get_cached_value",
				side_effect=lambda doctype, name, fieldname: "Fabricators"
				if fieldname == "company"
				else "Quarterly",
			),
		):
			validate_vat_period(document)

	def test_quarterly_period_must_align_to_calendar_quarter(self):
		document = build_document(
			vat_liquidation_cadence="Quarterly",
			period_start_date="2026-05-01",
			period_end_date="2026-06-30",
			due_date="2026-08-20",
		)

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe.throw",
				side_effect=raise_validation_error,
			),
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe.db.get_value",
				return_value=None,
			),
			self.assertRaisesRegex(ValidationError, "first day of a calendar quarter"),
		):
			validate_vat_period(document)

	def test_posted_period_requires_linked_settlement_entry(self):
		document = build_document(status="Posted")

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe.throw",
				side_effect=raise_validation_error,
			),
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe.db.get_value",
				return_value=None,
			),
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe.get_cached_value",
				side_effect=lambda doctype, name, fieldname: "Fabricators"
				if fieldname == "company"
				else "Monthly",
			),
			self.assertRaisesRegex(ValidationError, "Linked Settlement Entry"),
		):
			validate_vat_period(document)

	def test_configuration_company_must_match_period_company(self):
		document = build_document()

		def get_cached_value_side_effect(doctype, name, fieldname):
			if fieldname == "company":
				return "Other Company"
			return "Monthly"

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe.throw",
				side_effect=raise_validation_error,
			),
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe.db.get_value",
				return_value=None,
			),
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe.get_cached_value",
				side_effect=get_cached_value_side_effect,
			),
			self.assertRaisesRegex(ValidationError, "selected company"),
		):
			validate_vat_period(document)

	def test_duplicate_period_is_rejected(self):
		document = build_document()

		def get_cached_value_side_effect(doctype, name, fieldname):
			if fieldname == "company":
				return "Fabricators"
			return "Monthly"

		frappe_stub = SimpleNamespace(
			throw=Mock(side_effect=raise_validation_error),
			get_cached_value=Mock(side_effect=get_cached_value_side_effect),
			db=SimpleNamespace(get_value=Mock(return_value="VAT-PERIOD-2026-99999")),
		)

		with (
			patch("fab_italy_tax.fab_italy_tax.doctype.vat_period.vat_period.frappe", new=frappe_stub),
			self.assertRaisesRegex(ValidationError, "already exists"),
		):
			validate_vat_period(document)
