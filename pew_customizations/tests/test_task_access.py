"""Task access by the role matrix: Managers see and assign everything, Engineers work in the Scopes
assigned to them (projects/scope_access.py), Draftsmen see only the Tasks assigned to them, read-only
(projects/task_access.py). Everything else is Frappe's own role permissions, User Permissions and
share-on-assign.

Run: bench --site <site> run-tests --module pew_customizations.tests.test_task_access
Everything is rolled back after the run.
"""

from unittest.mock import patch

import frappe
from frappe.desk.form import assign_to
from frappe.desk.query_report import run as run_report
from frappe.desk.search import search_link
from frappe.tests import IntegrationTestCase

from pew_customizations.projects.task_access import share_with_assignees_who_cannot_read

MANAGER = "pew.test.access.manager@example.com"
ENGINEER = "pew.test.access.engineer@example.com"
OTHER_ENGINEER = "pew.test.access.engineer2@example.com"
LEAD = "pew.test.access.lead@example.com"  # Engineer and Projects Manager
DRAFTSMAN = "pew.test.access.draftsman@example.com"
# Draftsmen in production are also HR employees: the Employee role must not list Tasks either
EMPLOYEE_DRAFTSMAN = "pew.test.access.draftsman2@example.com"

DELIVERABLE = "access-test-deliverable.pdf"  # not a /files URL: Frappe does not look for it on disk


def _user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0].rsplit(".", 1)[-1].title(),
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	frappe.get_doc("User", email).add_roles(*roles)
	return email


