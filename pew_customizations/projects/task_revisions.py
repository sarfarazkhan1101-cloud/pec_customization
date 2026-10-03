"""Revision tracker on Task. Each Task is one deliverable document; its `pec_revisions` rows are the
submissions R0 to R10 and the client's answer to each. The latest row is summarised in the Task's
pec_latest_* fields and in the PEC DCI Report; both go through summarize().

Revisions never change Task status or progress: the Task -> Scope -> Project roll-up stays in utils.py.
"""

import frappe
from frappe import _
from frappe.utils import cstr, getdate

from pew_customizations.projects.approval_codes import get_codes

MAX_REVISIONS = 11  # R0 .. R10
# May still change a revision once a later one exists
LOCK_BYPASS_ROLES = ("System Manager", "PEC Administrator")
# What a user enters on a row; `revision` and `code_description` are derived
ROW_FIELDS = (
	"submission_date",
	"received_date",
	"approval_code",
	"document_link",
	"comment_attachment",
	"notes",
)

# Groups of Latest Status, used by the DCI report's filter and summary
NOT_SUBMITTED = "Not Submitted"
AWAITING_COMMENTS = "Awaiting Comments"
CODE_RECEIVED = "Code Received"
APPROVED = "Approved"
STATUS_GROUPS = [NOT_SUBMITTED, AWAITING_COMMENTS, CODE_RECEIVED, APPROVED]


def summarize(rows, closing_codes):
	"""Latest-revision summary of one document. `rows` are its revisions in order, R0 first."""
	summary = frappe._dict(
		revision=None,
		submission_date=None,
		received_date=None,
		code=None,
		status=NOT_SUBMITTED,
		status_group=NOT_SUBMITTED,
	)
	if not rows:
		return summary

	last = rows[-1]
	revision = f"R{len(rows) - 1}"
	code = last.get("approval_code") or None
	summary.update(
		revision=revision,
		submission_date=last.get("submission_date"),
		received_date=last.get("received_date"),
		code=code,
	)
	if not code:
		summary.status = f"{revision} Submitted – Awaiting Comments"  # noqa: RUF001 (client's wording)
		summary.status_group = AWAITING_COMMENTS
	elif code in closing_codes:
		summary.status = f"Approved ({revision}, Code {code})"
		summary.status_group = APPROVED
	else:
		summary.status = f"{revision} Code {code} Received"
		summary.status_group = CODE_RECEIVED
	return summary


def get_revisions(tasks):
	"""Revision rows of many Tasks in one query: {task: [rows in order]}."""
	revisions = {}
	if not tasks:
		return revisions
	for row in frappe.get_all(
		"PEC Task Revision",
		filters={"parenttype": "Task", "parentfield": "pec_revisions", "parent": ("in", tasks)},
		fields=["parent", "submission_date", "received_date", "approval_code"],
		order_by="parent asc, idx asc",
	):
		revisions.setdefault(row.parent, []).append(row)
	return revisions


def refresh_latest_fields(project):
	"""Recompute pec_latest_* on the Tasks of `project` without saving them."""
	closing_codes = _closing_codes(get_codes(project))
	tasks = frappe.get_all("Task", filters={"project": project, "is_template": 0}, pluck="name")
	for task, rows in get_revisions(tasks).items():
		frappe.db.set_value(
			"Task", task, _latest_fields(summarize(rows, closing_codes)), update_modified=False
		)


def _closing_codes(codes):
	return {row.code for row in codes if row.closes_document}


def _latest_fields(summary):
	return {
		"pec_latest_revision": summary.revision,
		"pec_latest_submission_date": summary.submission_date,
		"pec_latest_received_date": summary.received_date,
		"pec_latest_code": summary.code,
		"pec_latest_status": summary.status,
	}


