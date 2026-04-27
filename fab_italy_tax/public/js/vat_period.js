frappe.ui.form.on("VAT Period", {
	refresh(frm) {
		set_cash_flow_intro(frm);

		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(__("Recalculate VAT Totals"), async () => {
			await frm.call("calculate_amounts");
			await frm.reload_doc();
		}, __("Actions"));

		if (!["Posted", "Closed", "Cancelled"].includes(frm.doc.status) && !frm.doc.linked_settlement_entry) {
			frm.add_custom_button(__("Post Settlement Entry"), async () => {
				await frm.call("post_settlement_entry");
				await frm.reload_doc();
			}, __("Actions"));
		}

		if (frm.doc.tax_configuration && frm.doc.status !== "Cancelled") {
			frm.add_custom_button(__("Generate Next VAT Period"), async () => {
				const response = await frm.call("generate_next_period");
				if (response.message?.period_name) {
					frappe.set_route("Form", "VAT Period", response.message.period_name);
				}
			}, __("Actions"));
		}

		add_tax_calendar_button(frm);
	},
});

async function add_tax_calendar_button(frm) {
	const response = await frappe.call({
		method: "fab_italy_tax.tax_calendar.get_vat_payment_calendar_event",
		args: { vat_period: frm.doc.name },
		quiet: true,
	});
	const event = response.message;
	if (!event?.name) {
		return;
	}

	frm.add_custom_button(__("Open Tax Calendar Event"), () => {
		frappe.set_route("Form", "Tax Calendar Event", event.name);
	}, __("Actions"));
}

function set_cash_flow_intro(frm) {
	const payable = flt(frm.doc.final_payable_amount);
	const credit = flt(frm.doc.final_credit_amount);
	const dueDate = frm.doc.due_date ? frappe.datetime.str_to_user(frm.doc.due_date) : __("the due date");

	if (payable > 0) {
		const statusLabel = frm.doc.status === "Closed" ? __("settled") : __("scheduled");
		frm.set_intro(
			__("Cash flow: VAT payment of {0} is {1} for {2}.", [
				format_currency(payable),
				statusLabel,
				dueDate,
			]),
			frm.doc.status === "Closed" ? "green" : "orange"
		);
		return;
	}

	if (credit > 0) {
		frm.set_intro(
			__("Cash flow: VAT credit of {0} will be carried forward.", [format_currency(credit)]),
			"blue"
		);
		return;
	}

	frm.set_intro(__("Cash flow: no VAT payment is currently due for this period."), "green");
}
