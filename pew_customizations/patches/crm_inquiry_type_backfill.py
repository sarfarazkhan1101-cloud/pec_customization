"""Give Opportunities from before Inquiry Type one, so they can still be saved and moved on.

The type follows the old Tender Ref No rule (a ref was required for Government / PSU only):
Government / PSU -> Public / Govt Tender, any other deal with a Tender Ref No -> Corporate / Private
Tender, the rest -> Direct Private Inquiry. So no deal that already left Inquiry / Tender meets a tender
requirement it never had. A tender that had left it did so without a Bid Decision, so that is recorded as
approved rather than asked for after the fact. Each change is noted on the Opportunity; the type stays
editable.

Fixtures sync only after patches, so the fields are created here first.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from pew_customizations.crm.config import (
	BID_APPROVED,
	CORPORATE_TENDER,
	DIRECT_INQUIRY,
	INQUIRY,
	PUBLIC_TENDER,
	TENDER_INQUIRY_TYPES,
)
from pew_customizations.crm.customizations import CUSTOM_FIELDS

PUBLIC_ORGANIZATION_TYPES = ("Government", "PSU")


def execute():
	if not frappe.db.has_column("Opportunity", "pew_stage_index"):
		return  # fresh install: no Opportunities from before

	create_custom_fields({"Opportunity": CUSTOM_FIELDS["Opportunity"]}, update=True)

	for opp in frappe.get_all(
		"Opportunity",
		filters={"pew_inquiry_type": ("is", "not set")},
		fields=["name", "pew_organization_type", "pew_tender_ref_no", "pew_stage_index"],
	):
		if opp.pew_organization_type in PUBLIC_ORGANIZATION_TYPES:
			inquiry_type = PUBLIC_TENDER
		elif opp.pew_tender_ref_no:
			inquiry_type = CORPORATE_TENDER
		else:
			inquiry_type = DIRECT_INQUIRY
		values = {"pew_inquiry_type": inquiry_type}
		note = f"Inquiry Type set to {inquiry_type} (from Type of Organization and Tender Ref No) when Inquiry Type was introduced."
		if inquiry_type in TENDER_INQUIRY_TYPES and (opp.pew_stage_index or 0) > INQUIRY:
			values.update(pew_request_bid_approval=1, pew_bid_decision=BID_APPROVED)
			note += f" It had already passed Inquiry / Tender, so its Bid Decision is recorded as {BID_APPROVED}."

		frappe.db.set_value("Opportunity", opp.name, values, update_modified=False)
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Info",
				"reference_doctype": "Opportunity",
				"reference_name": opp.name,
				"content": note,
			}
		).insert(ignore_permissions=True)
