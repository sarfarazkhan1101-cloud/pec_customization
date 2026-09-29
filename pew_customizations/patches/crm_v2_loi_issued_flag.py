"""Tick "Client has issued a formal LOI or PO" on Opportunities that already have an LOI / PO date:
the date now shows only while that box is ticked.

Fixtures sync only after patches, so the field is created here first.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from pew_customizations.crm.customizations import CUSTOM_FIELDS, LOI_ISSUED_FIELD


def execute():
	if not frappe.db.has_column("Opportunity", "pew_loi_date"):
		return  # fresh install: no dates to carry over

	field = next(f for f in CUSTOM_FIELDS["Opportunity"] if f["fieldname"] == LOI_ISSUED_FIELD)
	create_custom_fields({"Opportunity": [field]}, update=True)
	# ("is", "set") compares the Date column with '', which strict MariaDB rejects in an UPDATE
	opportunity = frappe.qb.DocType("Opportunity")
	frappe.qb.update(opportunity).set(LOI_ISSUED_FIELD, 1).where(opportunity.pew_loi_date.isnotnull()).run()
