frappe.ui.form.on("Scope", {
	refresh(frm) {
		// the server asks for the same right (Scope.create_tasks_from_template)
		if (frm.is_new() || !frm.doc.scope_template || !frm.has_perm("write")) {
			return;
		}
		frm.add_custom_button(__("Create Tasks from Template"), () => {
			frm.call("create_tasks_from_template").then(() => {
				frm.reload_doc();
				frappe.set_route("List", "Task", { scope: frm.doc.name });
			});
		});
	},
});
