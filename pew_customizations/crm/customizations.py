"""Custom Fields and Property Setters for the tender pipeline.

This module is the authoring source: `crm.setup.apply_customizations()` writes it to the DB and
`bench export-fixtures` turns it into the JSON that migrate syncs. hooks.py builds the fixture
filters from `get_custom_field_names()` / `get_property_setter_names()`.
"""

import json

from pew_customizations.crm.config import (
	BID_APPROVED,
	BID_DECISIONS,
	BID_DECLINED,
	CONSORTIUM_BID,
	CORPORATE_TENDER,
	DEFAULT_STAGE,
	DOCUMENT_CLASSES,
	INQUIRY,
	INQUIRY_TYPES,
	ORGANIZATION_TYPES,
	QUALIFICATION,
	RATE_CONTRACT,
	REFERRAL_LEAD_SOURCE,
	TENDER_INQUIRY_TYPES,
	WORK_ORDER_FIELD,
	stage_from,
)

_YES_NO = "\nYes\nNo"
_FEASIBILITY = "\nYes\nNo\nReview Needed"
# fieldname fixed by the client spec, hence no pew_ prefix
LOI_ISSUED_FIELD = "client_has_issued_loi_or_po"
# Bid Decision and the rest of the Management Decision block: Sales Users read, Sales Managers write
MANAGEMENT_PERMLEVEL = 2


def _options(values):
	return "\n" + "\n".join(values)


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


def _sub_section(idx, name, label, condition):
	"""A labelled block inside stage `idx` that shows only when `condition` (JS) holds. It opens and
	collapses with its stage (pew_show_current_stage in public/js/opportunity.js matches the name)."""
	return {
		"fieldname": f"pew_stage{idx}_{name}_section",
		"label": label,
		"fieldtype": "Section Break",
		"collapsible": 1,
		"collapsible_depends_on": f"eval:doc.pew_stage_index=={idx}",
		"depends_on": f"eval:doc.pew_stage_index>={idx} && {condition}",
	}


def _column(name, label=None):
	return {"fieldname": name, "fieldtype": "Column Break", "label": label}


def _inquiry_type_in(*types):
	"""JS condition: the Opportunity's Inquiry Type is one of `types`."""
	return f"{json.dumps(list(types))}.includes(doc.pew_inquiry_type)"


_is_tender = _inquiry_type_in(*TENDER_INQUIRY_TYPES)


def _chain(fields, start_after):
	"""Give each field an insert_after pointing at the previous one."""
	previous = start_after
	for field in fields:
		field.setdefault("insert_after", previous)
		previous = field["fieldname"]
	return fields


