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
		{"label": "Project", "fieldname": "name", "fieldtype": "Link", "options": "Project", "width": 140},
		{"label": "Project Name", "fieldname": "project_name", "fieldtype": "Data", "width": 180},
		{"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
		{
			"label": "Project Manager",
			"fieldname": "project_manager",
			"fieldtype": "Link",
			"options": "User",
			"width": 150,
		},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": "% Complete", "fieldname": "percent_complete", "fieldtype": "Percent", "width": 100},
		{"label": "Scopes", "fieldname": "scope_count", "fieldtype": "Int", "width": 80},
		{"label": "Tasks", "fieldname": "task_count", "fieldtype": "Int", "width": 80},
		{"label": "Open Tasks", "fieldname": "open_task_count", "fieldtype": "Int", "width": 90},
		{"label": "Overdue Tasks", "fieldname": "overdue_task_count", "fieldtype": "Int", "width": 100},
	]


def get_data(filters):
	conditions = {}
	if filters.get("project"):
		conditions["name"] = filters["project"]
	if filters.get("status"):
		conditions["status"] = filters["status"]

	projects = frappe.get_all(
		"Project",
		filters=conditions,
		fields=["name", "project_name", "customer", "project_manager", "status", "percent_complete"],
		order_by="creation desc",
	)

	for row in projects:
		row["scope_count"] = frappe.db.count("Scope", {"project": row.name})
		row["task_count"] = frappe.db.count("Task", {"project": row.name})
		row["open_task_count"] = frappe.db.count(
			"Task", {"project": row.name, "status": ["in", ["Open", "Working", "Pending Review"]]}
		)
		row["overdue_task_count"] = frappe.db.count("Task", {"project": row.name, "status": "Overdue"})

	return projects
