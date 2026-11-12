"""Completion Attachment on Task: a Task is marked Completed only with its deliverable attached.

The check is on the server because the form is only one way to complete a Task: the list's
"Set as Completed", the Kanban board, Project > Set Status and a Timesheet's Completed tick all save
the Task without it. public/js/task.js marks the field mandatory in the form by the same rule.

Tasks that were Completed before this rule keep their status without a file. They need one only
once they are reopened and completed again.
"""

import frappe
from frappe import _

FIELD = "pec_completion_attachment"


def validate(doc, method=None):
	if doc.is_template or doc.status != "Completed" or doc.get(FIELD):
		return
	# the Custom Field arrives with the fixtures, after the first migrate's patches
	if not doc.meta.has_field(FIELD):
		return

	before = doc.get_doc_before_save()
	if before and before.status == "Completed":
		if not before.get(FIELD):
			return  # completed before the rule
		frappe.throw(
			_("Task {0} is Completed, so its Completion Attachment cannot be removed.").format(
				frappe.bold(_task_title(doc))
			),
			title=_("Completion Attachment Required"),
		)

	frappe.throw(
		_("Attach the Completion Attachment before marking Task {0} as Completed.").format(
			frappe.bold(_task_title(doc))
		),
		title=_("Completion Attachment Required"),
	)


def _task_title(doc):
	# the list's bulk action, the Kanban board and Project > Set Status can complete many Tasks at once
	return f"{doc.name}: {doc.subject}" if doc.name and doc.subject else doc.name or doc.subject
