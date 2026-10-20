"""Client Site Visit on the Frappe HR check-in (hr/employee_checkin.py, hr/pwa.py).

The scenario tests drive HRMS's own Employee Checkin and attendance processing, so they are skipped on
a site without HRMS; the coordinate and page-script tests run anywhere.

Run: CI=1 bench --site <site> run-tests --module pew_customizations.tests.test_client_site_checkin
Everything is rolled back after the run.
"""

import json
from types import SimpleNamespace
from unittest import SkipTest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, get_datetime, getdate, now_datetime
from werkzeug.wrappers import Response

from pew_customizations.hr.employee_checkin import (
	CLIENT_SITE_FIELD,
	EmployeeCheckinClientSite,
	validate_client_site_coordinates,
)
from pew_customizations.hr.pwa import SCRIPT, add_client_site_script

# The office (a Shift Location with a 200 m radius) and points around it, as (latitude, longitude)
OFFICE = (18.5204, 73.8567)
NEAR_OFFICE = (18.5208, 73.8567)  # ~45 m away
OUTSIDE_OFFICE = (18.5294, 73.8567)  # ~1 km away
CLIENT_SITE = (18.6554, 73.8567)  # ~15 km away
OTHER_CLIENT_SITE = (18.4529, 73.8652)  # ~7.5 km away

USER = "pew.test.clientsite.employee@example.com"
PREFIX = "PEW Client Site Test"


class TestClientSiteCoordinates(IntegrationTestCase):
	def test_valid(self):
		validate_client_site_coordinates(*CLIENT_SITE)
		validate_client_site_coordinates("18.6554", "73.8567")
		validate_client_site_coordinates(0, 73.8567)  # on the equator

	def test_missing(self):
		# 0, 0 is what the PWA sends when it could not get a location
		for latitude, longitude in ((0, 0), (None, None), ("", ""), (None, 73.8567), (18.6554, None)):
			with (
				self.subTest(latitude=latitude, longitude=longitude),
				self.assertRaises(frappe.ValidationError),
			):
				validate_client_site_coordinates(latitude, longitude)

	def test_not_on_the_globe(self):
		for latitude, longitude in (
			(91, 73.8567),
			(-90.5, 73.8567),
			(18.6554, 181),
			(18.6554, -180.5),
			("nan", 73),
		):
			with (
				self.subTest(latitude=latitude, longitude=longitude),
				self.assertRaises(frappe.ValidationError),
			):
				validate_client_site_coordinates(latitude, longitude)


class TestHrmsPageScript(IntegrationTestCase):
	PAGE = (
		"<!DOCTYPE html><html><body><div id='app'></div>"
		"<script type='module' src='/assets/hrms/frontend/assets/index.js'></script></body></html>"
	)

	def respond(self, path, body=PAGE, status=200, mimetype="text/html"):
		response = Response(body, status=status, mimetype=mimetype)
		add_client_site_script(response=response, request=SimpleNamespace(path=path))
		return response.get_data(as_text=True)

	def test_added_to_the_pwa_page(self):
		for path in ("/hrms", "/hrms/", "/hrms/home", "/hrms/employee-checkins/new"):
			with self.subTest(path=path):
				html = self.respond(path)
				self.assertEqual(html.count(SCRIPT), 1)
				self.assertGreater(html.index(SCRIPT), html.index("index.js"))  # after the PWA's own script
				self.assertTrue(html.endswith("</script>\n</body></html>"))

	def test_added_once(self):
		self.assertEqual(self.respond("/hrms", body=self.respond("/hrms")).count(SCRIPT), 1)

	def test_other_responses_untouched(self):
		for path, status, mimetype in (
			("/desk", 200, "text/html"),
			("/hrmsx", 200, "text/html"),
			("/assets/hrms/frontend/index.html", 200, "text/html"),
			("/api/method/hrms.api.get_hr_settings", 200, "application/json"),
			("/hrms", 404, "text/html"),
			("/hrms/home", 302, "text/html"),
		):
			with self.subTest(path=path, status=status):
				self.assertEqual(self.respond(path, status=status, mimetype=mimetype), self.PAGE)

	def test_no_response(self):
		# after an earlier failure the hook may get no response at all
		add_client_site_script(response=None, request=SimpleNamespace(path="/hrms"))


