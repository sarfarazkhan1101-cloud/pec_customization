import frappe


def sync_scope_from_tasks(doc, method=None):
	"""Task on_update/on_trash: roll this Task's Scope progress up as the
	average of its own (non-template) Tasks -- derived, never hand-entered --
	and auto-close the Scope once every one of its Tasks is Completed. A
	Scope that just auto-closed cascades on to check its Project too."""
	scope = doc.scope
	if not scope:
		return

	tasks = frappe.get_all(
		"Task", filters={"scope": scope, "is_template": 0}, fields=["status", "progress"]
	)
	if not tasks:
		return

	avg_progress = sum(t.progress or 0 for t in tasks) / len(tasks)
	frappe.db.set_value("Scope", scope, "progress", avg_progress, update_modified=False)

	all_completed = all(t.status == "Completed" for t in tasks)
	currently_completed = frappe.db.get_value("Scope", scope, "status") == "Completed"

	if all_completed and not currently_completed:
		frappe.db.set_value("Scope", scope, "status", "Completed", update_modified=False)
		project = frappe.db.get_value("Scope", scope, "project")
		_auto_complete_project(project)


def sync_project_from_scopes(doc, method=None):
	"""Scope on_update/on_trash: auto-close the Project once every one of its
	Scopes is Completed. Covers a Scope's status being changed directly, in
	addition to the auto-cascade in sync_scope_from_tasks above."""
	_auto_complete_project(doc.project)


def _auto_complete_project(project):
	if not project:
		return

	scopes = frappe.get_all("Scope", filters={"project": project}, fields=["status"])
	if not scopes or not all(s.status == "Completed" for s in scopes):
		return

	if frappe.db.get_value("Project", project, "status") != "Completed":
		frappe.db.set_value("Project", project, "status", "Completed", update_modified=False)


def resync_naming_series(prefix):
	"""Bring tabSeries.current up to the highest existing numeric suffix for
	`prefix` (e.g. "TASK-2026-"). This bench's Task autoname series has been
	observed to drift behind the actual max name after batches of template
	Task creation (likely NestedSet/tree naming peeks on Task consuming a
	series number without inserting a row) -- calling this before bulk-
	creating Tasks avoids a DuplicateEntryError on the next autoname."""
	max_suffix = frappe.db.sql(
		"""SELECT MAX(CAST(SUBSTRING(name, %s) AS UNSIGNED))
		FROM `tabTask` WHERE name LIKE %s""",
		(len(prefix) + 1, f"{prefix}%"),
	)[0][0]
	if not max_suffix:
		return

	frappe.db.sql(
		"""INSERT INTO `tabSeries` (name, current) VALUES (%s, %s)
		ON DUPLICATE KEY UPDATE current = GREATEST(current, %s)""",
		(prefix, max_suffix, max_suffix),
	)
