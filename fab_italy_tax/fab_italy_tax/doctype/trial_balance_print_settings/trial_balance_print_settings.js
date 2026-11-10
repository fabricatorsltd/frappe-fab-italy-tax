frappe.ui.form.on("Trial Balance Print Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Print two-sided trial balance"), () =>
			frappe.set_route("two-sided-trial-balance")
		);
	},
});
