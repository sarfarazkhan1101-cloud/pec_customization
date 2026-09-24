import frappe
from frappe import _


def sync_dci_rollup(doc, method=None):
	"""Keep DCI.current_revision / overall_status in sync with whichever PEC
	Revision has the highest revision_no for that DCI. Hooked on
	on_update/on_submit/on_cancel of PEC Revision so the DCI always reflects
	the latest revision without duplicating the workflow state anywhere else."""
	if not doc.dci:
		return

	latest = frappe.db.get_value(
		"PEC Revision",
		{"dci": doc.dci},
		["name", "revision_label", "workflow_state"],
		order_by="revision_no desc",
	)
	if not latest or latest[0] != doc.name:
		return

	frappe.db.set_value(
		"DCI",
		doc.dci,
		{"current_revision": latest[1], "overall_status": latest[2]},
		update_modified=False,
	)


@frappe.whitelist()
def create_new_revision(dci):
	"""Create the next PEC Revision for a DCI: R0 if none exist yet, otherwise
	the previous revision's number + 1. Refuses to open a second revision
	while one is still active, so a DCI never has two open revisions at once
	and older revisions are never edited in place."""
	if not frappe.db.exists("DCI", dci):
		frappe.throw(_("DCI {0} not found").format(dci))

	active = frappe.db.exists(
		"PEC Revision",
		{"dci": dci, "workflow_state": ["not in", ["Revision Required", "Approved"]]},
	)
	if active:
		frappe.throw(_("Revision {0} for this DCI is still in progress.").format(active))

	latest = frappe.db.get_value(
		"PEC Revision", {"dci": dci}, ["name", "revision_no"], order_by="revision_no desc"
	)
	next_no = (latest[1] + 1) if latest else 0

	revision = frappe.new_doc("PEC Revision")
	revision.dci = dci
	revision.revision_no = next_no
	revision.previous_revision = latest[0] if latest else None
	revision.submitted_by = frappe.session.user
	revision.submission_date = frappe.utils.today()
	revision.insert()
	return revision.name
