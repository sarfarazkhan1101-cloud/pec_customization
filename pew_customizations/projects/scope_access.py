"""Engineers work in the Scopes assigned to them: a Scope's Assigned Engineer gets a User Permission
on it, the same mechanism as the Execution Team on Project (project_team.py).

Frappe then shows an Engineer only their own Scopes and the Tasks in them, and refuses a new Task in
any other Scope. Tasks assigned to them elsewhere stay visible: Frappe shares those with them.
"""

import frappe

from pew_customizations.crm.config import PROJECT_ACCESS_BYPASS_ROLES

ENGINEER_ROLE = "Engineer"


def sync_engineer_access(doc, method=None):
	"""Scope on_update: the Assigned Engineer gets the Scope, a replaced one loses it."""
	before = doc.get_doc_before_save()
	previous = before.get("assigned_engineer") if before else None
	if previous and previous != doc.assigned_engineer:
		_revoke(doc.name, previous)

	engineer = doc.assigned_engineer
	if not engineer or not _restricted(engineer):
		return
	if not frappe.db.exists("User Permission", {"user": engineer, "allow": "Scope", "for_value": doc.name}):
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": engineer,
				"allow": "Scope",
				"for_value": doc.name,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)


def revoke_all(doc, method=None):
	"""Scope on_trash: a User Permission would otherwise block the delete (it links to the Scope)."""
	for user in frappe.get_all(
		"User Permission", filters={"allow": "Scope", "for_value": doc.name}, pluck="user"
	):
		_revoke(doc.name, user)


def _restricted(user):
	"""Only Engineers are limited to their Scopes; managers see every Scope."""
	roles = set(frappe.get_roles(user))
	return ENGINEER_ROLE in roles and not roles & set(PROJECT_ACCESS_BYPASS_ROLES)


def _revoke(scope, user):
	for name in frappe.get_all(
		"User Permission", filters={"allow": "Scope", "for_value": scope, "user": user}, pluck="name"
	):
		frappe.delete_doc("User Permission", name, ignore_permissions=True)
