"""Completion Attachment: a Task is marked Completed only with its deliverable attached, whichever
way it is completed (projects/task_completion.py).

Run: bench --site <site> run-tests --module pew_customizations.tests.test_task_completion
Everything is rolled back after the run.
"""

import json
from unittest.mock import patch

import frappe
from erpnext.projects.doctype.project.project import set_project_status
from erpnext.projects.doctype.task.task import set_multiple_status
from frappe.tests import IntegrationTestCase
from frappe.utils import today

FIELD = "pec_completion_attachment"
# not a /files URL, so Frappe's attach_files_to_document does not look for the file on disk (and
# log an error for each save that can't find it)
DELIVERABLE = "completion-test-deliverable.pdf"


class TestTaskCompletion(IntegrationTestCase):
	SHOW_TRANSACTION_COMMIT_WARNINGS = True  # everything here must be rolled back

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.enterClassContext(patch("frappe.sendmail"))
		cls.company = (
			frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
		)

	def setUp(self):
		frappe.set_user("Administrator")
		self.project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"Completion test {frappe.generate_hash(length=8)}",
				"company": self.company,
			}
		).insert(ignore_permissions=True)

	def new_task(self, **values):
		return frappe.get_doc(
			{"doctype": "Task", "subject": "Completion test task", "project": self.project.name, **values}
		).insert(ignore_permissions=True)

	def assert_refused(self, action):
		with self.assertRaisesRegex(frappe.ValidationError, "Completion Attachment"):
			action()

	def status(self, task):
		return frappe.db.get_value("Task", task.name, "status")

	def test_field_sits_above_completed_by(self):
		meta = frappe.get_meta("Task")
		fields = [df.fieldname for df in meta.fields]
		self.assertEqual(fields.index(FIELD) + 1, fields.index("completed_by"))
		df = meta.get_field(FIELD)
		self.assertEqual(df.fieldtype, "Attach")
		self.assertEqual(df.depends_on, 'eval:doc.status == "Completed"')
		self.assertTrue(df.no_copy)

	def test_form_save_needs_the_attachment(self):
		task = self.new_task()
		task.status = "Completed"
		self.assert_refused(task.save)
		self.assertEqual(self.status(task), "Open")

		task.reload()
		task.update({"status": "Completed", FIELD: DELIVERABLE})
		task.save()
		self.assertEqual(self.status(task), "Completed")
		self.assertEqual(str(task.completed_on), today())  # ERPNext's own completion logic still runs

	def test_new_task_cannot_start_completed_without_it(self):
		self.assert_refused(lambda: self.new_task(status="Completed"))
		self.assertEqual(self.new_task(status="Completed", **{FIELD: DELIVERABLE}).status, "Completed")

	def test_list_bulk_action_and_kanban(self):
		task = self.new_task()
		# the list's "Set as Completed"
		self.assert_refused(lambda: set_multiple_status(json.dumps([task.name]), "Completed"))
		# the Kanban board saves the dragged card's column with frappe.set_value
		self.assert_refused(lambda: frappe.set_value("Task", task.name, "status", "Completed"))
		self.assertEqual(self.status(task), "Open")

		frappe.set_value("Task", task.name, FIELD, DELIVERABLE)
		set_multiple_status(json.dumps([task.name]), "Completed")
		self.assertEqual(self.status(task), "Completed")

	def test_project_set_status(self):
		task = self.new_task()
		self.assert_refused(lambda: set_project_status(self.project.name, "Completed"))
		self.assertEqual(self.status(task), "Open")

		frappe.set_value("Task", task.name, FIELD, DELIVERABLE)
		set_project_status(self.project.name, "Completed")
		self.assertEqual(self.status(task), "Completed")
		self.assertEqual(frappe.db.get_value("Project", self.project.name, "status"), "Completed")

	def test_attachment_cannot_be_removed_while_completed(self):
		task = self.new_task(status="Completed", **{FIELD: DELIVERABLE})
		task.set(FIELD, None)
		self.assert_refused(task.save)

		# reopening keeps the file, so the Task can be completed again without attaching it twice
		task.reload()
		task.status = "Open"
		task.save()
		self.assertEqual(task.get(FIELD), DELIVERABLE)
		task.status = "Completed"
		task.save()
		self.assertEqual(self.status(task), "Completed")

	def test_task_completed_before_the_rule_stays_editable(self):
		task = self.new_task()
		frappe.db.set_value("Task", task.name, {"status": "Completed", "completed_on": today()})

		task.reload()
		task.description = "Edited after completion"
		task.save()
		self.assertEqual(self.status(task), "Completed")

		# once reopened it follows the rule like any other Task
		task.status = "Open"
		task.save()
		task.status = "Completed"
		self.assert_refused(task.save)

	def test_other_statuses_and_templates_are_untouched(self):
		task = self.new_task()
		for status in ("Working", "Pending Review", "Cancelled", "Open"):
			task.status = status
			task.save()
			self.assertEqual(self.status(task), status)

		template = frappe.get_doc(
			{"doctype": "Task", "subject": "Completion test template", "is_template": 1}
		).insert(ignore_permissions=True)
		self.assertEqual(template.status, "Template")
		self.assertFalse(template.get(FIELD))
