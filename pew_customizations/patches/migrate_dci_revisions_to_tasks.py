"""The DCI is now a report over Tasks (PEC DCI Report) and each Task carries its own revisions
R0 - R10. This copies the PEC Revisions of every DCI onto the DCI's Task and gives the existing
Projects the default Approval Codes those rows use. DCI and PEC Revision records stay as they are.

Fixtures sync only after patches, so the new Project / Task fields are created here first.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import getdate

from pew_customizations.projects.approval_codes import DEFAULT_APPROVAL_CODES, get_codes
from pew_customizations.projects.task_revisions import MAX_REVISIONS, NOT_SUBMITTED, refresh_latest_fields
from pew_customizations.setup.install import get_custom_fields

# PEC Revision workflow state -> default Approval Code. Revisions still in progress get no code:
# they were submitted and are waiting for comments.
STATE_CODES = {"Approved": "1", "Revision Required": "3"}


def execute():
	create_custom_fields(
		{
			doctype: [field for field in fields if field["fieldname"].startswith("pec_")]
			for doctype, fields in get_custom_fields().items()
		},
		update=True,
	)

	_add_default_codes()

	task = frappe.qb.DocType("Task")
	(
		frappe.qb.update(task)
		.set(task.pec_latest_status, NOT_SUBMITTED)
		.where(task.is_template == 0)
		.where(task.pec_latest_status.isnull())
		.run()
	)

	skipped = []
	projects = set()
	for dci in frappe.get_all("DCI", fields=["name", "task"], order_by="creation asc"):
		project = _copy_revisions(dci, skipped)
		if project:
			projects.add(project)
	for project in projects:
		refresh_latest_fields(project)

	if skipped:
		message = "\n".join(skipped)
		print(f"PEC DCI migration, left as they are:\n{message}")
		frappe.log_error(title="PEC DCI migration: DCIs not copied to a Task", message=message)


def _add_default_codes():
	"""New Projects get the default codes on insert; the existing ones have none yet."""
	with_codes = set(frappe.get_all("PEC Approval Code", filters={"parenttype": "Project"}, pluck="parent"))
	for project in frappe.get_all("Project", pluck="name"):
		if project in with_codes:
			continue
		for idx, (code, description, closes_document) in enumerate(DEFAULT_APPROVAL_CODES, start=1):
			frappe.get_doc(
				{
					"doctype": "PEC Approval Code",
					"parent": project,
					"parenttype": "Project",
					"parentfield": "pec_approval_codes",
					"idx": idx,
					"code": code,
					"description": description,
					"closes_document": closes_document,
				}
			).db_insert()


def _copy_revisions(dci, skipped):
	"""Returns the Task's Project when rows were copied."""
	revisions = frappe.get_all(
		"PEC Revision",
		filters={"dci": dci.name, "docstatus": ("!=", 2)},
		fields=[
			"name",
			"workflow_state",
			"submission_date",
			"creation",
			"modified",
			"document_file",
			"overall_comments",
			"client_comments",
		],
		order_by="revision_no asc, creation asc",
	)

	if not dci.task or not frappe.db.exists("Task", dci.task):
		reason = f"its Task {dci.task} no longer exists" if dci.task else "no Task"
		skipped.append(f"{dci.name}: {reason} ({len(revisions)} revision(s) not copied)")
		return None
	if not revisions:
		return None
	if frappe.db.exists("PEC Task Revision", {"parent": dci.task, "parenttype": "Task"}):
		skipped.append(f"{dci.name}: Task {dci.task} already has revisions ({len(revisions)} not copied)")
		return None
	if len(revisions) > MAX_REVISIONS:
		skipped.append(
			f"{dci.name}: only the first {MAX_REVISIONS} of {len(revisions)} revisions were copied"
		)

	project = frappe.db.get_value("Task", dci.task, "project")
	codes = {row.code: row for row in get_codes(project)}

	for position, revision in enumerate(revisions[:MAX_REVISIONS]):
		code = STATE_CODES.get(revision.workflow_state)
		if code not in codes:
			code = None
		stages = frappe.get_all(
			"PEC Revision Review Stage",
			filters={"parent": revision.name},
			fields=["reviewed_on", "comments"],
			order_by="sequence asc",
		)
		frappe.get_doc(
			{
				"doctype": "PEC Task Revision",
				"parent": dci.task,
				"parenttype": "Task",
				"parentfield": "pec_revisions",
				"idx": position + 1,
				"revision": f"R{position}",
				"submission_date": revision.submission_date or getdate(revision.creation),
				"received_date": _received_date(revision, stages) if code else None,
				"approval_code": code,
				"code_description": codes[code].description if code else None,
				"document_link": revision.document_file,
				"notes": _notes(dci, revision, stages),
			}
		).db_insert()
	return project


def _received_date(revision, stages):
	"""When the review was decided: the last review stage, otherwise the revision's last change."""
	reviewed_on = [stage.reviewed_on for stage in stages if stage.reviewed_on]
	received = getdate(max(reviewed_on) if reviewed_on else revision.modified)
	submitted = getdate(revision.submission_date or revision.creation)
	return received if received >= submitted else None


def _notes(dci, revision, stages):
	notes = [f"Copied from {revision.name} ({dci.name}), {revision.workflow_state}."]
	notes += [comment for comment in (revision.overall_comments, revision.client_comments) if comment]
	notes += [stage.comments for stage in stages if stage.comments]
	return "\n".join(notes)
