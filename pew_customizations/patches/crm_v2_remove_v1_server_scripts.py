import frappe

from pew_customizations.crm.config import V1_SERVER_SCRIPTS


def execute():
	"""The v1 Server Scripts are replaced by pew_customizations.crm / .projects. Their fixture file is
	gone, but fixtures never delete records, so remove them here."""
	for name in V1_SERVER_SCRIPTS:
		if frappe.db.exists("Server Script", name):
			frappe.delete_doc("Server Script", name, ignore_permissions=True, force=True)
