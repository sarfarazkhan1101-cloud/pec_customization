"""Client Site Visit on Employee Checkin (Frappe HR): an employee visiting a client may check in or
out away from the office.

HRMS refuses a check-in made outside the radius of the employee's Shift Location
(`EmployeeCheckin.validate_distance_from_shift_location`). A check-in flagged as a Client Site Visit
skips only that radius check: its coordinates are still required and must be valid, and every other
HRMS check (active employee, duplicate log, shift, geolocation) runs unchanged.

Only employees HR has ticked "Allow Client Site Visit" for may flag a new check-in; the PWA shows the
checkbox to them alone (hr/pwa.py).

No HRMS file is changed. The fields are Custom Fields created here, the radius check is a mixin added
through the `extend_doctype_class` hook, and the permission checks are doc_events. On a site without
HRMS all of it is inert.
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import flt

CLIENT_SITE_FIELD = "pew_client_site_visit"
ALLOWED_FIELD = "pew_allow_client_site_visit"
# Who may change ALLOWED_FIELD. HRMS's Employee Self Service role can edit an employee's own record.
HR_ROLES = {"HR Manager", "HR User", "System Manager"}

# Created from code rather than exported as a fixture: a fixture for a doctype that does not exist
# would stop `bench migrate` on a site without HRMS.
CUSTOM_FIELDS = {
	"Employee Checkin": [
		{
			"fieldname": CLIENT_SITE_FIELD,
			"label": "Client Site Visit",
			"fieldtype": "Check",
			"insert_after": "log_type",
			"in_list_view": 1,
			"in_standard_filter": 1,
			# part of the audit trail: cannot be ticked later to excuse a check-in away from the office
			"set_only_once": 1,
			"description": "Checked in or out at a client site. The office radius is not applied; the location is still required.",
		}
	],
	"Employee": [
		{
			"fieldname": ALLOWED_FIELD,
			"label": "Allow Client Site Visit",
			"fieldtype": "Check",
			"insert_after": "attendance_device_id",
			"in_standard_filter": 1,
			"description": "Shows the Client Site Visit checkbox in the Frappe HR app, so this employee can check in and out at a client site. Only HR can change this.",
		}
	],
}


def after_migrate():
	if frappe.db.exists("DocType", "Employee Checkin"):
		create_custom_fields(CUSTOM_FIELDS, update=True)


class EmployeeCheckinClientSite:
	"""Mixin for HRMS's EmployeeCheckin (hooks.py `extend_doctype_class`)."""

	def validate_distance_from_shift_location(self):
		if not (self.meta.has_field(CLIENT_SITE_FIELD) and self.get(CLIENT_SITE_FIELD)):
			return super().validate_distance_from_shift_location()

		# Same switch as the HRMS check: without geolocation tracking no location is asked for at all
		if frappe.db.get_single_value("HR Settings", "allow_geolocation_tracking"):
			validate_client_site_coordinates(self.latitude, self.longitude)


def validate_client_site_allowed(doc, method=None):
	"""Employee Checkin before_validate: only an allowed employee may flag a new check-in. Existing ones
	stay valid when HR later withdraws the permission."""
	if doc.is_new() and doc.get(CLIENT_SITE_FIELD) and not is_allowed(doc.employee):
		frappe.throw(
			_("Client Site Visit is not enabled for {0}. Please contact HR.").format(
				doc.employee_name or doc.employee
			),
			title=_("Not Allowed"),
		)


def validate_employee(doc, method=None):
	"""Employee validate: only HR may change "Allow Client Site Visit"."""
	changed = doc.get(ALLOWED_FIELD) if doc.is_new() else doc.has_value_changed(ALLOWED_FIELD)
	if changed and not HR_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("Only HR can change Allow Client Site Visit."), frappe.PermissionError)


def is_allowed(employee):
	return bool(
		employee
		and frappe.get_meta("Employee").has_field(ALLOWED_FIELD)
		and frappe.db.get_value("Employee", employee, ALLOWED_FIELD)
	)


def validate_client_site_coordinates(latitude, longitude):
	"""Both coordinates present and on the globe. The PWA sends 0, 0 when it could not get a location,
	so that counts as missing."""
	lat, lng = flt(latitude), flt(longitude)
	if latitude in (None, "") or longitude in (None, "") or (lat == 0 and lng == 0):
		frappe.throw(
			_(
				"Your current location is required for a Client Site Visit. Allow location access and try again."
			),
			title=_("Location Required"),
		)
	if not (-90 <= lat <= 90 and -180 <= lng <= 180):
		frappe.throw(
			_("The location sent with this check-in is not valid. Please try again."),
			title=_("Invalid Location"),
		)
