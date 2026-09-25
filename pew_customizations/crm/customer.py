import frappe
from frappe import _
from frappe.utils import cint

from pew_customizations.crm.config import ACTIVE_STATUSES, COLD_STAGE, WON_STAGE
from pew_customizations.crm.opportunity import get_pipeline_counts


def onload(doc, method=None):
	"""Live Opportunity counts for the "Tender Pipeline" section of the Customer dashboard."""
	if doc.is_new() or not frappe.has_permission("Opportunity", "read"):
		return
	counts = get_pipeline_counts("Customer", doc.name)
	doc.set_onload(
		"pew_opportunity_stats",
		{
			"counts": {key: cint(value) for key, value in counts.items()},
			"stages": {"cold": COLD_STAGE, "won": WON_STAGE},
			"active_statuses": list(ACTIVE_STATUSES),
		},
	)


def repoint_source_opportunity(doc, method=None):
	"""Customer made with Opportunity > Create > Customer: move that Opportunity onto the new Customer
	so it passes the Inquiry / Tender gate and is counted on the Customer dashboard."""
	if not doc.opportunity_name or not frappe.db.exists("Opportunity", doc.opportunity_name):
		return
	opportunity_from = frappe.db.get_value("Opportunity", doc.opportunity_name, "opportunity_from")
	if opportunity_from == "Customer":
		return
	frappe.db.set_value(
		"Opportunity",
		doc.opportunity_name,
		{"opportunity_from": "Customer", "party_name": doc.name, "customer_name": doc.customer_name},
	)
	frappe.get_doc("Opportunity", doc.opportunity_name).add_comment(
		"Info", _("Organization changed from {0} to Customer {1}.").format(opportunity_from, doc.name)
	)
