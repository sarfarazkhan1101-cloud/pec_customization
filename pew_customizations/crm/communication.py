import re

import frappe

# The email composer always appends "(#<docname>)" to the subject; people also type "[<docname>]".
SUBJECT_TAG = re.compile(r"[#\[]\s*([A-Za-z]+(?:-[A-Za-z]+)*-\d{4}-\d+)")


def link_by_subject_tag(doc, method=None):
	"""Link an incoming email to the Opportunity named in its subject.

	Frappe only parses the subject when the Email Account has `append_to` set, and in that mode every
	unmatched email creates a new Opportunity. We keep `append_to` empty and do the matching here.
	Replies to emails sent from ERPNext are already linked through In-Reply-To before this runs."""
	if doc.reference_doctype or doc.communication_type != "Communication" or doc.sent_or_received != "Received":
		return

	for candidate in SUBJECT_TAG.findall(doc.subject or ""):
		name = frappe.db.get_value("Opportunity", candidate.upper())
		if name:
			doc.reference_doctype = "Opportunity"
			doc.reference_name = name
			return
