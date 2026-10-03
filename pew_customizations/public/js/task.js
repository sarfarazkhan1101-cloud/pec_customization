// Revision tracker on Task (R0 - R10). The Approval Code options come from the Task's Project.
// The rules (sequence, locked earlier revisions, 11 rows at most) are enforced on the server in
// projects/task_revisions.py; this script only keeps the grid convenient.
const PEC_MAX_REVISIONS = 11;

frappe.ui.form.on("Task", {
	refresh(frm) {
		pec_load_approval_codes(frm);
		pec_toggle_add_row(frm);
	},

	project(frm) {
		pec_load_approval_codes(frm);
	},
});

frappe.ui.form.on("PEC Task Revision", {
	pec_revisions_add(frm) {
		pec_renumber_revisions(frm);
	},

	pec_revisions_remove(frm) {
		pec_renumber_revisions(frm);
	},

	pec_revisions_move(frm) {
		pec_renumber_revisions(frm);
	},

	approval_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const code = (frm.pec_approval_codes || []).find((d) => d.code === row.approval_code);
		frappe.model.set_value(cdt, cdn, "code_description", code ? code.description : "");
	},
});

function pec_load_approval_codes(frm) {
	const grid = frm.fields_dict.pec_revisions?.grid;
	if (!grid) {
		return;
	}

	const set_options = (codes) => {
		frm.pec_approval_codes = codes;
		// codes already on the rows stay selectable, e.g. after the Task moved to another Project
		const used = (frm.doc.pec_revisions || []).map((row) => row.approval_code).filter(Boolean);
		const options = [...new Set(["", ...codes.map((d) => d.code), ...used])];
		grid.update_docfield_property("approval_code", "options", options);
	};

	if (!frm.doc.project) {
		set_options([]);
		return;
	}
	frappe
		.xcall("pew_customizations.projects.approval_codes.get_approval_codes", {
			project: frm.doc.project,
		})
		.then((codes) => set_options(codes || []));
}

// The grid redraws itself after each of the add / remove / move events
function pec_renumber_revisions(frm) {
	[...(frm.doc.pec_revisions || [])]
		.sort((a, b) => a.idx - b.idx)
		.forEach((row, position) => {
			row.revision = `R${position}`;
		});
	pec_toggle_add_row(frm);
}

function pec_toggle_add_row(frm) {
	const grid = frm.fields_dict.pec_revisions?.grid;
	if (!grid) {
		return;
	}
	grid.cannot_add_rows = (frm.doc.pec_revisions || []).length >= PEC_MAX_REVISIONS;
	grid.wrapper.find(".grid-add-row").toggleClass("hidden", grid.cannot_add_rows);
}
