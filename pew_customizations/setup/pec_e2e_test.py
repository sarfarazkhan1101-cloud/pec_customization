"""End-to-end test for the PEC (Project -> Scope -> Task -> revisions R0 - R10 -> DCI report)
process (check()/cleanup() pattern). The rules are covered in detail by tests/test_task_revisions.py
and the tender pipeline by tests/test_opportunity_pipeline.py.

Run: bench --site <site> execute pew_customizations.setup.pec_e2e_test.run
"""

import frappe
from frappe.utils import add_days, today

from pew_customizations.pew_customizations.report.pec_dci_report.pec_dci_report import get_dci_data


def run():
	frappe.set_user("Administrator")
	results = []
	created = {"project": None, "scope": None, "users": [], "tasks": []}

	def check(label, condition):
		status = "PASS" if condition else "FAIL"
		results.append((status, label))
		print(f"[{status}] {label}")

	try:
		_run_checks(check, created)
	finally:
		frappe.set_user("Administrator")
		_cleanup(created)
		failures = [r for r in results if r[0] == "FAIL"]
		print(f"\n{len(results) - len(failures)}/{len(results)} checks passed.")
		if failures:
			print("FAILURES:", failures)


def _cleanup(created):
	for name in created.get("tasks", []):
		if frappe.db.exists("Task", name):
			frappe.delete_doc("Task", name, ignore_permissions=True, force=True)
	if created.get("scope") and frappe.db.exists("Scope", created["scope"]):
		frappe.delete_doc("Scope", created["scope"], ignore_permissions=True, force=True)
	if created.get("project") and frappe.db.exists("Project", created["project"]):
		frappe.delete_doc("Project", created["project"], ignore_permissions=True, force=True)
	for user in created.get("users", []):
		# The Drive app hooks User creation to auto-create a "Drive Settings" row
		# keyed by user email; it must go first or a re-run's User re-creation
		# collides with the leftover row.
		if frappe.db.exists("Drive Settings", user):
			frappe.delete_doc("Drive Settings", user, ignore_permissions=True, force=True)
		if frappe.db.exists("User", user):
			frappe.delete_doc("User", user, ignore_permissions=True, force=True)
	frappe.db.commit()
	print("--- cleaned up all PEC test data ---")


