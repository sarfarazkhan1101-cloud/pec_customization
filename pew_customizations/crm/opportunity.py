"""doc_events for the standard Opportunity: stage gates, Lost freeze, document classification and the
Project handoff when a deal reaches Closure (Won).

`mandatory_depends_on` is only enforced by the browser, so every rule the pipeline depends on is
re-checked here; that also covers Kanban drags (frappe.set_value -> save) and API writes.
"""

import frappe
from frappe import _
from frappe.desk.doctype.tag.tag import DocTags
from frappe.utils import cint, flt, getdate, today

from pew_customizations.crm.config import (
	ACTIVE_STATUSES,
	ATTACH_FIELD_CATEGORIES,
	COLD_STAGE,
	DOCUMENT_CLASSES,
	DOCUMENT_TABLES,
	ENTRY_GATES,
	EXIT_GATES,
	LOST_TAG,
	MANAGER_ROLES,
	PIPELINE_STAGES,
	PROJECT_NAMING_SERIES,
	RESTRICTED_DOCUMENT_TYPE,
	TECHNICAL,
	WON,
	WORK_ORDER_FIELD,
)

_FEASIBILITY_FIELDS = (
	"pew_location_feasibility",
	"pew_budget_feasibility",
	"pew_authority_feasibility",
	"pew_timeline_feasibility",
	"pew_bandwidth_feasibility",
)


def stage_index(stage):
	if not stage:
		return 0
	return cint(frappe.get_cached_value("Sales Stage", stage, "pew_stage_order"))


def is_manager(user=None):
	return bool(set(frappe.get_roles(user)) & set(MANAGER_ROLES))


def _skip_rules():
	flags = frappe.flags
	return bool(flags.in_import or flags.in_patch or flags.in_migrate or flags.in_install)


def get_missing_items(doc, target_index):
	"""Checklist items that block the deal from being at `target_index`: exit gates of every earlier
	stage plus entry gates up to and including the target stage."""
	meta = frappe.get_meta("Opportunity")
	missing = []
	for gates, reached in ((EXIT_GATES, lambda n: n < target_index), (ENTRY_GATES, lambda n: n <= target_index)):
		for stage_idx, stage_gates in gates.items():
			if not reached(stage_idx):
				continue
			for gate in stage_gates:
				if gate.applies(doc) and not gate.passes(doc):
					label = gate.label or meta.get_label(gate.fieldname)
					missing.append((stage_idx, _(label)))
	return sorted(missing, key=lambda item: item[0])


def onload(doc, method=None):
	idx = stage_index(doc.sales_stage)
	next_stage = PIPELINE_STAGES[idx] if 0 < idx < WON else None
	doc.set_onload(
		"pew_pipeline",
		{
			"is_manager": is_manager(),
			"stage_order": {stage: pos for pos, stage in enumerate(PIPELINE_STAGES, start=1)},
			"next_stage": next_stage,
			"missing": [label for _stage, label in get_missing_items(doc, idx + 1)] if next_stage else [],
			"document_classes": DOCUMENT_CLASSES,
		},
	)


def validate(doc, method=None):
	old = doc.get_doc_before_save()
	old_status = old.status if old else None
	old_idx = stage_index(old.sales_stage) if old else 0

	if not doc.sales_stage:
		doc.sales_stage = COLD_STAGE
	idx = stage_index(doc.sales_stage)
	doc.pew_stage_index = idx

	if _validate_lost(doc, old_status, idx, old_idx):
		return

	if not idx:
		frappe.throw(
			_("Sales Stage {0} is not part of the tender pipeline. Pick one of: {1}").format(
				frappe.bold(doc.sales_stage), ", ".join(PIPELINE_STAGES)
			)
		)

	if doc.status == "Closed" and old_status != "Closed" and not is_manager():
		frappe.throw(_("Use Declare Lost to close an Opportunity that is not being pursued."))

	if not _skip_rules():
		_validate_stage_move(doc, idx, old_idx)

	if idx == WON:
		doc.status = "Converted"
	elif doc.status == "Converted" and old_idx == WON:
		doc.status = "Open"

	_stamp_document_rows(doc)
	_mirror_customer_fields(doc)
	_validate_values(doc)
	_warn_on_risky_go(doc)


def _validate_lost(doc, old_status, idx, old_idx):
	"""Lost freeze. Returns True when the rest of validate must be skipped (the deal is Lost)."""
	if old_status == "Lost" and not is_manager() and not _skip_rules():
		frappe.throw(
			_("This Opportunity was declared Lost and is read-only. Ask a Sales Manager to reopen it."),
			title=_("Opportunity Lost"),
		)

	if doc.status != "Lost":
		doc.pew_lost_on = None
		return False

	if old_status != "Lost":
		if not doc.lost_reasons:
			frappe.throw(_("Select at least one Loss Reason before declaring this Opportunity Lost."))
		if idx == WON:
			frappe.throw(_("A won Opportunity cannot be declared Lost."))
		if old_idx and idx != old_idx:
			frappe.throw(_("The Sales Stage cannot change while declaring an Opportunity Lost."))
		doc.pew_lost_on = today()
	return True


