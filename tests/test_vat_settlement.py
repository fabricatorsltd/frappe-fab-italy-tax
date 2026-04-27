from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from frappe.exceptions import ValidationError

from fab_italy_tax.vat_settlement import post_vat_settlement


def raise_validation_error(message):
	raise ValidationError(str(message))


def build_vat_period(**overrides):
	defaults = {
		"name": "VAT-PERIOD-2026-00001",
		"company": "Fabricators",
		"tax_configuration": "TAX-CONFIG-FAB",
		"status": "Open",
		"period_label": "Q1 2026",
		"period_end_date": "2026-03-31",
		"due_date": "2026-05-16",
		"previous_credit_brought_forward": 40.0,
		"output_vat_total": 0.0,
		"input_vat_total": 0.0,
		"quarterly_interest_amount": 0.0,
		"final_payable_amount": 0.0,
		"final_credit_amount": 0.0,
		"linked_settlement_entry": None,
		"save": Mock(),
	}
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


def build_tax_configuration(**overrides):
	defaults = {
		"settlement_journal_naming_series": "JV-TAX-.YYYY.-",
		"vat_output_account": "VAT Output - FAB",
		"vat_input_account": "VAT Input - FAB",
		"vat_payable_account": "VAT Payable - FAB",
		"vat_credit_account": "VAT Credit - FAB",
		"quarterly_interest_account": "Quarterly Interest - FAB",
		"carry_forward_account": "Carry Forward - FAB",
	}
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


