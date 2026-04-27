from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from frappe.exceptions import ValidationError

from fab_italy_tax.vat_period_generation import (
	generate_missing_vat_periods_for_configuration,
	generate_next_vat_period,
	sync_next_vat_period_credit,
)


def raise_validation_error(message):
	raise ValidationError(str(message))


def build_configuration(**overrides):
	defaults = {
		"name": "FAB-TAX-CONFIG",
		"company": "Fabricators",
		"enabled": 1,
		"vat_liquidation_cadence": "Monthly",
		"first_managed_period_start_date": "2026-01-01",
	}
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


def build_vat_period(**overrides):
	defaults = {
		"name": "VAT-PERIOD-2026-00001",
		"company": "Fabricators",
		"tax_configuration": "FAB-TAX-CONFIG",
		"vat_liquidation_cadence": "Monthly",
		"period_start_date": "2026-01-01",
		"period_end_date": "2026-01-31",
		"status": "Calculated",
		"final_credit_amount": 90.0,
	}
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


class TestVATPeriodGeneration(unittest.TestCase):
	def test_generate_missing_monthly_periods_creates_until_current_month(self):
		configuration = build_configuration()
		created_docs = []

		def get_doc_side_effect(*args, **kwargs):
			if len(args) == 2 and args[0] == "Italy Tax Configuration":
				return configuration
			payload = args[0]
			doc = SimpleNamespace(name=None, insert=Mock(side_effect=lambda ignore_permissions=True: None))

			def insert(ignore_permissions=True):
				doc.name = f"VAT-PERIOD-{payload['period_start_date']}"
				created_docs.append(payload.copy())

			doc.insert = Mock(side_effect=insert)
			return doc

		frappe_stub = SimpleNamespace(
			get_doc=Mock(side_effect=get_doc_side_effect),
			get_all=Mock(return_value=[]),
			db=SimpleNamespace(get_value=Mock(return_value=None)),
			throw=Mock(side_effect=raise_validation_error),
		)

		with (
			patch("fab_italy_tax.vat_period_generation.frappe", new=frappe_stub),
			patch("fab_italy_tax.vat_period_generation.nowdate", return_value="2026-03-10"),
			patch(
				"fab_italy_tax.vat_period_generation.get_fiscal_year",
				side_effect=lambda date, company=None, raise_on_missing=False: ("2026", "2026-01-01", "2026-12-31"),
			),
		):
			result = generate_missing_vat_periods_for_configuration("FAB-TAX-CONFIG")

		self.assertEqual(
			[payload["period_label"] for payload in created_docs],
			["01/2026", "02/2026", "03/2026"],
		)
		self.assertEqual(created_docs[0]["due_date"].isoformat(), "2026-02-16")
		self.assertEqual(created_docs[1]["due_date"].isoformat(), "2026-03-16")
		self.assertEqual(created_docs[2]["due_date"].isoformat(), "2026-04-16")
		self.assertEqual(result["created_periods"], ["VAT-PERIOD-2026-01-01", "VAT-PERIOD-2026-02-01", "VAT-PERIOD-2026-03-01"])

	def test_generate_next_quarterly_period_uses_august_due_date_and_existing_credit(self):
		configuration = build_configuration(vat_liquidation_cadence="Quarterly")
		current_period = build_vat_period(
			vat_liquidation_cadence="Quarterly",
			period_start_date="2026-01-01",
			period_end_date="2026-03-31",
			final_credit_amount=125.0,
		)
		created_payload = {}

		def get_doc_side_effect(*args, **kwargs):
			if len(args) == 2 and args[0] == "VAT Period":
				return current_period
			if len(args) == 2 and args[0] == "Italy Tax Configuration":
				return configuration

			payload = args[0]
			doc = SimpleNamespace(name="VAT-PERIOD-2026-00002")

			def insert(ignore_permissions=True):
				created_payload.update(payload)

			doc.insert = Mock(side_effect=insert)
			return doc

		def get_all_side_effect(doctype, **kwargs):
			if doctype == "VAT Period":
				return [{"final_credit_amount": 125.0}]
			return []

		frappe_stub = SimpleNamespace(
			get_doc=Mock(side_effect=get_doc_side_effect),
			get_all=Mock(side_effect=get_all_side_effect),
			db=SimpleNamespace(get_value=Mock(return_value=None)),
			throw=Mock(side_effect=raise_validation_error),
		)

		with patch("fab_italy_tax.vat_period_generation.frappe", new=frappe_stub), patch(
			"fab_italy_tax.vat_period_generation.get_fiscal_year",
			side_effect=lambda date, company=None, raise_on_missing=False: ("2026", "2026-01-01", "2026-12-31"),
		):
			result = generate_next_vat_period("VAT-PERIOD-2026-00001")

		self.assertTrue(result["created"])
		self.assertEqual(created_payload["period_start_date"].isoformat(), "2026-04-01")
		self.assertEqual(created_payload["period_end_date"].isoformat(), "2026-06-30")
		self.assertEqual(created_payload["due_date"].isoformat(), "2026-08-20")
		self.assertEqual(created_payload["previous_credit_brought_forward"], 125.0)
		self.assertEqual(created_payload["period_label"], "Q2 2026")

	def test_generate_missing_periods_requires_aligned_managed_start_date(self):
		configuration = build_configuration(
			vat_liquidation_cadence="Quarterly", first_managed_period_start_date="2026-02-01"
		)
		frappe_stub = SimpleNamespace(
			get_doc=Mock(return_value=configuration),
			throw=Mock(side_effect=raise_validation_error),
		)

		with (
			patch("fab_italy_tax.vat_period_generation.frappe", new=frappe_stub),
			self.assertRaisesRegex(ValidationError, "First Managed Period Start Date"),
		):
			generate_missing_vat_periods_for_configuration("FAB-TAX-CONFIG")

	def test_sync_next_vat_period_credit_updates_open_next_period_only(self):
		document = build_vat_period(final_credit_amount=77.5)
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				get_value=Mock(return_value="VAT-PERIOD-2026-00002"),
				set_value=Mock(),
			),
			get_cached_value=Mock(side_effect=lambda doctype, name, fieldname: "Open" if fieldname == "status" else 0.0),
		)

		with patch("fab_italy_tax.vat_period_generation.frappe", new=frappe_stub):
			sync_next_vat_period_credit(document)

		frappe_stub.db.set_value.assert_called_once_with(
			"VAT Period",
			"VAT-PERIOD-2026-00002",
			"previous_credit_brought_forward",
			77.5,
			update_modified=False,
		)
