"""Description on Additional Salary (Frappe HR payroll): why this amount is paid or deducted.

One optional Custom Field, shown once a Salary Component is chosen. HRMS never reads it: its validation,
the Salary Slip and the documents that create Additional Salary from code (Employee Advance, Leave
Encashment, Gratuity, Retention Bonus, Employee Incentive, Employee Referral) work as before. No HRMS
file is changed.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

DESCRIPTION_FIELD = "pew_description"

# Created from code rather than exported as a fixture: a fixture for a doctype that does not exist
# would stop `bench migrate` on a site without HRMS.
CUSTOM_FIELDS = {
	"Additional Salary": [
		{
			"fieldname": DESCRIPTION_FIELD,
			"label": "Description",
			"fieldtype": "Small Text",
			"insert_after": "amount",
			"depends_on": "eval:doc.salary_component",
		}
	],
}


def after_migrate():
	if frappe.db.exists("DocType", "Additional Salary"):
		create_custom_fields(CUSTOM_FIELDS, update=True)
