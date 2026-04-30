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

		frm.add_custom_button(__("Review Italy Tax Onboarding"), async () => {
			await open_tax_onboarding_dialog(frm);
		}, __("Actions"));
	},
});

function escape_onboarding_html(value) {
	return String(value || "")
		.replaceAll("&", "&amp;")
		.replaceAll("<", "&lt;")
		.replaceAll(">", "&gt;")
		.replaceAll('"', "&quot;")
		.replaceAll("'", "&#39;");
}

function get_onboarding_badge(step) {
	if (step.status === "done") {
		return { label: __("Done"), color: "green" };
	}
	if (step.status === "pending") {
		return { label: __("Required"), color: "orange" };
	}
	return { label: __("Review"), color: "blue" };
}

async function open_tax_onboarding_dialog(frm) {
	const response = await frappe.call({
		method: "fab_italy_tax.company_tax_settings.get_company_tax_onboarding",
		args: { company: frm.doc.company },
		freeze: false,
	});
	const onboarding = response.message;
	if (!onboarding) {
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Italy Tax Onboarding"),
		fields: [{ fieldtype: "HTML", fieldname: "steps_html" }],
		primary_action_label: __("Close"),
		primary_action() {
			dialog.hide();
		},
	});

	const html = onboarding.steps
		.map((step, index) => {
			const badge = get_onboarding_badge(step);
			return `
				<div style="border: 1px solid var(--border-color); border-radius: 8px; padding: 12px; margin-bottom: 12px;">
					<div style="display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 8px;">
						<div style="font-weight: 600;">${escape_onboarding_html(step.title)}</div>
						<span class="indicator-pill ${badge.color}">${escape_onboarding_html(badge.label)}</span>
					</div>
					<div style="margin-bottom: 10px; color: var(--text-muted);">${escape_onboarding_html(step.description)}</div>
					${
						step.action_label
							? `<button class="btn btn-sm btn-default itx-onboarding-action" data-step-index="${index}">${escape_onboarding_html(step.action_label)}</button>`
							: ""
					}
				</div>
			`;
		})
		.join("");

	dialog.fields_dict.steps_html.$wrapper.html(html);
	dialog.$wrapper.on("click", ".itx-onboarding-action", (event) => {
		const index = Number(event.currentTarget.dataset.stepIndex);
		const step = onboarding.steps[index];
		if (!step?.route?.length) {
			return;
		}
		dialog.hide();
		if (step.route_options) {
			frappe.route_options = step.route_options;
		}
		frappe.set_route(...step.route);
	});
	dialog.show();
}

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
