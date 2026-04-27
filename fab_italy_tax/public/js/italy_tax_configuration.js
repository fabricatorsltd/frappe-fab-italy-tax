frappe.ui.form.on("Italy Tax Configuration", {
	refresh(frm) {
		set_setup_intro(frm);

		if (frm.is_new() || !frm.doc.company) {
			return;
		}

		frm.add_custom_button(__("Provision VAT Setup"), async () => {
			await frappe.call({
				method: "fab_italy_tax.company_tax_settings.provision_tax_configuration_setup",
				args: { tax_configuration: frm.doc.name },
				freeze: true,
				freeze_message: __("Provisioning VAT setup..."),
			});
			await frm.reload_doc();
		}, __("Actions"));

		frm.add_custom_button(__("Generate VAT Periods"), async () => {
			const response = await frappe.call({
				method: "fab_italy_tax.vat_period_generation.generate_missing_vat_periods",
				args: { tax_configuration: frm.doc.name },
				freeze: true,
				freeze_message: __("Generating VAT periods..."),
			});
			if (response.message?.message) {
				frappe.show_alert({ message: response.message.message, indicator: "green" });
			}
			await frm.reload_doc();
			frappe.set_route("List", "VAT Period", { tax_configuration: frm.doc.name });
		}, __("Actions"));

		frm.add_custom_button(__("Open VAT Periods"), () => {
			frappe.set_route("List", "VAT Period", { tax_configuration: frm.doc.name });
		}, __("Actions"));
	},
});

function set_setup_intro(frm) {
	const missing = [];
	if (!frm.doc.first_managed_period_start_date) {
		missing.push(__("first managed period start date"));
	}
	if (!frm.doc.default_tax_payment_mode) {
		missing.push(__("default tax payment mode"));
	}
	if (!frm.doc.vat_output_account) {
		missing.push(__("VAT output account"));
	}
	if (!frm.doc.vat_input_account) {
		missing.push(__("VAT input account"));
	}
	if (!frm.doc.vat_payable_account) {
		missing.push(__("VAT payable account"));
	}
	if (!frm.doc.vat_credit_account) {
		missing.push(__("VAT credit account"));
	}
	if (frm.doc.vat_liquidation_cadence === "Quarterly" && !frm.doc.quarterly_interest_account) {
		missing.push(__("quarterly interest account"));
	}
	if (!frm.doc.carry_forward_account) {
		missing.push(__("carry forward account"));
	}

	if (!missing.length) {
		frm.set_intro(__("VAT setup is complete."), "green");
		return;
	}

	frm.set_intro(
		__("Missing setup: {0}. Use Provision VAT Setup to create the defaults.", [missing.join(", ")]),
		"orange"
	);
}
