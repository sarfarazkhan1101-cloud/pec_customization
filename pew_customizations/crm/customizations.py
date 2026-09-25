"""Custom Fields and Property Setters for the tender pipeline.

This module is the authoring source: `crm.setup.apply_customizations()` writes it to the DB and
`bench export-fixtures` turns it into the JSON that migrate syncs. hooks.py builds the fixture
filters from `get_custom_field_names()` / `get_property_setter_names()`.
"""

import json

from pew_customizations.crm.config import (
	DOCUMENT_CLASSES,
	EVALUATION,
	INQUIRY,
	ORGANIZATION_TYPES,
	PROPOSAL,
	QUALIFICATION,
	REFERRAL_LEAD_SOURCE,
	TENDER_REF_REQUIRED_FOR,
	WON,
	WORK_ORDER_FIELD,
	stage_from,
)

_YES_NO = "\nYes\nNo"
_FEASIBILITY = "\nYes\nNo\nReview Needed"


def _section(idx, label):
	return {
		"fieldname": f"pew_stage{idx}_section",
		"label": label,
		"fieldtype": "Section Break",
		"collapsible": 1,
		# current stage expanded, earlier ones collapsed (still visible), later ones hidden
		"collapsible_depends_on": f"eval:doc.pew_stage_index=={idx}",
		"depends_on": stage_from(idx),
	}


def _column(name, label=None):
	return {"fieldname": name, "fieldtype": "Column Break", "label": label}


def _chain(fields, start_after):
	"""Give each field an insert_after pointing at the previous one."""
	previous = start_after
	for field in fields:
		field.setdefault("insert_after", previous)
		previous = field["fieldname"]
	return fields


_tender_ref_rule = json.dumps(list(TENDER_REF_REQUIRED_FOR))

