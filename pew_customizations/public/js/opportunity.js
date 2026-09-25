// Tender pipeline UX on the standard Opportunity form. The rules themselves are enforced on the
// server (pew_customizations/crm/opportunity.py); this only guides the user.

frappe.ui.form.on("Opportunity", {
	setup(frm) {
		frm.set_query("sales_stage", () => ({ filters: { pew_stage_order: [">", 0] } }));
	},

	refresh(frm) {
		const info = pew_pipeline_info(frm);
		frm.pew_saved_stage = frm.doc.sales_stage;

		pew_show_checklist(frm, info);
		pew_setup_lost_state(frm, info);
		pew_setup_buttons(frm, info);
	},

	sales_stage(frm) {
		const info = pew_pipeline_info(frm);
		const order = info.stage_order || {};
		const from = order[frm.pew_saved_stage] || 0;
		const to = order[frm.doc.sales_stage] || 0;
		const revert = () => frm.set_value("sales_stage", frm.pew_saved_stage);

		if (!frm.pew_saved_stage || !to || to <= from) return;

		if (to === 7 && !info.is_manager) {
			frappe.msgprint(__("Only a Sales Manager can move an Opportunity to {0}.", [frm.doc.sales_stage]));
			revert();
		} else if (to - from > 1) {
			frappe.confirm(
				__(
					"This skips {0} stage(s). Every skipped stage's checklist must already be complete. Continue?",
					[to - from - 1]
				),
				null,
				revert
			);
		}
	},

	pew_stage_index(frm) {
		// fetched from the Sales Stage whenever a new stage is picked
		pew_show_current_stage(frm);
	},

	party_name(frm) {
		if (frm.doc.opportunity_from !== "Customer" || !frm.doc.party_name) return;
		frappe.db
			.get_value("Customer", frm.doc.party_name, [
				"pew_organization_type",
				"pew_parent_customer",
				"pew_is_key_account",
			])
			.then(({ message }) => {
				if (!message) return;
				if (!frm.doc.pew_organization_type && message.pew_organization_type) {
					frm.set_value("pew_organization_type", message.pew_organization_type);
				}
				frm.set_value("pew_parent_customer", message.pew_parent_customer || "");
				frm.set_value("pew_is_key_account", message.pew_is_key_account || 0);
			});
	},

	pew_go_no_go(frm) {
		if (frm.doc.pew_go_no_go !== "No-Go" || frm.is_new()) return;
		frappe.confirm(__("The decision is No-Go. Save and declare this Opportunity Lost now?"), () =>
			frm.save().then(() => frm.trigger("set_as_lost_dialog"))
		);
	},
});

frappe.ui.form.on("PEW Opportunity Document", {
	document_type(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const classes = pew_pipeline_info(frm).document_classes || {};
		frappe.model.set_value(cdt, cdn, "document_class", classes[row.document_type] || "");
	},
});

function pew_pipeline_info(frm) {
	return (frm.doc.__onload && frm.doc.__onload.pew_pipeline) || {};
}

// Opens the current stage's section on the EPC Pipeline tab and collapses the others. The sections'
// collapsible_depends_on does this on load, but Frappe only re-evaluates it on refresh.
function pew_show_current_stage(frm) {
	const current = cint(frm.doc.pew_stage_index);
	const section = frm.fields_dict[`pew_stage${current}_section`];
	if (!section) return;

	for (let idx = 1; idx <= 7; idx++) {
		const other = frm.fields_dict[`pew_stage${idx}_section`];
		// like on refresh, a section with missing mandatory fields stays open
		if (other) other.collapse(idx !== current && !other.has_missing_mandatory());
	}
	frm.layout.select_tab("pew_pipeline_tab");
	frappe.utils.scroll_to(section.wrapper, true, 15);
}

function pew_show_checklist(frm, info) {
	if (frm.is_new() || frm.doc.status === "Lost" || !info.next_stage || !(info.missing || []).length) {
		return;
	}
	const items = info.missing.map((label) => `<li>${frappe.utils.escape_html(label)}</li>`).join("");
	frm.set_intro(
		`${__("To move to <b>{0}</b>, complete:", [frappe.utils.escape_html(info.next_stage)])}
		<ul class="mb-0">${items}</ul>`,
		"yellow"
	);
}

