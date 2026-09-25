import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# The tender pipeline on Opportunity (stages, fields, notifications, handoff) lives in
# pew_customizations.crm; this module keeps the PEC project-execution setup.

MARKET_SEGMENTS = [
	"Water & Wastewater",
	"Oil & Gas",
	"Power & Energy",
	"Infrastructure & Roads",
	"Industrial/Manufacturing Plants",
	"Marine & Ports",
	"Government/Municipal",
]

# Sequential engineering service lifecycle. (task_name, start_day, duration_days)
LIFECYCLE_TASKS = [
	("Input Data Received", 0, 3),
	("Design & Drafting", 3, 10),
	("Initial Client Submission", 13, 2),
	("Revision/Comment Cycle 1", 15, 5),
	("Revision 2", 20, 5),
	("Revision 3", 25, 5),
	("Final Approval", 30, 3),
]
PROJECT_TEMPLATE_NAME = "PEW Engineering Service Lifecycle"

WORKFLOW_NAME = "Project Approval Workflow"

# PEC (Project Engineering / Execution) process additions
# Engineer, Draftsman, Associate and Client Reviewer are used by the PEC doctype permissions.
PEC_ROLES = [
	"Reviewer",
	"Scope Manager",
	"PEC Administrator",
	"Engineer",
	"Draftsman",
	"Associate",
	"Client Reviewer",
]
PEC_PROJECT_NAMING_SERIES = "PEC-.YYYY.-.####"
PEC_REVISION_WORKFLOW_NAME = "PEC Revision Approval Workflow"

# Same 7-task checklist for every discipline (spec's own example). Task rows
# are matched/reused by subject across templates, same as LIFECYCLE_TASKS.
SCOPE_TEMPLATE_TASKS = [
	("Input Data Collection", 0, 3),
	("Design", 3, 7),
	("Internal Check", 10, 2),
	("Engineering Review", 12, 3),
	("Drafting", 15, 7),
	("Final Review", 22, 3),
	("Submission", 25, 2),
]
SCOPE_TEMPLATE_NAMES = {
	"Piping": "PEC Piping Scope Template",
	"Mechanical": "PEC Mechanical Scope Template",
	"Electrical": "PEC Electrical Scope Template",
}

NOTIFICATION_REVISION_SUBMITTED = "PEC Revision Sent for Review"
NOTIFICATION_REVISION_REJECTED = "PEC Revision Requires Changes"
NOTIFICATION_REVISION_APPROVED = "PEC Revision Approved"
NOTIFICATION_TASK_OVERDUE = "PEC Task Overdue"


def run():
	from pew_customizations.crm.setup import apply_customizations

	create_all_custom_fields()
	create_market_segments()
	create_project_approval_workflow()
	create_engineering_service_lifecycle_template()
	create_pec_roles()
	create_project_naming_series_option()
	create_pec_revision_workflow()
	create_pec_notifications()
	create_scope_templates()
	apply_customizations()
	frappe.db.commit()
	print("pew_customizations setup complete.")


def create_all_custom_fields():
	create_custom_fields(get_custom_fields(), update=True)


def get_custom_field_names():
	"""Custom Field record names ("<doctype>-<fieldname>") created here. Used to scope the
	`fixtures` export to exactly our own records (e.g. File has other apps' custom fields)."""
	return [f"{dt}-{field['fieldname']}" for dt, fields in get_custom_fields().items() for field in fields]


