"""Printable two-sided trial balance (bilancio di verifica a sezioni contrapposte).

Balance sheet accounts print their closing balance at the to-date, profit and loss
accounts their movement within the period. Both sides of each section are grouped
by the account tree and balanced by the result of the period.
"""

from __future__ import annotations

import re
from itertools import zip_longest
from typing import Any

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, fmt_money, formatdate, getdate, nowdate

PDF_GENERATOR_CONF_KEY = "trial_balance_pdf_generator"
TEMPLATE = "fab_italy_tax/templates/trial_balance/two_sided_trial_balance.html"
ALLOWED_ROLES = ("Accounts User", "Accounts Manager")
DEFAULT_ACCENT = "#6f8aa0"
FONT_FALLBACK = "Arial, Helvetica, sans-serif"

# root type -> (section, side, natural balance)
ROOT_TYPES = {
	"Asset": ("balance_sheet", "left", 1),
	"Liability": ("balance_sheet", "right", -1),
	"Equity": ("balance_sheet", "right", -1),
	"Expense": ("profit_and_loss", "left", 1),
	"Income": ("profit_and_loss", "right", -1),
}


# --------------------------------------------------------------------------
# filters and permissions


def normalize_filters(filters: dict | str | None) -> frappe._dict:
	filters = frappe._dict(frappe.parse_json(filters) if isinstance(filters, str) else (filters or {}))
	if not filters.get("company"):
		frappe.throw(_("Select a Company first."))
	if filters.get("fiscal_year") and not (filters.get("from_date") and filters.get("to_date")):
		start, end = frappe.db.get_value(
			"Fiscal Year", filters.fiscal_year, ["year_start_date", "year_end_date"]
		) or (None, None)
		if not start:
			frappe.throw(_("Fiscal Year {0} does not exist").format(filters.fiscal_year))
		companies = frappe.get_all(
			"Fiscal Year Company", filters={"parent": filters.fiscal_year}, pluck="company"
		)
		if companies and filters.company not in companies:
			frappe.throw(
				_("Fiscal Year {0} is not available for Company {1}.").format(filters.fiscal_year, filters.company)
			)
		filters.from_date, filters.to_date = start, end
	if not (filters.get("from_date") and filters.get("to_date")):
		frappe.throw(_("Select a Fiscal Year or both From Date and To Date."))
	filters.from_date = getdate(filters.from_date)
	filters.to_date = getdate(filters.to_date)
	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date must be before To Date"))
	filters.include_default_book_entries = cint(filters.get("include_default_book_entries", 1))
	return filters


def check_permission(company: str, user: str | None = None) -> None:
	"""Accounts User or Manager who can read the ledger and this company,
	User Permissions on Company included."""
	user = user or frappe.session.user
	allowed = (
		set(ALLOWED_ROLES) & set(frappe.get_roles(user))
		and frappe.has_permission("GL Entry", "read", user=user)
		and frappe.db.exists("Company", company)
		and frappe.has_permission("Company", "read", doc=company, user=user)
	)
	if not allowed:
		frappe.throw(_("Not permitted"), frappe.PermissionError)


# --------------------------------------------------------------------------
# data


def get_settings():
	return frappe.get_cached_doc("Trial Balance Print Settings")


def get_accounts(company: str) -> list[frappe._dict]:
	return frappe.get_all(
		"Account",
		filters={"company": company},
		fields=["name", "account_name", "account_number", "parent_account", "is_group", "root_type", "lft"],
		order_by="lft",
	)


def _ledger_balances(filters, from_date, to_date, root_types, ignore_closing_entries) -> dict[str, float]:
	"""debit - credit per leaf account, through ERPNext's own query so the finance book,
	cost center, accounting dimension and User Permission rules match its statements."""
	from erpnext.accounts.report.financial_statements import get_accounting_entries

	out: dict[str, float] = {}
	for root_type in root_types:
		rows = get_accounting_entries(
			"GL Entry",
			from_date,
			to_date,
			frappe._dict(filters),
			root_type=root_type,
			ignore_closing_entries=ignore_closing_entries,
			group_by_account=True,
		)
		for row in rows:
			out[row.account] = out.get(row.account, 0.0) + flt(row.debit) - flt(row.credit)
	return out