class TestClientSiteCheckin(IntegrationTestCase):
	"""Scenarios A-E against HRMS: the office radius is skipped only for a flagged check-in."""

	SHOW_TRANSACTION_COMMIT_WARNINGS = True  # everything here must be rolled back

	@classmethod
	def setUpClass(cls):
		if not frappe.db.exists("DocType", "Employee Checkin"):
			raise SkipTest("Frappe HR (hrms) is not installed on this site")
		super().setUpClass()
		cls.enterClassContext(patch("frappe.sendmail"))
		if not frappe.get_meta("Employee Checkin").has_field(CLIENT_SITE_FIELD):
			raise AssertionError(f"Employee Checkin has no {CLIENT_SITE_FIELD} field: run bench migrate")

		frappe.db.set_single_value("HR Settings", "allow_geolocation_tracking", 1)
		cls.company = (
			frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
		)
		today = getdate()
		cls.joined = add_days(today, -30)

		holiday_list = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": f"{PREFIX} Holidays",
				"from_date": add_days(today, -60),
				"to_date": add_days(today, 60),
			}
		).insert()
		cls.employee = _employee(cls.company, cls.joined, holiday_list.name)
		cls.office = frappe.get_doc(
			{
				"doctype": "Shift Location",
				"location_name": f"{PREFIX} Office",
				"latitude": OFFICE[0],
				"longitude": OFFICE[1],
				"checkin_radius": 200,
			}
		).insert()
		cls.shift = frappe.get_doc(
			{
				"doctype": "Shift Type",
				"__newname": f"{PREFIX} Shift",
				"start_time": "09:00:00",
				"end_time": "18:00:00",
				"holiday_list": holiday_list.name,
				"enable_auto_attendance": 1,
				"determine_check_in_and_check_out": "Alternating entries as IN and OUT during the same shift",
				"working_hours_calculation_based_on": "First Check-in and Last Check-out",
				"begin_check_in_before_shift_start_time": 60,
				"allow_check_out_after_shift_end_time": 60,
				"process_attendance_after": add_days(today, -20),
				"last_sync_of_checkin": now_datetime(),
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Shift Assignment",
				"employee": cls.employee,
				"shift_type": cls.shift.name,
				"company": cls.company,
				"start_date": cls.joined,
				"shift_location": cls.office.name,
				"status": "Active",
			}
		).submit()

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	# helpers -----------------------------------------------------------------------------------

	def day(self, offset):
		"""A past working day of the test employee; each test uses its own days."""
		return add_days(getdate(), -offset)

	def checkin(self, day, time, log_type, location, client_site=0):
		return frappe.get_doc(
			_checkin_dict(self.employee, day, time, log_type, location, client_site)
		).insert()

	def assert_saved(self, doc, day, time, location, client_site):
		doc.reload()
		self.assertEqual(doc.time, get_datetime(f"{day} {time}"))
		self.assertEqual((doc.latitude, doc.longitude), location)
		self.assertEqual(
			json.loads(doc.geolocation)["features"][0]["geometry"]["coordinates"], [location[1], location[0]]
		)
		self.assertEqual(doc.get(CLIENT_SITE_FIELD), client_site)
		self.assertEqual(doc.shift, self.shift.name)

	# scenarios ---------------------------------------------------------------------------------

	def test_a_office_check_unchanged(self):
		from hrms.hr.doctype.employee_checkin.employee_checkin import CheckinRadiusExceededError

		day = self.day(12)
		office_in = self.checkin(day, "09:00:00", "IN", NEAR_OFFICE)
		self.assert_saved(office_in, day, "09:00:00", NEAR_OFFICE, 0)

		with self.assertRaises(CheckinRadiusExceededError):
			self.checkin(day, "12:00:00", "OUT", OUTSIDE_OFFICE)
		with self.assertRaises(CheckinRadiusExceededError):
			self.checkin(day, "12:00:00", "OUT", CLIENT_SITE)
		with self.assertRaises(frappe.ValidationError):  # HRMS's own "Latitude and longitude ... required"
			self.checkin(day, "12:00:00", "OUT", (0, 0))

	def test_b_direct_client_site_visit(self):
		"""No office check-in that day. Made the way the PWA makes it: frappe.client.insert as the
		employee, who cannot write `time`, so HRMS records the server's clock, not the phone's."""
		from hrms.hr.doctype.employee_checkin.employee_checkin import CheckinRadiusExceededError

		day = self.day(11)
		server_clock = patch(  # the source of the `time` default ("Now") HRMS sets for employees
			"frappe.model.create_new.now_datetime", return_value=get_datetime(f"{day} 09:30:00")
		)
		with server_clock, self.set_user(USER):
			phone_time = "06:00:00"
			inserted = frappe.client.insert(
				_checkin_dict(self.employee, day, phone_time, "IN", CLIENT_SITE, 1)
			)
			# the same punch without the box ticked is refused, as before
			with self.assertRaises(CheckinRadiusExceededError):
				frappe.client.insert(_checkin_dict(self.employee, day, phone_time, "OUT", CLIENT_SITE, 0))

		self.assert_saved(
			frappe.get_doc("Employee Checkin", inserted["name"]), day, "09:30:00", CLIENT_SITE, 1
		)
		self.assertEqual(
			frappe.db.count(
				"Employee Checkin",
				{"employee": self.employee, "time": ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]]},
			),
			1,
		)

	def test_c_office_then_client_site(self):
		from hrms.hr.doctype.employee_checkin.employee_checkin import CheckinRadiusExceededError

		day = self.day(10)
		events = [
			("09:00:00", "IN", NEAR_OFFICE, 0),
			("12:00:00", "OUT", CLIENT_SITE, 1),
			("12:05:00", "IN", CLIENT_SITE, 1),
			("16:00:00", "OUT", OTHER_CLIENT_SITE, 1),
			("16:30:00", "IN", OTHER_CLIENT_SITE, 1),
			("18:00:00", "OUT", OTHER_CLIENT_SITE, 1),
		]
		for time, log_type, location, client_site in events:
			doc = self.checkin(day, time, log_type, location, client_site)
			self.assert_saved(doc, day, time, location, client_site)

		# the same punch at the client site without the box ticked is still refused
		with self.assertRaises(CheckinRadiusExceededError):
			self.checkin(day, "18:30:00", "IN", CLIENT_SITE)

	def test_d_missing_or_invalid_location_refused(self):
		day = self.day(9)
		for location in ((0, 0), (None, None), (91, 73.8567), (18.6554, 181)):
			with self.subTest(location=location), self.assertRaises(frappe.ValidationError):
				self.checkin(day, "09:30:00", "IN", location, client_site=1)
		self.assertFalse(
			frappe.db.exists("Employee Checkin", {"employee": self.employee, "time": f"{day} 09:30:00"})
		)

	def test_d_other_hrms_checks_still_apply(self):
		day = self.day(8)
		self.checkin(day, "09:30:00", "IN", CLIENT_SITE, client_site=1)
		with self.assertRaisesRegex(frappe.ValidationError, "same timestamp"):
			self.checkin(day, "09:30:00", "IN", CLIENT_SITE, client_site=1)

		frappe.db.set_value("Employee", self.employee, "status", "Inactive")
		try:
			with self.assertRaises(frappe.ValidationError):
				self.checkin(day, "18:00:00", "OUT", CLIENT_SITE, client_site=1)
		finally:
			frappe.db.set_value("Employee", self.employee, "status", "Active")

	def test_d_no_location_rules_without_geolocation_tracking(self):
		"""Same switch as HRMS: with tracking off neither check asks for a location."""
		day = self.day(7)
		frappe.db.set_single_value("HR Settings", "allow_geolocation_tracking", 0)
		try:
			self.checkin(day, "09:30:00", "IN", (0, 0), client_site=1)
			self.checkin(day, "18:00:00", "OUT", (0, 0))
		finally:
			frappe.db.set_single_value("HR Settings", "allow_geolocation_tracking", 1)

	def test_e_attendance_as_for_an_office_day(self):
		office_day, mixed_day, client_day = self.day(6), self.day(5), self.day(4)
		self.checkin(office_day, "09:00:00", "IN", NEAR_OFFICE)
		self.checkin(office_day, "18:00:00", "OUT", OFFICE)

		self.checkin(mixed_day, "09:00:00", "IN", NEAR_OFFICE)
		self.checkin(mixed_day, "13:00:00", "OUT", CLIENT_SITE, client_site=1)
		self.checkin(mixed_day, "13:05:00", "IN", CLIENT_SITE, client_site=1)
		self.checkin(mixed_day, "18:00:00", "OUT", CLIENT_SITE, client_site=1)

		# recorded out of order: HRMS orders the logs by time
		self.checkin(client_day, "17:30:00", "OUT", CLIENT_SITE, client_site=1)
		self.checkin(client_day, "09:30:00", "IN", CLIENT_SITE, client_site=1)

		self.shift.reload()
		self.shift.process_auto_attendance()

		office = self.attendance(office_day)
		mixed = self.attendance(mixed_day)
		client = self.attendance(client_day)
		self.assertEqual((office.status, office.working_hours), ("Present", 9))
		self.assertEqual((mixed.status, mixed.working_hours), ("Present", 9))
		self.assertEqual((client.status, client.working_hours), ("Present", 8))
		self.assertEqual(
			(mixed.in_time, mixed.out_time),
			(get_datetime(f"{mixed_day} 09:00:00"), get_datetime(f"{mixed_day} 18:00:00")),
		)

	def attendance(self, day):
		attendance = frappe.db.get_value(
			"Attendance",
			{"employee": self.employee, "attendance_date": day, "docstatus": 1},
			["name", "status", "working_hours", "in_time", "out_time", "shift"],
			as_dict=True,
		)
		self.assertEqual(attendance.shift, self.shift.name)
		linked = frappe.get_all(
			"Employee Checkin",
			{"employee": self.employee, "time": ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]]},
			pluck="attendance",
		)
		self.assertEqual(set(linked), {attendance.name})  # every log of the day, flagged or not
		return attendance

	def test_flag_cannot_be_changed_later(self):
		day = self.day(3)
		office_in = self.checkin(day, "09:00:00", "IN", NEAR_OFFICE)
		ticked_at_office = self.checkin(day, "12:00:00", "OUT", NEAR_OFFICE, client_site=1)
		for doc in (office_in, ticked_at_office):
			doc.set(CLIENT_SITE_FIELD, 1 - doc.get(CLIENT_SITE_FIELD))
			with self.assertRaises(frappe.CannotChangeConstantError):
				doc.save()

		# unticking a check-in made away from the office is refused even earlier, by the office radius
		client_in = self.checkin(day, "12:30:00", "IN", CLIENT_SITE, client_site=1)
		client_in.set(CLIENT_SITE_FIELD, 0)
		with self.assertRaises(frappe.ValidationError):
			client_in.save()

	def test_hrms_still_has_the_extended_method(self):
		"""Fails if an HRMS update renames the geofence check, which would silently drop the bypass."""
		from hrms.hr.doctype.employee_checkin.employee_checkin import EmployeeCheckin

		self.assertTrue(callable(getattr(EmployeeCheckin, "validate_distance_from_shift_location", None)))
		self.assertIsInstance(frappe.new_doc("Employee Checkin"), EmployeeCheckinClientSite)
		self.assertIsInstance(frappe.new_doc("Employee Checkin"), EmployeeCheckin)


def _checkin_dict(employee, day, time, log_type, location, client_site):
	return {
		"doctype": "Employee Checkin",
		"employee": employee,
		"log_type": log_type,
		"time": f"{day} {time}",
		"latitude": location[0],
		"longitude": location[1],
		CLIENT_SITE_FIELD: client_site,
	}


def _employee(company, joined, holiday_list):
	if not frappe.db.exists("User", USER):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": USER,
				"first_name": "Client Site Employee",
				"send_welcome_email": 0,
				"roles": [{"role": "Employee"}],
			}
		).insert(ignore_permissions=True)
	return (
		frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": f"{PREFIX} Employee",
				"company": company,
				"user_id": USER,
				"gender": frappe.get_all("Gender", pluck="name", limit=1)[0],
				"date_of_birth": "1990-01-01",
				"date_of_joining": joined,
				"holiday_list": holiday_list,
				"status": "Active",
			}
		)
		.insert()
		.name
	)
