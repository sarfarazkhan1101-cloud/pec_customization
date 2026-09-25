"""Single source of truth for the PEW tender pipeline on the standard Opportunity.

Pure data (no DB access at import time) so hooks.py can import it for fixture filters.
The stage order itself lives on Sales Stage.pew_stage_order (see SALES_STAGE_ORDER);
Opportunity.pew_stage_index fetches it, which is what every depends_on expression uses.
"""

from dataclasses import dataclass
from typing import Callable

PIPELINE_STAGES = [
	"Cold",
	"Inquiry / Tender",
	"Qualification",
	"Queries & Clarifications",
	"Proposal Submitted",
	"Evaluation",
	"Closure (Won)",
]
SALES_STAGE_ORDER = {stage: idx for idx, stage in enumerate(PIPELINE_STAGES, start=1)}
COLD, INQUIRY, QUALIFICATION, QUERIES, PROPOSAL, EVALUATION, WON = range(1, 8)
COLD_STAGE = PIPELINE_STAGES[COLD - 1]
WON_STAGE = PIPELINE_STAGES[WON - 1]

# v1 stage names renamed/merged by patches.crm_v2_sales_stages
LEGACY_STAGE_RENAMES = {
	"Inquiry/Tender": "Inquiry / Tender",
	"Qualification (Go/No-Go)": "Qualification",
}

# Statuses of an Opportunity that is still being pursued (standard options, no custom status)
ACTIVE_STATUSES = ("Open", "Replied", "Quotation")

# May edit/reopen a Lost Opportunity, move a deal to Won, move it back after handoff,
# and read the Work Order / Client PO.
MANAGER_ROLES = ("Sales Manager", "System Manager")

LOST_TAG = "Lost"

LOST_REASONS = [
	"Outside Domain",
	"Internal No-Go/Lack of Bandwidth",
	"Unacceptable Commercial Terms",
	"Technical Disqualification",
	"Outbid on Price",
	"Client Cancelled Project",
	"Client Went Cold",
]

# Standard UTM Source records reused as "Lead Source". The first three are ERPNext defaults.
REFERRAL_LEAD_SOURCE = "Reference"
LEAD_SOURCES = ["Existing Customer", "Exhibition", REFERRAL_LEAD_SOURCE, "Tender Portal", "Direct Email"]

ORGANIZATION_TYPES = ["Government", "Private Sector", "PSU"]
TENDER_REF_REQUIRED_FOR = ("Government", "PSU")

# Document type -> class. Only "Technical" documents are copied to the Project on handoff.
DOCUMENT_CLASSES = {
	"Tender / RFQ Document": "Technical",
	"Drawing": "Technical",
	"Technical Specification": "Technical",
	"Clarification / Query Response": "Technical",
	"Addendum / Corrigendum": "Technical",
	"Minutes of Meeting": "Technical",
	"Site Visit Note": "Technical",
	"Proposal": "Commercial",
	"Pricing / BOQ": "Commercial",
	"EMD / Bid Security": "Commercial",
	"NDA": "Commercial",
	"Work Order / PO": "Commercial",
	"Other Commercial": "Commercial",
}
TECHNICAL = "Technical"
# Rows in the document tables may not use this type: the PO has its own restricted field.
RESTRICTED_DOCUMENT_TYPE = "Work Order / PO"

# Opportunity Table fields that use the PEW Opportunity Document child doctype
DOCUMENT_TABLES = ("pew_tender_documents", "pew_clarification_documents", "pew_commercial_documents")

# Single-file Attach fields -> File.document_category. Never copied to the Project.
ATTACH_FIELD_CATEGORIES = {
	"pew_nda_attachment": "NDA",
	"pew_final_proposal": "Proposal",
	"pew_work_order_file": "Work Order / PO",
}
WORK_ORDER_FIELD = "pew_work_order_file"

PROJECT_NAMING_SERIES = "PEC-.YYYY.-.####"
PROJECT_APPROVED_STATE = "Approved"
# Never restricted by the Execution Team's User Permissions
PROJECT_ACCESS_BYPASS_ROLES = ("Projects Manager", "System Manager")

KANBAN_BOARD = "Tender Pipeline"
KANBAN_INDICATORS = ["Gray", "Blue", "Cyan", "Purple", "Orange", "Yellow", "Green"]
KANBAN_CARD_FIELDS = ["customer_name", "opportunity_amount", "pew_bid_submission_deadline", "status"]

