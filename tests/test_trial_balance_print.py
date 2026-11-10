"""Two-sided trial balance.

The layout tests run on plain account lists. TestTrialBalanceLedger needs a dedicated
test site with ERPNext: it creates two companies with their own chart of accounts and
rolls everything back afterwards.
"""

from __future__ import annotations

import unittest
from datetime import date

import frappe

from fab_italy_tax import trial_balance_print as tb


def account(name, parent=None, number=None, root_type="Asset", is_group=0, lft=0):
	return frappe._dict(
		name=name,
		account_name=name,
		account_number=number,
		parent_account=parent,
		is_group=is_group,
		root_type=root_type,
		lft=lft,
	)


def sample_chart():
	"""Assets root > Current > Cash > (Till, Bank), Assets root > Loose (leaf under the root),
	plus a liability, an equity, a cost and a revenue branch."""
	rows = [
		account("Assets", is_group=1),
		account("Current", "Assets", "1", is_group=1),
		account("Cash", "Current", "10", is_group=1),
		account("Bank", "Cash", "1002"),
		account("Till", "Cash", "1001"),
		account("Receivables", "Current", "11", is_group=1),
		account("Customers", "Receivables", "1101"),
		account("Loose", "Assets"),
		account("Liabilities", root_type="Liability", is_group=1),
		account("Suppliers", "Liabilities", "2001", root_type="Liability"),
		account("Equity", root_type="Equity", is_group=1),
		account("Capital", "Equity", "3001", root_type="Equity"),
		account("Expenses", root_type="Expense", is_group=1),
		account("Services", "Expenses", "7001", root_type="Expense"),
		account("Rent", "Expenses", "7002", root_type="Expense"),
		account("Income", root_type="Income", is_group=1),
		account("Sales", "Income", "8001", root_type="Income"),
	]
	for index, row in enumerate(rows):
		row.lft = index + 1
	return rows


# debit - credit, as the ledger returns them
SAMPLE_BALANCES = {
	"Till": 100.0,
	"Bank": 900.0,
	"Customers": 0.0,
	"Loose": -40.0,
	"Suppliers": -300.0,
	"Capital": -500.0,
	"Services": 250.0,
	"Rent": 0.0,
	"Sales": -410.0,
}


def names(groups):
	return [(g.name, [line.name for line in g.lines]) for g in groups]


