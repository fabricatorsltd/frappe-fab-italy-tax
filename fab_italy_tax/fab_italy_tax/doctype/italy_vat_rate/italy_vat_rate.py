from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class ItalyVATRate(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		applies_to: DF.Literal["Sales", "Purchase"]
		description: DF.Data | None
		enabled: DF.Check
		nature: DF.Data | None
		rate: DF.Float
		rate_key: DF.Data | None
		reverse_charge: DF.Check
		seeded: DF.Check
	# end: auto-generated types

	def before_naming(self):
		from fab_italy_tax.vat_rates import build_rate_key

		self.nature = (self.nature or "").strip().upper()
		self.rate_key = build_rate_key(self.applies_to, self.rate, self.nature, self.reverse_charge)

	def validate(self):
		self.before_naming()
		if self.reverse_charge and self.applies_to != "Purchase":
			frappe.throw(_("Reverse charge only applies to purchase rates."))

	def on_update(self):
		from fab_italy_tax.vat_rates import sync_vat_rate_templates_for_rate

		sync_vat_rate_templates_for_rate(self)