def _run_checks(check, created):
	frappe.sendmail = lambda *a, **k: None

	company = frappe.defaults.get_global_default("company")

	# 1. Create Project via the PEC naming series
	project = frappe.new_doc("Project")
	project.naming_series = "PEC-.YYYY.-.####"
	project.project_name = "PEC E2E Test Project"
	project.company = company
	project.project_manager = "Administrator"
	project.insert(ignore_permissions=True)
	created["project"] = project.name
	check("Project created with PEC naming series", project.name.startswith("PEC-"))

	# 2. Create Scope against a Scope Template
	scope = frappe.new_doc("Scope")
	scope.scope_name = "E2E Piping Scope"
	scope.project = project.name
	scope.scope_type = "Piping Layout"
	scope.scope_template = "PEC Piping Scope Template"
	scope.start_date = frappe.utils.today()
	scope.insert(ignore_permissions=True)
	created["scope"] = scope.name
	check("Scope created and linked to Project", scope.project == project.name)

	# 3. Generate Tasks from the Scope Template
	task_names = scope.create_tasks_from_template()
	created["tasks"] = task_names
	check("Tasks generated from Scope Template", len(task_names) == 7)
	first_task = frappe.get_doc("Task", task_names[0])
	check("Generated Task traceable to Project -> Scope -> Task", first_task.project == project.name and first_task.scope == scope.name)

	# 4. Re-running create_tasks_from_template is blocked (no duplicate generation)
	blocked = False
	try:
		scope.create_tasks_from_template()
	except frappe.ValidationError:
		blocked = True
	check("Re-generating Tasks for the same Scope is blocked", blocked)

	# 5. Assign a user to the first Task (standard Frappe assignment)
	test_engineer = "pec_e2e_engineer@example.com"
	if not frappe.db.exists("User", test_engineer):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": test_engineer,
				"first_name": "E2E Engineer",
				"send_welcome_email": 0,
				"roles": [{"role": "Engineer"}],
			}
		).insert(ignore_permissions=True)
	created["users"].append(test_engineer)

	from frappe.desk.form.assign_to import add as assign_to_add

	assign_to_add({"doctype": "Task", "name": first_task.name, "assign_to": [test_engineer]})
	assignees = frappe.get_all("ToDo", filters={"reference_type": "Task", "reference_name": first_task.name}, fields=["allocated_to"])
	check("Task assigned via standard ToDo assignment", any(a.allocated_to == test_engineer for a in assignees))

	# 6. Update Task progress
	first_task.progress = 40
	first_task.status = "Working"
	first_task.save(ignore_permissions=True)
	check("Task progress updated", frappe.db.get_value("Task", first_task.name, "progress") == 40)

	# 7. A new Project carries the default Approval Codes; code 1 closes a document
	project.reload()
	check(
		"Project pre-filled with the default Approval Codes",
		[(row.code, row.closes_document) for row in project.pec_approval_codes]
		== [("1", 1), ("2", 0), ("3", 0), ("4", 0)],
	)

	# 8. The Task is the deliverable document: number it and submit R0
	first_task.reload()
	first_task.pec_document_number = "E2E-PIP-001"
	first_task.append("pec_revisions", {"submission_date": add_days(today(), -7)})
	first_task.save(ignore_permissions=True)
	check("R0 numbered from the row order", first_task.pec_revisions[0].revision == "R0")
	check(
		"R0 submitted: Latest Status is awaiting comments",
		first_task.pec_latest_status == "R0 Submitted – Awaiting Comments",  # noqa: RUF001
	)

	# 9. R1 cannot be opened before R0 has an Approval Code
	first_task.append("pec_revisions", {"submission_date": today()})
	check("R1 before R0 has a code is refused", _is_refused(first_task))

	# 10. The client answers R0 with code 3 (revise and resubmit), then R1 is submitted
	first_task.reload()
	first_task.pec_revisions[0].update({"approval_code": "3", "received_date": add_days(today(), -3)})
	first_task.save(ignore_permissions=True)
	check("R0 code 3 received", first_task.pec_latest_status == "R0 Code 3 Received")
	check(
		"Code description filled from the Project",
		first_task.pec_revisions[0].code_description == "Revise and resubmit",
	)

	first_task.append("pec_revisions", {"submission_date": today()})
	first_task.save(ignore_permissions=True)
	check(
		"R1 submitted after R0 was answered",
		first_task.pec_latest_status == "R1 Submitted – Awaiting Comments",  # noqa: RUF001
	)

	# 11. R0 is locked now that R1 exists: an Engineer cannot change it, an administrator can
	frappe.set_user(test_engineer)
	as_engineer = frappe.get_doc("Task", first_task.name)
	as_engineer.pec_revisions[0].notes = "changed after R1 was submitted"
	check("An Engineer cannot edit R0 once R1 exists", _is_refused(as_engineer))

	as_engineer.reload()
	as_engineer.pec_revisions[1].update({"approval_code": "1", "received_date": today()})
	as_engineer.save()
	check(
		"An Engineer can update the latest revision", as_engineer.pec_latest_status == "Approved (R1, Code 1)"
	)
	frappe.set_user("Administrator")

	first_task.reload()
	first_task.pec_revisions[0].notes = "corrected by the administrator"
	first_task.save(ignore_permissions=True)
	check(
		"An administrator can still edit R0",
		first_task.pec_revisions[0].notes == "corrected by the administrator",
	)

	# 12. Revisions leave the Task's own status and progress alone
	check(
		"Revisions did not change Task status or progress",
		first_task.status == "Working" and first_task.progress == 40,
	)

	# 13. At most 11 revisions (R0 - R10)
	second_task = frappe.get_doc("Task", task_names[1])
	for _n in range(11):
		second_task.append("pec_revisions", {"submission_date": today(), "approval_code": "3"})
	second_task.save(ignore_permissions=True)
	check("R0 to R10 accepted", second_task.pec_revisions[-1].revision == "R10")
	second_task.append("pec_revisions", {"submission_date": today()})
	check("A 12th revision (R11) is refused", _is_refused(second_task))

	# 14. The DCI is a report over the Project's Tasks
	rows = {row.task: row for row in get_dci_data({"project": project.name}).rows}
	row = rows[first_task.name]
	check("DCI report lists every Task of the Project", len(rows) == 7)
	check(
		"DCI report row shows the document and its revisions",
		row.document_number == "E2E-PIP-001" and row.r0_code == "3" and row.r1_code == "1",
	)
	check("DCI report Latest Status matches the Task", row.latest_status == "Approved (R1, Code 1)")
	check("Unsubmitted Tasks show as Not Submitted", rows[task_names[2]].latest_status == "Not Submitted")

	# 15. Engineers may export the DCI; Draftsmen may view it but not export it
	test_draftsman = "pec_e2e_draftsman@example.com"
	if not frappe.db.exists("User", test_draftsman):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": test_draftsman,
				"first_name": "E2E Draftsman",
				"send_welcome_email": 0,
				"roles": [{"role": "Draftsman"}],
			}
		).insert(ignore_permissions=True)
	created["users"].append(test_draftsman)

	frappe.set_user(test_engineer)
	check("Engineer can export Tasks (DCI report)", bool(frappe.permissions.can_export("Task")))
	frappe.set_user(test_draftsman)
	check(
		"Draftsman can view the DCI report but not export it",
		frappe.has_permission("Task", "report") and not frappe.permissions.can_export("Task"),
	)
	frappe.set_user("Administrator")

	# 16. No Task dependencies: generated Tasks don't block one another
	check(
		"Generated Tasks have no depends_on",
		not frappe.get_all("Task Depends On", filters={"parent": ["in", task_names]}, limit=1),
	)


def _is_refused(doc):
	try:
		doc.save(ignore_permissions=True)
	except frappe.ValidationError:
		return True
	return False
