"""Draftsmen see only the Tasks assigned to them, read-only.

The Draftsman role has no right on Task. When a Task is assigned to someone who cannot read it,
Frappe's own Assign To (frappe.desk.form.assign_to.add) shares it with them, read-only. The assigner
needs the Share right for that, which is why Engineers have it.

Frappe leaves that share in place when the assignment is removed, so a reassigned Task would stay
visible to the old assignee. remove_share_on_unassign takes it back.
"""

import frappe


def remove_share_on_unassign(doc, method=None):
	"""ToDo on_update: an assignment on a Task was removed (Cancelled), also when the Task itself is
	cancelled. A Task that was Completed closes its assignment instead, and stays visible."""
	if doc.reference_type != "Task" or doc.status != "Cancelled" or not doc.has_value_changed("status"):
		return
	user, task = doc.allocated_to, doc.reference_name
	if not (user and task):
		return

	still_assigned = frappe.db.exists(
		"ToDo",
		{
			"reference_type": "Task",
			"reference_name": task,
			"allocated_to": user,
			"status": ("!=", "Cancelled"),
			"name": ("!=", doc.name),
		},
	)
	if still_assigned:
		return

	share = frappe.db.get_value(
		"DocShare",
		{"share_doctype": "Task", "share_name": task, "user": user, "everyone": 0},
		["name", "write", "submit", "share"],
		as_dict=True,
	)
	# a share given by hand with more than read stays; an assignment only ever shares read
	if not share or share.write or share.submit or share.share:
		return
	frappe.delete_doc(
		"DocShare", share.name, ignore_permissions=True, flags={"ignore_share_permission": True}
	)


def share_with_assignees_who_cannot_read():
	"""Share each assigned Task, read-only, with assignees who cannot read it, as Frappe does on every
	new assignment. For assignments made while the Draftsman role still read every Task. Completed
	Tasks (assignment Closed) are shared too, so the assignee keeps their history."""
	todos = frappe.get_all(
		"ToDo",
		filters={"reference_type": "Task", "status": ("in", ("Open", "Closed"))},
		fields=["allocated_to", "reference_name"],
		distinct=True,
	)
	shared = 0
	for todo in todos:
		user, task = todo.allocated_to, todo.reference_name
		if not (user and frappe.db.exists("Task", task)):
			continue
		if not frappe.db.get_value("User", user, "enabled"):
			continue
		if frappe.has_permission("Task", "read", doc=task, user=user):
			continue
		frappe.share.add_docshare("Task", task, user, flags={"ignore_share_permission": True})
		shared += 1
	return shared
