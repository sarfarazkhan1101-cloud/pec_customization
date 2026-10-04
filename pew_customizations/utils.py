import frappe
from frappe import _

# Tasks that need no more work. ERPNext's own Project % Complete counts both as done.
FINISHED_TASK_STATUSES = ("Completed", "Cancelled")
# Scopes that need no more work
FINISHED_SCOPE_STATUSES = ("Completed", "Closed")


def validate_task_scope(doc, method=None):
	"""Task validate: a Task belongs to the Project of its Scope, so Project -> Scope -> Task stays
	one chain for the roll-up below and for the DCI report."""
	if not doc.get("scope"):
		return

	scope_project = frappe.db.get_value("Scope", doc.scope, "project")
	if not doc.project:
		doc.project = scope_project
	elif doc.project != scope_project:
		frappe.throw(
			_("Scope {0} belongs to Project {1}, not to Project {2}.").format(
				frappe.bold(doc.scope), frappe.bold(scope_project), frappe.bold(doc.project)
			),
			title=_("Scope Is In Another Project"),
		)


def sync_scope_from_tasks(doc, method=None):
	"""Task on_update/after_delete: roll the Task's Scope up from its Tasks, then check the Project.
	A Task that moved to another Scope updates the Scope it left as well."""
	before = doc.get_doc_before_save()
	projects = {doc.project}
	for scope in {doc.get("scope"), before.get("scope") if before else None}:
		if scope:
			projects.add(_sync_scope(scope))

	for project in projects:
		_sync_project(project)


def _sync_scope(scope):
	"""Progress is the average of the Scope's (non-template) Tasks -- derived, never hand-entered --
	and the Scope is Completed for as long as every one of them is. Cancelled Tasks are left out.
	Returns the Scope's Project."""
	details = frappe.db.get_value("Scope", scope, ["status", "project"], as_dict=True)
	if not details:
		return None

	tasks = frappe.get_all(
		"Task",
		filters={"scope": scope, "is_template": 0, "status": ("!=", "Cancelled")},
		fields=["status", "progress"],
	)
	values = {"progress": sum(t.progress or 0 for t in tasks) / len(tasks) if tasks else 0}
	if tasks:
		all_completed = all(t.status == "Completed" for t in tasks)
		if all_completed and details.status != "Completed":
			values["status"] = "Completed"
		elif not all_completed and details.status == "Completed":
			# a Task was reopened, added or moved in: there is work left
			values["status"] = "In Progress"

	frappe.db.set_value("Scope", scope, values, update_modified=False)
	return details.project


def sync_project_from_scopes(doc, method=None):
	"""Scope on_update/after_delete: covers a Scope's status being changed directly, a new Scope and
	a deleted one, in addition to the cascade in sync_scope_from_tasks above."""
	before = doc.get_doc_before_save()
	for project in {doc.project, before.project if before else None}:
		_sync_project(project)


def validate_project_status(doc, method=None):
	"""Project validate: ERPNext recomputes the status from the Tasks on every save, so the Scope
	rule is applied on top of it here."""
	if not doc.is_new():
		doc.status = _get_project_status(doc.name, doc.status, doc.percent_complete_method)


def _sync_project(project):
	if not project:
		return

	details = frappe.db.get_value("Project", project, ["status", "percent_complete_method"], as_dict=True)
	if not details:
		return

	status = _get_project_status(project, details.status, details.percent_complete_method)
	if status != details.status:
		frappe.db.set_value("Project", project, "status", status, update_modified=False)


def _get_project_status(project, status, percent_complete_method):
	"""A Project with Scopes is Completed once every Scope is finished and no Task is left open.
	ERPNext alone completes it as soon as all existing Tasks are done, which is too early while a
	Scope is still open, e.g. because its Tasks are not generated yet."""
	if status == "Cancelled":
		return status

	scopes = frappe.get_all("Scope", filters={"project": project}, pluck="status")
	if not scopes:
		return status  # no Scopes: ERPNext's own rule stands

	if all(scope_status in FINISHED_SCOPE_STATUSES for scope_status in scopes):
		open_task = frappe.db.exists(
			"Task", {"project": project, "is_template": 0, "status": ("not in", FINISHED_TASK_STATUSES)}
		)
		return status if open_task else "Completed"

	# a manually tracked Project keeps the status its manager gave it
	return status if percent_complete_method == "Manual" else "Open"


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
