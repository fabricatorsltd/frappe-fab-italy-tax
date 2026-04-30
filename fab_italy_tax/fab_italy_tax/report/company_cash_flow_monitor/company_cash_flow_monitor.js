function get_offset_date(month_offset = 0) {
	const date = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	date.setMonth(date.getMonth() + month_offset);
	return frappe.datetime.obj_to_str(date);
}

function get_report_filter_values(report, raise = false) {
	if (raise) {
		const mandatory = report.filters.filter((filter) => filter.df.reqd || filter.df.mandatory);
		const missing_mandatory = mandatory.filter((filter) => !filter.get_value());
		if (missing_mandatory.length) {
			const message = __("Please set filters");
			report.hide_loading_screen();
			report.toggle_message(raise, message);
			throw "Filter missing";
		}
	}

	raise && report.toggle_message(false);

	return report.filters
		.map((filter) => {
			let value = filter.get_value?.();
			if (filter.df.hidden) value = filter.value;
			if (value === "%") value = null;
			if (filter.df.wildcard_filter && value !== undefined && value !== null && value !== "") {
				value = `%${value}%`;
			}
			return {
				fieldname: filter.df.fieldname,
				value,
			};
		})
		.filter(
			({ value }) =>
				value !== undefined &&
				value !== null &&
				value !== "" &&
				(!Array.isArray(value) || value.length)
		)
		.reduce((filters, { fieldname, value }) => {
			filters[fieldname] = value;
			return filters;
		}, {});
}

function patch_filter_serialization(report) {
	if (report.__fab_company_cashflow_filters_patched) {
		return;
	}

	report.get_filter_values = (raise) => get_report_filter_values(report, raise);
	report.__fab_company_cashflow_filters_patched = true;
}

function refresh_current_report() {
	frappe.query_report?.refresh();
}

frappe.query_reports["Company Cash Flow Monitor"] = {
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
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: get_offset_date(3),
		},
		{
			fieldname: "include_overdue",
			label: __("Include Overdue"),
			fieldtype: "Check",
			default: 1,
			on_change: refresh_current_report,
		},
		{
			fieldname: "include_employee_cost",
			label: __("Include Employee Cost"),
			fieldtype: "Check",
			default: 1,
			on_change: refresh_current_report,
		},
		{
			fieldname: "trailing_months",
			label: __("Trailing Months"),
			fieldtype: "Int",
			default: 6,
			on_change: refresh_current_report,
		},
	],

	async onload(report) {
		patch_filter_serialization(report);

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