class TestTrialBalanceLayout(unittest.TestCase):
	def test_default_groups_by_parent_of_each_account(self):
		columns = tb.build_columns(sample_chart(), SAMPLE_BALANCES, group_level=0, hide_zero=True)
		assets = columns["balance_sheet"]["left"]
		# numbered groups by number, the unnumbered root after them; accounts by number
		self.assertEqual(names(assets), [("Cash", ["Till", "Bank"]), ("Assets", ["Loose"])])
		self.assertEqual(assets[0].number, "10")
		self.assertEqual(assets[0].total, 1000.0)
		self.assertEqual(assets[1].number, "")
		self.assertEqual(names(columns["balance_sheet"]["right"]), [("Liabilities", ["Suppliers"]), ("Equity", ["Capital"])])

	def test_group_level_picks_the_ancestor_at_that_depth(self):
		columns = tb.build_columns(sample_chart(), SAMPLE_BALANCES, group_level=1, hide_zero=False)
		self.assertEqual(
			names(columns["balance_sheet"]["left"]),
			[("Current", ["Till", "Bank", "Customers"]), ("Assets", ["Loose"])],
		)
		deeper = tb.build_columns(sample_chart(), SAMPLE_BALANCES, group_level=2, hide_zero=False)
		self.assertEqual(
			names(deeper["balance_sheet"]["left"]),
			[("Cash", ["Till", "Bank"]), ("Receivables", ["Customers"]), ("Assets", ["Loose"])],
		)

	def test_hide_zero_lines_drops_zero_accounts_and_empty_groups(self):
		hidden = tb.build_columns(sample_chart(), SAMPLE_BALANCES, group_level=2, hide_zero=True)
		self.assertNotIn("Receivables", [g.name for g in hidden["balance_sheet"]["left"]])
		self.assertEqual(names(hidden["profit_and_loss"]["left"]), [("Expenses", ["Services"])])

		shown = tb.build_columns(sample_chart(), SAMPLE_BALANCES, group_level=2, hide_zero=False)
		self.assertIn("Receivables", [g.name for g in shown["balance_sheet"]["left"]])
		self.assertEqual(names(shown["profit_and_loss"]["left"]), [("Expenses", ["Services", "Rent"])])

	def test_wrong_side_balance_stays_in_its_column_with_sign(self):
		columns = tb.build_columns(sample_chart(), SAMPLE_BALANCES)
		loose = columns["balance_sheet"]["left"][1].lines[0]
		self.assertEqual((loose.name, loose.amount), ("Loose", -40.0))
		self.assertEqual(columns["balance_sheet"]["right"][0].lines[0].amount, 300.0)

	def test_profit_balances_both_sections(self):
		report = tb.build_report(sample_chart(), SAMPLE_BALANCES, prior_profit=0.0)
		self.assertEqual(report.profit, 160.0)
		bs, pl = report.sections
		self.assertEqual((bs.left_total, bs.right_total), (960.0, 800.0))
		self.assertEqual(bs.right_results, [("Profit for the period", 160.0)])
		self.assertEqual(bs.left_pareggio, bs.right_pareggio)
		self.assertEqual(bs.left_pareggio, 960.0)
		self.assertEqual((pl.left_total, pl.right_total), (250.0, 410.0))
		self.assertEqual(pl.left_results, [("Profit for the period", 160.0)])
		self.assertEqual(pl.left_pareggio, pl.right_pareggio)
		self.assertEqual(report.difference, 0.0)

	def test_loss_and_prior_years_balance_on_the_debit_side(self):
		balances = dict(SAMPLE_BALANCES, Sales=-50.0, Bank=1140.0, Capital=-1200.0)
		report = tb.build_report(sample_chart(), balances, prior_profit=-100.0)
		bs, pl = report.sections
		self.assertEqual(report.profit, -200.0)
		self.assertEqual(pl.right_results, [("Loss for the period", 200.0)])
		self.assertEqual(pl.left_pareggio, pl.right_pareggio)
		self.assertEqual(
			bs.left_results, [("Prior years loss not closed", 100.0), ("Loss for the period", 200.0)]
		)
		self.assertEqual(bs.left_pareggio, bs.right_pareggio)
		self.assertEqual(report.difference, 0.0)

	def test_unsquared_balance_sheet_prints_the_difference(self):
		balances = dict(SAMPLE_BALANCES, Bank=950.0)
		report = tb.build_report(sample_chart(), balances)
		bs = report.sections[0]
		self.assertEqual(report.difference, 50.0)
		self.assertIn(("Unbalanced difference", 50.0), bs.right_results)
		self.assertEqual(bs.left_pareggio, bs.right_pareggio)

	def test_group_header_shares_a_row_with_its_first_line(self):
		columns = tb.build_columns(sample_chart(), SAMPLE_BALANCES)
		rows = tb.paired_rows(columns["balance_sheet"]["left"], columns["balance_sheet"]["right"])
		kinds = [([k for k, _v in left], [k for k, _v in right]) for left, right in rows]
		self.assertEqual(
			kinds,
			[
				(["group", "line"], ["group", "line"]),
				(["line"], ["blank"]),
				# the left header would sit on the second line: it waits for the next row
				(["blank", "empty"], ["group", "line"]),
				(["group", "line"], ["empty", "empty"]),
			],
		)

	def test_profit_earlier_in_the_year_gets_its_own_line(self):
		balances = dict(SAMPLE_BALANCES, Bank=1030.0)
		report = tb.build_report(sample_chart(), balances, prior_profit=50.0, earlier_profit=80.0)
		bs = report.sections[0]
		self.assertEqual(report.difference, 0.0)
		self.assertEqual(
			bs.right_results,
			[
				("Prior years profit not closed", 50.0),
				("Profit of the year before the period", 80.0),
				("Profit for the period", 160.0),
			],
		)
		self.assertEqual(bs.left_pareggio, bs.right_pareggio)


COMPANY = "Trial Balance Test Company"
ABBR = "TBTC"
OTHER_COMPANY = "Trial Balance Other Company"
OTHER_ABBR = "TBOC"
USER = "trial-balance-user@example.com"
OUTSIDER = "trial-balance-outsider@example.com"
FINANCE_BOOK = "Trial Balance Book"


def ensure_company(name, abbr):
	if not frappe.db.exists("Company", name):
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": name,
				"abbr": abbr,
				"default_currency": "EUR",
				"country": "Italy",
				"create_chart_of_accounts_based_on": "Standard Template",
				"chart_of_accounts": "Standard",
			}
		).insert(ignore_permissions=True)


def group_of(root_type):
	# the Standard chart has no sub-group under some roots: fall back to the root itself
	return frappe.db.get_value(
		"Account", {"company": COMPANY, "root_type": root_type, "is_group": 1}, order_by="lft desc"
	)


def make_account(name, root_type, number):
	existing = frappe.db.get_value("Account", {"account_name": name, "company": COMPANY})
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": name,
				"account_number": number,
				"parent_account": group_of(root_type),
				"company": COMPANY,
				"account_currency": "EUR",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def make_user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.set("roles", [])
	user.add_roles(*roles)
	return user