function pew_setup_lost_state(frm, info) {
	if (frm.doc.status !== "Lost") return;

	const reasons = (frm.doc.lost_reasons || []).map((r) => r.lost_reason).join(", ");
	const lost_on = frm.doc.pew_lost_on ? frappe.datetime.str_to_user(frm.doc.pew_lost_on) : "";
	frm.dashboard.set_headline_alert(
		__("Lost at stage {0} {1}: {2}", [
			`<b>${frappe.utils.escape_html(frm.doc.sales_stage || "")}</b>`,
			lost_on ? __("on {0}", [lost_on]) : "",
			frappe.utils.escape_html(reasons),
		]),
		"red"
	);

	if (!info.is_manager) {
		frm.disable_form();
		frm.remove_custom_button(__("Reopen"));
	}
}

function pew_setup_buttons(frm, info) {
	// "Closed" is not used: a deal that is not pursued is declared Lost with a reason.
	frm.remove_custom_button(__("Close"));
	if (frm.doc.status === "Converted" || !info.is_manager) {
		frm.remove_custom_button(__("Reopen"));
	}
	if (frm.is_new()) return;

	const stage_index = cint(frm.doc.pew_stage_index);
	if (frm.doc.status !== "Lost" && stage_index < 7 && frm.perm[0] && frm.perm[0].write) {
		// v16 has no Lost button; this opens the standard Declare Lost dialog
		frm.add_custom_button(__("Declare Lost"), () => frm.trigger("set_as_lost_dialog"));
	}

	if (frm.doc.pew_project) {
		frm.add_custom_button(
			__("Project"),
			() => frappe.set_route("Form", "Project", frm.doc.pew_project),
			__("View")
		);
	}

	frm.add_custom_button(__("Link Emails"), () => pew_link_emails_dialog(frm), __("Actions"));
}

function pew_link_emails_dialog(frm, show_all = 0) {
	frappe
		.call("pew_customizations.crm.api.get_unlinked_emails", {
			opportunity: frm.doc.name,
			show_all,
		})
		.then(({ message: emails = [] }) => {
			const dialog = new frappe.ui.Dialog({
				title: __("Link Emails to {0}", [frm.doc.title || frm.doc.name]),
				size: "large",
				fields: [{ fieldtype: "HTML", fieldname: "emails" }],
				primary_action_label: __("Link Selected"),
				primary_action() {
					const names = dialog.$wrapper
						.find("input.pew-email:checked")
						.map((i, el) => el.value)
						.get();
					if (!names.length) {
						frappe.msgprint(__("Select at least one email."));
						return;
					}
					frappe
						.call("pew_customizations.crm.api.link_emails", {
							opportunity: frm.doc.name,
							communications: names,
						})
						.then(({ message }) => {
							dialog.hide();
							frappe.show_alert({
								message: __("{0} email(s) linked", [message]),
								indicator: "green",
							});
							frm.reload_doc();
						});
				},
			});

			const rows = emails
				.map(
					(e) => `<tr>
						<td><input type="checkbox" class="pew-email" value="${frappe.utils.escape_html(e.name)}"></td>
						<td>${frappe.utils.escape_html(e.subject || "")}</td>
						<td>${frappe.utils.escape_html(e.sender || "")}</td>
						<td class="text-nowrap">${frappe.datetime.str_to_user(e.communication_date)}</td>
					</tr>`
				)
				.join("");
			dialog.fields_dict.emails.$wrapper.html(
				emails.length
					? `<table class="table table-sm">
						<thead><tr><th></th><th>${__("Subject")}</th><th>${__("From")}</th><th>${__(
							"Date"
					  )}</th></tr></thead>
						<tbody>${rows}</tbody></table>`
					: `<p class="text-muted">${__(
							"No unlinked emails from this customer's contacts in the last 90 days."
					  )}</p>`
			);

			if (!show_all && pew_pipeline_info(frm).is_manager) {
				dialog.set_secondary_action_label(__("Show All Unlinked"));
				dialog.set_secondary_action(() => {
					dialog.hide();
					pew_link_emails_dialog(frm, 1);
				});
			}
			dialog.show();
		});
}
