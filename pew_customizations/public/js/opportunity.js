// Tender pipeline UX on the standard Opportunity form. The rules themselves are enforced on the
// server (pew_customizations/crm/opportunity.py); this only guides the user.

// Mirrors PIPELINE_STAGES in crm/config.py (a test keeps them in sync). Unsaved Opportunities have no
// __onload, hence this list instead of pew_pipeline_info().stage_order.
const PEW_STAGES = [
	"Cold",
	"Inquiry / Tender",
	"Qualification",
	"Queries & Clarifications",
	"Proposal Submitted",
	"Evaluation",
	"Closure (Won)",
];
const PEW_WON = PEW_STAGES.length;

frappe.ui.form.on("Opportunity", {
	setup(frm) {
		frm.set_query("sales_stage", () => ({ filters: { pew_stage_order: [">", 0] } }));
	},

	refresh(frm) {
		const info = pew_pipeline_info(frm);
		frm.pew_saved_stage = frm.doc.sales_stage;

		pew_sort_stage_options(frm);
		pew_render_stage_progress(frm);
		pew_show_checklist(frm, info);
		pew_setup_lost_state(frm, info);
		pew_setup_buttons(frm, info);
	},

	sales_stage(frm) {
		pew_render_stage_progress(frm);

		const from = pew_stage_number(frm.pew_saved_stage);
		const to = pew_stage_number(frm.doc.sales_stage);
		if (frm.is_new() || !from || !to || to <= from) return;

		pew_confirm_forward_move(frm, from, to).catch(() =>
			frm.set_value("sales_stage", frm.pew_saved_stage)
		);
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

// 1-based position in the pipeline, 0 for an empty or unknown stage
function pew_stage_number(stage) {
	return PEW_STAGES.indexOf(stage) + 1;
}

// Frappe sorts link results alphabetically on the server, so the Sales Stage dropdown is re-sorted
// into pipeline order here (display only).
function pew_sort_stage_options(frm) {
	const awesomplete = frm.fields_dict.sales_stage && frm.fields_dict.sales_stage.awesomplete;
	if (!awesomplete) return;

	// unknown entries (filter note, "Create a new", "Advanced Search") keep their place at the end
	const position = (item) => pew_stage_number(item.value) || PEW_STAGES.length + 1;
	awesomplete.sort = (a, b) => position(a) - position(b);
}

// Prompts before moving forward, shared by the Sales Stage dropdown and the progress bar. Resolves
// when the move may go ahead; rejects when it is not allowed or the user cancels. The server re-checks
// both rules, so this is guidance only.
function pew_confirm_forward_move(frm, from, to) {
	return new Promise((resolve, reject) => {
		if (to === PEW_WON && !pew_pipeline_info(frm).is_manager) {
			frappe.msgprint(
				__("Only a Sales Manager can move an Opportunity to {0}.", [
					PEW_STAGES[PEW_WON - 1],
				])
			);
			reject();
		} else if (to - from > 1) {
			frappe.confirm(
				__(
					"This skips {0} stage(s). Every skipped stage's checklist must already be complete. Continue?",
					[to - from - 1]
				),
				resolve,
				reject
			);
		} else {
			resolve();
		}
	});
}

// Styles of the progress bar. They ship with this form script rather than pew_customizations.css:
// browsers cache /assets files for 12 hours and that URL carries no version, while this script is
// reloaded with the DocType. Colours are tokens on the bar, redefined for dark mode. Each step is a
// chevron cut with clip-path; every step after the first slides under the previous arrow by the arrow
// depth minus the gap, so arrow and notch nest with a thin gap between them.
const PEW_STAGE_PROGRESS_CSS = `
.pew-stage-progress {
	--pew-arrow: 14px;
	--pew-gap: 5px;
	--pew-todo-bg: #edf1f4;
	--pew-todo-fg: #8a97a4;
	--pew-done-bg: #dbe2e9;
	--pew-done-fg: #2d3a46;
	--pew-current-bg: #178074;
	--pew-current-fg: #ffffff;
	--pew-won-bg: #d3efe9;
	--pew-won-fg: #11645a;
	--pew-lost-bg: #cf3535;
	--pew-lost-fg: #ffffff;
	--pew-hover: brightness(0.95);
	margin: var(--margin-sm) 0 var(--margin-md);
	padding-inline: var(--padding-md); /* same inset as the page title and breadcrumb */
}
[data-theme="dark"] .pew-stage-progress {
	--pew-todo-bg: #242b33;
	--pew-todo-fg: #7f8c99;
	--pew-done-bg: #36424e;
	--pew-done-fg: #dbe2e9;
	--pew-current-bg: #1f9d8e;
	--pew-won-bg: #173f39;
	--pew-won-fg: #8fe0d3;
	--pew-lost-bg: #c43c3c;
	--pew-hover: brightness(1.15);
}
.pew-stage-progress-head {
	display: flex;
	flex-wrap: wrap;
	align-items: baseline;
	justify-content: space-between;
	gap: 2px var(--margin-sm);
	margin-bottom: var(--padding-sm);
}
.pew-stage-progress-title {
	white-space: nowrap;
	font-size: var(--text-lg);
	font-weight: var(--weight-semibold);
	color: var(--heading-color, var(--text-color));
}
.pew-stage-progress-count {
	font-size: var(--text-sm);
	color: var(--text-muted);
	white-space: nowrap;
}
.pew-stage-steps {
	display: flex;
	overflow: hidden; /* never a scrollbar: see pew_fit_stage_progress */
	border-radius: var(--border-radius-md); /* rounds the outer ends of the first and last step */
}
.pew-stage-step {
	/* equal shares of the row, but never narrower than the label */
	flex: 1 1 0;
	min-width: max-content;
	display: flex;
	align-items: center;
	justify-content: center;
	gap: 6px;
	margin: 0 0 0 calc(var(--pew-gap) - var(--pew-arrow));
	padding: 10px calc(var(--pew-arrow) + 6px);
	border: 0;
	border-radius: 0;
	font-size: var(--text-base);
	font-weight: var(--weight-medium);
	line-height: 20px;
	white-space: nowrap;
	background-color: var(--pew-todo-bg);
	color: var(--pew-todo-fg);
	cursor: pointer;
	clip-path: polygon(0 0, calc(100% - var(--pew-arrow)) 0, 100% 50%,
		calc(100% - var(--pew-arrow)) 100%, 0 100%, var(--pew-arrow) 50%);
	transition: background-color 0.2s, color 0.2s, filter 0.2s;
}
.pew-stage-step:first-child {
	margin-left: 0;
	clip-path: polygon(0 0, calc(100% - var(--pew-arrow)) 0, 100% 50%,
		calc(100% - var(--pew-arrow)) 100%, 0 100%);
}
.pew-stage-step:last-child {
	clip-path: polygon(0 0, 100% 0, 100% 100%, 0 100%, var(--pew-arrow) 50%);
}
.pew-stage-name {
	min-width: 0;
	overflow: hidden;
	text-overflow: ellipsis;
}
.pew-stage-num {
	display: none;
}
.pew-stage-done {
	background-color: var(--pew-done-bg);
	color: var(--pew-done-fg);
}
.pew-stage-done::before {
	content: "\\2713";
	font-weight: var(--weight-semibold);
}
.pew-stage-progress[data-state="won"] .pew-stage-done {
	background-color: var(--pew-won-bg);
	color: var(--pew-won-fg);
}
.pew-stage-current {
	background-color: var(--pew-current-bg);
	color: var(--pew-current-fg);
	font-weight: var(--weight-semibold);
}
.pew-stage-lost {
	background-color: var(--pew-lost-bg);
	color: var(--pew-lost-fg);
	font-weight: var(--weight-semibold);
}
.pew-stage-step:disabled {
	cursor: default;
}
.pew-stage-step:not(:disabled):hover {
	filter: var(--pew-hover);
}
.pew-stage-todo:not(:disabled):hover {
	color: var(--pew-done-fg);
}
.pew-stage-step:focus-visible {
	outline: none; /* would be cut off by the chevron */
	text-decoration: underline;
	text-underline-offset: 4px;
}
/* When the full labels do not fit (see pew_fit_stage_progress), completed steps shrink to their tick
   first ("short"), then upcoming ones to their number ("compact"). Full names stay in the tooltip and
   the current step always keeps its name, cut off with an ellipsis only on very small screens. */
.pew-stage-short .pew-stage-done,
.pew-stage-compact .pew-stage-todo {
	min-width: calc(2 * var(--pew-arrow) + 14px);
	padding-inline: calc(var(--pew-arrow) + 2px);
}
.pew-stage-short .pew-stage-done .pew-stage-name,
.pew-stage-compact .pew-stage-todo .pew-stage-name {
	display: none;
}
.pew-stage-compact .pew-stage-todo .pew-stage-num {
	display: inline;
}
.pew-stage-compact .pew-stage-step[aria-current] {
	flex: 1 1 auto;
	min-width: 0;
}
`;

// Chevron bar between the page header and the form, spanning the form and its sidebar like ERPNext's
// Lead Progress: stages before the current one are completed, the current one is highlighted, later
// ones are light. It reads and writes the standard sales_stage field; there is no separate value.
function pew_render_stage_progress(frm) {
	let $bar = frm.page.wrapper.find(".pew-stage-progress");
	if (!$bar.length) {
		// built once: Frappe reuses the same page (and frm) for every Opportunity that is opened
		frappe.dom.set_style(PEW_STAGE_PROGRESS_CSS, "pew-stage-progress-css");
		$bar = $(`<div class="pew-stage-progress">
			<div class="pew-stage-progress-head">
				<div class="pew-stage-progress-title">${__("Sales Stage Progress")}</div>
				<div class="pew-stage-progress-count"></div>
			</div>
			<nav class="pew-stage-steps" aria-label="${__("Sales Stage")}"></nav>
		</div>`).insertBefore(frm.page.main.closest(".layout-main"));

		$bar.on("click", ".pew-stage-step", (e) =>
			pew_move_to_stage(frm, cint(e.currentTarget.dataset.stage))
		);
		// the bar sits outside the page's views, so it hides itself while Print view is open
		frm.page.wrapper.on("view-change", () =>
			$bar.toggle(!frm.page.current_view_name || frm.page.current_view_name === "main")
		);
		// window resized, sidebar toggled, ...
		new ResizeObserver(() => pew_fit_stage_progress($bar)).observe($bar.get(0));
	}

	const current = pew_stage_number(frm.doc.sales_stage);
	const lost = frm.doc.status === "Lost";
	// a Lost deal is read-only until a Sales Manager reopens it, so its bar is display only
	const editable = !lost && Boolean(frm.perm[0] && frm.perm[0].write);

	// "won" tints the completed steps green; "lost" is shown on the current step itself
	$bar.attr("data-state", lost ? "lost" : current === PEW_WON ? "won" : "open");
	$bar.find(".pew-stage-progress-count").text(
		current ? __("Stage {0} of {1}", [current, PEW_WON]) : ""
	);

	const steps = PEW_STAGES.map((stage, i) => {
		const idx = i + 1;
		const state = idx < current ? "done" : idx > current ? "todo" : lost ? "lost" : "current";
		const name = frappe.utils.escape_html(__(stage));
		const label = name + (state === "lost" ? ` · ${__("Lost")}` : "");
		return `<button type="button" class="pew-stage-step pew-stage-${state}" data-stage="${idx}"
			title="${__("{0} (stage {1} of {2})", [name, idx, PEW_WON])}"
			${idx === current ? 'aria-current="step"' : ""}
			${!editable || idx === current ? "disabled" : ""}>
			<span class="pew-stage-num">${idx}</span><span class="pew-stage-name">${label}</span>
		</button>`;
	});
	$bar.find(".pew-stage-steps").html(steps.join(""));
	pew_fit_stage_progress($bar);
}

// Picks the widest layout that fits on one row: full labels, then "short", then "compact". Measured
// rather than a fixed breakpoint because the width depends on the sidebar, the font, the zoom level
// and the translated stage names.
function pew_fit_stage_progress($bar) {
	const steps = $bar.find(".pew-stage-steps").get(0);
	const overflows = () => steps.scrollWidth > steps.clientWidth + 1;

	$bar.removeClass("pew-stage-short pew-stage-compact");
	if (overflows()) $bar.addClass("pew-stage-short");
	if (overflows()) $bar.addClass("pew-stage-compact");
}

// Click on a progress bar step. A saved Opportunity is moved on the server, like a Kanban drag, so
// the stage gates in crm/opportunity.py decide and a rejected move leaves the form untouched. On
// success the form reloads and opens the new stage's section on the EPC Pipeline tab.
function pew_move_to_stage(frm, to) {
	const stage = PEW_STAGES[to - 1];
	if (!stage) return;
	const stage_html = `<b>${frappe.utils.escape_html(__(stage))}</b>`;

	// not complete yet: only set the field, Save validates it
	if (frm.is_new()) {
		frm.set_value("sales_stage", stage);
		return;
	}

	// the reload after the move would drop unsaved edits, so they are saved first
	if (frm.is_dirty()) {
		frappe.confirm(__("Save your changes and move to {0}?", [stage_html]), () =>
			frm.save().then(() => !frm.is_dirty() && pew_move_to_stage(frm, to))
		);
		return;
	}

	const from = pew_stage_number(frm.doc.sales_stage);
	if (to === from) return; // already there, e.g. after saving a stage picked in the dropdown
	const allowed =
		to > from
			? pew_confirm_forward_move(frm, from, to)
			: new Promise((resolve, reject) =>
					frappe.confirm(
						__("Move this Opportunity back to {0}?", [stage_html]),
						resolve,
						reject
					)
			  );

	allowed.then(
		// the callback only runs when the save succeeded; the server shows why it did not
		() =>
			frappe.db.set_value(frm.doctype, frm.docname, "sales_stage", stage, () =>
				frm.reload_doc().then(() => pew_show_current_stage(frm))
			),
		() => {}
	);
}

// Opens the current stage's section on the EPC Pipeline tab and collapses the others. The sections'
// collapsible_depends_on does this on load, but Frappe only re-evaluates it on refresh.
function pew_show_current_stage(frm) {
	const current = cint(frm.doc.pew_stage_index);
	const section = frm.fields_dict[`pew_stage${current}_section`];
	if (!section) return;

	for (let idx = 1; idx <= PEW_WON; idx++) {
		const other = frm.fields_dict[`pew_stage${idx}_section`];
		// like on refresh, a section with missing mandatory fields stays open
		if (other) other.collapse(idx !== current && !other.has_missing_mandatory());
	}
	// a new Opportunity fetches the index from the default stage on load, so it stays on Details
	if (frm.is_new()) return;
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
	if (frm.doc.status !== "Lost" && stage_index < PEW_WON && frm.perm[0] && frm.perm[0].write) {
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
