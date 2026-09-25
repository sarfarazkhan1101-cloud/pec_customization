import frappe

from pew_customizations.crm.config import MANAGER_ROLES, WORK_ORDER_FIELD


def has_permission(doc, ptype=None, user=None, debug=False):
	"""has_permission hooks can only deny, and must return True to leave the decision to the others."""
	if doc.attached_to_doctype == "Opportunity" and doc.attached_to_field == WORK_ORDER_FIELD:
		return bool(set(frappe.get_roles(user)) & set(MANAGER_ROLES))
	return True
