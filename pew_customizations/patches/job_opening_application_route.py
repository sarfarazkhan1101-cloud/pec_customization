"""Point the Apply button of existing Job Openings at PEW's Job Application form (hr/job_application.py).

An opening that already names a form of its own keeps it. Openings created later get the route as the
field's default (a Property Setter). The form itself is created by `after_migrate`, later in the same
migrate.
"""

import frappe

from pew_customizations.hr.job_application import ROUTE


def execute():
	if not frappe.db.exists("DocType", "Job Opening"):
		return  # no HRMS on this site

	frappe.db.set_value(
		"Job Opening",
		{"job_application_route": ("is", "not set")},
		"job_application_route",
		ROUTE,
		update_modified=False,
	)
