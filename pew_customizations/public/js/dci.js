frappe.ui.form.on("DCI", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		const label = frm.doc.current_revision ? __("Create Next Revision") : __("Create Revision (R0)");
		frm.add_custom_button(label, () => {
			frappe.call({
				method: "pew_customizations.pec_revision_utils.create_new_revision",
				args: { dci: frm.doc.name },
				callback: (r) => {
					if (r.message) {
						frappe.set_route("Form", "PEC Revision", r.message);
					}
				},
			});
		});

		frm.add_custom_button(__("Revision History"), () => {
			frappe.set_route("List", "PEC Revision", { dci: frm.doc.name });
		});
	},
});
