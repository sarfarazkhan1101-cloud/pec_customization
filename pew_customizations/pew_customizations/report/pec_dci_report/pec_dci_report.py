# Copyright (c) 2026, PEW Engineering & Consultancy Pvt Ltd and contributors
# For license information, please see license.txt

"""Document Control Index of a Project: one row per Task (= one deliverable document) with its
R0 - R10 submissions and the latest status.

get_dci_data() is also what the client-format Excel (api/dci_export.py) is built from, so the report
and the Excel cannot disagree.
"""

import json
from collections import Counter

import frappe
from frappe import _

from pew_customizations.projects.approval_codes import get_codes
from pew_customizations.projects.task_revisions import (
	AWAITING_COMMENTS,
	MAX_REVISIONS,
	NOT_SUBMITTED,
	get_revisions,
	summarize,
)

# (fieldname, label, fieldtype, width)
LEAD_COLUMNS = [
	("sr_no", "Sr. No.", "Int", 70),
	("scope_name", "Scope Name", "Data", 160),
	("document_number", "Document Number", "Data", 160),
	("document_name", "Document Name", "Data", 220),
	("manager", "Manager", "Data", 140),
	("engineer", "Engineer", "Data", 140),
	("team", "Draftsman / Associate / Sub-vendor", "Data", 220),
]
# Repeated for every revision as r{n}_{fieldname}, labelled "R{n} {label}"
REVISION_COLUMNS = [
	("submission", "Submission Date", "Date", 130),
	("received", "Received Date", "Date", 130),
	("code", "Approval Code", "Data", 120),
]
LATEST_COLUMNS = [
	("latest_revision", "Latest Revision", "Data", 110),
	("latest_submission_date", "Latest Submission Date", "Date", 150),
	("latest_received_date", "Latest Received Date", "Date", 150),
	("latest_code", "Latest Code", "Data", 100),
	("latest_status", "Latest Status", "Data", 260),
]


def execute(filters=None):
	dci = get_dci_data(filters)
	return get_columns(), dci.rows, None, get_chart(dci), get_report_summary(dci)


def get_columns():
	columns = [_column(*column) for column in LEAD_COLUMNS]
	for n in range(MAX_REVISIONS):
		columns += [
			_column(f"r{n}_{fieldname}", f"R{n} {label}", fieldtype, width)
			for fieldname, label, fieldtype, width in REVISION_COLUMNS
		]
	return columns + [_column(*column) for column in LATEST_COLUMNS]


def _column(fieldname, label, fieldtype, width):
	return {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width}


def get_dci_data(filters=None):
	"""The DCI rows of a Project and the Project's Approval Codes.

	Tasks are read with the user's own permissions, so the Execution Team's restriction to their
	Projects (projects/project_team.py) applies to the report and to every export of it."""
	filters = frappe._dict(filters or {})
	dci = frappe._dict(project=filters.project, codes=get_codes(filters.project), rows=[])
	if not filters.project:
		return dci

	task_filters = {"project": filters.project, "is_template": 0}
	if filters.scope:
		task_filters["scope"] = filters.scope
	tasks = frappe.get_list(
		"Task",
		filters=task_filters,
		fields=["name", "subject", "scope", "pec_document_number", "_assign", "creation"],
	)
	# by Scope, then Document Number; documents without a number yet come last in their Scope
	tasks.sort(
		key=lambda task: (
			not task.scope,
			task.scope or "",
			not task.pec_document_number,
			task.pec_document_number or "",
			task.creation,
		)
	)

	scopes = _get_scopes({task.scope for task in tasks if task.scope})
	if filters.engineer:
		tasks = [
			task for task in tasks if scopes.get(task.scope, {}).get("assigned_engineer") == filters.engineer
		]

	project_manager, project_owner = frappe.db.get_value(
		"Project", filters.project, ["project_manager", "owner"]
	) or (None, None)
	revisions = get_revisions([task.name for task in tasks])
	closing_codes = {code.code for code in dci.codes if code.closes_document}

	for task in tasks:
		scope = scopes.get(task.scope) or frappe._dict()
		task_revisions = revisions.get(task.name, [])
		latest = summarize(task_revisions, closing_codes)
		if filters.latest_code and latest.code != filters.latest_code:
			continue
		if filters.latest_status and latest.status_group != filters.latest_status:
			continue

		row = frappe._dict(
			task=task.name,
			scope=task.scope,
			scope_name=scope.scope_name,
			document_number=task.pec_document_number,
			document_name=task.subject,
			# the Scope's owner; a Task without a Scope falls back to the Project's manager / owner
			manager=scope.owner or project_manager or project_owner,
			engineer=scope.assigned_engineer,
			team=[*json.loads(task._assign or "[]"), scope.associate],
			latest_revision=latest.revision,
			latest_submission_date=latest.submission_date,
			latest_received_date=latest.received_date,
			latest_code=latest.code,
			latest_status=latest.status,
			status_group=latest.status_group,
		)
		for n, revision in enumerate(task_revisions[:MAX_REVISIONS]):
			row[f"r{n}_submission"] = revision.submission_date
			row[f"r{n}_received"] = revision.received_date
			row[f"r{n}_code"] = revision.approval_code
		dci.rows.append(row)

	_set_full_names(dci.rows)
	for sr_no, row in enumerate(dci.rows, start=1):
		row.sr_no = sr_no
	return dci


