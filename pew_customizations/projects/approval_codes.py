"""Approval Codes of a Project (the `pec_approval_codes` table): the answers a client can give to a
submitted document, e.g. 1 = no comments, 3 = revise and resubmit. They are set per Project, and every
Task revision of that Project picks its Approval Code from them (see projects/task_revisions.py).
"""

import frappe
from frappe import _
from frappe.query_builder.functions import IfNull
from frappe.utils import cstr

# (code, description, closes_document). Pre-filled on new Projects; users can edit the set.
DEFAULT_APPROVAL_CODES = [
	("1", "No comments, proceed", 1),
	("2", "Proceed with comments incorporated", 0),
	("3", "Revise and resubmit", 0),
	("4", "For information only", 0),
]


def get_codes(project):
	"""The Project's codes in table order: [{code, description, closes_document}]."""
	if not project:
		return []
	return frappe.get_all(
		"PEC Approval Code",
		filters={"parent": project, "parenttype": "Project", "parentfield": "pec_approval_codes"},
		fields=["code", "description", "closes_document"],
		order_by="idx asc",
	)


@frappe.whitelist()
def get_approval_codes(project: str | None = None):
	"""For the Task revision grid and the DCI report filter. Anyone who may read Tasks can read the
	codes: the Execution Team's roles do not all open the Project form itself."""
	frappe.has_permission("Task", "read", throw=True)
	return get_codes(project)


def set_default_codes(doc, method=None):
	"""Project before_insert, so it covers Projects created by hand and from a won Opportunity."""
	# the Custom Field arrives with the fixtures, after the first migrate's patches
	if doc.get("pec_approval_codes") or not doc.meta.has_field("pec_approval_codes"):
		return
	for code, description, closes_document in DEFAULT_APPROVAL_CODES:
		doc.append(
			"pec_approval_codes",
			{"code": code, "description": description, "closes_document": closes_document},
		)


def validate_codes(doc, method=None):
	if not doc.meta.has_field("pec_approval_codes"):
		return

	seen = set()
	for row in doc.get("pec_approval_codes"):
		row.code = cstr(row.code).strip()
		if row.code.lower() in seen:
			frappe.throw(
				_("Row {0}: Approval Code {1} is already in the list.").format(
					row.idx, frappe.bold(row.code)
				),
				title=_("Duplicate Approval Code"),
			)
		seen.add(row.code.lower())

	if not doc.is_new():
		_validate_codes_in_use(doc)


def _validate_codes_in_use(doc):
	"""A code that Task revisions already carry cannot be removed or renamed, otherwise those
	documents drop out of the DCI report's count per code."""
	revision = frappe.qb.DocType("PEC Task Revision")
	task = frappe.qb.DocType("Task")
	used = (
		frappe.qb.from_(revision)
		.join(task)
		.on(task.name == revision.parent)
		.select(revision.approval_code)
		.distinct()
		.where(revision.parenttype == "Task")
		.where(task.project == doc.name)
		.where(IfNull(revision.approval_code, "") != "")
		.run(pluck=True)
	)
	missing = sorted(set(used) - {row.code for row in doc.get("pec_approval_codes")})
	if missing:
		frappe.throw(
			_(
				"Approval Code {0} is used in the revisions of this Project's Tasks, so it cannot be removed or renamed."
			).format(frappe.bold(", ".join(missing))),
			title=_("Approval Code In Use"),
		)


def refresh_task_status(doc, method=None):
	"""Project on_update: a Task's Latest Status says "Approved" when its latest code closes the
	document, so it is recomputed when the set of closing codes changes."""
	before = doc.get_doc_before_save()
	if not before or _closing_codes(before) == _closing_codes(doc):
		return

	from pew_customizations.projects.task_revisions import refresh_latest_fields

	refresh_latest_fields(doc.name)


def _closing_codes(doc):
	return {row.code for row in doc.get("pec_approval_codes") or [] if row.closes_document}
