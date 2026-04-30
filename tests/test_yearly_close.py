from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fab_italy_tax.yearly_close import (
	FULLY_DEDUCTIBLE,
	NON_DEDUCTIBLE,
	PARTIALLY_DEDUCTIBLE_AMOUNT,
	PARTIALLY_DEDUCTIBLE_PERCENTAGE,
	allocate_amount_to_period,
	build_competence_accounts,
	build_header_competence_adjustments,
	get_allowed_competence_years,
	get_deductibility_ratio,
	get_result_deductibility_ratio,
	is_prior_year_competence_selected,
	validate_invoice_competence_year,
	validate_purchase_deductibility,
	validate_sales_invoice_yearly_close,
)


class TestYearlyClose(unittest.TestCase):
	def test_allocate_amount_to_period_prorates_days(self):
		self.assertEqual(
			allocate_amount_to_period(
				amount=310.0,
				start_date="2025-12-01",
				end_date="2025-12-31",
				period_start="2025-12-01",
				period_end="2025-12-15",
			),
			150.0,
		)

	def test_get_deductibility_ratio_uses_percentage_mode(self):
		item = SimpleNamespace(
			fab_itx_deductibility_mode=PARTIALLY_DEDUCTIBLE_PERCENTAGE,
			fab_itx_deductible_percentage=40.0,
			fab_itx_deductible_amount=0.0,
			base_net_amount=100.0,
		)

		self.assertEqual(get_deductibility_ratio(item), 0.4)

	def test_get_deductibility_ratio_uses_amount_mode(self):
		item = SimpleNamespace(
			fab_itx_deductibility_mode=PARTIALLY_DEDUCTIBLE_AMOUNT,
			fab_itx_deductible_percentage=0.0,
			fab_itx_deductible_amount=30.0,
			base_net_amount=120.0,
		)

		self.assertEqual(get_deductibility_ratio(item), 0.25)

	def test_get_deductibility_ratio_marks_non_deductible(self):
		item = SimpleNamespace(
			fab_itx_deductibility_mode=NON_DEDUCTIBLE,
			fab_itx_deductible_percentage=0.0,
			fab_itx_deductible_amount=0.0,
			base_net_amount=120.0,
		)

		self.assertEqual(get_deductibility_ratio(item), 0.0)

	def test_validate_purchase_deductibility_rejects_amount_above_line_total(self):
		document = SimpleNamespace(
			items=[
				SimpleNamespace(
					idx=1,
					fab_itx_deductibility_mode=PARTIALLY_DEDUCTIBLE_AMOUNT,
					fab_itx_deductible_amount=120.0,
					fab_itx_deductible_percentage=0.0,
					base_net_amount=100.0,
				)
			]
		)

		with patch("fab_italy_tax.yearly_close.frappe.throw", side_effect=RuntimeError("boom")):
			with self.assertRaisesRegex(RuntimeError, "boom"):
				validate_purchase_deductibility(document)

	def test_validate_purchase_deductibility_accepts_invoice_override_and_ignores_invalid_rows(self):
		document = SimpleNamespace(
			fab_itx_invoice_deductibility_mode=PARTIALLY_DEDUCTIBLE_PERCENTAGE,
			fab_itx_invoice_deductible_percentage=60.0,
			fab_itx_invoice_deductible_amount=10.0,
			items=[
				SimpleNamespace(
					idx=1,
					fab_itx_deductibility_mode=PARTIALLY_DEDUCTIBLE_AMOUNT,
					fab_itx_deductible_amount=120.0,
					fab_itx_deductible_percentage=0.0,
					base_net_amount=100.0,
				)
			],
		)

		validate_purchase_deductibility(document)

		self.assertEqual(document.fab_itx_invoice_deductible_amount, 0)

	def test_get_result_deductibility_ratio_uses_invoice_override_amount(self):
		result = SimpleNamespace(
			fab_itx_invoice_deductibility_mode=PARTIALLY_DEDUCTIBLE_AMOUNT,
			fab_itx_invoice_deductible_percentage=0.0,
			fab_itx_invoice_deductible_amount=30.0,
			fab_itx_deductibility_mode=NON_DEDUCTIBLE,
			fab_itx_deductible_percentage=0.0,
			fab_itx_deductible_amount=0.0,
			base_net_amount=100.0,
		)

		self.assertEqual(get_result_deductibility_ratio(result, invoice_total_amount=120.0), 0.25)

	def test_validate_sales_invoice_yearly_close_syncs_forward_deferral(self):
		item = SimpleNamespace(
			idx=1,
			fab_itx_competence_start_date="2026-02-01",
			fab_itx_competence_end_date="2026-02-28",
			enable_deferred_revenue=0,
			service_start_date=None,
			service_end_date=None,
			service_stop_date=None,
		)
		document = SimpleNamespace(doctype="Sales Invoice", posting_date="2026-01-15", items=[item])

		validate_sales_invoice_yearly_close(document)

		self.assertEqual(item.enable_deferred_revenue, 1)
		self.assertEqual(str(item.service_start_date), "2026-02-01")
		self.assertEqual(str(item.service_end_date), "2026-02-28")
		self.assertEqual(str(item.service_stop_date), "2026-02-28")

	def test_build_competence_accounts_creates_sales_accrual_pairs(self):
		rows = build_competence_accounts(
			document_type="Sales Invoice",
			amount=100.0,
			profit_account="4110 - Sales - fab",
			balance_account="1315 - Accrued Revenue - fab",
			entry_kind="accrual",
			dimensions={"cost_center": "Main - fab"},
		)

		self.assertEqual(rows[0]["account"], "1315 - Accrued Revenue - fab")
		self.assertEqual(rows[0]["debit_in_account_currency"], 100.0)
		self.assertEqual(rows[1]["account"], "4110 - Sales - fab")
		self.assertEqual(rows[1]["credit_in_account_currency"], 100.0)
		self.assertEqual(rows[1]["cost_center"], "Main - fab")

	def test_full_deductibility_defaults_to_one(self):
		item = SimpleNamespace(
			fab_itx_deductibility_mode=FULLY_DEDUCTIBLE,
			fab_itx_deductible_percentage=0.0,
			fab_itx_deductible_amount=0.0,
			base_net_amount=80.0,
		)

		self.assertEqual(get_deductibility_ratio(item), 1.0)

	def test_validate_invoice_competence_year_defaults_to_invoice_year(self):
		document = SimpleNamespace(posting_date="2026-01-05", fab_itx_competence_year="")

		validate_invoice_competence_year(document)

		self.assertEqual(document.fab_itx_competence_year, "2026")

	def test_validate_invoice_competence_year_rejects_other_values(self):
		document = SimpleNamespace(posting_date="2026-01-05", fab_itx_competence_year="2024")

		with patch("fab_italy_tax.yearly_close.frappe.throw", side_effect=RuntimeError("boom")):
			with self.assertRaisesRegex(RuntimeError, "boom"):
				validate_invoice_competence_year(document)

	def test_get_allowed_competence_years_only_include_invoice_year_and_previous(self):
		document = SimpleNamespace(posting_date="2026-01-05")

		self.assertEqual(get_allowed_competence_years(document), ["2026", "2025"])

	def test_is_prior_year_competence_selected_detects_previous_year(self):
		document = SimpleNamespace(posting_date="2026-01-05", fab_itx_competence_year="2025")

		self.assertTrue(is_prior_year_competence_selected(document))

	def test_build_header_competence_adjustments_uses_full_invoice_amount(self):
		document = SimpleNamespace(
			doctype="Sales Invoice",
			company="fabricators",
			posting_date="2026-01-05",
			fab_itx_competence_year="2025",
			items=[
				SimpleNamespace(name="ROW-1", income_account="4120 - Service - fab", base_net_amount=80.0),
				SimpleNamespace(name="ROW-2", income_account="4120 - Service - fab", base_net_amount=20.0),
			],
		)

		with (
			patch("fab_italy_tax.yearly_close.frappe.get_doc", return_value=SimpleNamespace(name="fabricators")),
			patch("fab_italy_tax.yearly_close.get_competence_balance_account", return_value="1365 - Accrued Revenue - fab"),
			patch("fab_italy_tax.yearly_close.get_item_dimensions", return_value={}),
			patch(
				"fab_italy_tax.yearly_close.get_fiscal_year_for_date",
				return_value={"name": "2025", "year_end_date": "2025-12-31"},
			),
		):
			rows = build_header_competence_adjustments(document)

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["fiscal_year"], "2025")
		self.assertEqual(sum(row["amount"] for row in rows[0]["rows"]), 100.0)
