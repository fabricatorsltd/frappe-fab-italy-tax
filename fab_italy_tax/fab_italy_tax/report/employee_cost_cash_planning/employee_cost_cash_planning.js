function get_month_start(month_offset = 0) {
	const date = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	date.setDate(1);
	date.setMonth(date.getMonth() + month_offset);
	return frappe.datetime.obj_to_str(date);
}

frappe.query_reports["Employee Cost Cash Planning"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default:
				frappe.defaults.get_user_default("Company") || frappe.defaults.get_user_default("company"),
		},
		{
			fieldname: "from_month",
			label: __("From Month"),
			fieldtype: "Date",
			reqd: 1,
			default: get_month_start(),
		},
		{
			fieldname: "to_month",
			label: __("To Month"),
			fieldtype: "Date",
			reqd: 1,
			default: get_month_start(3),
		},
		{
			fieldname: "include_estimates",
			label: __("Include Estimates"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "trailing_months",
			label: __("Trailing Months"),
			fieldtype: "Int",
			default: 6,
		},
	],

	async onload(report) {
		const company_filter = report.get_filter("company");
		if (company_filter.get_value()) {
			report.refresh();
			return;
		}

		const response = await frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Company",
				fields: ["name"],
				limit_page_length: 2,
			},
		});
		const companies = response.message || [];
		if (companies.length === 1) {
			company_filter.set_value(companies[0].name);
			report.refresh();
		}
	},
};
