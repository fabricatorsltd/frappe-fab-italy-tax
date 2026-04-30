from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from frappe.exceptions import ValidationError

from fab_italy_tax.labor_costs import (
	build_actual_monthly_totals,
	ensure_employee_cost_cash_planning_enabled,
	exclude_submitted_journal_entry_rows,
	get_submitted_journal_entry_months,
	get_employee_cost_cash_planning,
)


def raise_validation_error(message):
	raise ValidationError(str(message))


class TestLaborCosts(unittest.TestCase):
	def test_build_actual_monthly_totals_aggregates_employee_cost_rows(self):
		totals = build_actual_monthly_totals(
			[
				{
					"cost_month": "2025-12-01",
					"employee_identifier": "EMP-001",
					"source_type": "Jet HR",
					"gross_monthly_amount": 1000,
					"employer_contribution_amount": 300,
					"inail_amount": 10,
					"tfr_accrual_amount": 74.1,
					"total_company_cost": 1384.1,
				},
				{
					"cost_month": "2025-12-15",
					"employee_identifier": "EMP-002",
					"source_type": "Jet HR",
					"gross_monthly_amount": 500,
					"employer_contribution_amount": 150,
					"inail_amount": 5,
					"tfr_accrual_amount": 37.05,
					"total_company_cost": 692.05,
				},
			]
		)

		self.assertEqual(totals["2025-12-01"]["gross_monthly_amount"], 1500.0)
		self.assertEqual(totals["2025-12-01"]["employer_contribution_amount"], 450.0)
		self.assertEqual(totals["2025-12-01"]["inail_amount"], 15.0)
		self.assertAlmostEqual(totals["2025-12-01"]["tfr_accrual_amount"], 111.15)
		self.assertAlmostEqual(totals["2025-12-01"]["total_company_cost"], 2076.15)
		self.assertEqual(totals["2025-12-01"]["source_types"], {"Jet HR"})
		self.assertEqual(totals["2025-12-01"]["employees"], {"EMP-001", "EMP-002"})

	def test_ensure_employee_cost_cash_planning_enabled_requires_matching_mode(self):
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				get_value=lambda *args, **kwargs: {
					"fab_itx_include_employee_cost_in_cash_planning": 1,
					"fab_itx_employee_cost_source_mode": "Accounting Entries",
				}
			),
			throw=raise_validation_error,
		)

		with (
			patch("fab_italy_tax.labor_costs.frappe", new=frappe_stub),
			self.assertRaisesRegex(ValidationError, "Employee Cost Source Mode"),
		):
			ensure_employee_cost_cash_planning_enabled("Fabricators")

	def test_get_employee_cost_cash_planning_includes_estimated_future_months(self):
		history_rows = [
			{
				"cost_month": "2025-12-01",
				"employee_identifier": "EMP-001",
				"source_type": "Jet HR",
				"gross_monthly_amount": 1000,
				"employer_contribution_amount": 300,
				"inail_amount": 10,
				"tfr_accrual_amount": 74.1,
				"total_company_cost": 1384.1,
			}
		]
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(get_value=lambda *args, **kwargs: "EUR"),
			get_all=lambda *args, **kwargs: history_rows,
		)

		with (
			patch("fab_italy_tax.labor_costs.frappe", new=frappe_stub),
			patch("fab_italy_tax.labor_costs.ensure_employee_cost_cash_planning_enabled"),
			patch("fab_italy_tax.labor_costs.ensure_employee_cost_entry_support"),
			patch(
				"fab_italy_tax.labor_costs.summarize_trailing_history",
				return_value={
					"month_count": 1,
					"average_monthly_headcount": 1.0,
					"average_monthly_gross_monthly_amount": 1000.0,
					"average_monthly_employer_contribution_amount": 300.0,
					"average_monthly_employer_insurance_amount": 10.0,
					"average_monthly_tfr_accrual_amount": 74.1,
					"average_monthly_total_company_cost": 1384.1,
				},
			),
		):
			rows = get_employee_cost_cash_planning(
				company="Fabricators",
				from_month="2025-12-01",
				to_month="2026-01-01",
			)

		self.assertEqual(len(rows), 2)
		self.assertEqual(rows[0]["planning_type"], "Actual")
		self.assertEqual(rows[0]["total_company_cost"], 1384.1)
		self.assertEqual(rows[1]["planning_type"], "Estimated")
		self.assertEqual(rows[1]["total_company_cost"], 1384.1)

	def test_exclude_submitted_journal_entry_rows_skips_posted_entries(self):
		frappe_stub = SimpleNamespace(
			get_all=lambda doctype, **kwargs: ["ACC-JV-2026-00001"] if doctype == "Journal Entry" else []
		)

		with patch("fab_italy_tax.labor_costs.frappe", new=frappe_stub):
			rows = exclude_submitted_journal_entry_rows(
				[
					{"name": "ROW-1", "accrual_journal_entry": "ACC-JV-2026-00001"},
					{"name": "ROW-2", "accrual_journal_entry": ""},
				]
			)

		self.assertEqual(rows, [{"name": "ROW-2", "accrual_journal_entry": ""}])

	def test_get_submitted_journal_entry_months_returns_posted_months(self):
		frappe_stub = SimpleNamespace(
			get_all=lambda doctype, **kwargs: ["ACC-JV-2026-00001"] if doctype == "Journal Entry" else []
		)

		with patch("fab_italy_tax.labor_costs.frappe", new=frappe_stub):
			months = get_submitted_journal_entry_months(
				[
					{"cost_month": "2025-12-15", "accrual_journal_entry": "ACC-JV-2026-00001"},
					{"cost_month": "2026-01-01", "accrual_journal_entry": ""},
				]
			)

		self.assertEqual(months, {"2025-12-01"})

	def test_get_employee_cost_cash_planning_skips_posted_months_without_estimating_them(self):
		history_rows = [
			{
				"cost_month": "2025-12-01",
				"employee_identifier": "EMP-001",
				"source_type": "Jet HR",
				"accrual_journal_entry": "ACC-JV-2026-00001",
				"gross_monthly_amount": 1000,
				"employer_contribution_amount": 300,
				"inail_amount": 10,
				"tfr_accrual_amount": 74.1,
				"total_company_cost": 1384.1,
			}
		]
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(get_value=lambda *args, **kwargs: "EUR"),
			get_all=lambda doctype, **kwargs: ["ACC-JV-2026-00001"] if doctype == "Journal Entry" else history_rows,
		)

		with (
			patch("fab_italy_tax.labor_costs.frappe", new=frappe_stub),
			patch("fab_italy_tax.labor_costs.ensure_employee_cost_cash_planning_enabled"),
			patch("fab_italy_tax.labor_costs.ensure_employee_cost_entry_support"),
			patch(
				"fab_italy_tax.labor_costs.summarize_trailing_history",
				return_value={
					"month_count": 1,
					"average_monthly_headcount": 1.0,
					"average_monthly_gross_monthly_amount": 1000.0,
					"average_monthly_employer_contribution_amount": 300.0,
					"average_monthly_employer_insurance_amount": 10.0,
					"average_monthly_tfr_accrual_amount": 74.1,
					"average_monthly_total_company_cost": 1384.1,
				},
			),
		):
			rows = get_employee_cost_cash_planning(
				company="Fabricators",
				from_month="2025-12-01",
				to_month="2026-01-01",
				exclude_posted_entries=True,
			)

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["planning_month"], "2026-01-01")
		self.assertEqual(rows[0]["planning_type"], "Estimated")
