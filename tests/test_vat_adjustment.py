from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from frappe.exceptions import ValidationError

from fab_italy_tax.fab_italy_tax.doctype.vat_adjustment.vat_adjustment import (
	enforce_vat_adjustment_append_only,
	prevent_vat_adjustment_deletion,
	validate_vat_adjustment,
)


def raise_validation_error(message):
	raise ValidationError(str(message))


def build_document(**overrides):
	defaults = {
		"company": "Fabricators",
		"vat_period": "VAT-PERIOD-2026-00001",
		"adjustment_type": "Settlement Correction",
		"direction": "Increase Payable",
		"amount": 120.0,
		"reason": "Manual reconciliation difference",
		"reference_doctype": "",
		"reference_name": "",
		"notes": "",
	}
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


class TestVATAdjustment(unittest.TestCase):
	def test_valid_adjustment_passes(self):
		document = build_document()

		def get_cached_value_side_effect(doctype, name, fieldname):
			values = {
				("VAT Period", "VAT-PERIOD-2026-00001", "company"): "Fabricators",
				("VAT Period", "VAT-PERIOD-2026-00001", "status"): "Draft",
				("VAT Period", "VAT-PERIOD-2026-00001", "vat_liquidation_cadence"): "Quarterly",
			}
			return values.get((doctype, name, fieldname))

		frappe_stub = SimpleNamespace(
			throw=Mock(side_effect=raise_validation_error),
			db=SimpleNamespace(exists=Mock(side_effect=lambda doctype, name=None: True)),
			get_cached_value=Mock(side_effect=get_cached_value_side_effect),
		)

		with patch("fab_italy_tax.fab_italy_tax.doctype.vat_adjustment.vat_adjustment.frappe", new=frappe_stub):
			validate_vat_adjustment(document)

	def test_amount_must_be_positive(self):
		document = build_document(amount=0)

		frappe_stub = SimpleNamespace(throw=Mock(side_effect=raise_validation_error))

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_adjustment.vat_adjustment.frappe",
				new=frappe_stub,
			),
			self.assertRaisesRegex(ValidationError, "greater than zero"),
		):
			validate_vat_adjustment(document)

	def test_company_must_match_vat_period(self):
		document = build_document()

		def get_cached_value_side_effect(doctype, name, fieldname):
			values = {
				("VAT Period", "VAT-PERIOD-2026-00001", "company"): "Other Company",
				("VAT Period", "VAT-PERIOD-2026-00001", "status"): "Draft",
				("VAT Period", "VAT-PERIOD-2026-00001", "vat_liquidation_cadence"): "Monthly",
			}
			return values.get((doctype, name, fieldname))

		frappe_stub = SimpleNamespace(
			throw=Mock(side_effect=raise_validation_error),
			db=SimpleNamespace(exists=Mock(side_effect=lambda doctype, name=None: True)),
			get_cached_value=Mock(side_effect=get_cached_value_side_effect),
		)

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_adjustment.vat_adjustment.frappe",
				new=frappe_stub,
			),
			self.assertRaisesRegex(ValidationError, "company must match"),
		):
			validate_vat_adjustment(document)

	def test_locked_vat_period_rejects_new_adjustments(self):
		document = build_document()

		def get_cached_value_side_effect(doctype, name, fieldname):
			values = {
				("VAT Period", "VAT-PERIOD-2026-00001", "company"): "Fabricators",
				("VAT Period", "VAT-PERIOD-2026-00001", "status"): "Posted",
				("VAT Period", "VAT-PERIOD-2026-00001", "vat_liquidation_cadence"): "Quarterly",
			}
			return values.get((doctype, name, fieldname))

		frappe_stub = SimpleNamespace(
			throw=Mock(side_effect=raise_validation_error),
			db=SimpleNamespace(exists=Mock(side_effect=lambda doctype, name=None: True)),
			get_cached_value=Mock(side_effect=get_cached_value_side_effect),
		)

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_adjustment.vat_adjustment.frappe",
				new=frappe_stub,
			),
			self.assertRaisesRegex(ValidationError, "Posted, Closed, or Cancelled"),
		):
			validate_vat_adjustment(document)

	def test_quarterly_interest_requires_quarterly_period_and_increase_payable(self):
		document = build_document(adjustment_type="Quarterly Interest", direction="Decrease Payable")

		def get_cached_value_side_effect(doctype, name, fieldname):
			values = {
				("VAT Period", "VAT-PERIOD-2026-00001", "company"): "Fabricators",
				("VAT Period", "VAT-PERIOD-2026-00001", "status"): "Draft",
				("VAT Period", "VAT-PERIOD-2026-00001", "vat_liquidation_cadence"): "Quarterly",
			}
			return values.get((doctype, name, fieldname))

		frappe_stub = SimpleNamespace(
			throw=Mock(side_effect=raise_validation_error),
			db=SimpleNamespace(exists=Mock(side_effect=lambda doctype, name=None: True)),
			get_cached_value=Mock(side_effect=get_cached_value_side_effect),
		)

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_adjustment.vat_adjustment.frappe",
				new=frappe_stub,
			),
			self.assertRaisesRegex(ValidationError, "Increase Payable"),
		):
			validate_vat_adjustment(document)

	def test_reference_pair_must_exist(self):
		document = build_document(reference_doctype="Sales Invoice", reference_name="ACC-SINV-2026-00001")

		def exists_side_effect(doctype, name=None):
			if doctype == "VAT Period":
				return True
			if doctype == "DocType":
				return True
			if doctype == "Sales Invoice":
				return False
			return True

		def get_cached_value_side_effect(doctype, name, fieldname):
			values = {
				("VAT Period", "VAT-PERIOD-2026-00001", "company"): "Fabricators",
				("VAT Period", "VAT-PERIOD-2026-00001", "status"): "Draft",
				("VAT Period", "VAT-PERIOD-2026-00001", "vat_liquidation_cadence"): "Quarterly",
			}
			return values.get((doctype, name, fieldname))

		frappe_stub = SimpleNamespace(
			throw=Mock(side_effect=raise_validation_error),
			db=SimpleNamespace(exists=Mock(side_effect=exists_side_effect)),
			get_cached_value=Mock(side_effect=get_cached_value_side_effect),
		)

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_adjustment.vat_adjustment.frappe",
				new=frappe_stub,
			),
			self.assertRaisesRegex(ValidationError, "Reference Name does not exist"),
		):
			validate_vat_adjustment(document)

	def test_adjustment_records_are_append_only(self):
		document = build_document()
		document.is_new = lambda: False
		document.get_doc_before_save = lambda: SimpleNamespace(name="VAT-ADJ-2026-00001")

		frappe_stub = SimpleNamespace(throw=Mock(side_effect=raise_validation_error))

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_adjustment.vat_adjustment.frappe",
				new=frappe_stub,
			),
			self.assertRaisesRegex(ValidationError, "append-only"),
		):
			enforce_vat_adjustment_append_only(document)

	def test_adjustment_records_cannot_be_deleted(self):
		frappe_stub = SimpleNamespace(throw=Mock(side_effect=raise_validation_error))

		with (
			patch(
				"fab_italy_tax.fab_italy_tax.doctype.vat_adjustment.vat_adjustment.frappe",
				new=frappe_stub,
			),
			self.assertRaisesRegex(ValidationError, "reversing adjustment"),
		):
			prevent_vat_adjustment_deletion()
