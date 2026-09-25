"""Execution Team access: the standard Project `users` table (relabelled "Execution Team") is the
source of truth for who may work on a Project.

Each member gets a User Permission on the Project, which limits them to their own Projects and to
everything linked to those Projects (Task, Timesheet, Scope, DCI, Query, PEC Revision). Files
attached to a Project are readable by anyone who can read it, so no per-file sharing is needed.
Members still need a role that can read Project (e.g. Projects User).
"""

import frappe
from frappe import _

from pew_customizations.crm.config import PROJECT_ACCESS_BYPASS_ROLES, PROJECT_APPROVED_STATE


def sync_team_access(doc, method=None):
	# Access is granted once the Project is approved (no workflow_state means no approval workflow).
	if doc.get("workflow_state") not in (None, "", PROJECT_APPROVED_STATE):
		return

	team = {row.user for row in doc.users if row.user}
	granted = set(_granted_users(doc.name))

	for user in sorted(team - granted):
		roles = set(frappe.get_roles(user))
		if roles & set(PROJECT_ACCESS_BYPASS_ROLES):
			continue
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": "Project",
				"for_value": doc.name,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		if not frappe.has_permission("Project", "read", user=user):
			frappe.msgprint(
				_("{0} was added to the Execution Team but has no role that can open Projects.").format(user),
				indicator="orange",
				alert=True,
			)

	for user in granted - team:
		_revoke(doc.name, user)


def revoke_all(doc, method=None):
	for user in _granted_users(doc.name):
		_revoke(doc.name, user)


def _granted_users(project):
	return frappe.get_all("User Permission", filters={"allow": "Project", "for_value": project}, pluck="user")


def _revoke(project, user):
	for name in frappe.get_all(
		"User Permission", filters={"allow": "Project", "for_value": project, "user": user}, pluck="name"
	):
		frappe.delete_doc("User Permission", name, ignore_permissions=True)
