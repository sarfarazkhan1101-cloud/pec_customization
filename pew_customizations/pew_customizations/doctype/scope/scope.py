# Copyright (c) 2026, PEW Engineering & Consultancy Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, today

from pew_customizations.utils import resync_naming_series


class Scope(Document):
	def validate(self):
		# its Tasks carry the Project too (utils.validate_task_scope)
		if (
			not self.is_new()
			and self.has_value_changed("project")
			and frappe.db.exists("Task", {"scope": self.name})
		):
			frappe.throw(_("The Project of a Scope cannot be changed once the Scope has Tasks."))

	@frappe.whitelist()
	def create_tasks_from_template(self):
		"""Generate this Scope's real Tasks from its scope_template (a standard
		Project Template). Mirrors ERPNext's own Project-Template-to-Task logic
		(erpnext.projects.doctype.project.project) but scoped to one Scope
		instead of a whole Project, stamping `scope` on every created Task.
		Template depends_on is deliberately not copied: PEW Tasks don't block
		one another, so any Task can be completed on its own."""
		# the Tasks are inserted without a Task permission check, so the Scope's own right decides
		self.check_permission("write")

		if not self.scope_template:
			frappe.throw(_("Select a Scope Template first."))

		if frappe.db.exists("Task", {"scope": self.name}):
			frappe.throw(_("Tasks already exist for this Scope."))

		template = frappe.get_doc("Project Template", self.scope_template)
		if not template.tasks:
			frappe.throw(_("Scope Template {0} has no Tasks defined.").format(self.scope_template))

		start_date = self.start_date or today()
		resync_naming_series(f"TASK-{today()[:4]}-")
		created = []

		for row in template.tasks:
			template_task = frappe.get_doc("Task", row.task)
			new_task = frappe.new_doc("Task")
			new_task.subject = template_task.subject
			new_task.project = self.project
			new_task.scope = self.name
			new_task.status = "Open"
			new_task.priority = "Medium"
			new_task.exp_start_date = add_days(start_date, template_task.start or 0)
			new_task.exp_end_date = add_days(
				start_date, (template_task.start or 0) + (template_task.duration or 0)
			)
			new_task.insert(ignore_permissions=True)
			created.append(new_task.name)

		frappe.msgprint(
			_("Created {0} Task(s) from Scope Template {1}.").format(len(created), self.scope_template),
			alert=True,
			indicator="green",
		)
		return created
