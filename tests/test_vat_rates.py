from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fab_italy_tax.vat_rates import (
	BARE_NATURA_EXEMPTION,
	STANDARD_VAT_RATES,
	TAX_EXEMPTION_REASONS,
	build_rate_key,
	build_template_taxes,
	build_template_title,
	exemption_reason_for,
)


def make_row(applies_to="Sales", rate=22.0, nature="", reverse_charge=0, description=""):
	return SimpleNamespace(
		applies_to=applies_to,
		rate=rate,
		nature=nature,
		reverse_charge=reverse_charge,
		description=description,
		enabled=1,
	)


class TestRateKey(unittest.TestCase):
	def test_positive_sales_rate(self):
		self.assertEqual(build_rate_key("Sales", 22.0, "", 0), "S-22")

	def test_zero_rated_with_nature(self):
		self.assertEqual(build_rate_key("Sales", 0.0, "N3.1", 0), "S-0-N3.1")

	def test_purchase_reverse_charge(self):
		self.assertEqual(build_rate_key("Purchase", 22.0, "N6.7", 1), "P-RC-22-N6.7")

	def test_keys_are_unique_across_the_matrix(self):
		keys = [
			build_rate_key(s["applies_to"], s["rate"], s.get("nature"), s.get("reverse_charge"))
			for s in STANDARD_VAT_RATES
		]
		self.assertEqual(len(keys), len(set(keys)))


class TestTemplateTitle(unittest.TestCase):
	def test_titles(self):
		self.assertEqual(build_template_title(make_row()), "IVA 22")
		self.assertEqual(build_template_title(make_row(rate=0.0, nature="N3.1")), "IVA 0 N3.1")
		self.assertEqual(
			build_template_title(make_row(applies_to="Purchase", reverse_charge=1)), "IVA RC 22"
		)


class TestTemplateTaxes(unittest.TestCase):
	def run_build(self, row, doctype):
		with patch("fab_italy_tax.vat_rates.frappe") as frappe:
			frappe.db.get_value.return_value = ("VAT debt", "VAT credit")
			return build_template_taxes(row, "FABRICATORS S.R.L.", doctype)

	def test_sales_row_hits_output_account(self):
		taxes = self.run_build(make_row(), "Sales Taxes and Charges Template")
		self.assertEqual(len(taxes), 1)
		self.assertEqual(taxes[0]["account_head"], "VAT debt")
		self.assertEqual(taxes[0]["rate"], 22.0)

	def test_purchase_row_hits_input_account(self):
		taxes = self.run_build(
			make_row(applies_to="Purchase"), "Purchase Taxes and Charges Template"
		)
		self.assertEqual(len(taxes), 1)
		self.assertEqual(taxes[0]["account_head"], "VAT credit")
		self.assertEqual(taxes[0]["add_deduct_tax"], "Add")

	def test_reverse_charge_books_both_sides_net_zero(self):
		taxes = self.run_build(
			make_row(applies_to="Purchase", reverse_charge=1),
			"Purchase Taxes and Charges Template",
		)
		self.assertEqual(len(taxes), 2)
		add = next(t for t in taxes if t["add_deduct_tax"] == "Add")
		deduct = next(t for t in taxes if t["add_deduct_tax"] == "Deduct")
		self.assertEqual(add["account_head"], "VAT credit")
		self.assertEqual(deduct["account_head"], "VAT debt")
		self.assertEqual(add["rate"], deduct["rate"])


class TestStandardMatrix(unittest.TestCase):
	def test_default_enabled_set_matches_odoo_usage(self):
		enabled = {
			build_rate_key(s["applies_to"], s["rate"], s.get("nature"), s.get("reverse_charge"))
			for s in STANDARD_VAT_RATES
			if s.get("enabled")
		}
		self.assertEqual(
			enabled,
			{
				"S-22",
				"S-0-N1",
				"S-0-N2.1",
				"S-0-N3.1",
				"S-0-N3.2",
				"P-22",
				"P-10",
				"P-4",
				"P-0-N2.2",
				"P-RC-22",
				"P-RC-22-N6.7",
				"P-RC-22-UE",
			},
		)

	def test_reverse_charge_rows_are_purchase_only(self):
		for spec in STANDARD_VAT_RATES:
			if spec.get("reverse_charge"):
				self.assertEqual(spec["applies_to"], "Purchase")


class TestExemptionReason(unittest.TestCase):
	def test_sub_code_reaches_the_xml(self):
		# the e-invoice template emits the value up to the first dash
		reason = exemption_reason_for("N2.1")
		self.assertEqual(reason.split("-")[0], "N2.1")

	def test_standalone_code_is_kept_whole(self):
		self.assertEqual(exemption_reason_for("N1"), "N1-Escluse ex art. 15")

	def test_bare_sub_coded_parents_are_never_generated(self):
		for nature in BARE_NATURA_EXEMPTION:
			self.assertIsNone(exemption_reason_for(nature))

	def test_unknown_nature_has_no_reason(self):
		self.assertIsNone(exemption_reason_for("UE"))
		self.assertIsNone(exemption_reason_for(""))

	def test_every_sales_nature_in_the_matrix_is_expressible(self):
		for spec in STANDARD_VAT_RATES:
			nature = spec.get("nature")
			if not nature or spec["applies_to"] != "Sales":
				continue
			self.assertEqual(exemption_reason_for(nature).split("-")[0], nature)

	def test_select_options_keep_the_codes_erpnext_shipped(self):
		# a row booked before the sub-codes existed must still pass Select validation
		from erpnext.regional.italy import tax_exemption_reasons

		self.assertLessEqual(set(tax_exemption_reasons), set(TAX_EXEMPTION_REASONS))
		self.assertLessEqual(set(BARE_NATURA_EXEMPTION.values()), set(tax_exemption_reasons))


if __name__ == "__main__":
	unittest.main()
