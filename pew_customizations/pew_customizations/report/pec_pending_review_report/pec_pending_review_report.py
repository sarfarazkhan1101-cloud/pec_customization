# Copyright (c) 2026, PEW Engineering & Consultancy Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import date_diff, today


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
		{"label": "Status", "fieldname": "workflow_state", "fieldtype": "Data", "width": 130},
		{
			"label": "Current Reviewer",
			"fieldname": "current_reviewer",
			"fieldtype": "Link",
			"options": "User",
			"width": 150,
		},
		{"label": "Submission Date", "fieldname": "submission_date", "fieldtype": "Date", "width": 120},
		{"label": "Days Pending", "fieldname": "days_pending", "fieldtype": "Int", "width": 100},
	]


def get_data(filters):
	conditions = {"workflow_state": ["in", ["Submitted", "Under Review"]]}
	for field in ("project", "scope"):
		if filters.get(field):
			conditions[field] = filters[field]
	if filters.get("reviewer"):
		conditions["current_reviewer"] = filters["reviewer"]

	revisions = frappe.get_all(
		"PEC Revision",
		filters=conditions,
		fields=[
			"name",
			"revision_label",
			"dci",
			"project",
			"scope",
			"workflow_state",
			"current_reviewer",
			"submission_date",
		],
		order_by="submission_date asc",
	)

	for row in revisions:
		row["days_pending"] = date_diff(today(), row.submission_date) if row.submission_date else None

	return revisions
