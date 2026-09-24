"""Idempotent PEC demo data: 2 Customers, 5 demo Users, 2 Projects, and on
Project 001 a Piping + Mechanical Scope (Tasks generated from their Scope
Templates) with 2 DCIs driven through the real revision Workflow end-to-end --
one to Approved (R0 rejected, R1 approved) and one left mid-lifecycle
(R0 rejected, R1 still Draft), matching the client's requested demo lifecycle.

Run explicitly (not wired to after_install):
	bench --site <site> execute pew_customizations.setup.demo_data.run
"""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import add_months, today

from pew_customizations.pec_revision_utils import create_new_revision

DEMO_CUSTOMERS = ["ABC Engineering Pvt Ltd", "XYZ Industrial Ltd"]

# (email, first_name, last_name, role)
DEMO_USERS = [
	("pec.pm@example.com", "Priya", "Menon", "Projects Manager"),
	("pec.engineer1@example.com", "Arjun", "Rao", "Engineer"),
	("pec.engineer2@example.com", "Sana", "Iyer", "Engineer"),
	("pec.draughtsman1@example.com", "Vikram", "Shah", "Draftsman"),
	("pec.reviewer1@example.com", "Meera", "Nair", "Reviewer"),
]

PM = "pec.pm@example.com"
ENGINEER = "pec.engineer1@example.com"
DRAUGHTSMAN = "pec.draughtsman1@example.com"
REVIEWER = "pec.reviewer1@example.com"


def run():
	frappe.set_user("Administrator")
	create_demo_customers()
	create_demo_users()
	projects = create_demo_projects()
	create_scope_task_dci_lifecycle(projects[0])
	frappe.db.commit()
	print("PEC demo data created/verified.")


def create_demo_customers():
	for customer in DEMO_CUSTOMERS:
		if not frappe.db.exists("Customer", customer):
			frappe.get_doc(
				{"doctype": "Customer", "customer_name": customer, "customer_type": "Company"}
			).insert(ignore_permissions=True)


def create_demo_users():
	for email, first_name, last_name, role in DEMO_USERS:
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": first_name,
					"last_name": last_name,
					"send_welcome_email": 0,
					"roles": [{"role": role}],
				}
			).insert(ignore_permissions=True)
		elif not frappe.db.exists("Has Role", {"parent": email, "role": role}):
			user = frappe.get_doc("User", email)
			user.append("roles", {"role": role})
			user.save(ignore_permissions=True)


def create_demo_projects():
	company = frappe.defaults.get_global_default("company")
	specs = [
		("PEC Demo Project 001", DEMO_CUSTOMERS[0], "Coastal Terminal Operator Ltd", "Blue Ridge Consultants"),
		("PEC Demo Project 002", DEMO_CUSTOMERS[1], "XYZ Refinery Division", "Blue Ridge Consultants"),
	]

	created = []
	for project_name, customer, end_user, consultant in specs:
		existing = frappe.db.get_value("Project", {"project_name": project_name})
		if existing:
			created.append(existing)
			continue

		project = frappe.new_doc("Project")
		project.naming_series = "PEC-.YYYY.-.####"
		project.project_name = project_name
		if frappe.db.exists("Customer", customer):
			project.customer = customer
		project.company = company
		project.status = "Open"
		project.project_manager = PM
		project.end_user = end_user
		project.consultant = consultant
		project.expected_start_date = today()
		project.expected_end_date = add_months(today(), 3)
		project.insert(ignore_permissions=True)
		created.append(project.name)

	return created


def create_scope_task_dci_lifecycle(project_name):
	scope1 = _get_or_create_scope(project_name, "Piping Scope", "Piping Layout", "PEC Piping Scope Template")
	scope2 = _get_or_create_scope(
		project_name, "Mechanical Scope", "Mechanical Calculation", "PEC Mechanical Scope Template"
	)

	tasks1 = _ensure_tasks_from_template(scope1)
	tasks2 = _ensure_tasks_from_template(scope2)

	if len(tasks1) < 2:
		return

	# Realistic progress on the first few tasks of each scope, so Scope.progress
	# (derived from Task progress, not entered by hand) isn't just sitting at 0%.
	# Named by task, never by subject -- a subject match would also touch any
	# other Scope in the system built from the same template.
	_seed_task_progress(tasks1, [100, 70, 30])
	_seed_task_progress(tasks2, [100, 40])

	dci1 = _get_or_create_dci(project_name, scope1, tasks1[0], "Piping Layout Drawing - Sheet 1")
	dci2 = _get_or_create_dci(project_name, scope1, tasks1[1], "Piping Isometric Drawing - Sheet 1")

	_drive_to_approved(dci1)
	_drive_to_revision_required(dci2, open_next_revision=True)


def _seed_task_progress(task_names, percentages):
	# Task's on_update hook (sync_scope_from_tasks) recomputes the
	# parent Scope's rolled-up progress automatically on each save below.
	for task_name, pct in zip(task_names, percentages):
		task = frappe.get_doc("Task", task_name)
		if task.progress:
			continue  # already seeded on a previous run
		task.progress = pct
		task.status = "Completed" if pct == 100 else "Working"
		task.save(ignore_permissions=True)