OPPORTUNITY_PIPELINE_FIELDS = _chain(
	[
		# 1 · Cold
		_section(1, "1 · Cold"),
		{"fieldname": "pew_expected_tender_release", "label": "Expected Tender Release Date", "fieldtype": "Date"},
		_column("pew_stage1_cb"),
		{"fieldname": "pew_cold_notes", "label": "Cold Stage Notes", "fieldtype": "Small Text"},
		# 2 · Inquiry / Tender
		_section(2, "2 · Inquiry / Tender"),
		{
			"fieldname": "pew_organization_type",
			"label": "Type of Organization",
			"fieldtype": "Select",
			"options": "\n" + "\n".join(ORGANIZATION_TYPES),
			"mandatory_depends_on": stage_from(INQUIRY + 1),
		},
		{
			"fieldname": "pew_parent_customer",
			"label": "Holding / Parent Company",
			"fieldtype": "Link",
			"options": "Customer",
			"read_only": 1,
			"description": "From the Customer master.",
		},
		{
			"fieldname": "pew_is_key_account",
			"label": "Key Account",
			"fieldtype": "Check",
			"read_only": 1,
			"description": "From the Customer master.",
		},
		# the reused standard contact fields sit between these two breaks (see PIPELINE_LAYOUT_HEAD)
		_column("pew_stage2_cb1", "Contact"),
		_column("pew_stage2_cb2", "Deal"),
		{
			"fieldname": "pew_tender_ref_no",
			"label": "Tender Ref No",
			"fieldtype": "Data",
			"mandatory_depends_on": (
				f"eval:doc.pew_stage_index>={INQUIRY + 1} && "
				f"{_tender_ref_rule}.includes(doc.pew_organization_type)"
			),
		},
		{
			"fieldname": "pew_referral_type",
			"label": "Referral Type",
			"fieldtype": "Select",
			"options": "\nCustomer\nContact",
			"depends_on": f'eval:doc.utm_source=="{REFERRAL_LEAD_SOURCE}"',
		},
		{
			"fieldname": "pew_referral_from",
			"label": "Referral Received From",
			"fieldtype": "Dynamic Link",
			"options": "pew_referral_type",
			"depends_on": f'eval:doc.utm_source=="{REFERRAL_LEAD_SOURCE}"',
			"mandatory_depends_on": (
				f'eval:doc.utm_source=="{REFERRAL_LEAD_SOURCE}" && doc.pew_stage_index>={INQUIRY + 1}'
			),
		},
		{
			"fieldname": "pew_wingmen",
			"label": "Wingman",
			"fieldtype": "Table MultiSelect",
			"options": "PEW Opportunity Wingman",
		},
		{
			"fieldname": "pew_inquiry_received_on",
			"label": "Inquiry Received On",
			"fieldtype": "Date",
			"mandatory_depends_on": stage_from(INQUIRY + 1),
		},
		# 3 · Qualification (Go / No-Go)
		_section(3, "3 · Qualification (Go / No-Go)"),
		{
			"fieldname": "pew_tender_documents",
			"label": "Tender / RFQ Documents",
			"fieldtype": "Table",
			"options": "PEW Opportunity Document",
			"mandatory_depends_on": stage_from(QUALIFICATION + 1),
		},
		{
			"fieldname": "pew_bid_submission_deadline",
			"label": "Bid Submission Deadline",
			"fieldtype": "Datetime",
			"mandatory_depends_on": stage_from(QUALIFICATION + 1),
		},
		{"fieldname": "pew_query_deadline", "label": "Query / RFI Deadline", "fieldtype": "Datetime"},
		{
			"fieldname": "pew_nda_status",
			"label": "NDA Status",
			"fieldtype": "Select",
			"options": "\nYes\nNo\nNot Required",
			"mandatory_depends_on": stage_from(QUALIFICATION + 1),
		},
		{
			"fieldname": "pew_nda_attachment",
			"label": "NDA Attachment",
			"fieldtype": "Attach",
			"depends_on": 'eval:doc.pew_nda_status=="Yes"',
			"mandatory_depends_on": f'eval:doc.pew_nda_status=="Yes" && doc.pew_stage_index>={QUALIFICATION + 1}',
		},
		_column("pew_stage3_cb1", "Feasibility"),
		{
			"fieldname": "pew_location_feasibility",
			"label": "Location Feasibility",
			"fieldtype": "Select",
			"options": _FEASIBILITY,
		},
		{
			"fieldname": "pew_budget_feasibility",
			"label": "Budget & Finance",
			"fieldtype": "Select",
			"options": _FEASIBILITY,
		},
		{
			"fieldname": "pew_authority_feasibility",
			"label": "Authority",
			"fieldtype": "Select",
			"options": _FEASIBILITY,
		},
		{
			"fieldname": "pew_timeline_feasibility",
			"label": "Timeline Feasibility",
			"fieldtype": "Select",
			"options": _FEASIBILITY,
		},
		{
			"fieldname": "pew_bandwidth_feasibility",
			"label": "Complexity & Scope / Bandwidth",
			"fieldtype": "Select",
			"options": _FEASIBILITY,
		},
		# two columns, not three, so the documents table gets half the width
		{
			"fieldname": "pew_subcontract_required",
			"label": "Subcontract Required",
			"fieldtype": "Select",
			"options": _YES_NO,
		},
		{
			"fieldname": "pew_subcontracted_scope",
			"label": "Subcontracted Scope",
			"fieldtype": "Small Text",
			"depends_on": 'eval:doc.pew_subcontract_required=="Yes"',
			"mandatory_depends_on": (
				f'eval:doc.pew_subcontract_required=="Yes" && doc.pew_stage_index>={QUALIFICATION + 1}'
			),
		},
		{
			"fieldname": "pew_go_no_go",
			"label": "Go / No-Go Decision",
			"fieldtype": "Select",
			"options": "\nGo\nNo-Go",
			"mandatory_depends_on": stage_from(QUALIFICATION + 1),
			"description": "Choosing No-Go offers to declare the Opportunity Lost.",
		},
		# 4 · Queries & Clarifications
		_section(4, "4 · Queries & Clarifications"),
		{"fieldname": "pew_pre_bid_meeting_date", "label": "Pre-Bid Meeting Date", "fieldtype": "Date"},
		{
			"fieldname": "pew_clarification_documents",
			"label": "Clarifications & Addendums",
			"fieldtype": "Table",
			"options": "PEW Opportunity Document",
		},
		_column("pew_stage4_cb1", "Checklist"),
		{"fieldname": "pew_queries_clarified", "label": "All queries clarified", "fieldtype": "Check"},
		{"fieldname": "pew_scope_locked", "label": "Final scope locked", "fieldtype": "Check"},
		# 5 · Proposal Submitted
		_section(5, "5 · Proposal Submitted"),
		{
			"fieldname": "pew_submitted_bid_value",
			"label": "Submitted Bid Value",
			"fieldtype": "Currency",
			"options": "currency",
			"mandatory_depends_on": stage_from(PROPOSAL),
		},
		{
			"fieldname": "pew_bid_validity_expiry",
			"label": "Bid Validity Expiry Date",
			"fieldtype": "Date",
			"mandatory_depends_on": stage_from(PROPOSAL),
		},
		{
			"fieldname": "pew_final_proposal",
			"label": "Final Proposal",
			"fieldtype": "Attach",
			"mandatory_depends_on": stage_from(PROPOSAL),
			"description": "Commercial document. Never copied to the Project.",
		},
		_column("pew_stage5_cb1"),
		{
			"fieldname": "pew_emd_status",
			"label": "EMD / Bid Security",
			"fieldtype": "Select",
			"options": "\nPending\nSubmitted\nNot Applicable",
			"mandatory_depends_on": stage_from(PROPOSAL),
		},
		{
			"fieldname": "pew_emd_reference",
			"label": "EMD Reference",
			"fieldtype": "Data",
			"depends_on": 'eval:doc.pew_emd_status=="Submitted"',
		},
		{
			"fieldname": "pew_commercial_documents",
			"label": "Pricing / BOQ & Commercial Documents",
			"fieldtype": "Table",
			"options": "PEW Opportunity Document",
		},
		# 6 · Evaluation
		_section(6, "6 · Evaluation"),
		{
			"fieldname": "pew_evaluation_substage",
			"label": "Sub-Stage Status",
			"fieldtype": "Select",
			"options": "\nTechnical Bid Review\nPrice Bid Review\nCommercial Negotiation",
			"mandatory_depends_on": stage_from(EVALUATION),
		},
		{
			"fieldname": "pew_commercial_rank",
			"label": "Our Commercial Rank",
			"fieldtype": "Select",
			"options": "\nL1\nL2\nL3\nN/A",
			"depends_on": (
				'eval:["Price Bid Review","Commercial Negotiation"].includes(doc.pew_evaluation_substage)'
			),
		},
		_column("pew_stage6_cb1"),
		{
			"fieldname": "pew_loi_date",
			"label": "LOI / PO Issued On",
			"fieldtype": "Date",
			"mandatory_depends_on": stage_from(EVALUATION + 1),
		},
		# 7 · Closure (Won)
		_section(7, "7 · Closure (Won)"),
		{
			"fieldname": "pew_final_contract_value",
			"label": "Final Negotiated Contract Value",
			"fieldtype": "Currency",
			"options": "currency",
			"mandatory_depends_on": stage_from(WON),
		},
		{
			"fieldname": "pew_project_start_date",
			"label": "Expected Project Start Date",
			"fieldtype": "Date",
			"mandatory_depends_on": stage_from(WON),
		},
		{
			"fieldname": "pew_project_end_date",
			"label": "Expected Project End Date",
			"fieldtype": "Date",
			"mandatory_depends_on": stage_from(WON),
		},
		_column("pew_stage7_cb1"),
		{
			"fieldname": WORK_ORDER_FIELD,
			"label": "Work Order / Client PO",
			"fieldtype": "Attach",
			"permlevel": 1,
			"mandatory_depends_on": stage_from(WON),
			"description": "Visible to Sales Managers only. Stays on the Opportunity; upload as a private file.",
		},
		{
			"fieldname": "pew_project",
			"label": "Project",
			"fieldtype": "Link",
			"options": "Project",
			"read_only": 1,
			"no_copy": 1,
			"depends_on": "eval:doc.pew_project",
		},
	],
	start_after="pew_pipeline_tab",
)

