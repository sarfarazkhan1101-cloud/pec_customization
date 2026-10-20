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
# Stage of every new Opportunity (form, Lead / Customer / Prospect "Create", API). Cold stays
# selectable for early market intelligence.
DEFAULT_STAGE = PIPELINE_STAGES[INQUIRY - 1]
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

# Standard UTM Source records reused as "Marketing / Lead Source". The first three are ERPNext defaults.
REFERRAL_LEAD_SOURCE = "Reference"
LEAD_SOURCES = ["Existing Customer", "Exhibition", REFERRAL_LEAD_SOURCE, "Tender Portal", "Direct Email", "Website"]

# Customer master only; the Opportunity keeps a hidden copy, filled from the Customer while empty
# (ERPNext's Opportunity.map_fields)
ORGANIZATION_TYPES = ["Government", "Private Sector", "PSU"]

# Inquiry Type drives which Stage 2 blocks show (depends_on) and which gates apply.
PUBLIC_TENDER = "Public / Govt Tender"
CORPORATE_TENDER = "Corporate / Private Tender"
DIRECT_INQUIRY = "Direct Private Inquiry"
CONSORTIUM_BID = "Back-to-Back / Consortium Bid"
RATE_CONTRACT = "Rate Contract / Call-Off Order"
INQUIRY_TYPES = [PUBLIC_TENDER, CORPORATE_TENDER, DIRECT_INQUIRY, CONSORTIUM_BID, RATE_CONTRACT]
# Show Tender Details and need management approval to leave Inquiry / Tender
TENDER_INQUIRY_TYPES = (PUBLIC_TENDER, CORPORATE_TENDER, CONSORTIUM_BID)

BID_PENDING = "Pending"
BID_APPROVED = "Approved to Bid"
BID_DECLINED = "Declined / No-Bid"
BID_DECISIONS = [BID_PENDING, BID_APPROVED, BID_DECLINED]

# Standard Market Segment records offered on Opportunity. Older records stay for existing documents;
# public/js/opportunity.js keeps a copy for the dropdown filter (a test keeps them in sync).
MARKET_SEGMENTS = [
	"Refineries & Petrochemicals",
	"Terminals & Tank Farms",
	"Pipelines & Marine",
	"Green Energy & Transition",
	"Power Plants & Utilities",
]

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
	"PQC / Verification Proof": "Commercial",
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
	"pew_pqc_document": "PQC / Verification Proof",
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
NOTIFICATION_BID_APPROVAL_REQUESTED = "Bid Approval Requested"
NOTIFICATION_BID_DECISION = "Bid Decision Made"
NOTIFICATIONS = [
	NOTIFICATION_BID_VALIDITY,
	NOTIFICATION_BID_DEADLINE,
	NOTIFICATION_QUERY_DEADLINE,
	NOTIFICATION_TENDER_RELEASE,
	NOTIFICATION_PROJECT_REVIEW,
	NOTIFICATION_BID_APPROVAL_REQUESTED,
	NOTIFICATION_BID_DECISION,
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


def is_tender(doc):
	return doc.pew_inquiry_type in TENDER_INQUIRY_TYPES


# Must be satisfied to LEAVE stage n, i.e. whenever the deal is beyond n.
# Fields listed here carry mandatory_depends_on = stage_from(n + 1) (checked by the test suite).
EXIT_GATES = {
	INQUIRY: [
		Gate("contact_person"),
		Gate("market_segment"),
		Gate("utm_source"),
		Gate("opportunity_owner"),
		Gate("pew_inquiry_received_on"),
		Gate("pew_tender_ref_no", when=is_tender),
		Gate("pew_referral_from", when=lambda d: d.utm_source == REFERRAL_LEAD_SOURCE),
		# Management approval (Bid Decision is permlevel 2: only Sales Managers can set it)
		Gate("pew_request_bid_approval", when=is_tender),
		Gate(
			label=f"Bid Decision is {BID_APPROVED}",
			check=lambda d: d.pew_bid_decision == BID_APPROVED,
			when=is_tender,
		),
		# whatever the Inquiry Type is now: switching a declined tender to Direct does not lift the No-Bid
		Gate(label=f"Bid Decision is not {BID_DECLINED}", check=lambda d: d.pew_bid_decision != BID_DECLINED),
		Gate(label="Organization saved as a Customer", check=_is_customer),
		Gate(label="Assigned to the estimation team", check=_is_assigned),
	],
	QUALIFICATION: [
		# File is optional on document rows, so a row only counts once something is uploaded
		Gate("pew_tender_documents", check=lambda d: any(row.file for row in d.pew_tender_documents)),
		Gate("pew_bid_submission_deadline", when=is_tender),
		Gate("pew_nda_status"),
		Gate("pew_nda_attachment", when=lambda d: d.pew_nda_status == "Yes"),
		Gate("pew_subcontracted_scope", when=lambda d: d.pew_subcontract_required == "Yes"),
		Gate("pew_go_no_go"),
		Gate(label="Go / No-Go decision is Go", check=lambda d: d.pew_go_no_go == "Go"),
	],
}

# Required while AT or beyond stage n. mandatory_depends_on = stage_from(n).
# From Queries & Clarifications (stage 4) on, nothing is mandatory, so a deal that passed
# Qualification can move freely up to Closure (Won).
ENTRY_GATES = {
	INQUIRY: [
		Gate("pew_inquiry_type"),
		Gate("title"),
	],
}