def validate(doc, method=None):
	# the Custom Fields arrive with the fixtures, after the first migrate's patches
	if doc.is_template or not doc.meta.has_field("pec_revisions"):
		return

	_validate_document_number(doc)

	rows = doc.get("pec_revisions") or []
	old = doc.get_doc_before_save()
	old_rows = (old.get("pec_revisions") or []) if old else []

	if len(rows) > MAX_REVISIONS:
		frappe.throw(
			_("A document can have at most {0} revisions (R0 to R{1}).").format(
				MAX_REVISIONS, MAX_REVISIONS - 1
			),
			title=_("Too Many Revisions"),
		)

	if not set(frappe.get_roles()) & set(LOCK_BYPASS_ROLES):
		_validate_locked_rows(rows, old_rows)

	# The revision number is the row's position, so rows cannot be put out of sequence
	old_by_name = {row.name: row for row in old_rows}
	for position, row in enumerate(rows):
		row.revision = f"R{position}"
		if position and row.name not in old_by_name and not rows[position - 1].approval_code:
			frappe.throw(
				_("{0} can be added only after {1} has an Approval Code.").format(
					frappe.bold(row.revision), frappe.bold(f"R{position - 1}")
				),
				title=_("Previous Revision Is Still Open"),
			)

	codes = {row.code: row for row in get_codes(doc.project)} if rows else {}
	for row in rows:
		old_row = old_by_name.get(row.name)
		# untouched rows are not re-checked, so a Task with older revisions can always be saved
		if not old_row or _values(row) != _values(old_row):
			_validate_row(doc, row, codes)

	doc.update(_latest_fields(summarize(rows, _closing_codes(codes.values()))))


def _validate_document_number(doc):
	doc.pec_document_number = cstr(doc.pec_document_number).strip() or None
	if not doc.pec_document_number or not doc.project:
		return
	if not (doc.is_new() or doc.has_value_changed("pec_document_number") or doc.has_value_changed("project")):
		return

	duplicate = frappe.db.get_value(
		"Task",
		{
			"project": doc.project,
			"pec_document_number": doc.pec_document_number,
			"name": ("!=", doc.name or ""),
		},
	)
	if duplicate:
		frappe.throw(
			_("Document Number {0} is already used by Task {1} in this Project.").format(
				frappe.bold(doc.pec_document_number), frappe.bold(duplicate)
			),
			title=_("Duplicate Document Number"),
		)


def _values(row):
	return [cstr(row.get(fieldname) or "") for fieldname in ROW_FIELDS]


def _validate_locked_rows(rows, old_rows):
	"""A revision that already had a later one must be unchanged and still in its place."""
	for position, old_row in enumerate(old_rows[:-1]):
		row = rows[position] if position < len(rows) else None
		if not row or row.name != old_row.name or _values(row) != _values(old_row):
			frappe.throw(
				_(
					"{0} is locked because {1} exists. Only a System Manager or PEC Administrator can change, move or delete it."
				).format(frappe.bold(f"R{position}"), frappe.bold(f"R{position + 1}")),
				title=_("Revision Locked"),
			)


def _validate_row(doc, row, codes):
	if row.approval_code:
		if not doc.project:
			frappe.throw(
				_("{0}: set the Task's Project first. Approval Codes are defined on the Project.").format(
					frappe.bold(row.revision)
				)
			)
		if row.approval_code not in codes:
			if not codes:
				frappe.throw(
					_("Project {0} has no Approval Codes yet. Add them on the Project first.").format(
						frappe.bold(doc.project)
					)
				)
			frappe.throw(
				_("{0}: Approval Code {1} is not one of Project {2}'s codes ({3}).").format(
					frappe.bold(row.revision),
					frappe.bold(row.approval_code),
					frappe.bold(doc.project),
					", ".join(codes),
				),
				title=_("Unknown Approval Code"),
			)
		row.code_description = codes[row.approval_code].description
	else:
		row.code_description = None

	if (
		row.submission_date
		and row.received_date
		and getdate(row.received_date) < getdate(row.submission_date)
	):
		frappe.throw(
			_("{0}: Comment / Received Date cannot be before the Submission Date.").format(
				frappe.bold(row.revision)
			)
		)
