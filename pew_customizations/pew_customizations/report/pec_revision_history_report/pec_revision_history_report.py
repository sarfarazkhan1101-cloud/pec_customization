# Copyright (c) 2026, PEW Engineering & Consultancy Pvt Ltd and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": "Revision", "fieldname": "name", "fieldtype": "Link", "options": "PEC Revision", "width": 130},
		{"label": "Rev.", "fieldname": "revision_label", "fieldtype": "Data", "width": 60},
		{"label": "DCI", "fieldname": "dci", "fieldtype": "Link", "options": "DCI", "width": 130},
		{"label": "Project", "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 120},
		{"label": "Scope", "fieldname": "scope", "fieldtype": "Link", "options": "Scope", "width": 120},
		{"label": "Task", "fieldname": "task", "fieldtype": "Link", "options": "Task", "width": 120},
		{"label": "Status", "fieldname": "workflow_state", "fieldtype": "Data", "width": 140},
		{"label": "Submitted By", "fieldname": "submitted_by", "fieldtype": "Link", "options": "User", "width": 150},
		{"label": "Submission Date", "fieldname": "submission_date", "fieldtype": "Date", "width": 120},
		{
			"label": "Current Reviewer",
			"fieldname": "current_reviewer",
			"fieldtype": "Link",
			"options": "User",
			"width": 150,
		},
		{
			"label": "Previous Revision",
			"fieldname": "previous_revision",
			"fieldtype": "Link",
			"options": "PEC Revision",
			"width": 130,
		},
	]


def get_data(filters):
	conditions = {}
	for field in ("project", "scope", "task", "dci"):
		if filters.get(field):
			conditions[field] = filters[field]

	revisions = frappe.get_all(
		"PEC Revision",
		filters=conditions,
		fields=[
			"name",
			"revision_label",
			"revision_no",
			"dci",
			"project",
			"scope",
			"task",
			"workflow_state",
			"submitted_by",
			"submission_date",
			"current_reviewer",
			"previous_revision",
		],
		order_by="dci asc, revision_no asc",
	)

	if filters.get("latest_only"):
		latest_by_dci = {}
		for row in revisions:
			existing = latest_by_dci.get(row.dci)
			if not existing or row.revision_no > existing.revision_no:
				latest_by_dci[row.dci] = row
		revisions = list(latest_by_dci.values())

	return revisions
