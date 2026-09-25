"""End-to-end test for the PEC (Project -> Scope -> Task -> Revision) process
(check()/cleanup() pattern). The tender pipeline is covered by tests/test_opportunity_pipeline.py.

Run: bench --site <site> execute pew_customizations.setup.pec_e2e_test.run
"""

import frappe
from frappe.model.workflow import apply_workflow


def run():
	frappe.set_user("Administrator")
	results = []
	created = {"project": None, "scope": None, "dci": None, "revisions": [], "users": [], "tasks": []}

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
	for name in created.get("revisions", []):
		if frappe.db.exists("PEC Revision", name):
			doc = frappe.get_doc("PEC Revision", name)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc("PEC Revision", name, ignore_permissions=True, force=True)
	if created.get("dci") and frappe.db.exists("DCI", created["dci"]):
		doc = frappe.get_doc("DCI", created["dci"])
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("DCI", created["dci"], ignore_permissions=True, force=True)
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

	# 7. Create DCI (document register) for this Task
	dci = frappe.new_doc("DCI")
	dci.document_title = "E2E Piping Layout Drawing"
	dci.document_category = "Piping Layout Drawing"
	dci.project = project.name
	dci.scope = scope.name
	dci.task = first_task.name
	dci.responsible_engineer = test_engineer
	dci.insert(ignore_permissions=True)
	created["dci"] = dci.name
	check("DCI created and traceable to Project/Scope/Task", dci.project == project.name and dci.scope == scope.name and dci.task == first_task.name)

	# 8. Create Revision 0 (R0) and submit it for review
	from pew_customizations.pec_revision_utils import create_new_revision

	r0_name = create_new_revision(dci.name)
	created["revisions"].append(r0_name)
	r0 = frappe.get_doc("PEC Revision", r0_name)
	check("R0 created with revision_no 0 and label R0", r0.revision_no == 0 and r0.revision_label == "R0")

	r0.append("review_stages", {"sequence": 1, "stage_name": "Engineering Review", "reviewer": "Administrator"})
	r0.save(ignore_permissions=True)

	r0 = apply_workflow(r0, "Submit for Review")
	check("R0 moved to Submitted", r0.workflow_state == "Submitted")

	r0 = apply_workflow(r0, "Start Review")
	check("R0 moved to Under Review", r0.workflow_state == "Under Review")

	# 9. Add review comments and reject -> Revision Required
	r0.mark_stage_reviewed(r0.review_stages[0].name, "Rejected", "Please correct the pipe schedule.")
	r0.reload()
	check("R0 moved to Revision Required after rejection", r0.workflow_state == "Revision Required")
	check("R0 review comment preserved", r0.review_stages[0].comments == "Please correct the pipe schedule.")

	# 10. A second active revision cannot be opened while none is required yet
	# (guard check: create_new_revision blocked while an active revision exists)
	dci.reload()
	check("DCI current_revision rolled up to R0", dci.current_revision == "R0")
	check("DCI overall_status rolled up to Revision Required", dci.overall_status == "Revision Required")

	# 11. Create Revision 1 (R1)
	r1_name = create_new_revision(dci.name)
	created["revisions"].append(r1_name)
	r1 = frappe.get_doc("PEC Revision", r1_name)
	check("R1 created with revision_no 1 and previous_revision -> R0", r1.revision_no == 1 and r1.previous_revision == r0_name)

	r1.append("review_stages", {"sequence": 1, "stage_name": "Engineering Review", "reviewer": "Administrator"})
	r1.overall_comments = "Corrections incorporated."
	r1.save(ignore_permissions=True)

	# A second active revision is now blocked (R1 is active)
	blocked_duplicate = False
	try:
		create_new_revision(dci.name)
	except frappe.ValidationError:
		blocked_duplicate = True
	check("Opening a second active revision while R1 is open is blocked", blocked_duplicate)

	r1 = apply_workflow(r1, "Submit for Review")
	r1 = apply_workflow(r1, "Start Review")
	r1.mark_stage_reviewed(r1.review_stages[0].name, "Approved", "Looks good.")
	r1.reload()
	check("R1 approved (docstatus submitted)", r1.workflow_state == "Approved" and r1.docstatus == 1)

	# 12. Verify R0's history is completely unchanged after R1's lifecycle
	r0_after = frappe.get_doc("PEC Revision", r0_name)
	check(
		"R0 history unchanged after R1 was created/approved",
		r0_after.workflow_state == "Revision Required"
		and r0_after.review_stages[0].status == "Rejected"
		and r0_after.review_stages[0].comments == "Please correct the pipe schedule.",
	)

	# 13. DCI roll-up now reflects R1 (latest), not R0
	dci.reload()
	check("DCI current_revision rolled up to R1", dci.current_revision == "R1")
	check("DCI overall_status rolled up to Approved", dci.overall_status == "Approved")

	# 14. Permission: a user who is NOT the stage reviewer cannot action it
	test_outsider = "pec_e2e_outsider@example.com"
	if not frappe.db.exists("User", test_outsider):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": test_outsider,
				"first_name": "E2E Outsider",
				"send_welcome_email": 0,
				"roles": [{"role": "Engineer"}],
			}
		).insert(ignore_permissions=True)
	created["users"].append(test_outsider)

	dci2 = frappe.new_doc("DCI")
	dci2.document_title = "E2E Piping Layout Drawing 2"
	dci2.document_category = "Piping Layout Drawing"
	dci2.project = project.name
	dci2.scope = scope.name
	dci2.task = first_task.name
	dci2.insert(ignore_permissions=True)
	created["dci"] = None  # tracked separately below for cleanup

	r2_name = create_new_revision(dci2.name)
	created["revisions"].append(r2_name)
	r2 = frappe.get_doc("PEC Revision", r2_name)
	r2.append("review_stages", {"sequence": 1, "stage_name": "Engineering Review", "reviewer": test_engineer})
	r2.save(ignore_permissions=True)
	r2 = apply_workflow(r2, "Submit for Review")
	r2 = apply_workflow(r2, "Start Review")

	frappe.set_user(test_outsider)
	denied = False
	try:
		r2.mark_stage_reviewed(r2.review_stages[0].name, "Approved", "Trying to approve without being the reviewer.")
	except frappe.ValidationError:
		denied = True
	frappe.set_user("Administrator")
	check("A non-reviewer user is denied actioning the review stage", denied)

	frappe.delete_doc("PEC Revision", r2_name, ignore_permissions=True, force=True)
	frappe.delete_doc("DCI", dci2.name, ignore_permissions=True, force=True)
	created["revisions"].remove(r2_name)

	# 15. Notifications: PEC Revision workflow-state Notifications exist and are enabled
	notif_names = ["PEC Revision Sent for Review", "PEC Revision Requires Changes", "PEC Revision Approved"]
	existing_notifs = frappe.get_all("Notification", filters={"name": ["in", notif_names], "enabled": 1})
	check("PEC Revision notifications exist and are enabled", len(existing_notifs) == len(notif_names))

	# 16. Task dependency: Task 2 of the template depends_on Task 1
	task2 = frappe.get_doc("Task", task_names[1])
	check(
		"Generated Task 2 depends_on Task 1 (standard ERPNext dependency)",
		bool(task2.depends_on) and task2.depends_on[0].task == task_names[0],
	)