def _get_or_create_scope(project, scope_name, scope_type, template_name):
	existing = frappe.db.get_value("Scope", {"project": project, "scope_name": scope_name})
	if existing:
		return existing

	scope = frappe.new_doc("Scope")
	scope.scope_name = scope_name
	scope.project = project
	scope.scope_type = scope_type
	scope.scope_template = template_name
	scope.assigned_engineer = ENGINEER
	scope.associate = DRAUGHTSMAN
	scope.status = "In Progress"
	scope.start_date = today()
	scope.end_date = add_months(today(), 2)
	scope.insert(ignore_permissions=True)
	return scope.name


def _ensure_tasks_from_template(scope_name):
	tasks = frappe.get_all("Task", filters={"scope": scope_name}, fields=["name"], order_by="exp_start_date asc")
	if tasks:
		return [t.name for t in tasks]

	from frappe.desk.form.assign_to import add as assign_to_add

	scope = frappe.get_doc("Scope", scope_name)
	created = scope.create_tasks_from_template()
	for idx, task_name in enumerate(created):
		frappe.db.set_value("Task", task_name, "reviewer", REVIEWER)
		# Realistic demo assignment: engineer owns the earlier tasks, draughtsman the later ones.
		assignee = ENGINEER if idx < 4 else DRAUGHTSMAN
		assign_to_add({"doctype": "Task", "name": task_name, "assign_to": [assignee]})
	return created


def _get_or_create_dci(project, scope, task, title):
	existing = frappe.db.get_value("DCI", {"project": project, "task": task, "document_title": title})
	if existing:
		return existing

	dci = frappe.new_doc("DCI")
	dci.document_title = title
	dci.document_category = "Piping Layout Drawing"
	dci.project = project
	dci.scope = scope
	dci.task = task
	dci.responsible_engineer = ENGINEER
	dci.assigned_to = DRAUGHTSMAN
	dci.insert(ignore_permissions=True)
	return dci.name


def _new_revision_with_stage(dci, comments=None):
	if frappe.db.exists("PEC Revision", {"dci": dci, "workflow_state": "Draft"}):
		return frappe.get_doc("PEC Revision", frappe.db.get_value("PEC Revision", {"dci": dci, "workflow_state": "Draft"}))

	name = create_new_revision(dci)
	revision = frappe.get_doc("PEC Revision", name)
	revision.submitted_by = ENGINEER
	revision.append("review_stages", {"sequence": 1, "stage_name": "Engineering Review", "reviewer": REVIEWER})
	if comments:
		revision.overall_comments = comments
	revision.save(ignore_permissions=True)
	return revision


def _drive_to_approved(dci):
	if frappe.db.get_value("DCI", dci, "overall_status") == "Approved":
		return

	r0 = _new_revision_with_stage(dci, "Initial issue for review.")
	if r0.workflow_state == "Draft":
		r0 = apply_workflow(r0, "Submit for Review")
	if r0.workflow_state == "Submitted":
		r0 = apply_workflow(r0, "Start Review")
	if r0.workflow_state == "Under Review":
		r0.mark_stage_reviewed(
			r0.review_stages[0].name, "Rejected", "Pipe schedule missing on sheet 1, please add and resubmit."
		)

	r1 = _new_revision_with_stage(dci, "Corrections incorporated: pipe schedule added to sheet 1.")
	if r1.workflow_state == "Draft":
		r1 = apply_workflow(r1, "Submit for Review")
	if r1.workflow_state == "Submitted":
		r1 = apply_workflow(r1, "Start Review")
	if r1.workflow_state == "Under Review":
		r1.reload()
		r1.mark_stage_reviewed(r1.review_stages[0].name, "Approved", "Looks good, approved.")


def _drive_to_revision_required(dci, open_next_revision=False):
	if frappe.db.exists("PEC Revision", {"dci": dci}):
		r0 = frappe.get_doc(
			"PEC Revision", frappe.db.get_value("PEC Revision", {"dci": dci, "revision_no": 0})
		)
	else:
		r0 = _new_revision_with_stage(dci, "Initial issue for review.")

	if r0.workflow_state == "Draft":
		r0 = apply_workflow(r0, "Submit for Review")
	if r0.workflow_state == "Submitted":
		r0 = apply_workflow(r0, "Start Review")
	if r0.workflow_state == "Under Review":
		r0.mark_stage_reviewed(
			r0.review_stages[0].name, "Rejected", "Isometric numbering is inconsistent with the layout drawing, please revise."
		)

	if open_next_revision and not frappe.db.exists("PEC Revision", {"dci": dci, "revision_no": 1}):
		r1_name = create_new_revision(dci)  # left in Draft -> represents "In Progress"
		frappe.db.set_value("PEC Revision", r1_name, "submitted_by", DRAUGHTSMAN)
