from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from datetime import date

from fab_italy_tax.company_tax_settings import (
	ensure_default_company_tax_setup,
	provision_tax_configuration_setup,
	sync_company_tax_fields_from_configuration,
	sync_tax_configuration_from_company,
)


def build_company(**overrides):
	defaults = {
		"name": "Fabricators",
		"country": "Italy",
		"fab_itx_enabled": 1,
		"fab_itx_vat_liquidation_cadence": "Quarterly",
		"fab_itx_first_managed_period_start_date": "2026-01-01",
		"fab_itx_settlement_journal_naming_series": "JV-TAX-.YYYY.-",
		"fab_itx_default_tax_payment_mode": "Bank Transfer",
		"fab_itx_vat_output_account": "VAT Output - FAB",
		"fab_itx_vat_input_account": "VAT Input - FAB",
		"fab_itx_vat_payable_account": "VAT Payable - FAB",
		"fab_itx_vat_credit_account": "VAT Credit - FAB",
		"fab_itx_quarterly_interest_account": "Quarterly Interest - FAB",
		"fab_itx_carry_forward_account": "Carry Forward - FAB",
		"fab_itx_include_employee_cost_in_cash_planning": 1,
		"fab_itx_employee_cost_source_mode": "HRMS Payroll",
	}
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