def fiscal_year_start(filters):
	from erpnext.accounts.utils import get_fiscal_year

	try:
		return getdate(get_fiscal_year(filters.from_date, company=filters.company)[1])
	except Exception:
		return filters.from_date


def get_balances(filters) -> tuple[dict[str, float], float, float]:
	"""Per account debit - credit, the profit of prior fiscal years still open at from_date
	and the profit of the same fiscal year before from_date.

	The print is the pre-closing trial balance: a Period Closing Voucher inside the period
	is left out, so the year result shows as such instead of already sitting in equity.
	Closing vouchers of earlier years are kept, so closed years add nothing."""
	ledger_filters = {
		k: filters.get(k)
		for k in ("company", "finance_book", "cost_center", "include_default_book_entries")
		if filters.get(k)
	}
	before = add_days(filters.from_date, -1)
	balance_sheet = ("Asset", "Liability", "Equity")
	profit_and_loss = ("Income", "Expense")

	balances = _ledger_balances(ledger_filters, None, before, balance_sheet, False)
	for account, value in _ledger_balances(
		ledger_filters, filters.from_date, filters.to_date, balance_sheet + profit_and_loss, True
	).items():
		balances[account] = balances.get(account, 0.0) + value

	year_start = min(fiscal_year_start(filters), filters.from_date)
	prior = _ledger_balances(ledger_filters, None, add_days(year_start, -1), profit_and_loss, False)
	earlier = {}
	if year_start < filters.from_date:
		earlier = _ledger_balances(ledger_filters, year_start, before, profit_and_loss, True)
	return balances, -sum(prior.values()), -sum(earlier.values())


# --------------------------------------------------------------------------
# layout


def group_of(account: str, accounts_by_name: dict, group_level: int) -> str:
	"""The ancestor printed as the bold group line: the direct parent for level 0,
	else the ancestor at that depth (root = 0), or the parent when the account sits higher."""
	path = []
	current = accounts_by_name.get(account)
	while current and current.parent_account:
		path.append(current.parent_account)
		current = accounts_by_name.get(current.parent_account)
	if not path:
		return account
	parent = path[0]
	if group_level <= 0:
		return parent
	path.reverse()  # root first
	return path[group_level] if group_level < len(path) else parent


def _sort_key(account) -> tuple:
	# numbered accounts by number, as ERPNext's statements do, the others in tree order
	return (0, account.account_number, account.lft) if account.account_number else (1, "", account.lft)


def build_columns(accounts, balances, group_level=0, hide_zero=True) -> dict[str, dict[str, list]]:
	"""{section: {side: [group, ...]}}, each group {account, number, name, total, lines}.

	A balance on the unusual side (a credit on an asset, a debit on a cost) stays in the
	account's natural column with a minus sign, as accountants read it, instead of moving
	across to the other side."""
	accounts_by_name = {a.name: a for a in accounts}
	columns: dict[str, dict[str, dict[str, Any]]] = {
		"balance_sheet": {"left": {}, "right": {}},
		"profit_and_loss": {"left": {}, "right": {}},
	}
	for account in accounts:
		if account.is_group or account.root_type not in ROOT_TYPES:
			continue
		section, side, sign = ROOT_TYPES[account.root_type]
		amount = flt(sign * balances.get(account.name, 0.0), 2)
		if hide_zero and not amount:
			continue
		group_name = group_of(account.name, accounts_by_name, group_level)
		groups = columns[section][side]
		if group_name not in groups:
			group_account = accounts_by_name.get(group_name) or account
			groups[group_name] = frappe._dict(
				account=group_name,
				number=group_account.account_number or "",
				name=group_account.account_name,
				sort_key=_sort_key(group_account),
				total=0.0,
				lines=[],
			)
		group = groups[group_name]
		group.total = flt(group.total + amount, 2)
		group.lines.append(
			frappe._dict(
				account=account.name,
				number=account.account_number or "",
				name=account.account_name,
				amount=amount,
				sort_key=_sort_key(account),
			)
		)

	out: dict[str, dict[str, list]] = {}
	for section, sides in columns.items():
		out[section] = {}
		for side, groups in sides.items():
			ordered = sorted(groups.values(), key=lambda g: g.sort_key)
			for group in ordered:
				group.lines.sort(key=lambda line: line.sort_key)
			out[section][side] = ordered
	return out


