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
			},
		)
