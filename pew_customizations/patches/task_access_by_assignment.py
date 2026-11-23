"""Task access by the role matrix (Manager / Engineer / Draftsman):

1. Task rights: Engineers may create and share Tasks; Draftsmen have no right on Task, so they see
   only the Tasks shared with them by assignment (projects/task_access.py). The HRMS Employee role
   loses its select right on Task, which listed every Task to Draftsmen.
   fixtures/12_custom_docperm.json writes the same Engineer / Draftsman values after the patches;
   they are applied here first so that step 3 sees them.
2. Each Scope's Assigned Engineer gets a User Permission on it (projects/scope_access.py).
3. Tasks already assigned to users who can no longer read them are shared with them, read-only.
"""

import frappe
from frappe.permissions import update_permission_property

from pew_customizations.projects.scope_access import sync_engineer_access
from pew_customizations.projects.task_access import share_with_assignees_who_cannot_read
from pew_customizations.setup.install import create_task_permissions


def execute():
	create_task_permissions()
	if frappe.db.exists("Custom DocPerm", {"parent": "Task", "role": "Employee", "permlevel": 0}):
		update_permission_property("Task", "Employee", 0, "select", 0)

	for name in frappe.get_all("Scope", filters={"assigned_engineer": ("is", "set")}, pluck="name"):
		sync_engineer_access(frappe.get_doc("Scope", name))

	shared = share_with_assignees_who_cannot_read()
	if shared:
		print(f"Shared {shared} assigned Task(s) with assignees who can no longer read them.")
