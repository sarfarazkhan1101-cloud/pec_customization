"""Adds PEC connections to standard doctypes' dashboards without touching
core files. `data` arrives already containing the base implementation's own
output (and any other app's additions) -- we only append to it."""


def get_project_dashboard_data(data):
	data.setdefault("transactions", []).append({"label": "PEC", "items": ["Scope"]})
	return data


def get_task_dashboard_data(data):
	data.setdefault("transactions", []).append({"label": "PEC", "items": ["DCI"]})
	return data
