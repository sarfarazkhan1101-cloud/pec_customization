// Draftsmen have no role right on Task: they see only the Tasks assigned to them (shared with them,
// see projects/task_access.py). Their list opens on the unfinished ones (ERPNext's default is
// Status = Open, which hides Working, Pending Review and Overdue). Completed Tasks are one filter
// away. A user's own saved filters still come first.
(() => {
	const settings = frappe.listview_settings["Task"];
	const meta = frappe.get_meta("Task");
	// by role: frappe.perm.has_perm also counts the Tasks shared with the user
	if (!settings || !meta || frappe.perm.get_role_permissions(meta)[0].read) {
		return;
	}
	settings.filters = [["status", "not in", ["Completed", "Cancelled"]]];
})();
