from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.model.document import Document


class TrialBalancePrintSettings(Document):
	def validate(self):
		if self.accent_color and not re.fullmatch(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?", self.accent_color):
			frappe.throw(_("Accent Color must be a hex color such as #6f8aa0."))
		if self.font_family and re.search(r"[;{}<>]", self.font_family):
			frappe.throw(_("Font Family must be a plain CSS font family list."))
		if (self.group_level or 0) < 0:
			frappe.throw(_("Group Level cannot be negative."))