OPPORTUNITY_PIPELINE_FIELDS = _chain(
	[
		# 1 · Cold
		_section(1, "1 · Cold"),
		{"fieldname": "pew_expected_tender_release", "label": "Expected Tender Release Date", "fieldtype": "Date"},
		_column("pew_stage1_cb"),
		{"fieldname": "pew_cold_notes", "label": "Cold Stage Notes", "fieldtype": "Small Text"},
		# 2 · Inquiry / Tender: fixed fields for every Inquiry Type (the reused standard fields sit
		# between these custom ones, see PIPELINE_LAYOUT_HEAD)
		_section(2, "2 · Inquiry / Tender"),
		_column("pew_stage2_cb0", "Classification"),
		{
			"fieldname": "pew_inquiry_type",
			"label": "Inquiry Type",
			"fieldtype": "Select",
			"options": _options(INQUIRY_TYPES),
			"mandatory_depends_on": stage_from(INQUIRY),
			"in_standard_filter": 1,
			"description": "Decides which tender fields and approvals apply.",
		},
		{
			"fieldname": "pew_application_scope",
			"label": "Application / Scope of Work",
			"fieldtype": "Select",
			"options": _options(
				[
					"Conceptual & Feasibility Studies",
					"Multi-Disciplinary Detailed Engineering",
					"Storage Tank Design & Engineering",
					"Advanced Analysis & Simulation",
					"Specialized Advisory & Brownfield",
					"3D Modeling & Digital Solutions",
				]
			),
		},
		{
			"fieldname": "pew_project_nature",
			"label": "Project Nature",
			"fieldtype": "Select",
			"options": _options(
				[
					"Greenfield (New Facility)",
					"Revamp / Routine Maintenance",
					"Third-Party Vetting / Document Review",
					"Pure Advisory / Conceptual Study",
				]
			),
		},
		{"fieldname": "pew_project_scope", "label": "Project Detail / Scope", "fieldtype": "Small Text"},
		# Customer master data, not shown on the Opportunity (kept for reports and filters)
		{
			"fieldname": "pew_organization_type",
			"label": "Type of Organization",
			"fieldtype": "Select",
			"options": _options(ORGANIZATION_TYPES),
			"hidden": 1,
			"mandatory_depends_on": "",
		},
		{
			"fieldname": "pew_parent_customer",
			"label": "Holding / Parent Company",
			"fieldtype": "Link",
			"options": "Customer",
			"read_only": 1,
			"hidden": 1,
			"description": "From the Customer master.",
		},
		{
			"fieldname": "pew_is_key_account",
			"label": "Key Account",
			"fieldtype": "Check",
			"read_only": 1,
			"hidden": 1,
			"description": "From the Customer master.",
		},
		_column("pew_stage2_cb1", "Contact"),
		_column("pew_stage2_cb2", "Deal"),
		{
			"fieldname": "pew_inquiry_received_on",
			"label": "Inquiry Received On",
			"fieldtype": "Date",
			# today on new forms at Inquiry / Tender, set by public/js/opportunity.js: a static default
			# would also date a Cold deal, which has received no inquiry yet (frappe applies it on insert)
			"default": "",
			"mandatory_depends_on": stage_from(INQUIRY + 1),
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
		# replaced on the form by the standard Leading Deal Responsible (opportunity_owner); existing
		# rows still receive the deal team's reminders
		{
			"fieldname": "pew_wingmen",
			"label": "Wingman",
			"fieldtype": "Table MultiSelect",
			"options": "PEW Opportunity Wingman",
			"hidden": 1,
		},
		# 2 · Tender Details: the three tender Inquiry Types
		_sub_section(INQUIRY, "tender", "Tender Details", _is_tender),
		{
			"fieldname": "pew_tender_ref_no",
			"label": "Tender / Bid Ref No",
			"fieldtype": "Data",
			"mandatory_depends_on": f"eval:doc.pew_stage_index>={INQUIRY + 1} && {_is_tender}",
		},
		{
			"fieldname": "pew_procurement_portal",
			"label": "Procurement Portal",
			"fieldtype": "Select",
			"options": _options(["SAP Ariba", "Coupa", "Client Custom Portal", "Email"]),
			"depends_on": f"eval:{_inquiry_type_in(CORPORATE_TENDER)}",
		},
		{
			"fieldname": "pew_end_client",
			"label": "End Client / Ultimate Owner",
			"fieldtype": "Link",
			"options": "Customer",
			"depends_on": f"eval:{_inquiry_type_in(CONSORTIUM_BID)}",
			"description": "The project owner; Inquiry From is the bidding partner.",
		},
		{
			"fieldname": "pew_credential_sharing",
			"label": "Credential Sharing Mode",
			"fieldtype": "Select",
			"options": _options(["Using our credentials", "Using partner credentials"]),
			"depends_on": f"eval:{_inquiry_type_in(CONSORTIUM_BID)}",
		},
		# the bid submission deadline: reminders and the Kanban card use this fieldname
		{
			"fieldname": "pew_bid_submission_deadline",
			"label": "Due Date & Time",
			"fieldtype": "Datetime",
			"mandatory_depends_on": f"eval:doc.pew_stage_index>={QUALIFICATION + 1} && {_is_tender}",
		},
		{
			"fieldname": "pew_execution_period",
			"label": "Execution Period",
			"fieldtype": "Data",
			"description": "e.g. 12 Months",
		},
		_column("pew_stage2_tender_cb1", "Pre-Qualification"),
		{
			"fieldname": "pew_pqc_financial",
			"label": "PQC - Financial (Bidder Turnover)",
			"fieldtype": "Currency",
			"options": "currency",
		},
		{"fieldname": "pew_pqc_technical", "label": "PQC - Technical", "fieldtype": "Small Text"},
		_column("pew_stage2_tender_cb2", "Bid Conditions"),
		{
			"fieldname": "pew_reverse_auction",
			"label": "Reverse Auction (RA)",
			"fieldtype": "Select",
			"options": _YES_NO,
		},
		{
			"fieldname": "pew_ra_details",
			"label": "RA Details",
			"fieldtype": "Small Text",
			"depends_on": 'eval:doc.pew_reverse_auction=="Yes"',
		},
		{"fieldname": "pew_emd_exemption", "label": "EMD Exemption", "fieldtype": "Select", "options": _YES_NO},
		{
			"fieldname": "pew_emd_amount",
			"label": "EMD Amount",
			"fieldtype": "Currency",
			"options": "currency",
			"depends_on": 'eval:doc.pew_emd_exemption=="No"',
		},
		{
			"fieldname": "pew_pbg_required",
			"label": "Performance Bank Guarantee (PBG)",
			"fieldtype": "Select",
			"options": _YES_NO,
		},
		{
			"fieldname": "pew_pbg_value",
			"label": "PBG Value / Percentage",
			"fieldtype": "Data",
			"depends_on": 'eval:doc.pew_pbg_required=="Yes"',
		},
		{
			"fieldname": "pew_request_bid_approval",
			"label": "Request Bid Approval?",
			"fieldtype": "Check",
			# locked once management has decided; a Sales Manager can set the decision back to Pending
			"read_only_depends_on": f'eval:["{BID_APPROVED}", "{BID_DECLINED}"].includes(doc.pew_bid_decision)',
			"description": "Sends the details above to management for a Bid Decision.",
			# a duplicated tender asks for (and gets) its own approval
			"no_copy": 1,
		},
		# 2 · Management Decision: once the team has requested approval
		_sub_section(INQUIRY, "approval", "Management Decision", f"{_is_tender} && doc.pew_request_bid_approval"),
		{
			"fieldname": "pew_bid_decision",
			"label": "Bid Decision (Go / No-Go)",
			"fieldtype": "Select",
			"options": _options(BID_DECISIONS),
			"permlevel": MANAGEMENT_PERMLEVEL,
			"no_copy": 1,
			"description": f"{BID_DECLINED} offers to declare the Opportunity Lost.",
		},
		{
			"fieldname": "pew_pqc_document",
			"label": "PQC-Doc (Verification Proof)",
			"fieldtype": "Attach",
			"permlevel": MANAGEMENT_PERMLEVEL,
			"no_copy": 1,
		},
		_column("pew_stage2_approval_cb1"),
		{
			"fieldname": "pew_bid_target_date",
			"label": "Bid Target Date",
			"fieldtype": "Date",
			"permlevel": MANAGEMENT_PERMLEVEL,
			"no_copy": 1,
			"description": "Internal target to finalize the submission.",
		},
		{
			"fieldname": "pew_submission_mode",
			"label": "Submission Mode",
			"fieldtype": "Select",
			"options": _options(["Online Portal", "GeM", "Email", "Physical"]),
			"permlevel": MANAGEMENT_PERMLEVEL,
			"no_copy": 1,
		},
		# 2 · Release Order Details: call-offs under a rate contract
		_sub_section(INQUIRY, "release", "Release Order Details", _inquiry_type_in(RATE_CONTRACT)),
		{"fieldname": "pew_master_contract_ref", "label": "Master ARC / Contract Ref No", "fieldtype": "Data"},
		_column("pew_stage2_release_cb1"),
		{"fieldname": "pew_release_order_no", "label": "Call-Off / Release Order No", "fieldtype": "Data"},
		_column("pew_stage2_release_cb2"),
		{"fieldname": "pew_sla_deadline", "label": "SLA / Turnaround Deadline", "fieldtype": "Date"},
		# 3 · Qualification (Go / No-Go)
		_section(3, "3 · Qualification (Go / No-Go)"),
		{
			"fieldname": "pew_tender_documents",
			"label": "Tender / RFQ Documents",
			"fieldtype": "Table",
			"options": "PEW Opportunity Document",
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
		},
		{
			"fieldname": "pew_bid_validity_expiry",
			"label": "Bid Validity Expiry Date",
			"fieldtype": "Date",
		},
		{
			"fieldname": "pew_final_proposal",
			"label": "Final Proposal",
			"fieldtype": "Attach",
			"description": "Commercial document. Never copied to the Project.",
		},
		_column("pew_stage5_cb1"),
		{
			"fieldname": "pew_emd_status",
			"label": "EMD / Bid Security",
			"fieldtype": "Select",
			"options": "\nPending\nSubmitted\nNot Applicable",
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
			"fieldname": LOI_ISSUED_FIELD,
			"label": "Client has issued a formal LOI or PO",
			"fieldtype": "Check",
			"description": "Check this box once the client has formally issued an LOI or PO.",
		},
		{
			"fieldname": "pew_loi_date",
			"label": "LOI / PO Issued On",
			"fieldtype": "Date",
			"depends_on": f"eval:doc.{LOI_ISSUED_FIELD}",
		},
		# 7 · Closure (Won)
		_section(7, "7 · Closure (Won)"),
		{
			"fieldname": "pew_final_contract_value",
			"label": "Final Negotiated Contract Value",
			"fieldtype": "Currency",
			"options": "currency",
		},
		{
			"fieldname": "pew_project_start_date",
			"label": "Expected Project Start Date",
			"fieldtype": "Date",
		},
		{
			"fieldname": "pew_project_end_date",
			"label": "Expected Project End Date",
			"fieldtype": "Date",
		},
		_column("pew_stage7_cb1"),
		{
			"fieldname": WORK_ORDER_FIELD,
			"label": "Work Order / Client PO",
			"fieldtype": "Attach",
			"permlevel": 1,
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
		# the default stage's (Inquiry / Tender): forms mapped from a Customer or Lead never fetch it
		"default": str(INQUIRY),
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
	("sales_stage", "default", DEFAULT_STAGE, "Data"),
	("sales_stage", "reqd", "1", "Check"),
	# Inquiry From (Organization) is always a Customer (enforced in crm.opportunity.validate). It locks
	# once it is one, so an older Lead-based Opportunity can still be pointed at its Customer. The form
	# label is set again in public/js/opportunity.js: ERPNext relabels Party on every refresh.
	("opportunity_from", "default", "Customer", "Data"),
	("opportunity_from", "read_only_depends_on", 'eval:doc.opportunity_from=="Customer"', "Code"),
	("party_name", "label", "Inquiry From (Organization)", "Data"),
	("market_segment", "label", "Market Segment", "Data"),
	("market_segment", "mandatory_depends_on", stage_from(INQUIRY + 1), "Code"),
	("contact_person", "mandatory_depends_on", stage_from(INQUIRY + 1), "Code"),
	# Contact details come from the selected Contact: picking one refreshes them (ERPNext for email and
	# mobile, public/js/opportunity.js for job title and phone); the server fills them only while empty,
	# so values typed before they became read-only are kept
	("job_title", "fetch_from", "contact_person.designation", "Small Text"),
	("job_title", "fetch_if_empty", "1", "Check"),
	("job_title", "read_only", "1", "Check"),
	("contact_email", "fetch_from", "contact_person.email_id", "Small Text"),
	("contact_email", "fetch_if_empty", "1", "Check"),
	("contact_email", "read_only", "1", "Check"),
	("contact_mobile", "fetch_from", "contact_person.mobile_no", "Small Text"),
	("contact_mobile", "fetch_if_empty", "1", "Check"),
	("contact_mobile", "read_only", "1", "Check"),
	("phone", "fetch_from", "contact_person.phone", "Small Text"),
	("phone", "fetch_if_empty", "1", "Check"),
	("phone", "read_only", "1", "Check"),
	# Customer master data, not shown on the Opportunity. Kept as setters (rather than dropped) because
	# fixture sync never deletes a Property Setter that leaves the fixtures.
	("customer_address", "hidden", "1", "Check"),
	("address_display", "hidden", "1", "Check"),
	("website", "hidden", "1", "Check"),
	("title", "hidden", "0", "Check"),
	("title", "label", "Opportunity Name", "Data"),
	("title", "bold", "1", "Check"),
	("title", "mandatory_depends_on", stage_from(INQUIRY), "Code"),
	("opportunity_amount", "label", "Estimated Value", "Data"),
	("expected_closing", "label", "Expected Award Date", "Data"),
	("utm_source", "label", "Marketing / Lead Source", "Data"),
	("utm_source", "mandatory_depends_on", stage_from(INQUIRY + 1), "Code"),
	("opportunity_owner", "label", "Leading Deal Responsible", "Data"),
	("opportunity_owner", "mandatory_depends_on", stage_from(INQUIRY + 1), "Code"),
	# the field sits in Stage 2, hidden on Cold deals, whose Tender Release Follow-up goes to it
	("opportunity_owner", "default", "__user", "Data"),
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

# The EPC Pipeline tab, last (after Connections): this block (stage 1 and the fixed Stage 2 fields),
# followed by the Stage 2 Inquiry Type blocks and the stage 3-7 fields in spec order.
PIPELINE_LAYOUT_HEAD = [
	"pew_pipeline_tab",
	"pew_stage1_section",
	"pew_expected_tender_release",
	"pew_stage1_cb",
	"pew_cold_notes",
	"pew_stage2_section",
	"pew_stage2_cb0",
	"pew_inquiry_type",
	"market_segment",
	"pew_application_scope",
	"pew_project_nature",
	"pew_project_scope",
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
	"pew_inquiry_received_on",
	"utm_source",
	"pew_referral_type",
	"pew_referral_from",
	"opportunity_owner",
	"pew_wingmen",
	"opportunity_amount",
	"expected_closing",
]


def get_pipeline_layout():
	names = [f["fieldname"] for f in OPPORTUNITY_PIPELINE_FIELDS]
	return PIPELINE_LAYOUT_HEAD + names[names.index("pew_wingmen") + 1 :]


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
