# Copyright (c) 2026, PEW Engineering & Consultancy Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.workflow import apply_workflow


class PECRevision(Document):
	def validate(self):
		self.revision_label = f"R{self.revision_no or 0}"
		self.set_current_reviewer()

	def set_current_reviewer(self):
		"""Current reviewer = reviewer of the first not-yet-Approved stage, in
		sequence order, but only while the revision is actively being reviewed.
		Once it's Revision Required or Approved there is nothing left to action,
		so the field is cleared rather than pointing at whoever last acted.
		Kept as a plain field so list views/reports/notification recipients
		don't need to inspect the child table."""
		if self.workflow_state not in ("Submitted", "Under Review"):
			self.current_reviewer = None
			return

		pending = sorted(
			(row for row in self.review_stages if row.status != "Approved"),
			key=lambda row: row.sequence or 0,
		)
		self.current_reviewer = pending[0].reviewer if pending else None

	@frappe.whitelist()
	def mark_stage_reviewed(self, row_name, status, comments=None):
		"""Action a single review stage. Stages must be cleared in sequence --
		core Workflow only governs the parent document's state, so the
		stage-ordering rule lives here instead of a second workflow engine."""
		if status not in ("Approved", "Rejected"):
			frappe.throw(_("Status must be Approved or Rejected"))

		stage = next((row for row in self.review_stages if row.name == row_name), None)
		if not stage:
			frappe.throw(_("Review stage {0} not found on this revision").format(row_name))

		earlier_pending = [
			row
			for row in self.review_stages
			if (row.sequence or 0) < (stage.sequence or 0) and row.status == "Pending"
		]
		if earlier_pending:
			frappe.throw(
				_("Stage {0} must be reviewed before stage {1}").format(
					earlier_pending[0].stage_name, stage.stage_name
				)
			)

		if frappe.session.user not in (stage.reviewer, "Administrator") and not frappe.db.get_value(
			"Has Role", {"parent": frappe.session.user, "role": "PEC Administrator"}
		):
			frappe.throw(_("Only {0} can action this review stage").format(stage.reviewer))

		stage.status = status
		stage.comments = comments
		stage.reviewed_on = frappe.utils.now_datetime()
		self.save(ignore_permissions=True)

		if status == "Rejected":
			apply_workflow(self, "Request Revision")
		elif all(row.status == "Approved" for row in self.review_stages):
			apply_workflow(self, "Approve")