class TestVATSettlement(unittest.TestCase):
	def test_post_vat_settlement_creates_payable_journal_entry(self):
		document = build_vat_period()
		configuration = build_tax_configuration()
		entry = SimpleNamespace(name="ACC-JV-2026-00001", insert=Mock(), submit=Mock())

		def get_doc_side_effect(doctype, name):
			if doctype == "Italy Tax Configuration":
				return configuration
			raise AssertionError(f"Unexpected get_doc call: {doctype} {name}")

		def calculate_side_effect(vat_period):
			vat_period.output_vat_total = 220.0
			vat_period.input_vat_total = 80.0
			vat_period.quarterly_interest_amount = 10.0
			vat_period.final_payable_amount = 110.0
			vat_period.final_credit_amount = 0.0
			vat_period.status = "Calculated"
			return {
				"output_vat_total": 220.0,
				"input_vat_total": 80.0,
				"quarterly_interest_amount": 10.0,
				"final_payable_amount": 110.0,
				"final_credit_amount": 0.0,
			}

		frappe_stub = SimpleNamespace(
			throw=Mock(side_effect=raise_validation_error),
			get_doc=Mock(side_effect=get_doc_side_effect),
			new_doc=Mock(return_value=entry),
		)

		with (
			patch("fab_italy_tax.vat_settlement.frappe", new=frappe_stub),
			patch("fab_italy_tax.vat_settlement.calculate_vat_period", side_effect=calculate_side_effect),
		):
			result = post_vat_settlement(document)

		self.assertIs(result, entry)
		self.assertEqual(entry.naming_series, "JV-TAX-.YYYY.-")
		self.assertEqual(entry.posting_date, "2026-05-16")
		self.assertEqual(
			entry.accounts,
			[
				{
					"account": "VAT Output - FAB",
					"debit_in_account_currency": 220.0,
					"credit_in_account_currency": 0.0,
				},
				{
					"account": "VAT Input - FAB",
					"debit_in_account_currency": 0.0,
					"credit_in_account_currency": 80.0,
				},
				{
					"account": "Carry Forward - FAB",
					"debit_in_account_currency": 0.0,
					"credit_in_account_currency": 40.0,
				},
				{
					"account": "Quarterly Interest - FAB",
					"debit_in_account_currency": 10.0,
					"credit_in_account_currency": 0.0,
				},
				{
					"account": "VAT Payable - FAB",
					"debit_in_account_currency": 0.0,
					"credit_in_account_currency": 110.0,
				},
			],
		)
		self.assertEqual(document.linked_settlement_entry, "ACC-JV-2026-00001")
		self.assertEqual(document.status, "Posted")
		entry.insert.assert_called_once_with(ignore_permissions=True)
		entry.submit.assert_called_once_with()
		document.save.assert_called_once_with(ignore_permissions=True)

	def test_post_vat_settlement_creates_credit_journal_entry(self):
		document = build_vat_period(previous_credit_brought_forward=20.0)
		configuration = build_tax_configuration()
		entry = SimpleNamespace(name="ACC-JV-2026-00002", insert=Mock(), submit=Mock())

		def get_doc_side_effect(doctype, name):
			if doctype == "Italy Tax Configuration":
				return configuration
			raise AssertionError(f"Unexpected get_doc call: {doctype} {name}")

		def calculate_side_effect(vat_period):
			vat_period.output_vat_total = 100.0
			vat_period.input_vat_total = 180.0
			vat_period.quarterly_interest_amount = 0.0
			vat_period.final_payable_amount = 0.0
			vat_period.final_credit_amount = 100.0
			vat_period.status = "Calculated"
			return {
				"output_vat_total": 100.0,
				"input_vat_total": 180.0,
				"quarterly_interest_amount": 0.0,
				"final_payable_amount": 0.0,
				"final_credit_amount": 100.0,
			}

		frappe_stub = SimpleNamespace(
			throw=Mock(side_effect=raise_validation_error),
			get_doc=Mock(side_effect=get_doc_side_effect),
			new_doc=Mock(return_value=entry),
		)

		with (
			patch("fab_italy_tax.vat_settlement.frappe", new=frappe_stub),
			patch("fab_italy_tax.vat_settlement.calculate_vat_period", side_effect=calculate_side_effect),
		):
			post_vat_settlement(document)

		self.assertEqual(
			entry.accounts,
			[
				{
					"account": "VAT Output - FAB",
					"debit_in_account_currency": 100.0,
					"credit_in_account_currency": 0.0,
				},
				{
					"account": "VAT Input - FAB",
					"debit_in_account_currency": 0.0,
					"credit_in_account_currency": 180.0,
				},
				{
					"account": "Carry Forward - FAB",
					"debit_in_account_currency": 0.0,
					"credit_in_account_currency": 20.0,
				},
				{
					"account": "VAT Credit - FAB",
					"debit_in_account_currency": 100.0,
					"credit_in_account_currency": 0.0,
				},
			],
		)
		self.assertEqual(document.status, "Posted")

	def test_existing_linked_entry_blocks_duplicate_posting(self):
		document = build_vat_period(linked_settlement_entry="ACC-JV-2026-99999")
		frappe_stub = SimpleNamespace(
			throw=Mock(side_effect=raise_validation_error),
		)

		with (
			patch("fab_italy_tax.vat_settlement.frappe", new=frappe_stub),
			self.assertRaisesRegex(ValidationError, "already has a Linked Settlement Entry"),
		):
			post_vat_settlement(document)

	def test_missing_required_account_blocks_posting(self):
		document = build_vat_period()
		configuration = build_tax_configuration(vat_payable_account="")

		def get_doc_side_effect(doctype, name):
			if doctype == "Italy Tax Configuration":
				return configuration
			raise AssertionError(f"Unexpected get_doc call: {doctype} {name}")

		def calculate_side_effect(vat_period):
			vat_period.output_vat_total = 220.0
			vat_period.input_vat_total = 80.0
			vat_period.quarterly_interest_amount = 10.0
			vat_period.final_payable_amount = 110.0
			vat_period.final_credit_amount = 0.0
			vat_period.status = "Calculated"
			return {}

		frappe_stub = SimpleNamespace(
			throw=Mock(side_effect=raise_validation_error),
			get_doc=Mock(side_effect=get_doc_side_effect),
			new_doc=Mock(),
		)

		with (
			patch("fab_italy_tax.vat_settlement.frappe", new=frappe_stub),
			patch("fab_italy_tax.vat_settlement.calculate_vat_period", side_effect=calculate_side_effect),
			self.assertRaisesRegex(ValidationError, "VAT Payable Account"),
		):
			post_vat_settlement(document)