class TestTaskAccess(IntegrationTestCase):
	SHOW_TRANSACTION_COMMIT_WARNINGS = True  # everything here must be rolled back

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.enterClassContext(patch("frappe.sendmail"))
		cls.company = (
			frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
		)
		_user(MANAGER, ["Projects Manager"])
		_user(ENGINEER, ["Engineer"])
		_user(OTHER_ENGINEER, ["Engineer"])
		_user(LEAD, ["Engineer", "Projects Manager"])
		_user(DRAFTSMAN, ["Draftsman"])
		_user(EMPLOYEE_DRAFTSMAN, ["Draftsman", "Employee"])

	def setUp(self):
		frappe.set_user("Administrator")
		self.project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"Access test {frappe.generate_hash(length=8)}",
				"company": self.company,
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	# helpers -----------------------------------------------------------------------------------

	def new_scope(self, engineer=None):
		return frappe.get_doc(
			{
				"doctype": "Scope",
				"scope_name": "Piping scope",
				"project": self.project.name,
				"assigned_engineer": engineer,
			}
		).insert(ignore_permissions=True)

	def new_task(self, scope, subject="Layout"):
		return frappe.get_doc({"doctype": "Task", "subject": subject, "scope": scope.name}).insert(
			ignore_permissions=True
		)

	def scope_grants(self, scope):
		return set(
			frappe.get_all(
				"User Permission", filters={"allow": "Scope", "for_value": scope.name}, pluck="user"
			)
		)

	def visible_tasks(self, user):
		frappe.set_user(user)
		try:
			return set(frappe.get_list("Task", filters={"project": self.project.name}, pluck="name"))
		except frappe.PermissionError:
			return set()
		finally:
			frappe.set_user("Administrator")

	def assign(self, task, user, by=ENGINEER):
		frappe.set_user(by)
		assign_to.add({"assign_to": [user], "doctype": "Task", "name": task.name})
		frappe.set_user("Administrator")

	def can_read(self, task, user):
		return frappe.has_permission("Task", "read", doc=task.name, user=user)

	# role rights -------------------------------------------------------------------------------

	def test_role_rights_follow_the_matrix(self):
		self.assertTrue(frappe.has_permission("Task", "create", user=MANAGER))
		self.assertTrue(frappe.has_permission("Scope", "create", user=MANAGER))

		self.assertTrue(frappe.has_permission("Task", "create", user=ENGINEER))
		self.assertTrue(frappe.has_permission("Task", "share", user=ENGINEER))
		self.assertFalse(frappe.has_permission("Scope", "create", user=ENGINEER))
		self.assertTrue(frappe.has_permission("Scope", "write", user=ENGINEER))
		self.assertFalse(frappe.has_permission("Project", "create", user=ENGINEER))

		for user in (DRAFTSMAN, EMPLOYEE_DRAFTSMAN):
			# by role (has_permission on the DocType turns true once any Task is shared with them)
			rights = frappe.permissions.get_role_permissions(frappe.get_meta("Task"), user=user)
			for ptype in ("select", "read", "write", "create", "report", "export", "share"):
				self.assertFalse(rights.get(ptype), (user, ptype))
			self.assertFalse(frappe.has_permission("Scope", "write", user=user))
			self.assertFalse(frappe.has_permission("Project", "write", user=user))

	def test_draftsmen_no_longer_get_the_dci_report(self):
		frappe.set_user(DRAFTSMAN)
		with self.assertRaises(frappe.PermissionError):
			run_report("PEC DCI Report", filters={"project": self.project.name})

	# Engineers and their Scopes ----------------------------------------------------------------

	def test_assigned_engineer_gets_the_scope_and_a_replaced_one_loses_it(self):
		scope = self.new_scope(ENGINEER)
		self.assertEqual(self.scope_grants(scope), {ENGINEER})

		scope.assigned_engineer = OTHER_ENGINEER
		scope.save(ignore_permissions=True)
		self.assertEqual(self.scope_grants(scope), {OTHER_ENGINEER})

		scope.assigned_engineer = None
		scope.save(ignore_permissions=True)
		self.assertEqual(self.scope_grants(scope), set())

	def test_managers_and_non_engineers_are_not_limited_to_a_scope(self):
		self.assertEqual(self.scope_grants(self.new_scope(LEAD)), set())
		self.assertEqual(self.scope_grants(self.new_scope(DRAFTSMAN)), set())
		self.assertEqual(self.scope_grants(self.new_scope("Administrator")), set())

	def test_a_scope_with_an_engineer_can_still_be_deleted(self):
		scope = self.new_scope(ENGINEER)
		frappe.delete_doc("Scope", scope.name)
		self.assertFalse(frappe.db.exists("Scope", scope.name))
		self.assertEqual(self.scope_grants(scope), set())

	def test_engineer_sees_and_creates_tasks_in_their_scopes_only(self):
		own, other = self.new_scope(ENGINEER), self.new_scope()
		own_task, other_task = self.new_task(own), self.new_task(other)

		self.assertEqual(self.visible_tasks(ENGINEER), {own_task.name})
		self.assertEqual(self.visible_tasks(MANAGER), {own_task.name, other_task.name})

		frappe.set_user(ENGINEER)
		created = frappe.get_doc({"doctype": "Task", "subject": "Isometric", "scope": own.name}).insert()
		self.assertEqual(created.project, self.project.name)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc({"doctype": "Task", "subject": "Isometric", "scope": other.name}).insert()
		self.assertTrue(frappe.has_permission("Scope", "read", doc=own.name))
		self.assertFalse(frappe.has_permission("Scope", "read", doc=other.name))

	def test_engineer_still_sees_a_task_assigned_to_them_in_another_scope(self):
		self.new_scope(ENGINEER)
		elsewhere = self.new_task(self.new_scope())
		self.assertFalse(self.can_read(elsewhere, ENGINEER))

		self.assign(elsewhere, ENGINEER, by=MANAGER)
		self.assertTrue(self.can_read(elsewhere, ENGINEER))

	# Draftsmen and their assignments -----------------------------------------------------------

	def test_draftsman_sees_only_tasks_assigned_to_them_read_only(self):
		scope = self.new_scope(ENGINEER)
		assigned, unassigned = self.new_task(scope, "Layout"), self.new_task(scope, "Isometric")

		for user in (DRAFTSMAN, EMPLOYEE_DRAFTSMAN):
			self.assertEqual(self.visible_tasks(user), set(), user)
			self.assign(assigned, user)  # by the Engineer, through the standard Assign To
			self.assertEqual(self.visible_tasks(user), {assigned.name}, user)
			self.assertFalse(self.can_read(unassigned, user))

			share = frappe.db.get_value(
				"DocShare",
				{"share_doctype": "Task", "share_name": assigned.name, "user": user},
				["read", "write"],
			)
			self.assertEqual(share, (1, 0))
			self.assertFalse(frappe.has_permission("Task", "write", doc=assigned.name, user=user))

			frappe.set_user(user)
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc({"doctype": "Task", "subject": "Own task", "scope": scope.name}).insert()
			doc = frappe.get_doc("Task", assigned.name)
			doc.description = "changed by the draftsman"
			with self.assertRaises(frappe.PermissionError):
				doc.save()
			frappe.set_user("Administrator")

	def test_task_link_offers_a_draftsman_only_their_tasks(self):
		scope = self.new_scope(ENGINEER)
		assigned, _unassigned = self.new_task(scope, "Layout"), self.new_task(scope, "Isometric")
		self.assign(assigned, DRAFTSMAN)

		frappe.set_user(DRAFTSMAN)
		options = {row["value"] for row in search_link("Task", "", page_length=500)}
		frappe.set_user("Administrator")
		self.assertIn(assigned.name, options)
		self.assertNotIn(_unassigned.name, options)
		# only Tasks assigned to them (earlier tests of this class assign them a few more)
		assigned_to_them = set(
			frappe.get_all("ToDo", filters={"allocated_to": DRAFTSMAN}, pluck="reference_name")
		)
		self.assertLessEqual(options, assigned_to_them)

	def test_completed_task_stays_visible_to_its_draftsman(self):
		task = self.new_task(self.new_scope(ENGINEER))
		self.assign(task, DRAFTSMAN)

		frappe.set_user(ENGINEER)  # Draftsmen cannot edit Tasks: the Engineer completes them
		doc = frappe.get_doc("Task", task.name)
		doc.update({"status": "Completed", "pec_completion_attachment": DELIVERABLE})
		doc.save()
		frappe.set_user("Administrator")

		# ERPNext closes the assignment of a Completed Task; the share stays
		self.assertEqual(
			frappe.db.get_value("ToDo", {"reference_name": task.name, "allocated_to": DRAFTSMAN}, "status"),
			"Closed",
		)
		self.assertTrue(self.can_read(task, DRAFTSMAN))

	def test_removing_the_assignment_takes_the_task_back(self):
		task = self.new_task(self.new_scope(ENGINEER))
		self.assign(task, DRAFTSMAN)

		frappe.set_user(ENGINEER)
		assign_to.remove("Task", task.name, DRAFTSMAN)
		frappe.set_user("Administrator")
		self.assertFalse(self.can_read(task, DRAFTSMAN))
		self.assertEqual(self.visible_tasks(DRAFTSMAN), set())

	def test_reassigning_moves_the_task_to_the_new_draftsman(self):
		task = self.new_task(self.new_scope(ENGINEER))
		self.assign(task, DRAFTSMAN)

		frappe.set_user(ENGINEER)
		assign_to.remove("Task", task.name, DRAFTSMAN)
		assign_to.add({"assign_to": [EMPLOYEE_DRAFTSMAN], "doctype": "Task", "name": task.name})
		frappe.set_user("Administrator")

		self.assertFalse(self.can_read(task, DRAFTSMAN))
		self.assertTrue(self.can_read(task, EMPLOYEE_DRAFTSMAN))

	def test_cancelled_task_is_taken_back(self):
		task = self.new_task(self.new_scope(ENGINEER))
		self.assign(task, DRAFTSMAN)

		doc = frappe.get_doc("Task", task.name)
		doc.status = "Cancelled"
		doc.save(ignore_permissions=True)
		self.assertFalse(self.can_read(task, DRAFTSMAN))

	def test_a_share_given_by_hand_with_edit_rights_stays(self):
		task = self.new_task(self.new_scope(ENGINEER))
		self.assign(task, DRAFTSMAN)
		frappe.share.add_docshare(
			"Task", task.name, DRAFTSMAN, write=1, flags={"ignore_share_permission": True}
		)

		frappe.set_user(ENGINEER)
		assign_to.remove("Task", task.name, DRAFTSMAN)
		frappe.set_user("Administrator")
		self.assertTrue(frappe.has_permission("Task", "write", doc=task.name, user=DRAFTSMAN))

	def test_an_engineer_unassigned_from_a_task_in_their_scope_keeps_it(self):
		task = self.new_task(self.new_scope(ENGINEER))
		self.assign(task, ENGINEER, by=MANAGER)  # readable already: Frappe shares nothing
		frappe.set_user(MANAGER)
		assign_to.remove("Task", task.name, ENGINEER)
		frappe.set_user("Administrator")
		self.assertTrue(self.can_read(task, ENGINEER))

	# migration ---------------------------------------------------------------------------------

	def test_patch_shares_assignments_made_before_the_change(self):
		task = self.new_task(self.new_scope(ENGINEER))
		# an assignment from when Draftsmen read every Task: a ToDo without a share
		frappe.get_doc(
			{
				"doctype": "ToDo",
				"allocated_to": DRAFTSMAN,
				"reference_type": "Task",
				"reference_name": task.name,
				"description": "old assignment",
			}
		).insert(ignore_permissions=True)
		self.assertFalse(self.can_read(task, DRAFTSMAN))

		self.assertEqual(share_with_assignees_who_cannot_read(), 1)
		self.assertTrue(self.can_read(task, DRAFTSMAN))
		self.assertFalse(frappe.has_permission("Task", "write", doc=task.name, user=DRAFTSMAN))
		self.assertEqual(share_with_assignees_who_cannot_read(), 0)