def column_total(groups) -> float:
	return flt(sum(g.total for g in groups), 2)


def balance_section(left_total: float, right_total: float, results: list[tuple[str, str, float]]):
	"""Put each result on the side it balances. results = [(right label, left label, value)]:
	a positive value prints under the right column, a negative one under the left column
	as a positive amount. Returns (left lines, right lines, left and right totals a pareggio)."""
	left, right = [], []
	for right_label, left_label, value in results:
		value = flt(value, 2)
		if value > 0:
			right.append((right_label, value))
		elif value < 0:
			left.append((left_label, -value))
	left_pareggio = flt(left_total + sum(v for _label, v in left), 2)
	right_pareggio = flt(right_total + sum(v for _label, v in right), 2)
	return left, right, left_pareggio, right_pareggio


def build_report(
	accounts, balances, prior_profit=0.0, group_level=0, hide_zero=True, earlier_profit=0.0
) -> frappe._dict:
	columns = build_columns(accounts, balances, group_level, hide_zero)
	bs, pl = columns["balance_sheet"], columns["profit_and_loss"]
	costs, revenues = column_total(pl["left"]), column_total(pl["right"])
	assets, liabilities = column_total(bs["left"]), column_total(bs["right"])
	profit = flt(revenues - costs, 2)
	prior_profit = flt(prior_profit, 2)
	earlier_profit = flt(earlier_profit, 2)
	# zero without filters (double entry); a cost center or finance book filter can leave
	# balance sheet lines that do not square, printed as such instead of hidden in the result
	difference = flt(assets - liabilities - profit - prior_profit - earlier_profit, 2)

	profit_label = _("Profit for the period", context="trial_balance")
	loss_label = _("Loss for the period", context="trial_balance")
	# a profit balances the debit side on the profit and loss, the credit side on the balance sheet
	bs_results = [
		(
			_("Prior years profit not closed", context="trial_balance"),
			_("Prior years loss not closed", context="trial_balance"),
			prior_profit,
		),
		(
			_("Profit of the year before the period", context="trial_balance"),
			_("Loss of the year before the period", context="trial_balance"),
			earlier_profit,
		),
		(profit_label, loss_label, profit),
		(_("Unbalanced difference", context="trial_balance"), _("Unbalanced difference", context="trial_balance"), difference),
	]
	bs_left, bs_right, bs_lp, bs_rp = balance_section(assets, liabilities, bs_results)
	pl_left, pl_right, pl_lp, pl_rp = balance_section(costs, revenues, [(loss_label, profit_label, -profit)])

	return frappe._dict(
		profit=profit,
		prior_profit=prior_profit,
		earlier_profit=earlier_profit,
		difference=difference,
		sections=[
			frappe._dict(
				key="balance_sheet",
				left=bs["left"],
				right=bs["right"],
				left_total=assets,
				right_total=liabilities,
				left_results=bs_left,
				right_results=bs_right,
				left_pareggio=bs_lp,
				right_pareggio=bs_rp,
			),
			frappe._dict(
				key="profit_and_loss",
				left=pl["left"],
				right=pl["right"],
				left_total=costs,
				right_total=revenues,
				left_results=pl_left,
				right_results=pl_right,
				left_pareggio=pl_lp,
				right_pareggio=pl_rp,
			),
		],
	)


