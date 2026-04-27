from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fab_italy_tax.tax_calendar import sync_vat_period_tax_calendar_event


def build_vat_period(**overrides):
	defaults = {
		"name": "VAT-PERIOD-2026-00001",
		"company": "Fabricators",
		"tax_configuration": "Fabricators",
		"status": "Calculated",
		"period_label": "Q1 2026",
		"due_date": "2026-05-16",
		"period_end_date": "2026-03-31",
		"final_payable_amount": 110.0,
		"final_credit_amount": 0.0,
		"linked_settlement_entry": "ACC-JV-2026-00001",
	}
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


class TestTaxCalendar(unittest.TestCase):
	def test_sync_creates_tax_calendar_event_for_payable_vat(self):
		document = build_vat_period()
		event = SimpleNamespace(insert=Mock())
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(get_value=Mock(return_value=None)),
			get_cached_value=Mock(return_value="F24 Tax Payment"),
			new_doc=Mock(return_value=event),
		)

		with (
			patch("fab_italy_tax.tax_calendar.frappe", new=frappe_stub),
			patch("fab_italy_tax.tax_calendar.nowdate", return_value="2026-05-01"),
		):
			sync_vat_period_tax_calendar_event(document)

		self.assertEqual(event.event_type, "VAT Payment")
		self.assertEqual(event.status, "Planned")
		self.assertEqual(event.amount, 110.0)
		self.assertEqual(event.payment_mode, "F24 Tax Payment")
		event.insert.assert_called_once_with(ignore_permissions=True)

	def test_sync_marks_existing_event_settled_when_period_is_closed(self):
		document = build_vat_period(status="Closed")
		event = SimpleNamespace(save=Mock())
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(get_value=Mock(return_value="TAX-EVENT-2026-00001")),
			get_cached_value=Mock(return_value="F24 Tax Payment"),
			get_doc=Mock(return_value=event),
		)

		with (
			patch("fab_italy_tax.tax_calendar.frappe", new=frappe_stub),
			patch("fab_italy_tax.tax_calendar.nowdate", return_value="2026-05-20"),
		):
			sync_vat_period_tax_calendar_event(document)

		self.assertEqual(event.status, "Settled")
		event.save.assert_called_once_with(ignore_permissions=True)

	def test_sync_cancels_existing_event_when_no_payment_is_due(self):
		document = build_vat_period(final_payable_amount=0.0, final_credit_amount=80.0)
		event = SimpleNamespace(save=Mock())
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(get_value=Mock(return_value="TAX-EVENT-2026-00001")),
			get_cached_value=Mock(return_value="F24 Tax Payment"),
			get_doc=Mock(return_value=event),
		)

		with patch("fab_italy_tax.tax_calendar.frappe", new=frappe_stub):
			sync_vat_period_tax_calendar_event(document)

		self.assertEqual(event.status, "Cancelled")
		self.assertEqual(event.amount, 0.0)
		event.save.assert_called_once_with(ignore_permissions=True)
