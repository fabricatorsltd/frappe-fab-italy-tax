from __future__ import annotations

import unittest

from fab_italy_tax import install


class TestInstall(unittest.TestCase):
	def test_company_custom_fields_include_tax_configuration_controls(self):
		custom_fields = install.get_custom_fields()

		self.assertIn("Company", custom_fields)
		self.assertGreaterEqual(
			{field["fieldname"] for field in custom_fields["Company"]},
			{
				"fab_itx_section",
				"fab_itx_enabled",
				"fab_itx_vat_liquidation_cadence",
				"fab_itx_first_managed_period_start_date",
				"fab_itx_vat_output_account",
				"fab_itx_vat_input_account",
				"fab_itx_vat_payable_account",
				"fab_itx_vat_credit_account",
				"fab_itx_quarterly_interest_account",
				"fab_itx_carry_forward_account",
				"fab_itx_include_employee_cost_in_cash_planning",
				"fab_itx_employee_cost_source_mode",
				"fab_itx_accrued_revenue_account",
				"fab_itx_accrued_expense_account",
			},
		)

	def test_employee_cost_source_mode_includes_employee_cost_entries(self):
		custom_fields = install.get_custom_fields()
		field = next(
			field
			for field in custom_fields["Company"]
			if field["fieldname"] == "fab_itx_employee_cost_source_mode"
		)

		self.assertIn("Employee Cost Entries", field["options"])

	def test_invoice_item_custom_fields_cover_competence_and_deductibility(self):
		custom_fields = install.get_custom_fields()

		self.assertGreaterEqual(
			{field["fieldname"] for field in custom_fields["Sales Invoice"]},
			{"fab_itx_competence_year"},
		)
		self.assertGreaterEqual(
			{field["fieldname"] for field in custom_fields["Purchase Invoice"]},
			{
				"fab_itx_competence_year",
				"fab_itx_invoice_deductibility_mode",
				"fab_itx_invoice_deductible_percentage",
				"fab_itx_invoice_deductible_amount",
			},
		)

		self.assertGreaterEqual(
			{field["fieldname"] for field in custom_fields["Sales Invoice Item"]},
			{
				"fab_itx_competence_start_date",
				"fab_itx_competence_end_date",
			},
		)
		self.assertGreaterEqual(
			{field["fieldname"] for field in custom_fields["Purchase Invoice Item"]},
			{
				"fab_itx_competence_start_date",
				"fab_itx_competence_end_date",
				"fab_itx_deductibility_mode",
				"fab_itx_deductible_percentage",
				"fab_itx_deductible_amount",
			},
		)

		deductibility_mode = next(
			field
			for field in custom_fields["Purchase Invoice Item"]
			if field["fieldname"] == "fab_itx_deductibility_mode"
		)
		self.assertEqual(deductibility_mode["in_list_view"], 1)

		deductible_percentage = next(
			field
			for field in custom_fields["Purchase Invoice Item"]
			if field["fieldname"] == "fab_itx_deductible_percentage"
		)
		self.assertEqual(deductible_percentage["in_list_view"], 1)

		deductible_amount = next(
			field
			for field in custom_fields["Purchase Invoice Item"]
			if field["fieldname"] == "fab_itx_deductible_amount"
		)
		self.assertEqual(deductible_amount["in_list_view"], 1)
