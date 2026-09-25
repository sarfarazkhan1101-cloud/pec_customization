"""Setup for the tender pipeline.

Development workflow (records then travel to other sites as fixtures):
	bench --site <site> execute pew_customizations.crm.setup.apply_customizations
	bench --site <site> export-fixtures --app pew_customizations

`after_migrate` only maintains the Kanban board, which cannot be a fixture: its columns store the
site's own Opportunity names for card order.
"""

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.permissions import add_permission, update_permission_property

from pew_customizations.crm.config import (
	KANBAN_BOARD,
	KANBAN_CARD_FIELDS,
	KANBAN_INDICATORS,
	LEAD_SOURCES,
	LOST_REASONS,
	NOTIFICATION_BID_DEADLINE,
	NOTIFICATION_BID_VALIDITY,
	NOTIFICATION_PROJECT_REVIEW,
	NOTIFICATION_QUERY_DEADLINE,
	NOTIFICATION_TENDER_RELEASE,
	PIPELINE_STAGES,
	PROJECT_APPROVED_STATE,
	PROPOSAL,
	QUERIES,
	SALES_STAGE_ORDER,
)
from pew_customizations.crm.customizations import (
	CUSTOM_FIELDS,
	OPPORTUNITY_DOCTYPE_PROPERTY_SETTERS,
	OPPORTUNITY_PROPERTY_SETTERS,
	PROJECT_PROPERTY_SETTERS,
	build_field_order,
)

PROJECT_APPROVAL_WORKFLOW = "Project Approval Workflow"
WORK_ORDER_ROLE = "Sales Manager"


def apply_customizations():
	from pew_customizations.setup.install import create_all_custom_fields

	create_all_custom_fields()  # PEC Project/Task fields (Project.source_opportunity is unique)
	create_custom_fields(CUSTOM_FIELDS, update=True)
	apply_property_setters()
	ensure_sales_stages()
	ensure_masters()
	ensure_notifications()
	ensure_work_order_permissions()
	ensure_project_workflow_roles()
	ensure_tender_kanban()
	frappe.db.commit()
	print("PEW tender pipeline customizations applied.")


def after_migrate():
	ensure_tender_kanban()


def apply_property_setters():
	for fieldname, prop, value, ptype in OPPORTUNITY_PROPERTY_SETTERS:
		_set_property("Opportunity", fieldname, prop, value, ptype)
	for prop, value, ptype in OPPORTUNITY_DOCTYPE_PROPERTY_SETTERS:
		_set_property("Opportunity", None, prop, value, ptype)
	for fieldname, prop, value, ptype in PROJECT_PROPERTY_SETTERS:
		_set_property("Project", fieldname, prop, value, ptype)

	standard_order = [df.fieldname for df in frappe.get_doc("DocType", "Opportunity").fields]
	_set_property("Opportunity", None, "field_order", json.dumps(build_field_order(standard_order)), "Data")


def _set_property(doctype, fieldname, prop, value, ptype):
	name = f"{doctype}-{fieldname or 'main'}-{prop}"
	if frappe.db.get_value("Property Setter", name, "value") == value:
		return
	make_property_setter(doctype, fieldname, prop, value, ptype, for_doctype=not fieldname)


def ensure_sales_stages():
	for stage, order in SALES_STAGE_ORDER.items():
		if frappe.db.exists("Sales Stage", stage):
			frappe.db.set_value("Sales Stage", stage, "pew_stage_order", order)
		else:
			frappe.get_doc({"doctype": "Sales Stage", "stage_name": stage, "pew_stage_order": order}).insert(
				ignore_permissions=True
			)
	# anything else is not selectable on Opportunity
	frappe.db.set_value(
		"Sales Stage", {"name": ("not in", PIPELINE_STAGES), "pew_stage_order": ("!=", 0)}, "pew_stage_order", 0
	)


def ensure_masters():
	for reason in LOST_REASONS:
		if not frappe.db.exists("Opportunity Lost Reason", reason):
			frappe.get_doc({"doctype": "Opportunity Lost Reason", "lost_reason": reason}).insert(
				ignore_permissions=True
			)
	for source in LEAD_SOURCES:
		if not frappe.db.exists("UTM Source", source):
			doc = frappe.new_doc("UTM Source")
			doc.name = source
			doc.insert(ignore_permissions=True)


