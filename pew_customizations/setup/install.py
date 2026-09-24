import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

SALES_STAGES = [
	"Cold",
	"Inquiry/Tender",
	"Qualification (Go/No-Go)",
	"Queries & Clarifications",
	"Proposal Submitted",
	"Evaluation",
	"Closure (Won)",
]

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


def _stage_gate(min_stage):
	"""depends_on eval: section becomes visible once sales_stage reaches
	min_stage or later (and stays visible after, so earlier data is never
	hidden as the deal progresses)."""
	stage_list_js = str(SALES_STAGES).replace("'", '"')
	idx = SALES_STAGES.index(min_stage)
	return f"eval:{stage_list_js}.indexOf(doc.sales_stage) >= {idx}"

SERVER_SCRIPT_CREATE_PROJECT = "PEW: Create Project on Opportunity Won"
SERVER_SCRIPT_SHARE_FILES = "PEW: Share Project Files with New Team Member"
SERVER_SCRIPT_LOST_GUARD = "PEW: Enforce Lost Reason and Freeze Lost Opportunity"
NOTIFICATION_NAME = "Bid Validity Expiry Alert"
WORKFLOW_NAME = "Project Approval Workflow"

# PEC (Project Engineering / Execution) process additions
PEC_ROLES = ["Reviewer", "Scope Manager", "PEC Administrator"]
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
	create_all_custom_fields()
	create_sales_stages()
	create_market_segments()
	create_bid_validity_notification()
	create_project_approval_workflow()
	create_server_scripts()
	create_engineering_service_lifecycle_template()
	create_pec_roles()
	create_project_naming_series_option()
	create_pec_revision_workflow()
	create_pec_notifications()
	create_scope_templates()
	frappe.db.commit()
	print("pew_customizations setup complete.")


def create_all_custom_fields():
	create_custom_fields(get_custom_fields(), update=True)


def get_all_custom_fieldnames():
	"""Flat list of every fieldname this app creates, across all doctypes.
	Used to scope the `fixtures` export to exactly our own Custom Field records
	(e.g. File already has unrelated custom fields from the Drive app)."""
	return [field["fieldname"] for fields in get_custom_fields().values() for field in fields]