def _validate_stage_move(doc, idx, old_idx):
	if idx > old_idx:
		if idx == WON and not is_manager():
			frappe.throw(_("Only a Sales Manager can move an Opportunity to {0}.").format(PIPELINE_STAGES[WON - 1]))

		missing = get_missing_items(doc, idx)
		if missing:
			items = "".join(
				f"<li>{frappe.bold(PIPELINE_STAGES[stage_idx - 1])}: {label}</li>" for stage_idx, label in missing
			)
			frappe.throw(
				_("Complete these checklist items first:") + f"<ul>{items}</ul>",
				title=_("Cannot move to {0}").format(doc.sales_stage),
			)

	elif idx < old_idx and doc.pew_project and not is_manager():
		frappe.throw(
			_("Project {0} was already created from this Opportunity, so it cannot move back a stage.").format(
				frappe.bold(doc.pew_project)
			)
		)


def _stamp_document_rows(doc):
	for table in DOCUMENT_TABLES:
		for row in doc.get(table):
			if row.document_type == RESTRICTED_DOCUMENT_TYPE:
				frappe.throw(
					_("Row {0} of {1}: upload the Work Order / PO in its own field in the Closure (Won) section.").format(
						row.idx, _(doc.meta.get_label(table))
					)
				)
			row.document_class = DOCUMENT_CLASSES.get(row.document_type)
			if not row.stage:
				row.stage = doc.sales_stage


def _mirror_customer_fields(doc):
	"""Parent company and key account are Customer master data: always refresh them. Type of
	Organization is copied only when empty (standard map_fields) because it is editable here."""
	if doc.opportunity_from != "Customer" or not doc.party_name:
		return
	parent, key_account = frappe.get_cached_value(
		"Customer", doc.party_name, ["pew_parent_customer", "pew_is_key_account"]
	)
	doc.pew_parent_customer = parent
	doc.pew_is_key_account = cint(key_account)


def _validate_values(doc):
	if (
		doc.pew_project_start_date
		and doc.pew_project_end_date
		and getdate(doc.pew_project_end_date) < getdate(doc.pew_project_start_date)
	):
		frappe.throw(_("Expected Project End Date cannot be before the Start Date."))

	# public files skip permission checks entirely, so the PO must be private
	if (doc.get(WORK_ORDER_FIELD) or "").startswith("/files/"):
		frappe.throw(_("Upload the Work Order / Client PO as a private file (untick 'Is Public')."))


def _warn_on_risky_go(doc):
	if doc.pew_go_no_go != "Go" or not doc.has_value_changed("pew_go_no_go"):
		return
	failed = [_(doc.meta.get_label(f)) for f in _FEASIBILITY_FIELDS if doc.get(f) == "No"]
	if failed:
		frappe.msgprint(
			_("Go was chosen although these feasibility checks are No: {0}").format(", ".join(failed)),
			indicator="orange",
			alert=True,
		)


def on_update(doc, method=None):
	_sync_lost_tag(doc)
	_attach_document_files(doc)
	if stage_index(doc.sales_stage) == WON and doc.status != "Lost" and not _skip_rules():
		create_project(doc)


def _sync_lost_tag(doc):
	"""The standard Tag shows as a pill on Kanban cards, so Lost deals stand out in their column."""
	tags = DocTags(doc.doctype)
	has_tag = LOST_TAG in tags.get_tags(doc.name).split(",")
	if doc.status == "Lost" and not has_tag:
		tags.add(doc.name, LOST_TAG)
	elif doc.status != "Lost" and has_tag:
		tags.remove(doc.name, LOST_TAG)


def _attach_document_files(doc):
	"""Files uploaded into table rows before the first save stay unattached (frappe only re-links
	top-level Attach fields); attach them here and record each file's category on the File."""
	categories = {row.file: row.document_type for table in DOCUMENT_TABLES for row in doc.get(table) if row.file}
	categories.update({doc.get(f): cat for f, cat in ATTACH_FIELD_CATEGORIES.items() if doc.get(f)})

	for file_url, category in categories.items():
		name = frappe.db.get_value(
			"File", {"file_url": file_url, "attached_to_doctype": doc.doctype, "attached_to_name": doc.name}
		)
		if not name:
			name = frappe.db.get_value("File", {"file_url": file_url, "attached_to_name": ("is", "not set")})
			if not name:
				continue
			frappe.db.set_value("File", name, {"attached_to_doctype": doc.doctype, "attached_to_name": doc.name})
		frappe.db.set_value("File", name, "document_category", category, update_modified=False)