def get_custom_fields():
	return {
		"Project": [
			{
				"fieldname": "pending_review",
				"label": "Pending Review",
				"fieldtype": "Check",
				"default": "1",
				"insert_after": "status",
				"description": (
					"Set automatically when this Project is created from a won Opportunity. "
					"Cleared when a Projects Manager approves the Project via workflow."
				),
			},
			{
				"fieldname": "source_opportunity",
				"label": "Source Opportunity",
				"fieldtype": "Link",
				"options": "Opportunity",
				"insert_after": "pending_review",
				"read_only": 1,
				# DB-level guard: one Project per won Opportunity (see crm.opportunity.create_project)
				"unique": 1,
			},
			{
				"fieldname": "pec_details_tab",
				"label": "PEC Details",
				"fieldtype": "Tab Break",
				"insert_after": "message",
			},
			{
				"fieldname": "project_manager",
				"label": "Project Manager",
				"fieldtype": "Link",
				"options": "User",
				"insert_after": "pec_details_tab",
			},
			{
				"fieldname": "end_user",
				"label": "End User",
				"fieldtype": "Data",
				"description": "The end client / operating owner, where different from the billed Customer.",
				"insert_after": "project_manager",
			},
			{
				"fieldname": "consultant",
				"label": "Consultant",
				"fieldtype": "Data",
				"insert_after": "end_user",
			},
			{
				"fieldname": "pec_details_column_break",
				"fieldtype": "Column Break",
				"insert_after": "consultant",
			},
			{
				"fieldname": "project_folder_link",
				"label": "Project Folder / Drive Link",
				"fieldtype": "Data",
				"options": "URL",
				"insert_after": "pec_details_column_break",
			},
			{
				"fieldname": "sharepoint_link",
				"label": "SharePoint / External Document Link",
				"fieldtype": "Data",
				"options": "URL",
				"insert_after": "project_folder_link",
			},
			{
				"fieldname": "pec_input_section",
				"label": "Project Input / Design Basis",
				"fieldtype": "Section Break",
				"insert_after": "sharepoint_link",
			},
			{
				"fieldname": "project_input",
				"label": "Project Input",
				"fieldtype": "Attach",
				"insert_after": "pec_input_section",
			},
			{
				"fieldname": "design_basis",
				"label": "Design Basis",
				"fieldtype": "Text Editor",
				"insert_after": "project_input",
			},
		],
		"Task": [
			{
				"fieldname": "custom_discipline",
				"label": "Discipline",
				"fieldtype": "Select",
				"options": "\nMechanical\nPiping\nStructural\nCivil",
				"insert_after": "type",
			},
			{
				"fieldname": "scope",
				"label": "Scope",
				"fieldtype": "Link",
				"options": "Scope",
				"insert_after": "project",
				"in_standard_filter": 1,
				"description": "The PEC Scope this Task belongs to, for Project -> Scope -> Task traceability.",
			},
			{
				"fieldname": "reviewer",
				"label": "Reviewer",
				"fieldtype": "Link",
				"options": "User",
				"insert_after": "custom_discipline",
			},
		],
	}


def create_market_segments():
	for segment in MARKET_SEGMENTS:
		if not frappe.db.exists("Market Segment", segment):
			frappe.get_doc({"doctype": "Market Segment", "market_segment": segment}).insert(ignore_permissions=True)


def create_project_approval_workflow():
	if frappe.db.exists("Workflow", WORKFLOW_NAME):
		return

	manager_role = "Projects Manager" if frappe.db.exists("Role", "Projects Manager") else "System Manager"

	doc = frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": WORKFLOW_NAME,
			"document_type": "Project",
			"is_active": 1,
			"send_email_alert": 0,
			"states": [
				{
					"state": "Pending",
					"doc_status": "0",
					"update_field": "pending_review",
					"update_value": "1",
					"allow_edit": manager_role,
				},
				{
					"state": "Approved",
					"doc_status": "0",
					"update_field": "pending_review",
					"update_value": "0",
					"allow_edit": manager_role,
				},
			],
			"transitions": [
				{
					"state": "Pending",
					"action": "Approve",
					"next_state": "Approved",
					"allowed": manager_role,
				}
			],
		}
	)
	doc.insert(ignore_permissions=True)