def _get_scopes(names):
	if not names:
		return {}
	scopes = frappe.get_all(
		"Scope",
		filters={"name": ("in", list(names))},
		fields=["name", "scope_name", "owner", "assigned_engineer", "associate"],
	)
	return {scope.name: scope for scope in scopes}


def _set_full_names(rows):
	"""Replace the user ids in manager / engineer / team with full names, in one query."""
	users = {user for row in rows for user in (row.manager, row.engineer, *row.team) if user}
	full_names = {}
	if users:
		full_names = dict(
			frappe.get_all(
				"User", filters={"name": ("in", list(users))}, fields=["name", "full_name"], as_list=True
			)
		)

	def full_name(user):
		return full_names.get(user) or user

	for row in rows:
		row.manager = full_name(row.manager)
		row.engineer = full_name(row.engineer)
		# an assignee who is also the Scope's Associate / Sub-vendor is listed once
		row.team = ", ".join(full_name(user) for user in dict.fromkeys(row.team) if user)


def get_counts(dci):
	"""Documents per latest Approval Code, plus the ones that have no code yet."""
	latest_codes = Counter(row.latest_code for row in dci.rows if row.latest_code)
	status_groups = Counter(row.status_group for row in dci.rows)
	return frappe._dict(
		codes=[(code, latest_codes[code.code]) for code in dci.codes],
		not_submitted=status_groups[NOT_SUBMITTED],
		awaiting_comments=status_groups[AWAITING_COMMENTS],
		total=len(dci.rows),
	)


def get_report_summary(dci):
	if not dci.project:
		return None

	counts = get_counts(dci)
	summary = [
		{
			"label": _("Code {0}").format(code.code),
			"value": count,
			"datatype": "Int",
			"indicator": "Green" if code.closes_document else "Blue",
		}
		for code, count in counts.codes
	]
	return [
		*summary,
		{"label": _("Not Submitted"), "value": counts.not_submitted, "datatype": "Int"},
		{
			"label": _("Awaiting Comments"),
			"value": counts.awaiting_comments,
			"datatype": "Int",
			"indicator": "Orange",
		},
		{"label": _("Total Documents"), "value": counts.total, "datatype": "Int"},
	]


def get_chart(dci):
	counts = get_counts(dci)
	if not counts.total or not counts.codes:
		return None
	return {
		"data": {
			"labels": [_("Code {0}").format(code.code) for code, _count in counts.codes],
			"datasets": [{"name": _("Documents"), "values": [count for _code, count in counts.codes]}],
		},
		"type": "bar",
		"fieldtype": "Int",
	}
