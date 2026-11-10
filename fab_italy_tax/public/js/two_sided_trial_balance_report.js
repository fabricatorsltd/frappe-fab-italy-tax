// Two-sided trial balance PDF from the ERPNext financial statements, with their current filters.
// Frappe has no hook for the JS of another app's query report, so the shared QueryReport view
// is extended: refresh_report runs on every report load and calls the report's onload.
(() => {
	const REPORTS = ["Profit and Loss Statement", "Balance Sheet", "Trial Balance"];
	const ROLES = ["Accounts User", "Accounts Manager"];
	const METHOD = "/api/method/fab_italy_tax.trial_balance_print.download_pdf";
	const FIELDS = [
		"company",
		"filter_based_on",
		"from_fiscal_year",
		"to_fiscal_year",
		"period_start_date",
		"period_end_date",
		"fiscal_year",
		"from_date",
		"to_date",
		"finance_book",
		"cost_center",
		"include_default_book_entries",
	];

	const QueryReport = frappe.views.QueryReport;
	if (!QueryReport || QueryReport.prototype._two_sided_trial_balance) return;
	QueryReport.prototype._two_sided_trial_balance = true;

	function required_fields(values) {
		if (values.filter_based_on === "Fiscal Year") return ["company", "from_fiscal_year"];
		if (values.filter_based_on === "Date Range") return ["company", "period_start_date", "period_end_date"];
		return ["company", "from_date", "to_date"];
	}

	function download(report) {
		const values = {};
		for (const fieldname of FIELDS) {
			if (!report.get_filter(fieldname, false)) continue;
			const value = report.get_filter_value(fieldname, false);
			if (Array.isArray(value) ? value.length : value || value === 0) {
				values[fieldname] = value;
			}
		}
		const missing = required_fields(values).filter((fieldname) => !values[fieldname]);
		if (missing.length) {
			const labels = missing.map((f) => __(report.get_filter(f, false)?.df.label) || frappe.unscrub(f));
			frappe.msgprint(__("Set {0} in the report filters first.", [labels.join(", ")]));
			return;
		}
		const params = new URLSearchParams({ filters: JSON.stringify(values) });
		window.open(`${METHOD}?${params.toString()}`);
	}

	function menu_entry(report, text) {
		return report.page.menu
			.find("li > a.grey-link > span")
			.filter((_i, el) => $(el).text().trim() === text)
			.closest("li");
	}

	function is_target(report) {
		return REPORTS.includes(report.report_name) && frappe.user.has_role(ROLES);
	}

	function add_menu_entry(report, label) {
		// the menu outlives the report: drop the entry before adding it again or moving on
		menu_entry(report, label).remove();
		if (!is_target(report)) return;
		// "..." menu, right after Export
		const $item = report.page.add_menu_item(label, () => download(report), true).closest("li");
		const $export = menu_entry(report, __("Export"));
		if ($export.length) $item.insertAfter($export.last());
	}

	function add_actions_entry(report, label) {
		if (!is_target(report)) return;
		// add_inner_button also puts an "Actions > label" copy in the "..." menu for small
		// screens: the entry added above covers them
		report.page.add_inner_button(label, () => download(report), __("Actions"));
		menu_entry(report, `${__("Actions")} > ${label}`).remove();
	}

	function safely(fn, ...args) {
		try {
			fn(...args);
		} catch (e) {
			console.error(e);
		}
	}

	// refresh_report empties the Actions group (clear_custom_actions) right before the report's
	// onload, so that entry goes in after the onload, wrapped once per report settings object
	function wrap_onload(settings, label) {
		if (!settings || settings._two_sided_trial_balance) return;
		const onload = settings.onload;
		settings.onload = function (report) {
			const result = onload ? onload.apply(this, arguments) : undefined;
			safely(add_actions_entry, report, label);
			return result;
		};
		settings._two_sided_trial_balance = true;
	}

	const refresh_report = QueryReport.prototype.refresh_report;
	QueryReport.prototype.refresh_report = function (...args) {
		const label = __("Two-sided Trial Balance (PDF)");
		safely(add_menu_entry, this, label);
		if (is_target(this)) safely(wrap_onload, this.report_settings, label);
		return refresh_report.apply(this, args);
	};
})();
