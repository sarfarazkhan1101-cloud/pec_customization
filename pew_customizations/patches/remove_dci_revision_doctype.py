import frappe


def execute():
	"""Revisions moved from the DCI Revision child table into the standalone,
	Workflow-driven PEC Revision doctype (0 rows existed in DCI Revision at the
	time of this change, so there is no data to migrate). Runs pre_model_sync,
	before dci.json (which has already dropped the `revisions` field) and the
	now-deleted doctype/dci_revision/ folder are synced, so nothing references
	DCI Revision by the time doctype sync runs."""
	frappe.delete_doc("DocType", "DCI Revision", force=True, ignore_missing=True)
