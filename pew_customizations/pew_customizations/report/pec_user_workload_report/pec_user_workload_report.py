# Copyright (c) 2026, PEW Engineering & Consultancy Pvt Ltd and contributors
# For license information, please see license.txt

import json

import frappe

WORKLOAD_ROLES = ["Engineer", "Draftsman", "Reviewer", "Projects Manager", "Scope Manager", "PEC Administrator"]


def execute(filters=None):
	columns = get_columns()
	data = get_data()
	return columns, data


def get_columns():
	return [
		{"label": "User", "fieldname": "user", "fieldtype": "Link", "options": "User", "width": 200},
		{"label": "Open Tasks Assigned", "fieldname": "open_tasks", "fieldtype": "Int", "width": 140},
		{"label": "Overdue Tasks", "fieldname": "overdue_tasks", "fieldtype": "Int", "width": 110},
		{"label": "Pending Review Stages", "fieldname": "pending_reviews", "fieldtype": "Int", "width": 160},
		{"label": "Active Revisions Submitted", "fieldname": "active_revisions", "fieldtype": "Int", "width": 180},
	]


def get_data():
	users = frappe.get_all(
		"Has Role",
		filters={"role": ["in", WORKLOAD_ROLES], "parenttype": "User"},
		fields=["parent as user"],
		distinct=True,
	)
	user_names = {u.user for u in users} - {"Administrator", "Guest"}
	if not user_names:
		return []

	open_tasks = frappe.get_all(
		"Task",
		filters={"status": ["not in", ["Completed", "Cancelled", "Template"]]},
		fields=["name", "status", "_assign"],
	)

	rows = []
	for user in sorted(user_names):
		open_count = 0
		overdue_count = 0
		for task in open_tasks:
			assignees = json.loads(task._assign) if task._assign else []
			if user in assignees:
				open_count += 1
				if task.status == "Overdue":
					overdue_count += 1

		pending_reviews = frappe.db.count("PEC Revision Review Stage", {"reviewer": user, "status": "Pending"})
		active_revisions = frappe.db.count(
			"PEC Revision", {"submitted_by": user, "workflow_state": ["!=", "Approved"]}
		)

		if open_count or pending_reviews or active_revisions:
			rows.append(
				{
					"user": user,
					"open_tasks": open_count,
					"overdue_tasks": overdue_count,
					"pending_reviews": pending_reviews,
					"active_revisions": active_revisions,
				}
			)

	return rows