def flatten(groups) -> list[tuple[str, Any]]:
	"""One printed line per item: group header, its accounts, a blank line between groups."""
	lines: list[tuple[str, Any]] = []
	for index, group in enumerate(groups):
		if index:
			lines.append(("blank", None))
		lines.append(("group", group))
		lines.extend(("line", line) for line in group.lines)
	return lines


def paired_rows(left, right) -> list[tuple[list, list]]:
	"""Table rows of (left lines, right lines). A row holding a group header also holds its
	first account on the same side, two lines per side: a table row is never split across
	pages by either PDF engine, while wkhtmltopdf ignores break-after between rows. A header
	that would land on the second line of such a row waits for the next row."""
	queues = {"left": flatten(left), "right": flatten(right)}
	empty = ("empty", None)
	rows = []
	while queues["left"] or queues["right"]:
		size = 2 if any(q and q[0][0] == "group" for q in queues.values()) else 1
		row = {}
		for side, queue in queues.items():
			first = queue.pop(0) if queue else empty
			cells = [first]
			if size == 2:
				if first[0] == "group" or (queue and queue[0][0] != "group"):
					cells.append(queue.pop(0) if queue else empty)
				else:
					cells.append(empty)
			row[side] = cells
		rows.append((row["left"], row["right"]))
	return rows


# --------------------------------------------------------------------------
# rendering


def get_company_details(company: str) -> frappe._dict:
	from erpnext.setup.doctype.company.company import get_default_company_address

	doc = frappe.get_cached_doc("Company", company)
	address_line = ""
	address_name = get_default_company_address(company)
	if address_name:
		address = frappe.get_cached_doc("Address", address_name)
		city = " ".join(p for p in (address.pincode, address.city, address.state) if p)
		address_line = "  ".join(p for p in (address.address_line1, address.address_line2, city) if p)
	return frappe._dict(
		name=doc.company_name,
		tax_id=doc.tax_id or "",
		fiscal_code=(doc.get("fiscal_code") or "") if doc.get("fiscal_code") != doc.tax_id else "",
		address=address_line,
		currency=doc.default_currency,
	)


def tint(color: str, strength: float) -> str:
	"""The color mixed with white, for backgrounds and rules (no color-mix in wkhtmltopdf)."""
	value = color.lstrip("#")
	if len(value) == 3:
		value = "".join(c * 2 for c in value)
	try:
		rgb = [int(value[i : i + 2], 16) for i in (0, 2, 4)]
	except ValueError:
		return "#eef1f4"
	return "#" + "".join(f"{round(255 - (255 - c) * strength):02x}" for c in rgb)