OPPORTUNITY_FIELDS = [
	{
		"fieldname": "pew_stage_index",
		"label": "Stage Index",
		"fieldtype": "Int",
		"hidden": 1,
		"read_only": 1,
		"default": "1",
		"fetch_from": "sales_stage.pew_stage_order",
		"insert_after": "sales_stage",
	},
	{
		"fieldname": "pew_lost_on",
		"label": "Lost On",
		"fieldtype": "Date",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "order_lost_reason",
	},
	{
		"fieldname": "pew_pipeline_tab",
		"label": "EPC Pipeline",
		"fieldtype": "Tab Break",
		"insert_after": "dashboard_tab",
	},
	*OPPORTUNITY_PIPELINE_FIELDS,
]

CUSTOM_FIELDS = {
	"Opportunity": OPPORTUNITY_FIELDS,
	"Sales Stage": [
		{
			"fieldname": "pew_stage_order",
			"label": "Pipeline Order",
			"fieldtype": "Int",
			"in_list_view": 1,
			"insert_after": "stage_name",
			"description": "Position in the PEW tender pipeline (1-7). Blank = not selectable on Opportunity.",
		},
	],
	"Customer": [
		{
			"fieldname": "pew_organization_type",
			"label": "Type of Organization",
			"fieldtype": "Select",
			"options": "\n" + "\n".join(ORGANIZATION_TYPES),
			"insert_after": "customer_type",
		},
		{
			"fieldname": "pew_parent_customer",
			"label": "Holding / Parent Company",
			"fieldtype": "Link",
			"options": "Customer",
			"insert_after": "customer_group",
		},
		{
			"fieldname": "pew_is_key_account",
			"label": "Key Account",
			"fieldtype": "Check",
			"insert_after": "pew_parent_customer",
		},
	],
	"Project": [
		{
			"fieldname": "pew_contract_value",
			"label": "Contract Value",
			"fieldtype": "Currency",
			"options": "Company:company:default_currency",
			"read_only": 1,
			"insert_after": "estimated_costing",
			"description": "Final negotiated contract value from the source Opportunity, in company currency.",
		},
	],
	"File": [
		{
			"fieldname": "document_category",
			"label": "Document Category",
			"fieldtype": "Select",
			"options": "\n" + "\n".join(DOCUMENT_CLASSES),
			"insert_after": "file_type",
		},
	],
}

