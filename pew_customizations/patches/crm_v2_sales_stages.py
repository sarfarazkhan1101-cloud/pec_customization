"""Align Sales Stage records with the 7-stage pipeline.

- rename the v1 names ("Inquiry/Tender" -> "Inquiry / Tender") and merge "Qualification (Go/No-Go)"
  into the existing ERPNext "Qualification" record;
- move Opportunities on any other stage (ERPNext defaults such as "Prospecting") to "Cold", leaving a
  comment with the old stage;
- delete the other stages when nothing links to them.
The pipeline order (Sales Stage.pew_stage_order) comes from the Sales Stage fixture afterwards.
"""

import frappe
from frappe import _

from pew_customizations.crm.config import COLD_STAGE, LEGACY_STAGE_RENAMES, PIPELINE_STAGES


def execute():
	for old, new in LEGACY_STAGE_RENAMES.items():
		if frappe.db.exists("Sales Stage", old):
			frappe.rename_doc("Sales Stage", old, new, merge=bool(frappe.db.exists("Sales Stage", new)), force=True)

	if not frappe.db.exists("Sales Stage", COLD_STAGE):
		frappe.get_doc({"doctype": "Sales Stage", "stage_name": COLD_STAGE}).insert(ignore_permissions=True)

	for name, stage in frappe.get_all(
		"Opportunity",
		filters={"sales_stage": ("not in", PIPELINE_STAGES)},
		fields=["name", "sales_stage"],
		as_list=True,
	):
		frappe.db.set_value("Opportunity", name, "sales_stage", COLD_STAGE, update_modified=False)
		if stage:
			frappe.get_doc("Opportunity", name).add_comment(
				"Info", _("Sales Stage moved from {0} to {1} by the tender pipeline setup.").format(stage, COLD_STAGE)
			)

	for stage in frappe.get_all("Sales Stage", filters={"name": ("not in", PIPELINE_STAGES)}, pluck="name"):
		try:
			frappe.delete_doc("Sales Stage", stage, ignore_permissions=True)
		except frappe.LinkExistsError:
			frappe.clear_last_message()
