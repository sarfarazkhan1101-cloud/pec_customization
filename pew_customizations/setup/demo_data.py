"""Idempotent PEC demo data: 2 Customers, 5 demo Users, 2 Projects, and on
Project 001 a Piping + Mechanical Scope (Tasks generated from their Scope
Templates). Each Task is one deliverable document: the first few carry a
Document Number and a revision history, so the PEC DCI Report shows every
Latest Status (approved, comments received, awaiting comments, not submitted).

Run explicitly (not wired to after_install):
	bench --site <site> execute pew_customizations.setup.demo_data.run
"""

import frappe
from frappe.utils import add_days, add_months, today

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
	create_scope_task_revision_lifecycle(projects[0])
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


def create_scope_task_revision_lifecycle(project_name):
	scope1 = _get_or_create_scope(project_name, "Piping Scope", "Piping Layout", "PEC Piping Scope Template")
	scope2 = _get_or_create_scope(
		project_name, "Mechanical Scope", "Mechanical Calculation", "PEC Mechanical Scope Template"
	)

	tasks1 = _ensure_tasks_from_template(scope1)
	tasks2 = _ensure_tasks_from_template(scope2)

	if len(tasks1) < 3 or not tasks2:
		return

	# Realistic progress on the first few tasks of each scope, so Scope.progress
	# (derived from Task progress, not entered by hand) isn't just sitting at 0%.
	# Named by task, never by subject -- a subject match would also touch any
	# other Scope in the system built from the same template.
	_seed_task_progress(tasks1, [100, 70, 30])
	_seed_task_progress(tasks2, [100, 40])

	_set_document_numbers(tasks1, "DEMO-PIP")
	_set_document_numbers(tasks2, "DEMO-MEC")

	# (submitted days ago, answered days ago, Approval Code) per revision, R0 first.
	# The codes are the Project's default set: 1 closes the document, 3 = revise and resubmit.
	_seed_revisions(tasks1[0], [(30, 24, "3"), (18, 12, "1")])  # approved at R1
	_seed_revisions(tasks1[1], [(21, 15, "3"), (6, None, None)])  # R1 awaiting comments
	_seed_revisions(tasks1[2], [(9, 4, "2")])  # comments received on R0
	_seed_revisions(tasks2[0], [(5, None, None)])  # R0 awaiting comments


def _set_document_numbers(task_names, prefix):
	for number, task_name in enumerate(task_names, start=1):
		if not frappe.db.get_value("Task", task_name, "pec_document_number"):
			frappe.db.set_value("Task", task_name, "pec_document_number", f"{prefix}-{number:03d}")


def _seed_revisions(task_name, revisions):
	# Task's validate hook (projects/task_revisions.py) numbers the rows R0, R1 ...
	# and sets the Task's Latest Status from the last one.
	task = frappe.get_doc("Task", task_name)
	if task.pec_revisions:
		return  # already seeded on a previous run, or copied from an old DCI

	for submitted, answered, code in revisions:
		task.append(
			"pec_revisions",
			{
				"submission_date": add_days(today(), -submitted),
				"received_date": add_days(today(), -answered) if answered is not None else None,
				"approval_code": code,
			},
		)
	task.save(ignore_permissions=True)


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