# Standard Opportunity fields reused for the spec: (fieldname, property, value, property_type)
OPPORTUNITY_PROPERTY_SETTERS = [
	("sales_stage", "default", "Cold", "Data"),
	("sales_stage", "reqd", "1", "Check"),
	("market_segment", "label", "Market Segment / Application Type", "Data"),
	("market_segment", "mandatory_depends_on", stage_from(INQUIRY + 1), "Code"),
	("contact_person", "mandatory_depends_on", stage_from(INQUIRY + 1), "Code"),
	("job_title", "fetch_from", "contact_person.designation", "Small Text"),
	("job_title", "fetch_if_empty", "1", "Check"),
	("phone", "fetch_from", "contact_person.phone", "Small Text"),
	("phone", "fetch_if_empty", "1", "Check"),
	("customer_address", "hidden", "0", "Check"),
	("address_display", "hidden", "0", "Check"),
	("title", "hidden", "0", "Check"),
	("title", "label", "Opportunity Name", "Data"),
	("title", "bold", "1", "Check"),
	("title", "mandatory_depends_on", stage_from(INQUIRY + 1), "Code"),
	("opportunity_amount", "label", "Estimated Value", "Data"),
	("expected_closing", "label", "Expected Award Date", "Data"),
	("utm_source", "label", "Lead Source", "Data"),
	("utm_source", "mandatory_depends_on", stage_from(INQUIRY + 1), "Code"),
	("opportunity_owner", "label", "Leading Deal Responsible", "Data"),
	("opportunity_owner", "mandatory_depends_on", stage_from(INQUIRY + 1), "Code"),
	("lost_reasons", "label", "Loss Reason(s)", "Data"),
	("competitors", "label", "Competitor(s) Who Won", "Data"),
]

