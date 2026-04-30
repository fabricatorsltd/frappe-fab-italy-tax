from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fab_italy_tax.cashflow import (
	OPENING_BALANCE_EVENT_TYPE,
	apply_running_balance,
	build_party_cash_flow_row,
	convert_to_company_currency,
	get_company_cash_flow,
)


class TestCashFlow(unittest.TestCase):
	def test_convert_to_company_currency_uses_conversion_rate_for_foreign_documents(self):
		self.assertEqual(
			convert_to_company_currency(
				amount=36.2,
				document_currency="USD",
				company_currency="EUR",
				conversion_rate=0.85383,
			),
			30.91,
		)

	def test_build_party_cash_flow_row_marks_overdue_documents_on_start_date(self):
		row = build_party_cash_flow_row(
			document={
				"name": "PINV-0001",
				"supplier": "Atlassian Pty Ltd",
				"due_date": "2026-04-25",
				"outstanding_amount": 36.2,
				"currency": "USD",
				"conversion_rate": 0.85383,
			},
			company_currency="EUR",
			start_date="2026-04-28",
			include_overdue=True,
			event_type="Payable Due",
			reference_doctype="Purchase Invoice",
			party="Atlassian Pty Ltd",
			direction="Outflow",
		)

		self.assertEqual(str(row["event_date"]), "2026-04-28")
		self.assertEqual(row["status"], "Overdue")
		self.assertEqual(row["outflow_amount"], 30.91)
		self.assertEqual(row["source_detail"], "Original due date: 2026-04-25")

	def test_apply_running_balance_projects_balance_after_each_event(self):
		rows = apply_running_balance(
			[
				{
					"event_type": OPENING_BALANCE_EVENT_TYPE,
					"inflow_amount": 0.0,
					"outflow_amount": 0.0,
					"projected_balance": 0.0,
				},
				{"event_type": "Receivable Due", "inflow_amount": 100.0, "outflow_amount": 0.0},
				{"event_type": "Payable Due", "inflow_amount": 0.0, "outflow_amount": 35.0},
			],
			opening_balance=50.0,
		)

		self.assertEqual(rows[0]["projected_balance"], 50.0)
		self.assertEqual(rows[1]["projected_balance"], 150.0)
		self.assertEqual(rows[2]["projected_balance"], 115.0)

	def test_get_company_cash_flow_combines_opening_balance_and_events(self):
		frappe_stub = SimpleNamespace(db=SimpleNamespace(get_value=lambda *args, **kwargs: "EUR"))

		with (
			patch("fab_italy_tax.cashflow.frappe", new=frappe_stub),
			patch("fab_italy_tax.cashflow.get_liquid_account_names", return_value=["1110 - Cash - FAB"]),
			patch("fab_italy_tax.cashflow.get_opening_liquid_balance", return_value=200.0),
			patch(
				"fab_italy_tax.cashflow.get_receivable_cash_flow_rows",
				return_value=[
					{
						"event_date": "2026-04-30",
						"event_type": "Receivable Due",
						"inflow_amount": 122.0,
						"outflow_amount": 0.0,
						"currency": "EUR",
						"reference_doctype": "Sales Invoice",
						"reference_name": "ACC-SINV-2026-00001",
					}
				],
			),
			patch(
				"fab_italy_tax.cashflow.get_payable_cash_flow_rows",
				return_value=[
					{
						"event_date": "2026-04-30",
						"event_type": "Payable Due",
						"inflow_amount": 0.0,
						"outflow_amount": 50.0,
						"currency": "EUR",
						"reference_doctype": "Purchase Invoice",
						"reference_name": "ACC-PINV-2026-00001",
					}
				],
			),
			patch("fab_italy_tax.cashflow.get_tax_calendar_cash_flow_rows", return_value=[]),
			patch("fab_italy_tax.cashflow.get_employee_cost_cash_flow_rows", return_value=[]),
		):
			rows = get_company_cash_flow(
				company="Fabricators",
				from_date="2026-04-28",
				to_date="2026-05-31",
			)

		self.assertEqual(rows[0]["event_type"], OPENING_BALANCE_EVENT_TYPE)
		self.assertEqual(rows[0]["projected_balance"], 200.0)
		self.assertEqual(rows[1]["projected_balance"], 322.0)
		self.assertEqual(rows[2]["projected_balance"], 272.0)
