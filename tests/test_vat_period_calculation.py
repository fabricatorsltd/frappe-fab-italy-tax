from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from frappe.exceptions import ValidationError

from fab_italy_tax.vat_period_calculation import calculate_vat_period


def raise_validation_error(message):
	raise ValidationError(str(message))


def build_vat_period(**overrides):
	defaults = {
		"name": "VAT-PERIOD-2026-00001",
		"company": "Fabricators",
		"tax_configuration": "TAX-CONFIG-FAB",
		"status": "Draft",
		"period_start_date": "2026-01-01",
		"period_end_date": "2026-03-31",
		"previous_credit_brought_forward": 40.0,
		"output_vat_total": 0.0,
		"input_vat_total": 0.0,
		"quarterly_interest_amount": 0.0,
		"final_payable_amount": 0.0,
		"final_credit_amount": 0.0,
		"save": Mock(),
	}
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


def build_tax_configuration(**overrides):
	defaults = {
		"vat_output_account": "VAT Output - FAB",
		"vat_input_account": "VAT Input - FAB",
	}
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


class TestVATPeriodCalculation(unittest.TestCase):
	def test_calculate_vat_period_builds_payable_totals(self):
		document = build_vat_period()

		def get_doc_side_effect(doctype, name):
			if doctype == "VAT Period":
				return document
			raise AssertionError(f"Unexpected get_doc call: {doctype} {name}")

		def get_all_side_effect(doctype, **kwargs):
			if doctype == "GL Entry":
				return [
					{"account": "IVA 22% - FAB", "voucher_type": "Sales Invoice", "credit": 220.0, "debit": 0.0},
					{"account": "IVA 10% - FAB", "voucher_type": "Sales Invoice", "credit": 20.0, "debit": 0.0},
					{"account": "IVA 22% - FAB", "voucher_type": "Purchase Invoice", "credit": 0.0, "debit": 80.0},
					{"account": "Other Account - FAB", "credit": 50.0, "debit": 50.0},
				]
			if doctype == "Account":
				return ["IVA 22% - FAB", "IVA 10% - FAB"]
			if doctype == "VAT Adjustment":
				return [
					{
						"adjustment_type": "Quarterly Interest",
						"direction": "Increase Payable",
						"amount": 10.0,
					},
					{
						"adjustment_type": "Settlement Correction",
						"direction": "Increase Credit",
						"amount": 5.0,
					},
				]
			raise AssertionError(f"Unexpected get_all call: {doctype}")

		frappe_stub = SimpleNamespace(
			throw=Mock(side_effect=raise_validation_error),
			get_doc=Mock(side_effect=get_doc_side_effect),
			get_all=Mock(side_effect=get_all_side_effect),
		)

		with patch("fab_italy_tax.vat_period_calculation.frappe", new=frappe_stub):
			results = calculate_vat_period("VAT-PERIOD-2026-00001")

		self.assertEqual(results["output_vat_total"], 240.0)
		self.assertEqual(results["input_vat_total"], 80.0)
		self.assertEqual(results["quarterly_interest_amount"], 10.0)
		self.assertEqual(results["final_payable_amount"], 125.0)
		self.assertEqual(results["final_credit_amount"], 0.0)
		self.assertEqual(document.status, "Calculated")
		document.save.assert_called_once_with(ignore_permissions=True)

	def test_calculate_vat_period_builds_credit_totals(self):
		document = build_vat_period(previous_credit_brought_forward=20.0)

		def get_doc_side_effect(doctype, name):
			if doctype == "VAT Period":
				return document
			raise AssertionError(f"Unexpected get_doc call: {doctype} {name}")

		def get_all_side_effect(doctype, **kwargs):
			if doctype == "GL Entry":
				return [
					{"account": "IVA 22% - FAB", "voucher_type": "Sales Invoice", "credit": 100.0, "debit": 0.0},
					{"account": "IVA 22% - FAB", "voucher_type": "Purchase Invoice", "credit": 0.0, "debit": 180.0},
				]
			if doctype == "Account":
				return ["IVA 22% - FAB"]
			if doctype == "VAT Adjustment":
				return []
			raise AssertionError(f"Unexpected get_all call: {doctype}")

		frappe_stub = SimpleNamespace(
			throw=Mock(side_effect=raise_validation_error),
			get_doc=Mock(side_effect=get_doc_side_effect),
			get_all=Mock(side_effect=get_all_side_effect),
		)

		with patch("fab_italy_tax.vat_period_calculation.frappe", new=frappe_stub):
			results = calculate_vat_period("VAT-PERIOD-2026-00001")

		self.assertEqual(results["final_payable_amount"], 0.0)
		self.assertEqual(results["final_credit_amount"], 100.0)

	def test_calculate_vat_period_ignores_non_tax_accounts(self):
		document = build_vat_period(previous_credit_brought_forward=0.0)

		def get_doc_side_effect(doctype, name):
			if doctype == "VAT Period":
				return document
			raise AssertionError(f"Unexpected get_doc call: {doctype} {name}")

		def get_all_side_effect(doctype, **kwargs):
			if doctype == "GL Entry":
				return [
					{"account": "IVA 22% - FAB", "voucher_type": "Sales Invoice", "credit": 22.0, "debit": 0.0},
					{"account": "Sales - FAB", "voucher_type": "Sales Invoice", "credit": 100.0, "debit": 0.0},
					{"account": "IVA 22% - FAB", "voucher_type": "Purchase Invoice", "credit": 0.0, "debit": 5.0},
					{"account": "Expenses - FAB", "voucher_type": "Purchase Invoice", "credit": 0.0, "debit": 50.0},
				]
			if doctype == "Account":
				return ["IVA 22% - FAB"]
			if doctype == "VAT Adjustment":
				return []
			raise AssertionError(f"Unexpected get_all call: {doctype}")

		frappe_stub = SimpleNamespace(
			throw=Mock(side_effect=raise_validation_error),
			get_doc=Mock(side_effect=get_doc_side_effect),
			get_all=Mock(side_effect=get_all_side_effect),
		)

		with patch("fab_italy_tax.vat_period_calculation.frappe", new=frappe_stub):
			results = calculate_vat_period("VAT-PERIOD-2026-00001")

		self.assertEqual(results["output_vat_total"], 22.0)
		self.assertEqual(results["input_vat_total"], 5.0)
		self.assertEqual(results["final_payable_amount"], 17.0)

	def test_locked_period_cannot_be_recalculated(self):
		document = build_vat_period(status="Posted")

		frappe_stub = SimpleNamespace(
			throw=Mock(side_effect=raise_validation_error),
			get_doc=Mock(return_value=document),
		)

		with (
			patch("fab_italy_tax.vat_period_calculation.frappe", new=frappe_stub),
			self.assertRaisesRegex(ValidationError, "cannot be recalculated"),
		):
			calculate_vat_period("VAT-PERIOD-2026-00001")