# DocType-level: (property, value, property_type). field_order is added by build_field_order().
OPPORTUNITY_DOCTYPE_PROPERTY_SETTERS = [
	("track_changes", "1", "Check"),
]

PROJECT_PROPERTY_SETTERS = [
	("users_section", "label", "Execution Team", "Data"),
	("users", "label", "Execution Team", "Data"),
]

# Where the reused standard fields and the pipeline sections sit on the form; the remaining standard
# fields keep their default order. Lost details stay on the Details tab right after the header
# (after `probability`) so a Lost deal shows why at the top.
LOST_LAYOUT = [
	"lost_detail_section",
	"lost_reasons",
	"order_lost_reason",
	"pew_lost_on",
	"column_break_56",
	"competitors",
]

# The EPC Pipeline tab, last (after Connections): this block, followed by the stage 3-7 fields in
# spec order.
PIPELINE_LAYOUT_HEAD = [
	"pew_pipeline_tab",
	"pew_stage1_section",
	"pew_expected_tender_release",
	"market_segment",
	"pew_stage1_cb",
	"pew_cold_notes",
	"pew_stage2_section",
	"pew_organization_type",
	"pew_parent_customer",
	"pew_is_key_account",
	"website",
	"customer_address",
	"address_display",
	"pew_stage2_cb1",
	"contact_person",
	"job_title",
	"contact_email",
	"contact_mobile",
	"phone",
	"pew_stage2_cb2",
	"title",
	"pew_tender_ref_no",
	"opportunity_amount",
	"utm_source",
	"pew_referral_type",
	"pew_referral_from",
	"pew_wingmen",
	"pew_inquiry_received_on",
]


def get_pipeline_layout():
	names = [f["fieldname"] for f in OPPORTUNITY_PIPELINE_FIELDS]
	return PIPELINE_LAYOUT_HEAD + names[names.index("pew_inquiry_received_on") + 1 :]


def build_field_order(standard_order):
	"""Opportunity field_order: standard order with the Lost block after `probability`, the hidden
	stage index after `sales_stage` and the EPC Pipeline tab at the end."""
	pipeline = get_pipeline_layout()
	moved = set(LOST_LAYOUT) | set(pipeline) | {"pew_stage_index"}

	order = []
	for fieldname in standard_order:
		if fieldname in moved:
			continue
		order.append(fieldname)
		if fieldname == "sales_stage":
			order.append("pew_stage_index")
		if fieldname == "probability":
			order.extend(LOST_LAYOUT)
	return order + pipeline


def get_custom_field_names():
	return [f"{dt}-{field['fieldname']}" for dt, fields in CUSTOM_FIELDS.items() for field in fields]


def get_property_setter_names():
	names = [f"Opportunity-{field}-{prop}" for field, prop, _value, _type in OPPORTUNITY_PROPERTY_SETTERS]
	names += [f"Opportunity-main-{prop}" for prop, _value, _type in OPPORTUNITY_DOCTYPE_PROPERTY_SETTERS]
	names.append("Opportunity-main-field_order")
	names += [f"Project-{field}-{prop}" for field, prop, _value, _type in PROJECT_PROPERTY_SETTERS]
	return names
