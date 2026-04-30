function isItalianCompany(frm) {
	return (frm.doc.country || "").trim().toLowerCase() === "italy";
}

function escapeHtml(value) {
	return String(value || "")
		.replaceAll("&", "&amp;")
		.replaceAll("<", "&lt;")
		.replaceAll(">", "&gt;")
		.replaceAll('"', "&quot;")
		.replaceAll("'", "&#39;");
}

async function fetchOnboarding(frm) {
	if (!frm.doc.name || frm.is_new()) {
		return null;
	}
	const response = await frappe.call({
		method: "fab_italy_tax.company_tax_settings.get_company_tax_onboarding",
		args: { company: frm.doc.name },
		freeze: false,
	});
	return response.message || null;
}

function getStatusBadge(step) {
	if (step.status === "done") {
		return { label: __("Done"), color: "green" };
	}
	if (step.status === "pending") {
		return { label: __("Required"), color: "orange" };
	}
	return { label: __("Review"), color: "blue" };
}

async function refreshOnboardingIntro(frm) {
	if (!isItalianCompany(frm)) {
		return;
	}

	if (!frm.doc.fab_itx_enabled) {
		frm.set_intro(
			__(
				"Enable Italy Tax Management to provision VAT defaults and start the guided onboarding for year-end close, asset amortization, and fiscal adjustments."
			),
			"blue"
		);
		return;
	}

	const onboarding = await fetchOnboarding(frm);
	if (!onboarding) {
		return;
	}

	if (onboarding.pending_count > 0) {
		frm.set_intro(
			__(
				"Italy Tax onboarding has {0} required step(s) and {1} review step(s) remaining. Use Review Italy Tax Onboarding before go-live.",
				[onboarding.pending_count, onboarding.review_count]
			),
			"orange"
		);
		return;
	}

	if (onboarding.review_count > 0) {
		frm.set_intro(
			__(
				"Italy Tax base setup is ready. Review {0} guided step(s), including asset amortization and fiscal adjustment policy, before go-live.",
				[onboarding.review_count]
			),
			"blue"
		);
		return;
	}

	frm.set_intro(__("Italy Tax onboarding is complete."), "green");
}

async function openOnboardingDialog(frm) {
	const onboarding = await fetchOnboarding(frm);
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
			const badge = getStatusBadge(step);
			return `
				<div class="itx-onboarding-step" style="border: 1px solid var(--border-color); border-radius: 8px; padding: 12px; margin-bottom: 12px;">
					<div style="display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 8px;">
						<div style="font-weight: 600;">${escapeHtml(step.title)}</div>
						<span class="indicator-pill ${badge.color}">${escapeHtml(badge.label)}</span>
					</div>
					<div style="margin-bottom: 10px; color: var(--text-muted);">${escapeHtml(step.description)}</div>
					${
						step.action_label
							? `<button class="btn btn-sm btn-default itx-onboarding-action" data-step-index="${index}">${escapeHtml(step.action_label)}</button>`
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

function addOnboardingButton(frm) {
	if (!frm.doc.fab_itx_enabled || !frm.doc.name || frm.is_new()) {
		return;
	}

	frm.add_custom_button(
		__("Review Italy Tax Onboarding"),
		() => openOnboardingDialog(frm),
		__("Italy Tax")
	);
}

frappe.ui.form.on("Company", {
	refresh(frm) {
		if (!isItalianCompany(frm)) {
			return;
		}
		addOnboardingButton(frm);
		void refreshOnboardingIntro(frm);
	},
	fab_itx_enabled(frm) {
		frm.__fab_itx_just_enabled = !!frm.doc.fab_itx_enabled;
		if (frm.doc.fab_itx_enabled) {
			frappe.show_alert({
				message: __(
					"Save this Company to provision Italy Tax defaults and open the guided onboarding."
				),
				indicator: "blue",
			});
		}
	},
	async after_save(frm) {
		if (!isItalianCompany(frm)) {
			return;
		}
		await refreshOnboardingIntro(frm);
		if (frm.doc.fab_itx_enabled && frm.__fab_itx_just_enabled) {
			frm.__fab_itx_just_enabled = false;
			await openOnboardingDialog(frm);
		}
	},
});
