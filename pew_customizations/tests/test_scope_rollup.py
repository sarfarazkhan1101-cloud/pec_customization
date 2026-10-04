"""Project -> Scope -> Task: Task generation from a Scope Template and the roll-up of progress and
status from the Tasks to their Scope and on to the Project (utils.py).

Run: bench --site <site> run-tests --module pew_customizations.tests.test_scope_rollup
Everything is rolled back after the run.
"""

from unittest.mock import patch

import frappe
from frappe.desk.query_report import run as run_report
from frappe.tests import IntegrationTestCase

from pew_customizations.setup.install import SCOPE_TEMPLATE_NAMES, SCOPE_TEMPLATE_TASKS

MANAGER = "pew.test.rollup.manager@example.com"
ENGINEER = "pew.test.rollup.engineer@example.com"
DRAFTSMAN = "pew.test.rollup.draftsman@example.com"


def _user(email, first_name, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": first_name,
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
	return email


class TestScopeRollup(IntegrationTestCase):
	SHOW_TRANSACTION_COMMIT_WARNINGS = True  # everything here must be rolled back

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.enterClassContext(patch("frappe.sendmail"))
		cls.company = (
			frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
		)
		_user(MANAGER, "Rollup Manager", ["Projects Manager"])
		_user(ENGINEER, "Rollup Engineer", ["Projects User", "Engineer"])
		_user(DRAFTSMAN, "Rollup Draftsman", ["Projects User", "Draftsman"])

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	# helpers -----------------------------------------------------------------------------------

	def new_project(self):
		return frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"Rollup test {frappe.generate_hash(length=8)}",
				"company": self.company,
			}
		).insert(ignore_permissions=True)

	def new_scope(self, project, discipline="Piping", with_tasks=True):
		"""A Scope and, unless told otherwise, the names of its 7 template Tasks."""
		scope = frappe.get_doc(
			{
				"doctype": "Scope",
				"scope_name": f"{discipline} scope",
				"project": project.name,
				"scope_template": SCOPE_TEMPLATE_NAMES[discipline],
			}
		).insert(ignore_permissions=True)
		return scope, scope.create_tasks_from_template() if with_tasks else []

	def set_status(self, tasks, status, **values):
		for name in tasks:
			task = frappe.get_doc("Task", name)
			task.update({"status": status, **values})
			task.save(ignore_permissions=True)

	def scope_state(self, scope):
		status, progress = frappe.db.get_value("Scope", scope.name, ["status", "progress"])
		return status, round(progress, 2)

	def project_status(self, project):
		return frappe.db.get_value("Project", project.name, "status")

	# Task generation -----------------------------------------------------------------------------

	def test_each_scope_gets_its_own_tasks(self):
		project = self.new_project()
		piping, piping_tasks = self.new_scope(project, "Piping")
		mechanical, mechanical_tasks = self.new_scope(project, "Mechanical")

		self.assertEqual(len(piping_tasks), len(SCOPE_TEMPLATE_TASKS))
		self.assertFalse(set(piping_tasks) & set(mechanical_tasks))
		for scope, tasks in ((piping, piping_tasks), (mechanical, mechanical_tasks)):
			rows = frappe.get_all("Task", filters={"name": ("in", tasks)}, fields=["project", "scope"])
			self.assertEqual({(row.project, row.scope) for row in rows}, {(project.name, scope.name)})

		with self.assertRaises(frappe.ValidationError):
			piping.create_tasks_from_template()

	def test_generating_tasks_needs_write_on_the_scope(self):
		scope, _tasks = self.new_scope(self.new_project(), with_tasks=False)

		frappe.set_user(DRAFTSMAN)  # reads Scopes, cannot edit them
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Scope", scope.name).create_tasks_from_template()

		frappe.set_user(ENGINEER)
		self.assertEqual(len(frappe.get_doc("Scope", scope.name).create_tasks_from_template()), 7)

	def test_scope_creators_can_read_scope_templates(self):
		# ERPNext opens Project Template to System Managers only
		for user in (MANAGER, ENGINEER):
			self.assertTrue(frappe.has_permission("Project Template", "read", user=user), user)
		self.assertFalse(frappe.has_permission("Project Template", "write", user=MANAGER))

	def test_task_and_scope_share_one_project(self):
		project, other = self.new_project(), self.new_project()
		scope, _tasks = self.new_scope(project)

		task = frappe.get_doc({"doctype": "Task", "subject": "Extra document", "scope": scope.name})
		self.assertEqual(task.insert(ignore_permissions=True).project, project.name)

		task.project = other.name
		self.assertRaises(frappe.ValidationError, task.save, ignore_permissions=True)

		scope.project = other.name
		self.assertRaises(frappe.ValidationError, scope.save, ignore_permissions=True)

	# roll-up ---------------------------------------------------------------------------------

	def test_scope_follows_its_tasks(self):
		project = self.new_project()
		scope, tasks = self.new_scope(project)

		self.set_status(tasks[:1], "Working", progress=50)
		self.assertEqual(self.scope_state(scope), ("Open", round(50 / 7, 2)))

		self.set_status(tasks, "Completed")
		self.assertEqual(self.scope_state(scope), ("Completed", 100))
		self.assertEqual(self.project_status(project), "Completed")

		self.set_status(tasks[:1], "Working", progress=30)
		self.assertEqual(self.scope_state(scope), ("In Progress", 90))
		self.assertEqual(self.project_status(project), "Open")

	def test_project_waits_for_every_scope(self):
		project = self.new_project()
		_piping, piping_tasks = self.new_scope(project, "Piping")
		mechanical, _none = self.new_scope(project, "Mechanical", with_tasks=False)

		# every existing Task is done, but one Scope has not started
		self.set_status(piping_tasks, "Completed")
		self.assertEqual(self.project_status(project), "Open")
		project.reload()
		project.save(ignore_permissions=True)  # ERPNext recomputes the status on save
		self.assertEqual(self.project_status(project), "Open")

		self.set_status(mechanical.create_tasks_from_template(), "Completed")
		self.assertEqual(self.project_status(project), "Completed")
		project.reload()
		project.save(ignore_permissions=True)
		self.assertEqual(self.project_status(project), "Completed")

	def test_deleted_and_cancelled_tasks_leave_the_rollup(self):
		project = self.new_project()
		piping, piping_tasks = self.new_scope(project, "Piping")
		mechanical, mechanical_tasks = self.new_scope(project, "Mechanical")

		self.set_status(piping_tasks[:-1], "Completed")
		frappe.delete_doc("Task", piping_tasks[-1], ignore_permissions=True)
		self.assertEqual(self.scope_state(piping), ("Completed", 100))
		self.assertEqual(self.project_status(project), "Open")

		self.set_status(mechanical_tasks[:-1], "Completed")
		self.set_status(mechanical_tasks[-1:], "Cancelled")
		self.assertEqual(self.scope_state(mechanical), ("Completed", 100))
		self.assertEqual(self.project_status(project), "Completed")

	def test_task_moved_to_another_scope_updates_both(self):
		project = self.new_project()
		piping, piping_tasks = self.new_scope(project, "Piping")
		mechanical, _none = self.new_scope(project, "Mechanical", with_tasks=False)
		self.set_status(piping_tasks, "Completed")

		task = frappe.get_doc(
			{"doctype": "Task", "subject": "Extra", "project": project.name, "scope": mechanical.name}
		).insert(ignore_permissions=True)
		task.progress = 40
		task.save(ignore_permissions=True)
		self.assertEqual(self.scope_state(mechanical), ("Open", 40))

		task.scope = piping.name
		task.save(ignore_permissions=True)
		self.assertEqual(self.scope_state(piping), ("In Progress", 92.5))
		self.assertEqual(self.scope_state(mechanical), ("Open", 0))

	def test_closed_or_deleted_scope_no_longer_holds_the_project(self):
		project = self.new_project()
		_piping, piping_tasks = self.new_scope(project, "Piping")
		self.set_status(piping_tasks, "Completed")

		extra, _none = self.new_scope(project, "Mechanical", with_tasks=False)
		self.assertEqual(self.project_status(project), "Open")
		extra.status = "Closed"
		extra.save(ignore_permissions=True)
		self.assertEqual(self.project_status(project), "Completed")

		another, _none = self.new_scope(project, "Electrical", with_tasks=False)
		self.assertEqual(self.project_status(project), "Open")
		frappe.delete_doc("Scope", another.name, ignore_permissions=True)
		self.assertEqual(self.project_status(project), "Completed")

	# reports ---------------------------------------------------------------------------------

	def test_workload_report_opens_for_a_projects_manager(self):
		frappe.set_user(MANAGER)
		self.assertIn("result", run_report("PEC User Workload Report", filters={}))
