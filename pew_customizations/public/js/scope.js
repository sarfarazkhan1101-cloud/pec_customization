frappe.ui.form.on("Scope", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.scope_template) {
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
