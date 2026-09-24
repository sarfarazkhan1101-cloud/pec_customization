# Copyright (c) 2026, PEW Engineering & Consultancy Pvt Ltd and contributors
# For license information, please see license.txt

import json

import frappe


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": "Task", "fieldname": "name", "fieldtype": "Link", "options": "Task", "width": 140},
		{"label": "Subject", "fieldname": "subject", "fieldtype": "Data", "width": 200},
		{"label": "Project", "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 130},
		{"label": "Scope", "fieldname": "scope", "fieldtype": "Link", "options": "Scope", "width": 130},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": "Priority", "fieldname": "priority", "fieldtype": "Data", "width": 80},
		{"label": "Assigned To", "fieldname": "assigned_to", "fieldtype": "Data", "width": 180},
		{"label": "Reviewer", "fieldname": "reviewer", "fieldtype": "Link", "options": "User", "width": 150},
		{"label": "Exp Start", "fieldname": "exp_start_date", "fieldtype": "Datetime", "width": 130},
		{"label": "Exp End", "fieldname": "exp_end_date", "fieldtype": "Datetime", "width": 130},
		{"label": "Progress", "fieldname": "progress", "fieldtype": "Percent", "width": 90},
		{"label": "Level", "fieldname": "level", "fieldtype": "Data", "width": 90},
	]


def get_data(filters):
	conditions = {"is_template": ["!=", 1]}
	for field in ("project", "scope", "status", "reviewer"):
		if filters.get(field):
			conditions[field] = filters[field]

	tasks = frappe.get_all(
		"Task",
		filters=conditions,
		fields=[
			"name",
			"subject",
			"project",
			"scope",
			"status",
			"priority",
			"reviewer",
			"exp_start_date",
			"exp_end_date",
			"progress",
			"_assign",
		],
		order_by="exp_end_date asc",
	)

	assigned_to_filter = filters.get("assigned_to")
	rows = []
	for task in tasks:
		assignees = json.loads(task._assign) if task._assign else []
		if assigned_to_filter and assigned_to_filter not in assignees:
			continue
		task["assigned_to"] = ", ".join(assignees)
		task["level"] = "Level 3"
		rows.append(task)

	return rows
