import frappe
from frappe import _
from frappe.utils import add_days, now_datetime

from pew_customizations.crm.opportunity import is_manager

UNLINKED_EMAIL_DAYS = 90


def _customer_emails(opp):
	"""Email addresses of the Opportunity's contact and of every Contact linked to its party."""
	contacts = frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Contact", "link_doctype": opp.opportunity_from, "link_name": opp.party_name},
		pluck="parent",
	)
	emails = set(
		frappe.get_all("Contact Email", filters={"parent": ("in", contacts or [""])}, pluck="email_id")
	)
	if opp.contact_email:
		emails.add(opp.contact_email)
	return {e.lower() for e in emails if e}


@frappe.whitelist()
def get_unlinked_emails(opportunity: str, show_all: int = 0):
	"""Received emails not linked to any document yet. Everyone sees emails from this customer's
	contacts; only managers may browse all unlinked emails (subjects of other customers' mail)."""
	opp = frappe.get_doc("Opportunity", opportunity)
	opp.check_permission("write")
	show_all = int(show_all) and is_manager()

	filters = {
		"communication_type": "Communication",
		"sent_or_received": "Received",
		"reference_name": ("is", "not set"),
		"creation": (">", add_days(now_datetime(), -UNLINKED_EMAIL_DAYS)),
	}
	if not show_all:
		emails = _customer_emails(opp)
		if not emails:
			return []
		filters["sender"] = ("in", list(emails))

	return frappe.get_all(
		"Communication",
		filters=filters,
		fields=["name", "subject", "sender", "communication_date"],
		order_by="communication_date desc",
		limit=50,
	)


@frappe.whitelist()
def link_emails(opportunity: str, communications: str | list):
	opp = frappe.get_doc("Opportunity", opportunity)
	opp.check_permission("write")
	names = frappe.parse_json(communications) or []
	allowed_senders = None if is_manager() else _customer_emails(opp)

	linked = 0
	for name in names:
		comm = frappe.get_doc("Communication", name)
		if comm.reference_name:
			continue  # never move an email that is already linked elsewhere
		if allowed_senders is not None and (comm.sender or "").lower() not in allowed_senders:
			frappe.throw(_("Email {0} is not from a contact of this customer.").format(name))
		comm.reference_doctype = "Opportunity"
		comm.reference_name = opp.name
		comm.status = "Linked"
		comm.add_link("Opportunity", opp.name)
		comm.save(ignore_permissions=True)
		linked += 1
	return linked