class TestTrialBalanceLedger(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		frappe.flags.mute_emails = True
		for year in (2025, 2026):
			if not frappe.db.exists("Fiscal Year", str(year)):
				frappe.get_doc(
					{
						"doctype": "Fiscal Year",
						"year": str(year),
						"year_start_date": date(year, 1, 1),
						"year_end_date": date(year, 12, 31),
					}
				).insert(ignore_permissions=True)
		if not frappe.db.exists("Warehouse Type", "Transit"):
			# normally created by the setup wizard, needed by Company.on_update
			frappe.get_doc({"doctype": "Warehouse Type", "name": "Transit"}).insert(ignore_permissions=True)
		ensure_company(COMPANY, ABBR)
		ensure_company(OTHER_COMPANY, OTHER_ABBR)
		if not frappe.db.exists("Finance Book", FINANCE_BOOK):
			frappe.get_doc({"doctype": "Finance Book", "finance_book_name": FINANCE_BOOK}).insert(
				ignore_permissions=True
			)
		cls.main_cc = frappe.get_cached_value("Company", COMPANY, "cost_center")
		cls.other_cc = frappe.db.get_value("Cost Center", {"cost_center_name": "Second", "company": COMPANY})
		if not cls.other_cc:
			cls.other_cc = (
				frappe.get_doc(
					{
						"doctype": "Cost Center",
						"cost_center_name": "Second",
						"company": COMPANY,
						"parent_cost_center": frappe.db.get_value(
							"Cost Center", {"company": COMPANY, "is_group": 1, "parent_cost_center": ["is", "not set"]}
						),
					}
				)
				.insert(ignore_permissions=True)
				.name
			)
		cls.acc = {
			"bank": make_account("Trial Bank", "Asset", "T1001"),
			"capital": make_account("Trial Capital", "Equity", "T3001"),
			"sales": make_account("Trial Sales", "Income", "T8001"),
			"services": make_account("Trial Services", "Expense", "T7001"),
		}
		cls.post("2025-06-01", "bank", "capital", 1000)
		cls.post("2025-07-01", "bank", "sales", 300)
		cls.post("2026-02-01", "bank", "sales", 500)
		cls.post("2026-03-01", "services", "bank", 200)
		cls.post("2026-04-01", "services", "bank", 50, cost_center=cls.other_cc)
		cls.post("2026-05-01", "services", "bank", 70, finance_book=FINANCE_BOOK)
		cls.post("2026-08-01", "bank", "sales", 1000)
		make_user(USER, ["Accounts User"])
		make_user(OUTSIDER, ["Sales User"])
		if not frappe.db.exists("User Permission", {"user": USER, "allow": "Company"}):
			frappe.get_doc(
				{"doctype": "User Permission", "user": USER, "allow": "Company", "for_value": COMPANY}
			).insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def tearDown(self):
		frappe.set_user("Administrator")

	@classmethod
	def post(cls, posting_date, debit, credit, amount, cost_center=None, finance_book=None):
		cost_center = cost_center or cls.main_cc
		frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": COMPANY,
				"posting_date": posting_date,
				"finance_book": finance_book,
				"accounts": [
					{"account": cls.acc[debit], "debit_in_account_currency": amount, "cost_center": cost_center},
					{"account": cls.acc[credit], "credit_in_account_currency": amount, "cost_center": cost_center},
				],
			}
		).submit()

	def report(self, **filters):
		filters = tb.normalize_filters(dict(company=COMPANY, **filters))
		balances, prior, earlier = tb.get_balances(filters)
		return tb.build_report(tb.get_accounts(COMPANY), balances, prior, earlier_profit=earlier), filters

	def erpnext_profit(self, filters):
		from erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement import execute

		result = execute(
			frappe._dict(
				company=COMPANY,
				filter_based_on="Date Range",
				period_start_date=filters.from_date,
				period_end_date=filters.to_date,
				periodicity="Yearly",
				accumulated_values=1,
				cost_center=filters.get("cost_center"),
				finance_book=filters.get("finance_book"),
				include_default_book_entries=filters.include_default_book_entries,
			)
		)
		return result[5]

	def test_period_result_equals_erpnext_profit_and_loss(self):
		cases = [
			dict(from_date="2026-01-01", to_date="2026-06-30"),
			dict(fiscal_year="2026"),
			dict(from_date="2026-01-01", to_date="2026-06-30", cost_center=self.other_cc),
			dict(from_date="2026-01-01", to_date="2026-06-30", finance_book=FINANCE_BOOK),
			dict(
				from_date="2026-01-01",
				to_date="2026-06-30",
				finance_book=FINANCE_BOOK,
				include_default_book_entries=0,
			),
		]
		# with no finance book only entries without one count, as in ERPNext
		expected = [250.0, 1250.0, -50.0, 180.0, 180.0]
		for case, value in zip(cases, expected):
			with self.subTest(case=case):
				report, filters = self.report(**case)
				self.assertAlmostEqual(report.profit, self.erpnext_profit(filters), places=2)
				self.assertEqual(report.profit, value)

	def test_balance_sheet_squares_with_prior_and_period_result(self):
		report, _filters = self.report(from_date="2026-01-01", to_date="2026-06-30")
		bs, pl = report.sections
		self.assertEqual(report.prior_profit, 300.0)
		self.assertEqual(report.difference, 0.0)
		# bank 1000 + 300 + 500 - 200 - 50 (the finance book entry is out), capital 1000
		self.assertEqual((bs.left_total, bs.right_total), (1550.0, 1000.0))
		self.assertEqual(bs.left_pareggio, bs.right_pareggio)
		self.assertEqual(pl.left_pareggio, pl.right_pareggio)
		self.assertEqual(pl.right_pareggio, 500.0)

	def test_mid_year_start_splits_the_open_result(self):
		report, _filters = self.report(from_date="2026-04-01", to_date="2026-06-30")
		self.assertEqual((report.prior_profit, report.earlier_profit, report.profit), (300.0, 300.0, -50.0))
		self.assertEqual(report.difference, 0.0)
		bs = report.sections[0]
		self.assertEqual(bs.left_pareggio, bs.right_pareggio)

	def test_html_carries_both_sections_and_group_rows(self):
		frappe.local.lang = "en"
		report, filters = self.report(fiscal_year="2026")
		html = tb.render_html(filters, report=report)
		self.assertIn("Balance sheet from", html)
		self.assertIn("Profit and loss from", html)
		self.assertIn('<tr class="g">', html)
		self.assertIn("Trial Sales", html)
		self.assertIn('id="header-html"', html)

	def test_report_filters_pick_the_dates_of_filter_based_on(self):
		# the financial statements keep the hidden filters of the other mode filled in
		def dates(based_on, **filters):
			filters = tb.normalize_filters(
				dict(
					company=COMPANY,
					filter_based_on=based_on,
					period_start_date="2026-03-01",
					period_end_date="2026-03-31",
					**filters,
				)
			)
			self.assertNotIn("period_start_date", filters)
			return filters.from_date, filters.to_date

		self.assertEqual(
			dates("Fiscal Year", from_fiscal_year="2025", to_fiscal_year="2026"),
			(date(2025, 1, 1), date(2026, 12, 31)),
		)
		self.assertEqual(
			dates("Fiscal Year", from_fiscal_year="2026"), (date(2026, 1, 1), date(2026, 12, 31))
		)
		self.assertEqual(
			dates("Date Range", from_fiscal_year="2025", to_fiscal_year="2025"),
			(date(2026, 3, 1), date(2026, 3, 31)),
		)
		with self.assertRaises(frappe.ValidationError):
			dates("Fiscal Year")
		with self.assertRaises(frappe.ValidationError):
			dates("Fiscal Year", from_fiscal_year="2026", to_fiscal_year="2025")

	def test_cost_center_list_of_the_reports_filters_like_a_name(self):
		listed, filters = self.report(fiscal_year="2026", cost_center=[self.other_cc])
		named, _filters = self.report(fiscal_year="2026", cost_center=self.other_cc)
		self.assertEqual(filters.cost_center, [self.other_cc])
		html = tb.render_html(filters, report=listed)
		self.assertIn(f"Cost Center: {self.other_cc}<", html.replace("</td>", "<"))
		self.assertEqual(listed.profit, named.profit)
		self.assertEqual(listed.profit, -50.0)

	def test_unchecked_default_book_entries_stay_off(self):
		filters = tb.normalize_filters(
			dict(company=COMPANY, fiscal_year="2026", include_default_book_entries=0)
		)
		self.assertEqual(filters.include_default_book_entries, 0)

	def test_permission_follows_roles_and_user_permissions(self):
		tb.check_permission(COMPANY, user=USER)
		with self.assertRaises(frappe.PermissionError):
			tb.check_permission(OTHER_COMPANY, user=USER)
		with self.assertRaises(frappe.PermissionError):
			tb.check_permission(COMPANY, user=OUTSIDER)
		with self.assertRaises(frappe.PermissionError):
			tb.check_permission("No Such Company", user=USER)

	def test_download_checks_permission_before_rendering(self):
		frappe.set_user(USER)
		with self.assertRaises(frappe.PermissionError):
			tb.download_pdf(frappe.as_json({"company": OTHER_COMPANY, "fiscal_year": "2026"}))