def get_render_context(filters, settings=None, report=None, wkhtmltopdf=None) -> dict[str, Any]:
	settings = settings or get_settings()
	if report is None:
		balances, prior_profit, earlier_profit = get_balances(filters)
		report = build_report(
			get_accounts(filters.company),
			balances,
			prior_profit,
			group_level=cint(settings.group_level),
			hide_zero=cint(settings.hide_zero_lines),
			earlier_profit=earlier_profit,
		)
	letter_head = None
	if settings.letter_head:
		letter_head = frappe.db.get_value(
			"Letter Head", settings.letter_head, ["content", "footer"], as_dict=True
		)
	font = (settings.font_family or "").strip().rstrip(",")
	accent = settings.accent_color or DEFAULT_ACCENT
	period_from, period_to = formatdate(filters.from_date), formatdate(filters.to_date)
	section_titles = {
		"balance_sheet": (
			_("Balance sheet from {0} to {1}", context="trial_balance").format(period_from, period_to),
			_("Assets", context="trial_balance"),
			_("Liabilities", context="trial_balance"),
			_("Total assets", context="trial_balance"),
			_("Total liabilities", context="trial_balance"),
		),
		"profit_and_loss": (
			_("Profit and loss from {0} to {1}", context="trial_balance").format(period_from, period_to),
			_("Costs", context="trial_balance"),
			_("Revenues", context="trial_balance"),
			_("Total costs", context="trial_balance"),
			_("Total revenues", context="trial_balance"),
		),
	}
	for section in report.sections:
		(
			section.title,
			section.left_label,
			section.right_label,
			section.left_total_label,
			section.right_total_label,
		) = section_titles[section.key]
		section.rows = paired_rows(section.left, section.right)
		section.footer = list(zip_longest(section.left_results, section.right_results))
	title = (settings.report_title or "").strip() or _("Trial balance", context="trial_balance")
	letter_head_height = max(cint(settings.letter_head_height) or 25, 5)
	# header and footer get explicit heights: Chrome measures them once and reserves the space
	header_height = 22 + 15 * 2 + 8
	if filters.get("cost_center") or filters.get("finance_book"):
		header_height += 15
	if letter_head:
		header_height += round(letter_head_height * 96 / 25.4)
	footer_height = 24 + (40 if letter_head and letter_head.footer else 0)
	return {
		"title": title,
		"company": get_company_details(filters.company),
		"filters": filters,
		"period_from": period_from,
		"period_to": period_to,
		"print_date": formatdate(nowdate()),
		"report": report,
		"settings": settings,
		"letter_head": letter_head,
		"letter_head_height": letter_head_height,
		"header_height": header_height,
		"footer_height": footer_height,
		"logo": settings.logo if not letter_head else None,
		"accent": accent,
		"accent_tint": tint(accent, 0.12),
		"accent_tint_strong": tint(accent, 0.45),
		"font_family": f"{font}, {FONT_FALLBACK}" if font else FONT_FALLBACK,
		"wkhtmltopdf": pdf_generator() == "wkhtmltopdf" if wkhtmltopdf is None else wkhtmltopdf,
		"cost_center": filters.get("cost_center"),
		"finance_book": filters.get("finance_book"),
		"amount": lambda value: fmt_money(value, 2),
		"lang": frappe.local.lang or "en",
	}


def render_html(filters, settings=None, report=None, wkhtmltopdf=None) -> str:
	return frappe.render_template(TEMPLATE, get_render_context(filters, settings, report, wkhtmltopdf))


def pdf_generator() -> str:
	"""The site's choice: site config `trial_balance_pdf_generator`, else Print Settings."""
	return frappe.conf.get(PDF_GENERATOR_CONF_KEY) or (
		frappe.db.get_single_value("Print Settings", "pdf_generator") or "wkhtmltopdf"
	)


def render_pdf(filters, html: str | None = None) -> bytes:
	html = html or render_html(filters)
	generator = pdf_generator()
	if generator != "wkhtmltopdf":
		# the same hook chain Frappe uses for print formats
		for method in frappe.get_hooks("pdf_generator"):
			pdf = frappe.get_attr(method)("Standard", html, {}, None, pdf_generator=generator)
			if pdf:
				return pdf
		# no hook knows the generator: wkhtmltopdf needs its own page margins
		html = render_html(filters, wkhtmltopdf=True)
	from frappe.utils.pdf import get_pdf

	return get_pdf(html)


def pdf_filename(filters, title: str) -> str:
	name = f"{title} {filters.company} {filters.from_date} {filters.to_date}"
	return re.sub(r"[^\w.-]+", "_", name).strip("_") + ".pdf"


@frappe.whitelist()
def download_pdf(filters: str | dict) -> None:
	filters = normalize_filters(filters)
	check_permission(filters.company)
	html = render_html(filters)
	title = (get_settings().report_title or "").strip() or _("Trial balance", context="trial_balance")
	frappe.local.response.filename = pdf_filename(filters, title)
	frappe.local.response.filecontent = render_pdf(filters, html)
	frappe.local.response.type = "pdf"