NOTIFICATION_BID_VALIDITY = "Bid Validity Expiry Alert"
NOTIFICATION_BID_DEADLINE = "Bid Submission Deadline Reminder"
NOTIFICATION_QUERY_DEADLINE = "Query Deadline Reminder"
NOTIFICATION_TENDER_RELEASE = "Tender Release Follow-up"
NOTIFICATION_PROJECT_REVIEW = "Project Pending Review"
NOTIFICATIONS = [
	NOTIFICATION_BID_VALIDITY,
	NOTIFICATION_BID_DEADLINE,
	NOTIFICATION_QUERY_DEADLINE,
	NOTIFICATION_TENDER_RELEASE,
	NOTIFICATION_PROJECT_REVIEW,
]

V1_SERVER_SCRIPTS = [
	"PEW: Create Project on Opportunity Won",
	"PEW: Share Project Files with New Team Member",
	"PEW: Enforce Lost Reason and Freeze Lost Opportunity",
]


def stage_from(idx):
	"""depends_on / mandatory_depends_on expression: true once the deal is at stage `idx` or later."""
	return f"eval:doc.pew_stage_index>={idx}"


# Stage gates -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Gate:
	"""One checklist item. Either `fieldname` must be set (non-empty table, ticked checkbox) or `check`
	must return True. `when` limits the item to documents it applies to."""

	fieldname: str | None = None
	label: str | None = None
	check: Callable | None = None
	when: Callable | None = None

	def applies(self, doc):
		return self.when is None or bool(self.when(doc))

	def passes(self, doc):
		if self.check:
			return bool(self.check(doc))
		return bool(doc.get(self.fieldname))


def _is_customer(doc):
	return doc.opportunity_from == "Customer" and bool(doc.party_name)


def _is_assigned(doc):
	import frappe

	if doc.is_new():
		return False
	return bool(
		frappe.db.exists(
			"ToDo",
			{"reference_type": doc.doctype, "reference_name": doc.name, "status": ("!=", "Cancelled")},
		)
	)


# Must be satisfied to LEAVE stage n, i.e. whenever the deal is beyond n.
# Fields listed here carry mandatory_depends_on = stage_from(n + 1) (checked by the test suite).
EXIT_GATES = {
	INQUIRY: [
		Gate("title"),
		Gate("contact_person"),
		Gate("pew_organization_type"),
		Gate("market_segment"),
		Gate("utm_source"),
		Gate("opportunity_owner"),
		Gate("pew_inquiry_received_on"),
		Gate("pew_tender_ref_no", when=lambda d: d.pew_organization_type in TENDER_REF_REQUIRED_FOR),
		Gate("pew_referral_from", when=lambda d: d.utm_source == REFERRAL_LEAD_SOURCE),
		Gate(label="Organization saved as a Customer", check=_is_customer),
		Gate(label="Assigned to the estimation team", check=_is_assigned),
	],
	QUALIFICATION: [
		Gate("pew_tender_documents"),
		Gate("pew_bid_submission_deadline"),
		Gate("pew_nda_status"),
		Gate("pew_nda_attachment", when=lambda d: d.pew_nda_status == "Yes"),
		Gate("pew_subcontracted_scope", when=lambda d: d.pew_subcontract_required == "Yes"),
		Gate("pew_go_no_go"),
		Gate(label="Go / No-Go decision is Go", check=lambda d: d.pew_go_no_go == "Go"),
	],
	QUERIES: [
		Gate("pew_queries_clarified"),
		Gate("pew_scope_locked"),
	],
	PROPOSAL: [
		Gate(
			label="EMD / Bid Security submitted (or not applicable)",
			check=lambda d: d.pew_emd_status in ("Submitted", "Not Applicable"),
		),
	],
	EVALUATION: [
		Gate("pew_loi_date"),
	],
}

# Required while AT or beyond stage n: the stage name says the event already happened,
# or the data is the Project handoff payload. mandatory_depends_on = stage_from(n).
ENTRY_GATES = {
	PROPOSAL: [
		Gate("pew_submitted_bid_value"),
		Gate("pew_bid_validity_expiry"),
		Gate("pew_final_proposal"),
		Gate("pew_emd_status"),
	],
	EVALUATION: [
		Gate("pew_evaluation_substage"),
	],
	WON: [
		Gate("pew_final_contract_value"),
		Gate("pew_project_start_date"),
		Gate("pew_project_end_date"),
		Gate(WORK_ORDER_FIELD),
	],
}
