frappe.pages["two-sided-trial-balance"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Two-sided Trial Balance"),
		single_column: true,
	});
	page.set_primary_action(__("Print two-sided trial balance"), () => open_trial_balance_dialog(), "printer");
	page.add_inner_button(__("Settings"), () => frappe.set_route("Form", "Trial Balance Print Settings"));
	$(`<div class="text-muted" style="padding: 15px 0;"></div>`)
		.text(
			__(
				"Balance sheet and profit and loss side by side, grouped by the account tree, as a PDF. Layout and branding are in Trial Balance Print Settings."
			)
		)
		.appendTo(page.body);
	open_trial_balance_dialog();
};

function open_trial_balance_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Print two-sided trial balance"),
		fields: [
			{
				fieldname: "company",
				fieldtype: "Link",
				label: __("Company"),
				options: "Company",
				reqd: 1,
				default: frappe.defaults.get_user_default("Company"),
			},
			{
				fieldname: "filter_based_on",
				fieldtype: "Select",
				label: __("Filter Based On"),
				options: [
					{ value: "Fiscal Year", label: __("Fiscal Year") },
					{ value: "Date Range", label: __("Date Range") },
				],
				default: "Fiscal Year",
			},
			{
				fieldname: "fiscal_year",
				fieldtype: "Link",
				label: __("Fiscal Year"),
				options: "Fiscal Year",
				depends_on: "eval:doc.filter_based_on == 'Fiscal Year'",
				mandatory_depends_on: "eval:doc.filter_based_on == 'Fiscal Year'",
				default: frappe.defaults.get_user_default("fiscal_year"),
			},
			{ fieldname: "column_break_dates", fieldtype: "Column Break" },
			{
				fieldname: "from_date",
				fieldtype: "Date",
				label: __("From Date"),
				depends_on: "eval:doc.filter_based_on == 'Date Range'",
				mandatory_depends_on: "eval:doc.filter_based_on == 'Date Range'",
				default: frappe.datetime.year_start(),
			},
			{
				fieldname: "to_date",
				fieldtype: "Date",
				label: __("To Date"),
				depends_on: "eval:doc.filter_based_on == 'Date Range'",
				mandatory_depends_on: "eval:doc.filter_based_on == 'Date Range'",
				default: frappe.datetime.get_today(),
			},
			{ fieldname: "section_break_dimensions", fieldtype: "Section Break" },
			{
				fieldname: "cost_center",
				fieldtype: "Link",
				label: __("Cost Center"),
				options: "Cost Center",
				get_query: () => ({ filters: { company: dialog.get_value("company") } }),
			},
			{ fieldname: "column_break_dimensions", fieldtype: "Column Break" },
			{
				fieldname: "finance_book",
				fieldtype: "Link",
				label: __("Finance Book"),
				options: "Finance Book",
			},
			{
				fieldname: "include_default_book_entries",
				fieldtype: "Check",
				label: __("Include Default FB Entries"),
				default: 1,
			},
		],
		primary_action_label: __("Download PDF"),
		primary_action(values) {
			const filters = {
				company: values.company,
				cost_center: values.cost_center,
				finance_book: values.finance_book,
				include_default_book_entries: values.include_default_book_entries ? 1 : 0,
			};
			if (values.filter_based_on === "Date Range") {
				filters.from_date = values.from_date;
				filters.to_date = values.to_date;
			} else {
				filters.fiscal_year = values.fiscal_year;
			}
			const params = new URLSearchParams({ filters: JSON.stringify(filters) });
			window.open(`/api/method/fab_italy_tax.trial_balance_print.download_pdf?${params.toString()}`);
			dialog.hide();
		},
	});
	dialog.show();
}
