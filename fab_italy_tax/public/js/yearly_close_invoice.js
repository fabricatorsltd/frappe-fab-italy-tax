function get_competence_year_options(frm) {
	const postingDate = frm.doc.posting_date || frappe.datetime.get_today();
	const invoiceYear = frappe.datetime.str_to_obj(postingDate).getFullYear();
	return [String(invoiceYear), String(invoiceYear - 1)];
}

function refresh_competence_year_field(frm) {
	const options = get_competence_year_options(frm);
	frm.set_df_property("fab_itx_competence_year", "options", options.join("\n"));
	if (
		frm.is_new() &&
		(!frm.doc.fab_itx_competence_year || !options.includes(String(frm.doc.fab_itx_competence_year)))
	) {
		frm.set_value("fab_itx_competence_year", options[0]);
	}
}

function should_show_competence_intro(frm) {
	// competence back to the prior year is a start-of-year concern (an invoice
	// booked now for last year's cost): pointless mid year. Show it only in the
	// first quarter, or when this invoice is already flagged to the prior year.
	const invoiceYear = get_competence_year_options(frm)[0];
	const carried =
		frm.doc.fab_itx_competence_year && String(frm.doc.fab_itx_competence_year) !== invoiceYear;
	const postingDate = frm.doc.posting_date || frappe.datetime.get_today();
	const month = frappe.datetime.str_to_obj(postingDate).getMonth() + 1;
	return Boolean(carried || month <= 3);
}

function set_competence_year_intro(frm) {
	// frappe's show_message appends, so guard against a second box on re-refresh
	if (frm.__fab_competence_intro_shown || !should_show_competence_intro(frm)) {
		return;
	}
	const invoiceYear = get_competence_year_options(frm)[0];
	const messages = [
		__(
			"Competence Year controls whether this invoice stays in {0} or is accrued back to the prior year automatically on save.",
			[invoiceYear]
		),
	];
	if (frm.doctype === "Purchase Invoice") {
		messages.push(
			__(
				"Set cost deductibility on each item row, or use Invoice Deductibility Override in the header to apply one rule to the whole invoice."
			)
		);
	}
	frm.set_intro(messages.join(" "), "blue");
	frm.__fab_competence_intro_shown = true;
}

function refresh_purchase_deductibility_grid(frm) {
	if (frm.doctype !== "Purchase Invoice" || !frm.fields_dict.items?.grid) {
		return;
	}

	const grid = frm.fields_dict.items.grid;
	for (const fieldname of [
		"fab_itx_deductibility_mode",
		"fab_itx_deductible_percentage",
		"fab_itx_deductible_amount",
	]) {
		grid.update_docfield_property(fieldname, "in_list_view", 1);
	}
}

function add_year_close_actions(frm) {
	if (frm.is_new()) {
		return;
	}

	frm.add_custom_button(
		__("Open Italian Yearly Balance"),
		() => frappe.set_route("query-report", "Italian Yearly Balance", { company: frm.doc.company }),
		__("Italy Close")
	);
}

function setup_yearly_close_form(frm) {
	refresh_competence_year_field(frm);
	refresh_purchase_deductibility_grid(frm);
	set_competence_year_intro(frm);
	add_year_close_actions(frm);
}

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		setup_yearly_close_form(frm);
	},
	posting_date(frm) {
		frm.__fab_competence_intro_shown = false;
		refresh_competence_year_field(frm);
	},
});

frappe.ui.form.on("Purchase Invoice", {
	refresh(frm) {
		setup_yearly_close_form(frm);
	},
	posting_date(frm) {
		frm.__fab_competence_intro_shown = false;
		refresh_competence_year_field(frm);
	},
});
