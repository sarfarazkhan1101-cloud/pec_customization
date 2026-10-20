"""Client Site Visit on Employee Checkin (Frappe HR): an employee visiting a client may check in or
out away from the office.

HRMS refuses a check-in made outside the radius of the employee's Shift Location
(`EmployeeCheckin.validate_distance_from_shift_location`). A check-in flagged as a Client Site Visit
skips only that radius check: its coordinates are still required and must be valid, and every other
HRMS check (active employee, duplicate log, shift, geolocation) runs unchanged.

No HRMS file is changed. The flag is a Custom Field created here, the check is a mixin added through
the `extend_doctype_class` hook, and the PWA checkbox is added by hr/pwa.py. On a site without HRMS
all of it is inert.
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import flt

CLIENT_SITE_FIELD = "pew_client_site_visit"

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
	]
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