def _get_or_create_template_task_chain(task_specs):
	"""Get-or-create a sequential chain of is_template=1 Tasks matched by
	subject, linked via depends_on. Reused across multiple Project Templates
	so identically-named template tasks (e.g. the same 7-step checklist
	shared by every discipline's Scope Template) aren't duplicated."""
	from pew_customizations.utils import resync_naming_series

	resync_naming_series(f"TASK-{frappe.utils.today()[:4]}-")

	task_names = []
	previous_task_name = None

	for subject, start, duration in task_specs:
		existing = frappe.db.exists("Task", {"subject": subject, "is_template": 1})
		if existing:
			task_name = existing
		else:
			task = frappe.new_doc("Task")
			task.subject = subject
			task.is_template = 1
			task.status = "Template"
			task.start = start
			task.duration = duration
			if previous_task_name:
				task.append("depends_on", {"task": previous_task_name})
			task.insert(ignore_permissions=True)
			task_name = task.name

		task_names.append(task_name)
		previous_task_name = task_name

	return task_names


def _create_project_template(template_name, task_names):
	if frappe.db.exists("Project Template", template_name):
		return

	template = frappe.new_doc("Project Template")
	template.name = template_name
	for task_name in task_names:
		template.append("tasks", {"task": task_name})
	template.insert(ignore_permissions=True)


def create_engineering_service_lifecycle_template():
	task_names = _get_or_create_template_task_chain(LIFECYCLE_TASKS)
	_create_project_template(PROJECT_TEMPLATE_NAME, task_names)


def create_scope_templates():
	"""One Project Template per discipline, used as a Scope's `scope_template`
	so Scope.create_tasks_from_template() can generate that Scope's Tasks."""
	for template_name in SCOPE_TEMPLATE_NAMES.values():
		task_names = _get_or_create_template_task_chain(SCOPE_TEMPLATE_TASKS)
		_create_project_template(template_name, task_names)


def create_pec_roles():
	for role in PEC_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc(
				{"doctype": "Role", "role_name": role, "desk_access": 1}
			).insert(ignore_permissions=True)


def create_project_naming_series_option():
	"""Add 'PEC-.YYYY.-.####' as an additional naming_series option on the
	standard Project doctype, without removing the existing 'PROJ-.####'
	option (so already-created Projects like PROJ-0001 stay valid)."""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	current = frappe.db.get_value(
		"Property Setter",
		{"doc_type": "Project", "field_name": "naming_series", "property": "options"},
		"value",
	)
	if current is None:
		current = frappe.get_meta("Project").get_field("naming_series").options or ""

	options = [o for o in current.split("\n") if o]
	if PEC_PROJECT_NAMING_SERIES in options:
		return

	options.append(PEC_PROJECT_NAMING_SERIES)
	make_property_setter("Project", "naming_series", "options", "\n".join(options), "Text")


def _ensure_workflow_masters(states, actions):
	"""Workflow.states.state and Workflow.transitions.action/next_state are
	Link fields to the Workflow State / Workflow Action Master doctypes --
	get-or-create the master records this workflow needs before inserting it."""
	for state in states:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state}).insert(
				ignore_permissions=True
			)
	for action in actions:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(
				ignore_permissions=True
			)