def _notification_specs():
	active = 'doc.status not in ("Lost", "Closed", "Converted")'
	deal_team = [
		{"receiver_by_document_field": "opportunity_owner"},
		{"receiver_by_document_field": "user,pew_wingmen"},
	]
	link = '<a href="{{ frappe.utils.get_url_to_form(doc.doctype, doc.name) }}">{{ doc.title or doc.name }}</a>'
	return [
		{
			"name": NOTIFICATION_BID_VALIDITY,
			"document_type": "Opportunity",
			"event": "Days Before",
			"date_changed": "pew_bid_validity_expiry",
			"days_in_advance": 7,
			"condition": active,
			"subject": "Bid validity for {{ doc.title or doc.name }} expires in 7 days",
			"message": f"<p>The bid validity for {link} ({{{{ doc.customer_name or doc.party_name }}}}) "
			"expires on {{ frappe.utils.formatdate(doc.pew_bid_validity_expiry) }}. "
			"Request an extension from the client if the evaluation is still open.</p>",
			"recipients": deal_team,
		},
		{
			"name": NOTIFICATION_BID_DEADLINE,
			"document_type": "Opportunity",
			"event": "Days Before",
			"date_changed": "pew_bid_submission_deadline",
			"days_in_advance": 2,
			"condition": f"{active} and doc.pew_stage_index < {PROPOSAL}",
			"subject": "Bid for {{ doc.title or doc.name }} is due in 2 days",
			"message": f"<p>The bid for {link} must be submitted by "
			"{{ frappe.utils.format_datetime(doc.pew_bid_submission_deadline) }}.</p>",
			"recipients": deal_team,
		},
		{
			"name": NOTIFICATION_QUERY_DEADLINE,
			"document_type": "Opportunity",
			"event": "Days Before",
			"date_changed": "pew_query_deadline",
			"days_in_advance": 1,
			"condition": f"{active} and doc.pew_stage_index <= {QUERIES}",
			"subject": "Query / RFI deadline for {{ doc.title or doc.name }} is tomorrow",
			"message": f"<p>Queries for {link} must reach the client by "
			"{{ frappe.utils.format_datetime(doc.pew_query_deadline) }}.</p>",
			"recipients": deal_team,
		},
		{
			"name": NOTIFICATION_TENDER_RELEASE,
			"document_type": "Opportunity",
			"event": "Days Before",
			"date_changed": "pew_expected_tender_release",
			"days_in_advance": 7,
			"condition": f'{active} and doc.sales_stage == "{PIPELINE_STAGES[0]}"',
			"subject": "Tender for {{ doc.title or doc.name }} is expected next week",
			"message": f"<p>The tender for {link} is expected on "
			"{{ frappe.utils.formatdate(doc.pew_expected_tender_release) }}. Follow up with the client.</p>",
			"recipients": [{"receiver_by_document_field": "opportunity_owner"}],
		},
		{
			"name": NOTIFICATION_PROJECT_REVIEW,
			"document_type": "Project",
			"event": "New",
			"condition": "doc.source_opportunity",
			"subject": "Project {{ doc.name }} from a won tender needs review",
			"message": '<p>Project <a href="{{ frappe.utils.get_url_to_form(doc.doctype, doc.name) }}">'
			"{{ doc.project_name }}</a> was created from Opportunity {{ doc.source_opportunity }}. "
			"Review it, add the Execution Team and approve it.</p>",
			"recipients": [{"receiver_by_role": "Projects Manager"}],
		},
	]


def ensure_notifications():
	for spec in _notification_specs():
		spec = {
			"doctype": "Notification",
			"channel": "Email",
			"send_system_notification": 1,
			"enabled": 1,
			"condition_type": "Python",
			**spec,
		}
		if frappe.db.exists("Notification", spec["name"]):
			doc = frappe.get_doc("Notification", spec["name"])
			doc.set("recipients", [])
			doc.update(spec)
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc(spec).insert(ignore_permissions=True)


def ensure_work_order_permissions():
	"""Permission level 1 (the Work Order / Client PO field) is readable and writable by Sales
	Managers only. The first custom rule copies Opportunity's standard permissions into Custom
	DocPerm, which then replaces them for this doctype (exported as fixtures)."""
	if not frappe.db.exists("Custom DocPerm", {"parent": "Opportunity", "role": WORK_ORDER_ROLE, "permlevel": 1}):
		add_permission("Opportunity", WORK_ORDER_ROLE, permlevel=1)
	update_permission_property("Opportunity", WORK_ORDER_ROLE, 1, "write", 1)


def ensure_project_workflow_roles():
	"""Once approved, the Execution Team (Projects User) must be able to edit the Project, not only
	Projects Managers. Workflows allow several rows for one state, one per role."""
	if not frappe.db.exists("Workflow", PROJECT_APPROVAL_WORKFLOW):
		return
	workflow = frappe.get_doc("Workflow", PROJECT_APPROVAL_WORKFLOW)
	approved = [row for row in workflow.states if row.state == PROJECT_APPROVED_STATE]
	if not approved or any(row.allow_edit == "Projects User" for row in approved):
		return
	workflow.append(
		"states",
		{
			"state": PROJECT_APPROVED_STATE,
			"doc_status": approved[0].doc_status,
			"update_field": approved[0].update_field,
			"update_value": approved[0].update_value,
			"allow_edit": "Projects User",
		},
	)
	workflow.save(ignore_permissions=True)


def ensure_tender_kanban():
	"""Kanban on the standard sales_stage Link field. The board dialog only offers Select fields, but
	a board created in code works (cards move via frappe.set_value, so all save hooks run)."""
	if not frappe.db.exists("DocType", "Kanban Board"):
		return

	if frappe.db.exists("Kanban Board", KANBAN_BOARD):
		board = frappe.get_doc("Kanban Board", KANBAN_BOARD)
		existing = {col.column_name: col for col in board.columns}
		if [col.column_name for col in board.columns] == PIPELINE_STAGES:
			return
	else:
		board = frappe.new_doc("Kanban Board")
		board.kanban_board_name = KANBAN_BOARD
		board.fields = json.dumps(KANBAN_CARD_FIELDS)
		board.show_labels = 1
		existing = {}

	board.reference_doctype = "Opportunity"
	board.field_name = "sales_stage"
	board.set("columns", [])
	for stage, indicator in zip(PIPELINE_STAGES, KANBAN_INDICATORS, strict=True):
		column = existing.get(stage)
		board.append(
			"columns",
			{
				"column_name": stage,
				"status": "Active",
				"indicator": column.indicator if column else indicator,
				"order": column.order if column else None,
			},
		)
	board.save(ignore_permissions=True)