class TestCompanyTaxSettings(unittest.TestCase):
	def test_sync_creates_configuration_from_company_fields(self):
		company = build_company()
		new_doc = SimpleNamespace(insert=Mock())
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(get_value=Mock(return_value=None)),
			get_doc=Mock(return_value=new_doc),
		)

		with patch("fab_italy_tax.company_tax_settings.frappe", new=frappe_stub):
			sync_tax_configuration_from_company(company)

		payload = frappe_stub.get_doc.call_args.args[0]
		self.assertEqual(payload["doctype"], "Italy Tax Configuration")
		self.assertEqual(payload["company"], "Fabricators")
		self.assertEqual(payload["vat_liquidation_cadence"], "Quarterly")
		self.assertEqual(payload["employee_cost_source_mode"], "HRMS Payroll")
		new_doc.insert.assert_called_once_with(ignore_permissions=True)

	def test_sync_updates_existing_configuration(self):
		company = build_company(fab_itx_vat_liquidation_cadence="Monthly")
		config_values = {"enabled": 0, "vat_liquidation_cadence": "Quarterly"}
		config = SimpleNamespace(
			get=lambda fieldname: config_values.get(fieldname),
			set=Mock(side_effect=lambda fieldname, value: config_values.__setitem__(fieldname, value)),
			save=Mock(),
		)
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(get_value=Mock(return_value="Fabricators")),
			get_doc=Mock(return_value=config),
		)

		with patch("fab_italy_tax.company_tax_settings.frappe", new=frappe_stub):
			sync_tax_configuration_from_company(company)

		config.set.assert_any_call("enabled", 1)
		config.set.assert_any_call("vat_liquidation_cadence", "Monthly")
		config.save.assert_called_once_with(ignore_permissions=True)

	def test_sync_skips_non_italian_company_without_tax_values(self):
		company = build_company(
			country="Germany",
			fab_itx_enabled=0,
			fab_itx_first_managed_period_start_date=None,
			fab_itx_settlement_journal_naming_series="",
			fab_itx_default_tax_payment_mode="",
			fab_itx_vat_output_account="",
			fab_itx_vat_input_account="",
			fab_itx_vat_payable_account="",
			fab_itx_vat_credit_account="",
			fab_itx_quarterly_interest_account="",
			fab_itx_carry_forward_account="",
			fab_itx_include_employee_cost_in_cash_planning=0,
		)
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(get_value=Mock()),
			get_doc=Mock(),
		)

		with patch("fab_italy_tax.company_tax_settings.frappe", new=frappe_stub):
			sync_tax_configuration_from_company(company)

		frappe_stub.db.get_value.assert_not_called()
		frappe_stub.get_doc.assert_not_called()

	def test_enabled_italian_company_bootstraps_missing_accounts(self):
		company = build_company(
			fab_itx_first_managed_period_start_date=None,
			fab_itx_default_tax_payment_mode="",
			fab_itx_vat_output_account="",
			fab_itx_vat_input_account="",
			fab_itx_vat_payable_account="",
			fab_itx_vat_credit_account="",
			fab_itx_quarterly_interest_account="",
			fab_itx_carry_forward_account="",
		)
		payload = {
			"company": "Fabricators",
			"enabled": 1,
			"vat_liquidation_cadence": "Quarterly",
			"first_managed_period_start_date": None,
			"default_tax_payment_mode": "",
			"vat_output_account": "",
			"vat_input_account": "",
			"vat_payable_account": "",
			"vat_credit_account": "",
			"quarterly_interest_account": "",
			"carry_forward_account": "",
		}
		frappe_stub = SimpleNamespace(db=SimpleNamespace(set_value=Mock()))

		with (
			patch("fab_italy_tax.company_tax_settings.frappe", new=frappe_stub),
			patch(
				"fab_italy_tax.company_tax_settings.ensure_default_tax_account",
				side_effect=[
					"VAT Output - FAB",
					"VAT Input - FAB",
					"VAT Payable - FAB",
					"VAT Credit - FAB",
					"VAT Credit Carry Forward - FAB",
				],
			),
			patch(
				"fab_italy_tax.company_tax_settings.ensure_default_expense_account",
				return_value="Quarterly VAT Interest - FAB",
			),
			patch(
				"fab_italy_tax.company_tax_settings.ensure_default_mode_of_payment",
				return_value="F24 Tax Payment",
			),
			patch(
				"fab_italy_tax.company_tax_settings.resolve_first_managed_period_start_date",
				return_value=date(2026, 1, 1),
			),
		):
			result = ensure_default_company_tax_setup(company, payload)

		self.assertEqual(result["first_managed_period_start_date"], date(2026, 1, 1))
		self.assertEqual(result["default_tax_payment_mode"], "F24 Tax Payment")
		self.assertEqual(result["vat_output_account"], "VAT Output - FAB")
		self.assertEqual(result["vat_input_account"], "VAT Input - FAB")
		self.assertEqual(result["vat_payable_account"], "VAT Payable - FAB")
		self.assertEqual(result["vat_credit_account"], "VAT Credit - FAB")
		self.assertEqual(result["carry_forward_account"], "VAT Credit Carry Forward - FAB")
		self.assertEqual(result["quarterly_interest_account"], "Quarterly VAT Interest - FAB")
		frappe_stub.db.set_value.assert_called_once()
		self.assertEqual(company.fab_itx_vat_payable_account, "VAT Payable - FAB")
		self.assertEqual(company.fab_itx_default_tax_payment_mode, "F24 Tax Payment")

	def test_monthly_bootstrap_does_not_create_quarterly_interest_account(self):
		company = build_company(fab_itx_quarterly_interest_account="")
		payload = {
			"company": "Fabricators",
			"enabled": 1,
			"vat_liquidation_cadence": "Monthly",
			"vat_output_account": "VAT Output - FAB",
			"vat_input_account": "VAT Input - FAB",
			"vat_payable_account": "VAT Payable - FAB",
			"vat_credit_account": "VAT Credit - FAB",
			"quarterly_interest_account": "",
			"carry_forward_account": "VAT Credit Carry Forward - FAB",
		}
		frappe_stub = SimpleNamespace(db=SimpleNamespace(set_value=Mock()))

		with (
			patch("fab_italy_tax.company_tax_settings.frappe", new=frappe_stub),
			patch("fab_italy_tax.company_tax_settings.ensure_default_tax_account") as ensure_tax_account,
			patch("fab_italy_tax.company_tax_settings.ensure_default_expense_account") as ensure_expense_account,
		):
			result = ensure_default_company_tax_setup(company, payload)

		self.assertEqual(result["quarterly_interest_account"], "")
		ensure_tax_account.assert_not_called()
		ensure_expense_account.assert_not_called()
		frappe_stub.db.set_value.assert_not_called()

	def test_sync_company_fields_from_tax_configuration(self):
		document = SimpleNamespace(
			company="Fabricators",
			enabled=1,
			vat_liquidation_cadence="Quarterly",
			first_managed_period_start_date="2026-01-01",
			settlement_journal_naming_series="JV-TAX-.YYYY.-",
			default_tax_payment_mode="F24 Tax Payment",
			vat_output_account="VAT Output - FAB",
			vat_input_account="VAT Input - FAB",
			vat_payable_account="VAT Payable - FAB",
			vat_credit_account="VAT Credit - FAB",
			quarterly_interest_account="Quarterly VAT Interest - FAB",
			carry_forward_account="VAT Credit Carry Forward - FAB",
			include_employee_cost_in_cash_planning=1,
			employee_cost_source_mode="Accounting Entries",
		)
		frappe_stub = SimpleNamespace(db=SimpleNamespace(set_value=Mock()))

		with patch("fab_italy_tax.company_tax_settings.frappe", new=frappe_stub):
			sync_company_tax_fields_from_configuration(document)

		frappe_stub.db.set_value.assert_called_once()
		args = frappe_stub.db.set_value.call_args.args
		self.assertEqual(args[0], "Company")
		self.assertEqual(args[1], "Fabricators")
		self.assertEqual(args[2]["fab_itx_default_tax_payment_mode"], "F24 Tax Payment")
		self.assertEqual(args[2]["fab_itx_vat_payable_account"], "VAT Payable - FAB")

	def test_provision_tax_configuration_setup_fills_missing_defaults(self):
		document = SimpleNamespace(
			name="Fabricators",
			company="Fabricators",
			vat_liquidation_cadence="Quarterly",
			first_managed_period_start_date=None,
			default_tax_payment_mode="",
			vat_output_account="",
			vat_input_account="",
			vat_payable_account="",
			vat_credit_account="",
			quarterly_interest_account="",
			carry_forward_account="",
			save=Mock(),
		)
		frappe_stub = SimpleNamespace(get_doc=Mock(return_value=document))

		with (
			patch("fab_italy_tax.company_tax_settings.frappe", new=frappe_stub),
			patch(
				"fab_italy_tax.company_tax_settings.ensure_default_tax_account",
				side_effect=[
					"VAT Output - FAB",
					"VAT Input - FAB",
					"VAT Payable - FAB",
					"VAT Credit - FAB",
					"VAT Credit Carry Forward - FAB",
				],
			),
			patch(
				"fab_italy_tax.company_tax_settings.ensure_default_expense_account",
				return_value="Quarterly VAT Interest - FAB",
			),
			patch(
				"fab_italy_tax.company_tax_settings.ensure_default_mode_of_payment",
				return_value="F24 Tax Payment",
			),
			patch(
				"fab_italy_tax.company_tax_settings.resolve_first_managed_period_start_date",
				return_value=date(2026, 1, 1),
			),
			patch("fab_italy_tax.company_tax_settings.sync_company_tax_fields_from_configuration"),
		):
			result = provision_tax_configuration_setup("Fabricators")

		self.assertEqual(result["tax_configuration"], "Fabricators")
		self.assertIn("default_tax_payment_mode", result["updated_fields"])
		self.assertEqual(document.vat_payable_account, "VAT Payable - FAB")
		self.assertEqual(document.default_tax_payment_mode, "F24 Tax Payment")
		document.save.assert_called_once_with(ignore_permissions=True)
