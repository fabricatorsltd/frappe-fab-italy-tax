from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fab_italy_tax.invoice_naming import (
	DELIVERY_NOTE_RETURN_SERIES,
	DELIVERY_NOTE_SERIES,
	PURCHASE_CREDIT_NOTE_SERIES,
	PURCHASE_INVOICE_SERIES,
	QUOTATION_SERIES,
	SALES_CREDIT_NOTE_SERIES,
	SALES_INVOICE_SERIES,
	SALES_ORDER_SERIES,
	apply_italy_invoice_naming_series,
	sync_italy_invoice_naming_series,
)


def build_document(**overrides):
	defaults = {
		"doctype": "Sales Invoice",
		"company": "fabricators",
		"is_return": 0,
		"naming_series": "",
		"name": "",
		"__islocal": 1,
	}
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


class DocumentWithoutReturnFlag(SimpleNamespace):
	def __getattr__(self, name):
		if name == "is_return":
			raise AssertionError("is_return read on a doctype without a return series")
		raise AttributeError(name)


def build_document_without_return_flag(**overrides):
	document = build_document(**overrides)
	values = vars(document)
	values.pop("is_return", None)
	return DocumentWithoutReturnFlag(**values)


class TestInvoiceNaming(unittest.TestCase):
	def test_sets_sales_invoice_series(self):
		document = build_document(doctype="Sales Invoice")
		frappe_stub = SimpleNamespace(get_cached_value=Mock(side_effect=["Italy"]))

		with patch("fab_italy_tax.invoice_naming.frappe", new=frappe_stub):
			apply_italy_invoice_naming_series(document)

		self.assertEqual(document.naming_series, SALES_INVOICE_SERIES)

	def test_sets_sales_credit_note_series(self):
		document = build_document(doctype="Sales Invoice", is_return=1)
		frappe_stub = SimpleNamespace(get_cached_value=Mock(side_effect=["Italy"]))

		with patch("fab_italy_tax.invoice_naming.frappe", new=frappe_stub):
			apply_italy_invoice_naming_series(document)

		self.assertEqual(document.naming_series, SALES_CREDIT_NOTE_SERIES)

	def test_sets_purchase_series(self):
		document = build_document(doctype="Purchase Invoice")
		frappe_stub = SimpleNamespace(get_cached_value=Mock(side_effect=["Italy"]))

		with patch("fab_italy_tax.invoice_naming.frappe", new=frappe_stub):
			apply_italy_invoice_naming_series(document)

		self.assertEqual(document.naming_series, PURCHASE_INVOICE_SERIES)

	def test_sets_purchase_credit_note_series(self):
		document = build_document(doctype="Purchase Invoice", is_return=1)
		frappe_stub = SimpleNamespace(get_cached_value=Mock(side_effect=["Italy"]))

		with patch("fab_italy_tax.invoice_naming.frappe", new=frappe_stub):
			apply_italy_invoice_naming_series(document)

		self.assertEqual(document.naming_series, PURCHASE_CREDIT_NOTE_SERIES)

	def test_sets_quotation_series(self):
		document = build_document_without_return_flag(doctype="Quotation")
		frappe_stub = SimpleNamespace(get_cached_value=Mock(side_effect=["Italy"]))

		with patch("fab_italy_tax.invoice_naming.frappe", new=frappe_stub):
			apply_italy_invoice_naming_series(document)

		self.assertEqual(document.naming_series, QUOTATION_SERIES)

	def test_sets_sales_order_series(self):
		document = build_document_without_return_flag(doctype="Sales Order")
		frappe_stub = SimpleNamespace(get_cached_value=Mock(side_effect=["Italy"]))

		with patch("fab_italy_tax.invoice_naming.frappe", new=frappe_stub):
			apply_italy_invoice_naming_series(document)

		self.assertEqual(document.naming_series, SALES_ORDER_SERIES)

	def test_sets_delivery_note_series(self):
		document = build_document(doctype="Delivery Note")
		frappe_stub = SimpleNamespace(get_cached_value=Mock(side_effect=["Italy"]))

		with patch("fab_italy_tax.invoice_naming.frappe", new=frappe_stub):
			apply_italy_invoice_naming_series(document)

		self.assertEqual(document.naming_series, DELIVERY_NOTE_SERIES)

	def test_sets_delivery_note_return_series(self):
		document = build_document(doctype="Delivery Note", is_return=1)
		frappe_stub = SimpleNamespace(get_cached_value=Mock(side_effect=["Italy"]))

		with patch("fab_italy_tax.invoice_naming.frappe", new=frappe_stub):
			apply_italy_invoice_naming_series(document)

		self.assertEqual(document.naming_series, DELIVERY_NOTE_RETURN_SERIES)

	def test_does_not_change_persisted_document(self):
		document = build_document(name="FATT/2026/00001", __islocal=0, naming_series="SINV/.YY./")
		frappe_stub = SimpleNamespace(get_cached_value=Mock(side_effect=["Italy"]))

		with patch("fab_italy_tax.invoice_naming.frappe", new=frappe_stub):
			apply_italy_invoice_naming_series(document)

		self.assertEqual(document.naming_series, "SINV/.YY./")

	def test_sync_updates_property_setters(self):
		db_stub = SimpleNamespace(
			get_value=Mock(
				side_effect=[
					"sales-options",
					"SINV/.YY./\nNCINV/.YY./",
					"sales-default",
					"SINV/.YY./",
					"purchase-options",
					"PINV/.YY./\nPINVRE/.YY./",
					"purchase-default",
					"PINV/.YY./",
					"quotation-options",
					"SAL-QTN-.YYYY.-",
					"quotation-default",
					"SAL-QTN-.YYYY.-",
					"sales-order-options",
					"SAL-ORD-.YYYY.-",
					"sales-order-default",
					"SAL-ORD-.YYYY.-",
					"delivery-note-options",
					"MAT-DN-.YYYY.-\nMAT-DN-RET-.YYYY.-",
					"delivery-note-default",
					"MAT-DN-.YYYY.-",
				]
			),
			set_value=Mock(),
		)
		frappe_stub = SimpleNamespace(db=db_stub, make_property_setter=Mock())

		with patch("fab_italy_tax.invoice_naming.frappe", new=frappe_stub):
			sync_italy_invoice_naming_series()

		db_stub.set_value.assert_any_call(
			"Property Setter",
			"sales-options",
			"value",
			f"{SALES_INVOICE_SERIES}\n{SALES_CREDIT_NOTE_SERIES}",
			update_modified=False,
		)
		db_stub.set_value.assert_any_call(
			"Property Setter",
			"sales-default",
			"value",
			SALES_INVOICE_SERIES,
			update_modified=False,
		)
		db_stub.set_value.assert_any_call(
			"Property Setter",
			"purchase-options",
			"value",
			f"{PURCHASE_INVOICE_SERIES}\n{PURCHASE_CREDIT_NOTE_SERIES}",
			update_modified=False,
		)
		db_stub.set_value.assert_any_call(
			"Property Setter",
			"purchase-default",
			"value",
			PURCHASE_INVOICE_SERIES,
			update_modified=False,
		)
		db_stub.set_value.assert_any_call(
			"Property Setter",
			"quotation-options",
			"value",
			QUOTATION_SERIES,
			update_modified=False,
		)
		db_stub.set_value.assert_any_call(
			"Property Setter",
			"quotation-default",
			"value",
			QUOTATION_SERIES,
			update_modified=False,
		)
		db_stub.set_value.assert_any_call(
			"Property Setter",
			"sales-order-options",
			"value",
			SALES_ORDER_SERIES,
			update_modified=False,
		)
		db_stub.set_value.assert_any_call(
			"Property Setter",
			"sales-order-default",
			"value",
			SALES_ORDER_SERIES,
			update_modified=False,
		)
		db_stub.set_value.assert_any_call(
			"Property Setter",
			"delivery-note-options",
			"value",
			f"{DELIVERY_NOTE_SERIES}\n{DELIVERY_NOTE_RETURN_SERIES}",
			update_modified=False,
		)
		db_stub.set_value.assert_any_call(
			"Property Setter",
			"delivery-note-default",
			"value",
			DELIVERY_NOTE_SERIES,
			update_modified=False,
		)
