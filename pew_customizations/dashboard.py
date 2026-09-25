"""Adds PEC connections to standard doctypes' dashboards without touching
core files. `data` arrives already containing the base implementation's own
output (and any other app's additions) -- we only append to it."""


def get_project_dashboard_data(data):
	data.setdefault("transactions", []).append({"label": "PEC", "items": ["Scope"]})
	return data


def get_task_dashboard_data(data):
	data.setdefault("transactions", []).append({"label": "PEC", "items": ["DCI"]})
	return data


def get_opportunity_dashboard_data(data):
	# Project links back to the won Opportunity through `source_opportunity`
	data.setdefault("non_standard_fieldnames", {})["Project"] = "source_opportunity"
	data.setdefault("transactions", []).append({"label": "Execution", "items": ["Project"]})
	return data
