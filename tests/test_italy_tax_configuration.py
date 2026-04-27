from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from frappe.exceptions import ValidationError

from fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration import (
	validate_italy_tax_configuration,
)


def raise_validation_error(message):
	raise ValidationError(str(message))


def build_document(**overrides):
	defaults = {
		"company": "Fabricators",
		"enabled": 1,
		"vat_liquidation_cadence": "Monthly",
		"first_managed_period_start_date": "2026-01-01",
		"vat_output_account": "VAT Output - FAB",
		"vat_input_account": "VAT Input - FAB",
		"vat_payable_account": "VAT Payable - FAB",
		"vat_credit_account": "VAT Credit - FAB",
		"quarterly_interest_account": "Quarterly Interest - FAB",
		"carry_forward_account": "VAT Carry Forward - FAB",
		"include_employee_cost_in_cash_planning": 0,
		"employee_cost_source_mode": "Accounting Entries",
	}
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


class TestItalyTaxConfiguration(unittest.TestCase):
	def test_valid_monthly_configuration_passes(self):
		document = build_document()

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration.frappe.throw",
				side_effect=raise_validation_error,
			),
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration.frappe.get_cached_value",
				return_value="Fabricators",
			),
		):
			validate_italy_tax_configuration(document)

	def test_disabled_configuration_can_be_saved_without_accounts(self):
		document = build_document(
			enabled=0,
			first_managed_period_start_date=None,
			vat_output_account=None,
			vat_input_account=None,
			vat_payable_account=None,
			vat_credit_account=None,
			quarterly_interest_account=None,
			carry_forward_account=None,
		)

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration.frappe.throw",
				side_effect=raise_validation_error,
			),
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration.frappe.get_cached_value",
				return_value=None,
			),
		):
			validate_italy_tax_configuration(document)

	def test_enabled_configuration_requires_start_date(self):
		document = build_document(first_managed_period_start_date=None)

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration.frappe.throw",
				side_effect=raise_validation_error,
			),
			self.assertRaisesRegex(ValidationError, "First Managed Period Start Date"),
		):
			validate_italy_tax_configuration(document)

	def test_quarterly_configuration_requires_interest_account(self):
		document = build_document(vat_liquidation_cadence="Quarterly", quarterly_interest_account=None)

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration.frappe.throw",
				side_effect=raise_validation_error,
			),
			self.assertRaisesRegex(ValidationError, "Quarterly Interest Account"),
		):
			validate_italy_tax_configuration(document)

	def test_account_must_belong_to_selected_company(self):
		document = build_document()

		def get_cached_value_side_effect(doctype, name, fieldname):
			if doctype == "Account" and name == "VAT Payable - FAB":
				return "Other Company"
			return "Fabricators"

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration.frappe.throw",
				side_effect=raise_validation_error,
			),
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration.frappe.get_cached_value",
				side_effect=get_cached_value_side_effect,
			),
			self.assertRaisesRegex(ValidationError, "VAT Payable Account"),
		):
			validate_italy_tax_configuration(document)

	def test_employee_cost_mode_is_required_when_cash_planning_is_enabled(self):
		document = build_document(include_employee_cost_in_cash_planning=1, employee_cost_source_mode="")

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.italy_tax_configuration.italy_tax_configuration.frappe.throw",
				side_effect=raise_validation_error,
			),
			self.assertRaisesRegex(ValidationError, "Employee Cost Source Mode"),
		):
			validate_italy_tax_configuration(document)
