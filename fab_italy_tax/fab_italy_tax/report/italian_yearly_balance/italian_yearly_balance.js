frappe.query_reports["Italian Yearly Balance"] = {
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
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			reqd: 1,
			default:
				frappe.defaults.get_user_default("fiscal_year") || frappe.defaults.get_user_default("Fiscal Year"),
		},
	],
};