def on_trash(doc, method=None):
	if is_manager():
		return
	if doc.status == "Lost" or doc.pew_project or stage_index(doc.sales_stage) == WON:
		frappe.throw(_("Only a Sales Manager can delete a Lost or Won Opportunity."))


# Project handoff ---------------------------------------------------------------------------------


def create_project(opp):
	"""Create the execution Project for a won Opportunity. Idempotent: the pew_project link, a lookup
	by source_opportunity and the unique index on Project.source_opportunity all prevent duplicates.
	Runs inside the Opportunity's save, so a failure here rolls the stage change back."""
	if frappe.db.get_value("Opportunity", opp.name, "pew_project", for_update=True):
		return None

	existing = frappe.db.get_value("Project", {"source_opportunity": opp.name})
	if existing:
		opp.db_set("pew_project", existing)
		return existing

	# Project.project_name is unique; two won tenders can share an Opportunity Name
	project_name = opp.title or opp.customer_name or opp.name
	if frappe.db.exists("Project", {"project_name": project_name}):
		project_name = f"{project_name} ({opp.name})"

	project = frappe.get_doc(
		{
			"doctype": "Project",
			"naming_series": PROJECT_NAMING_SERIES,
			"project_name": project_name,
			"customer": opp.party_name if opp.opportunity_from == "Customer" else None,
			"company": opp.company,
			"expected_start_date": opp.pew_project_start_date,
			"expected_end_date": opp.pew_project_end_date,
			"pew_contract_value": flt(opp.pew_final_contract_value) * flt(opp.conversion_rate or 1),
			"source_opportunity": opp.name,
			"project_manager": opp.opportunity_owner,
		}
	)
	project.insert(ignore_permissions=True)  # Project Approval Workflow starts it in "Pending"

	copied = copy_technical_documents(opp, project.name)
	opp.db_set("pew_project", project.name)

	opp.add_comment(
		"Info", _("Project {0} created for review with {1} technical document(s).").format(project.name, copied)
	)
	project.add_comment("Info", _("Created from won Opportunity {0}.").format(opp.name))
	frappe.msgprint(
		_("Project {0} was created and is waiting for a Projects Manager to approve it.").format(
			frappe.bold(project.name)
		),
		alert=True,
		indicator="green",
	)
	return project.name


def copy_technical_documents(opp, project_name):
	"""Attach every Technical document of the Opportunity to the Project. The new File records point
	at the same stored file, so nothing is duplicated on disk. Commercial rows and the single Attach
	fields (NDA, Final Proposal, Work Order / PO) are never copied."""
	copied = 0
	for table in DOCUMENT_TABLES:
		for row in opp.get(table):
			if row.document_class != TECHNICAL or not row.file:
				continue
			if frappe.db.exists(
				"File", {"file_url": row.file, "attached_to_doctype": "Project", "attached_to_name": project_name}
			):
				continue
			source = frappe.db.get_value(
				"File",
				{"file_url": row.file, "attached_to_doctype": "Opportunity", "attached_to_name": opp.name},
				["file_name", "is_private"],
				as_dict=True,
			)
			if not source:
				continue
			frappe.get_doc(
				{
					"doctype": "File",
					"file_url": row.file,
					"file_name": source.file_name,
					"is_private": source.is_private,
					"attached_to_doctype": "Project",
					"attached_to_name": project_name,
					"document_category": row.document_type,
				}
			).insert(ignore_permissions=True)
			copied += 1
	return copied


def get_pipeline_counts(opportunity_from, party_name):
	"""Counts shown on the Customer form (see crm/customer.py)."""
	cold, won = COLD_STAGE, PIPELINE_STAGES[WON - 1]
	statuses = ", ".join(frappe.db.escape(s) for s in ACTIVE_STATUSES)
	return frappe.db.sql(
		f"""
		select
			count(*) as total,
			coalesce(sum(status != 'Lost' and sales_stage = %(won)s), 0) as won,
			coalesce(sum(status = 'Lost'), 0) as lost,
			coalesce(sum(status != 'Lost' and sales_stage = %(cold)s), 0) as cold,
			coalesce(sum(status in ({statuses}) and sales_stage not in (%(cold)s, %(won)s)), 0) as active
		from `tabOpportunity`
		where opportunity_from = %(from)s and party_name = %(party)s
		""",
		{"won": won, "cold": cold, "from": opportunity_from, "party": party_name},
		as_dict=True,
	)[0]
