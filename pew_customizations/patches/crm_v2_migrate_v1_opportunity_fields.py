"""Move data from the v1 Opportunity custom fields to the pew_* fields and delete the v1 fields.

Fixtures sync only after patches, so the v2 fields are created here first. Deleting a Custom Field
keeps its DB column, so the old values also stay in the table.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from pew_customizations.crm.customizations import CUSTOM_FIELDS

# v1 fieldname -> v2 fieldname (plain value copy)
V1_TO_V2 = {
	"expected_tender_release_date": "pew_expected_tender_release",
	"cold_stage_notes": "pew_cold_notes",
	"type_of_organization": "pew_organization_type",
	"referral_source_type": "pew_referral_type",
	"referral_received_from": "pew_referral_from",
	"nda_status": "pew_nda_status",
	"location_feasibility": "pew_location_feasibility",
	"budget_feasibility": "pew_budget_feasibility",
	"authority_confirmed": "pew_authority_feasibility",
	"timeline_feasibility": "pew_timeline_feasibility",
	"bandwidth_feasibility": "pew_bandwidth_feasibility",
	"subcontracted_scope": "pew_subcontracted_scope",
	"pre_bid_meeting_date": "pew_pre_bid_meeting_date",
	"submitted_bid_value": "pew_submitted_bid_value",
	"bid_validity_expiry_date": "pew_bid_validity_expiry",
	"evaluation_substage": "pew_evaluation_substage",
	"commercial_rank": "pew_commercial_rank",
}
# converted individually below
V1_SPECIAL = ["wingman", "subcontract_required", "competitor_who_won"]
V1_LAYOUT = [
	"tender_tracking_tab",
	"cold_stage_section",
	"qualification_section",
	"qualification_column_break",
	"feasibility_section",
	"feasibility_column_break",
	"queries_section",
	"proposal_section",
	"evaluation_section",
]


def execute():
	v1_fields = [*V1_TO_V2, *V1_SPECIAL, *V1_LAYOUT]
	existing = [f for f in v1_fields if frappe.db.exists("Custom Field", f"Opportunity-{f}")]
	if not existing:
		return

	frappe.reload_doc("pew_customizations", "doctype", "pew_opportunity_wingman")
	frappe.reload_doc("pew_customizations", "doctype", "pew_opportunity_document")
	create_custom_fields(
		{"Opportunity": CUSTOM_FIELDS["Opportunity"], "Sales Stage": CUSTOM_FIELDS["Sales Stage"]}, update=True
	)

	for old, new in V1_TO_V2.items():
		if frappe.db.has_column("Opportunity", old):
			frappe.db.sql(
				f"""update `tabOpportunity` set `{new}` = `{old}`
				where ifnull(`{old}`, '') != '' and ifnull(`{new}`, '') = ''"""
			)

	if frappe.db.has_column("Opportunity", "subcontract_required"):
		frappe.db.sql(
			"""update `tabOpportunity` set pew_subcontract_required = 'Yes'
			where subcontract_required = 1 and ifnull(pew_subcontract_required, '') = ''"""
		)

	if frappe.db.has_column("Opportunity", "wingman"):
		for name, user in frappe.db.sql(
			"select name, wingman from `tabOpportunity` where ifnull(wingman, '') != ''"
		):
			_append_row(name, "pew_wingmen", "PEW Opportunity Wingman", {"user": user})

	if frappe.db.has_column("Opportunity", "competitor_who_won"):
		for name, competitor in frappe.db.sql(
			"select name, competitor_who_won from `tabOpportunity` where ifnull(competitor_who_won, '') != ''"
		):
			if not frappe.db.exists("Competitor", competitor):
				frappe.get_doc({"doctype": "Competitor", "competitor_name": competitor}).insert(
					ignore_permissions=True
				)
			_append_row(name, "competitors", "Competitor Detail", {"competitor": competitor})

	for fieldname in existing:
		frappe.delete_doc("Custom Field", f"Opportunity-{fieldname}", ignore_permissions=True, force=True)
	frappe.clear_cache(doctype="Opportunity")


def _append_row(parent, parentfield, child_doctype, values):
	if frappe.db.exists(child_doctype, {"parent": parent, "parentfield": parentfield, **values}):
		return
	idx = frappe.db.count(child_doctype, {"parent": parent, "parentfield": parentfield}) + 1
	frappe.get_doc(
		{
			"doctype": child_doctype,
			"parent": parent,
			"parenttype": "Opportunity",
			"parentfield": parentfield,
			"idx": idx,
			**values,
		}
	).db_insert()