def get_custom_fields():
	return {
		"Opportunity": [
			{
				"fieldname": "tender_tracking_tab",
				"label": "Tender Tracking",
				"fieldtype": "Tab Break",
				"insert_after": "utm_analytics_section",
			},
			{
				"fieldname": "cold_stage_section",
				"label": "Cold Stage",
				"fieldtype": "Section Break",
				"insert_after": "tender_tracking_tab",
			},
			{
				"fieldname": "expected_tender_release_date",
				"label": "Expected Tender Release Date",
				"fieldtype": "Date",
				"insert_after": "cold_stage_section",
			},
			{
				"fieldname": "cold_stage_notes",
				"label": "Cold Stage Notes",
				"fieldtype": "Small Text",
				"insert_after": "expected_tender_release_date",
			},
			{
				"fieldname": "qualification_section",
				"label": "Qualification (Go/No-Go)",
				"fieldtype": "Section Break",
				"insert_after": "cold_stage_notes",
				"depends_on": _stage_gate("Inquiry/Tender"),
			},
			{
				"fieldname": "type_of_organization",
				"label": "Type of Organization",
				"fieldtype": "Select",
				"options": "\nGovernment\nPrivate Sector\nPSU",
				"insert_after": "qualification_section",
			},
			{
				"fieldname": "referral_source_type",
				"label": "Referral Source Type",
				"fieldtype": "Select",
				"options": "\nCustomer\nContact",
				"insert_after": "type_of_organization",
			},
			{
				"fieldname": "referral_received_from",
				"label": "Referral Received From",
				"fieldtype": "Dynamic Link",
				"options": "referral_source_type",
				"insert_after": "referral_source_type",
			},
			{
				"fieldname": "qualification_column_break",
				"fieldtype": "Column Break",
				"insert_after": "referral_received_from",
			},
			{
				"fieldname": "wingman",
				"label": "Wingman",
				"fieldtype": "Link",
				"options": "User",
				"insert_after": "qualification_column_break",
			},
			{
				"fieldname": "nda_status",
				"label": "NDA Status",
				"fieldtype": "Select",
				"options": "\nYes\nNo\nNot Required",
				"insert_after": "wingman",
			},
			{
				"fieldname": "feasibility_section",
				"label": "Feasibility Checks",
				"fieldtype": "Section Break",
				"insert_after": "nda_status",
				"depends_on": _stage_gate("Inquiry/Tender"),
			},
			{
				"fieldname": "location_feasibility",
				"label": "Location Feasibility",
				"fieldtype": "Select",
				"options": "\nYes\nNo\nReview Needed",
				"insert_after": "feasibility_section",
			},
			{
				"fieldname": "budget_feasibility",
				"label": "Budget Feasibility",
				"fieldtype": "Select",
				"options": "\nYes\nNo\nReview Needed",
				"insert_after": "location_feasibility",
			},
			{
				"fieldname": "authority_confirmed",
				"label": "Authority Confirmed",
				"fieldtype": "Select",
				"options": "\nYes\nNo\nReview Needed",
				"insert_after": "budget_feasibility",
			},
			{
				"fieldname": "feasibility_column_break",
				"fieldtype": "Column Break",
				"insert_after": "authority_confirmed",
			},
			{
				"fieldname": "timeline_feasibility",
				"label": "Timeline Feasibility",
				"fieldtype": "Select",
				"options": "\nYes\nNo\nReview Needed",
				"insert_after": "feasibility_column_break",
			},
			{
				"fieldname": "bandwidth_feasibility",
				"label": "Bandwidth Feasibility",
				"fieldtype": "Select",
				"options": "\nYes\nNo\nReview Needed",
				"insert_after": "timeline_feasibility",
			},
			{
				"fieldname": "subcontract_required",
				"label": "Subcontract Required",
				"fieldtype": "Check",
				"insert_after": "bandwidth_feasibility",
			},
			{
				"fieldname": "subcontracted_scope",
				"label": "Subcontracted Scope",
				"fieldtype": "Small Text",
				"depends_on": "eval:doc.subcontract_required",
				"insert_after": "subcontract_required",
			},
			{
				"fieldname": "queries_section",
				"label": "Queries & Clarifications",
				"fieldtype": "Section Break",
				"insert_after": "subcontracted_scope",
				"depends_on": _stage_gate("Queries & Clarifications"),
			},
			{
				"fieldname": "pre_bid_meeting_date",
				"label": "Pre-Bid Meeting Date",
				"fieldtype": "Date",
				"insert_after": "queries_section",
			},
			{
				"fieldname": "proposal_section",
				"label": "Proposal Submitted",
				"fieldtype": "Section Break",
				"insert_after": "pre_bid_meeting_date",
				"depends_on": _stage_gate("Proposal Submitted"),
			},
			{
				"fieldname": "submitted_bid_value",
				"label": "Submitted Bid Value",
				"fieldtype": "Currency",
				"insert_after": "proposal_section",
			},
			{
				"fieldname": "bid_validity_expiry_date",
				"label": "Bid Validity Expiry Date",
				"fieldtype": "Date",
				"insert_after": "submitted_bid_value",
			},
			{
				"fieldname": "evaluation_section",
				"label": "Evaluation",
				"fieldtype": "Section Break",
				"insert_after": "bid_validity_expiry_date",
				"depends_on": _stage_gate("Evaluation"),
			},
			{
				"fieldname": "evaluation_substage",
				"label": "Evaluation Sub-stage",
				"fieldtype": "Select",
				"options": "\nTechnical Bid Review\nPrice Bid Review\nCommercial Negotiation",
				"insert_after": "evaluation_section",
			},
			{
				"fieldname": "commercial_rank",
				"label": "Commercial Rank",
				"fieldtype": "Select",
				"options": "\nL1\nL2\nL3\nN/A",
				"insert_after": "evaluation_substage",
			},
			{
				"fieldname": "competitor_who_won",
				"label": "Competitor Who Won",
				"fieldtype": "Data",
				"insert_after": "commercial_rank",
			},
		],
		"File": [
			{
				"fieldname": "document_category",
				"label": "Document Category",
				"fieldtype": "Select",
				"options": (
					"\nTechnical Scope\nClient Clarification\nSite Visit Note\n"
					"Technical Addendum\nProposal\nPricing\nWork Order/PO"
				),
				"insert_after": "file_type",
			},
		],
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


def create_sales_stages():
	for stage in SALES_STAGES:
		if not frappe.db.exists("Sales Stage", stage):
			frappe.get_doc({"doctype": "Sales Stage", "stage_name": stage}).insert(ignore_permissions=True)


def create_market_segments():
	for segment in MARKET_SEGMENTS:
		if not frappe.db.exists("Market Segment", segment):
			frappe.get_doc({"doctype": "Market Segment", "market_segment": segment}).insert(ignore_permissions=True)


def create_bid_validity_notification():
	if frappe.db.exists("Notification", NOTIFICATION_NAME):
		return

	doc = frappe.get_doc(
		{
			"doctype": "Notification",
			"name": NOTIFICATION_NAME,
			"subject": "Bid validity for {{ doc.name }} expires in 7 days",
			"document_type": "Opportunity",
			"event": "Days Before",
			"date_changed": "bid_validity_expiry_date",
			"days_in_advance": 7,
			"condition": 'doc.status not in ("Closed", "Lost")',
			"channel": "Email",
			"send_system_notification": 1,
			"message": (
				"<p>The bid validity for Opportunity <b>{{ doc.name }}</b> "
				"({{ doc.customer_name or doc.party_name or \"\" }}) expires on "
				"{{ doc.bid_validity_expiry_date }}.</p>"
			),
			"recipients": [
				{"receiver_by_document_field": "opportunity_owner"},
				{"receiver_by_document_field": "wingman"},
			],
		}
	)
	doc.insert(ignore_permissions=True)


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


def create_server_scripts():
	create_project_creation_script()
	create_file_share_script()
	create_lost_guard_script()


def create_project_creation_script():
	if frappe.db.exists("Server Script", SERVER_SCRIPT_CREATE_PROJECT):
		return

	script = '''allowed_categories = ["Technical Scope", "Client Clarification", "Site Visit Note", "Technical Addendum"]

if doc.status == "Closed" and not frappe.db.exists("Project", {"source_opportunity": doc.name}):
	project = frappe.new_doc("Project")
	project.project_name = doc.title or doc.customer_name or doc.name
	project.customer = doc.party_name if doc.opportunity_from == "Customer" else None
	project.company = doc.company
	project.source_opportunity = doc.name
	project.pending_review = 1
	project.estimated_costing = doc.submitted_bid_value
	project.expected_start_date = doc.expected_closing
	project.insert(ignore_permissions=True)

	files = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Opportunity",
			"attached_to_name": doc.name,
			"document_category": ["in", allowed_categories],
		},
		fields=["file_name", "file_url", "is_private", "document_category", "folder"],
	)

	for f in files:
		new_file = frappe.new_doc("File")
		new_file.file_url = f.file_url
		new_file.file_name = f.file_name
		new_file.is_private = f.is_private
		new_file.document_category = f.document_category
		new_file.attached_to_doctype = "Project"
		new_file.attached_to_name = project.name
		new_file.insert(ignore_permissions=True)

	frappe.msgprint(
		f"Project {project.name} created (Pending Review) from this Opportunity.",
		alert=True,
		indicator="green",
	)
'''

	frappe.get_doc(
		{
			"doctype": "Server Script",
			"name": SERVER_SCRIPT_CREATE_PROJECT,
			"script_type": "DocType Event",
			"reference_doctype": "Opportunity",
			"doctype_event": "After Save",
			"disabled": 0,
			"script": script,
		}
	).insert(ignore_permissions=True)


def create_file_share_script():
	if frappe.db.exists("Server Script", SERVER_SCRIPT_SHARE_FILES):
		return

	# Note: this is bound to Project's own After Save event, not to the Project
	# User child doctype. Frappe persists child table rows via a raw db_update()
	# during the parent's save (see Document.update_child_table()), which never
	# calls the child row's insert() -- so an "After Insert" script on Project
	# User itself would never fire. Diffing get_doc_before_save() against the
	# current `users` table is the reliable way to detect newly added rows.
	script = '''before = doc.get_doc_before_save()
previous_users = {row.user for row in (before.users if before else [])}
current_users = {row.user for row in doc.users}
new_users = current_users - previous_users

if new_users and not doc.pending_review:
	files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Project", "attached_to_name": doc.name},
		fields=["name"],
	)
	for user in new_users:
		for f in files:
			already_shared = frappe.db.exists(
				"DocShare",
				{"share_doctype": "File", "share_name": f.name, "user": user},
			)
			if not already_shared:
				frappe.call(
					"frappe.share.add",
					doctype="File",
					name=f.name,
					user=user,
					read=1,
					write=0,
					notify=0,
				)
'''

	frappe.get_doc(
		{
			"doctype": "Server Script",
			"name": SERVER_SCRIPT_SHARE_FILES,
			"script_type": "DocType Event",
			"reference_doctype": "Project",
			"doctype_event": "After Save",
			"disabled": 0,
			"script": script,
		}
	).insert(ignore_permissions=True)


def create_lost_guard_script():
	if frappe.db.exists("Server Script", SERVER_SCRIPT_LOST_GUARD):
		return

	# "Lost is not a separate stage -- an Opportunity is marked Lost from
	# whatever stage it's in ... and the record freezes (no further stage
	# changes) after that." Also requires a Lost Reason to actually be
	# recorded, since nothing else enforces that outside the desk "Lost"
	# dialog (declare_enquiry_lost).
	script = '''before = doc.get_doc_before_save()

if before and before.status == "Lost":
	frappe.throw("This Opportunity is marked Lost and is locked. No further changes are allowed.")

if doc.status == "Lost" and not doc.lost_reasons:
	frappe.throw("Please select at least one Lost Reason before marking this Opportunity as Lost.")
'''

	frappe.get_doc(
		{
			"doctype": "Server Script",
			"name": SERVER_SCRIPT_LOST_GUARD,
			"script_type": "DocType Event",
			"reference_doctype": "Opportunity",
			"doctype_event": "Before Save",
			"disabled": 0,
			"script": script,
		}
	).insert(ignore_permissions=True)


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