def create_pec_revision_workflow():
	if frappe.db.exists("Workflow", PEC_REVISION_WORKFLOW_NAME):
		return

	_ensure_workflow_masters(
		states=["Draft", "Submitted", "Under Review", "Revision Required", "Approved"],
		actions=["Submit for Review", "Start Review", "Approve", "Request Revision"],
	)

	engineer_role = "Engineer"
	reviewer_role = "Reviewer" if frappe.db.exists("Role", "Reviewer") else "Projects Manager"
	admin_role = "PEC Administrator" if frappe.db.exists("Role", "PEC Administrator") else "System Manager"

	doc = frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": PEC_REVISION_WORKFLOW_NAME,
			"document_type": "PEC Revision",
			"workflow_state_field": "workflow_state",
			"is_active": 1,
			"send_email_alert": 0,
			"states": [
				{"state": "Draft", "doc_status": "0", "allow_edit": engineer_role},
				{"state": "Submitted", "doc_status": "0", "allow_edit": reviewer_role},
				{"state": "Under Review", "doc_status": "0", "allow_edit": reviewer_role},
				{"state": "Revision Required", "doc_status": "0", "allow_edit": admin_role},
				{"state": "Approved", "doc_status": "1", "allow_edit": admin_role},
			],
			"transitions": [
				{
					"state": "Draft",
					"action": "Submit for Review",
					"next_state": "Submitted",
					"allowed": engineer_role,
				},
				{
					"state": "Submitted",
					"action": "Start Review",
					"next_state": "Under Review",
					"allowed": reviewer_role,
				},
				{
					"state": "Under Review",
					"action": "Approve",
					"next_state": "Approved",
					"allowed": reviewer_role,
					# Workflow conditions run through frappe.safe_eval with a very small
					# global namespace (no builtins, no all()/any()) -- so "every review
					# stage is Approved" has to be phrased as a single db lookup for any
					# stage that ISN'T Approved, rather than a Python loop/comprehension.
					"condition": (
						"frappe.db.get_value('PEC Revision Review Stage', "
						"{'parent': doc.name, 'status': ['!=', 'Approved']}, 'name') is None"
					),
				},
				{
					"state": "Under Review",
					"action": "Request Revision",
					"next_state": "Revision Required",
					"allowed": reviewer_role,
				},
			],
		}
	)
	doc.insert(ignore_permissions=True)


def create_pec_notifications():
	_create_revision_state_notification(
		NOTIFICATION_REVISION_SUBMITTED,
		"Submitted",
		"PEC Revision {{ doc.name }} ({{ doc.revision_label }}) submitted for review",
		[{"receiver_by_document_field": "current_reviewer"}],
		"<p>Revision {{ doc.revision_label }} of DCI <b>{{ doc.dci }}</b> has been "
		"submitted and needs your review.</p>",
	)
	_create_revision_state_notification(
		NOTIFICATION_REVISION_REJECTED,
		"Revision Required",
		"Revision required on {{ doc.name }} ({{ doc.revision_label }})",
		[{"receiver_by_document_field": "submitted_by"}],
		"<p>Revision {{ doc.revision_label }} of DCI <b>{{ doc.dci }}</b> requires changes. "
		"Please review the comments and create the next revision.</p>",
	)
	_create_revision_state_notification(
		NOTIFICATION_REVISION_APPROVED,
		"Approved",
		"PEC Revision {{ doc.name }} ({{ doc.revision_label }}) approved",
		[{"receiver_by_document_field": "submitted_by"}, {"receiver_by_document_field": "responsible_engineer"}],
		"<p>Revision {{ doc.revision_label }} of DCI <b>{{ doc.dci }}</b> has been approved.</p>",
	)
	create_task_overdue_notification()


def _create_revision_state_notification(name, state_value, subject, recipients, message):
	if frappe.db.exists("Notification", name):
		return

	frappe.get_doc(
		{
			"doctype": "Notification",
			"name": name,
			"subject": subject,
			"document_type": "PEC Revision",
			"event": "Value Change",
			"value_changed": "workflow_state",
			"condition": f'doc.workflow_state == "{state_value}"',
			"channel": "Email",
			"send_system_notification": 1,
			"message": message,
			"recipients": recipients,
		}
	).insert(ignore_permissions=True)


def create_task_overdue_notification():
	if frappe.db.exists("Notification", NOTIFICATION_TASK_OVERDUE):
		return

	frappe.get_doc(
		{
			"doctype": "Notification",
			"name": NOTIFICATION_TASK_OVERDUE,
			"subject": "Task {{ doc.name }} is overdue",
			"document_type": "Task",
			"event": "Days After",
			"date_changed": "exp_end_date",
			"days_in_advance": 0,
			"condition": 'doc.status not in ("Completed", "Cancelled", "Template")',
			"channel": "Email",
			"send_system_notification": 1,
			"message": (
				"<p>Task <b>{{ doc.subject }}</b> ({{ doc.name }}) was due on "
				"{{ doc.exp_end_date }} and is not yet complete.</p>"
			),
			"recipients": [{"receiver_by_document_field": "reviewer"}],
		}
	).insert(ignore_permissions=True)
