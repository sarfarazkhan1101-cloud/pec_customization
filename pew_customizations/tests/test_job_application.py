"""PEW's Job Application form for Frappe HR (hr/job_application.py).

Drives HRMS's Job Applicant, Job Opening, Interview, Job Offer and Employee Referral, so it is skipped on
a site without HRMS.

Run: CI=1 bench --site <site> run-tests --module pew_customizations.tests.test_job_application
Everything is rolled back after the run.
"""

import json
from unittest import SkipTest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today
from frappe.website.doctype.web_form.web_form import accept

from pew_customizations.hr.job_application import (
	CUSTOM_FIELDS,
	NEW_APPLICANT,
	ROUTE,
	WEB_FORM_NAME,
	create_web_form,
	get_job_opening_title,
)
from pew_customizations.patches import job_opening_application_route

PREFIX = "PEW Job Application Test"
NEW_FIELDS = [f["fieldname"] for f in CUSTOM_FIELDS["Job Applicant"] if "Break" not in f["fieldtype"]]
# Every field the form asks for except the resume link
REQUIRED = [
	"applicant_name",
	"phone_number",
	"email_id",
	"pew_current_roles",
	"pew_current_salary",
	"pew_current_ctc",
	"pew_monthly_in_hand",
	"pew_expected_salary",
	"pew_notice_period",
	"resume_attachment",
]


class TestJobApplication(IntegrationTestCase):
	SHOW_TRANSACTION_COMMIT_WARNINGS = True  # everything here must be rolled back

	@classmethod
	def setUpClass(cls):
		if not frappe.db.exists("DocType", "Job Applicant"):
			raise SkipTest("Frappe HR (hrms) is not installed on this site")
		super().setUpClass()
		cls.enterClassContext(patch("frappe.sendmail"))
		if not frappe.db.exists("Web Form", WEB_FORM_NAME):
			raise SkipTest("Run bench migrate first: the Job Application form is not set up")

		cls.company = frappe.db.get_value("Company", {}, "name")
		cls.designation = frappe.db.get_value("Designation", {}, "name")
		cls.opening = frappe.get_doc(
			{
				"doctype": "Job Opening",
				"job_title": f"{PREFIX} Engineer",
				"designation": cls.designation,
				"company": cls.company,
				"status": "Open",
			}
		).insert()
		# What the browser's upload leaves before the form is sent: a File not attached to anything yet
		cls.resume = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "pew-test-resume.txt",
				"content": b"PEW test resume",
				"is_private": 0,
			}
		).insert()

	def tearDown(self):
		frappe.set_user("Administrator")

	def application(self, email="applicant@example.com", **values):
		data = {
			"doctype": "Job Applicant",
			"job_title": self.opening.name,
			"applicant_name": "Asha Kulkarni",
			"phone_number": "+91-9876543210",
			"email_id": email,
			"pew_current_roles": "Design engineer: HVAC load calculations and drawings for 4 years.",
			"currency": "INR",
			"pew_current_salary": 60000,
			"pew_current_ctc": 850000,
			"pew_monthly_in_hand": 52000,
			"pew_expected_salary": 1100000,
			"pew_notice_period": "60 Days",
			"resume_attachment": self.resume.file_url,
			"resume_link": "",
		}
		data.update(values)
		return data

	def apply_as_guest(self, data):
		frappe.set_user("Guest")
		try:
			return accept(WEB_FORM_NAME, json.dumps(data))
		finally:
			frappe.set_user("Administrator")

	def test_form_is_set_up(self):
		web_form = frappe.get_doc("Web Form", WEB_FORM_NAME)
		self.assertEqual(web_form.route, ROUTE)
		self.assertEqual(web_form.doc_type, "Job Applicant")
		self.assertTrue(web_form.published)
		self.assertFalse(web_form.login_required)
		self.assertFalse(web_form.is_standard)
		self.assertEqual(sorted(f.fieldname for f in web_form.web_form_fields if f.reqd), sorted(REQUIRED))
		self.assertEqual(frappe.get_meta("Job Applicant").get_label("phone_number"), "Mobile Number")

		# HRMS's own form is left as it was
		self.assertEqual(frappe.db.get_value("Web Form", {"route": "job_application"}, "is_standard"), 1)

	def test_guest_application_is_saved(self):
		applicant = self.apply_as_guest(self.application())
		applicant.reload()

		self.assertEqual(applicant.job_title, self.opening.name)
		self.assertEqual(applicant.status, "Open")
		self.assertEqual(applicant.source, "Website Listing")  # HRMS sets this for web form applicants
		self.assertEqual(applicant.currency, "INR")
		self.assertEqual(applicant.pew_current_salary, 60000)
		self.assertEqual(applicant.pew_current_ctc, 850000)
		self.assertEqual(applicant.pew_monthly_in_hand, 52000)
		self.assertEqual(applicant.pew_expected_salary, 1100000)
		self.assertEqual(applicant.pew_notice_period, "60 Days")
		self.assertIn("HVAC", applicant.pew_current_roles)
		self.assertEqual(applicant.resume_attachment, self.resume.file_url)

	def test_each_required_field_is_enforced_on_the_server(self):
		# A request sent straight to the server, past the browser's check
		for fieldname in REQUIRED:
			with self.subTest(fieldname=fieldname):
				data = self.application(email=f"missing.{fieldname}@example.com")
				data.pop(fieldname)
				with self.assertRaisesRegex(frappe.ValidationError, "Mandatory Information missing"):
					self.apply_as_guest(data)

		self.assertFalse(frappe.db.exists("Job Applicant", {"email_id": ("like", "missing.%@example.com")}))

	def test_resume_link_is_optional_and_zero_salary_is_accepted(self):
		# A fresher: not employed, nothing earned yet
		applicant = self.apply_as_guest(
			self.application(
				email="fresher@example.com",
				pew_current_salary=0,
				pew_current_ctc=0,
				pew_monthly_in_hand=0,
				pew_current_roles="Fresher",
				pew_notice_period="Immediate",
				resume_link=None,
			)
		)
		self.assertEqual(applicant.pew_current_ctc, 0)
		self.assertFalse(applicant.resume_link)

	def test_desk_requires_the_fields_only_for_a_new_applicant(self):
		meta = frappe.get_meta("Job Applicant")
		for fieldname in [*NEW_FIELDS, "phone_number", "resume_attachment"]:
			with self.subTest(fieldname=fieldname):
				df = meta.get_field(fieldname)
				self.assertEqual(df.mandatory_depends_on, NEW_APPLICANT)
				self.assertFalse(df.reqd)  # never required on the server: HRMS saves applicants itself

	def old_applicant(self, email):
		"""An applicant from before the new fields, or one made from code (email, HRMS)."""
		return frappe.get_doc(
			{
				"doctype": "Job Applicant",
				"applicant_name": "Old Applicant",
				"email_id": email,
				"job_title": self.opening.name,
			}
		).insert()

	def test_interview_status_update_still_works(self):
		from hrms.hr.doctype.interview.interview import update_job_applicant_status

		applicant = self.old_applicant("old.interview@example.com")
		update_job_applicant_status("Rejected", applicant.name)
		self.assertEqual(frappe.db.get_value("Job Applicant", applicant.name, "status"), "Rejected")

	def test_job_offer_status_update_still_works(self):
		from hrms.hr.doctype.job_offer.job_offer import update_job_applicant

		applicant = self.old_applicant("old.offer@example.com")
		update_job_applicant("Accepted", applicant.name)
		self.assertEqual(frappe.db.get_value("Job Applicant", applicant.name, "status"), "Accepted")

	def test_employee_referral_still_creates_an_applicant(self):
		from hrms.hr.doctype.employee_referral.employee_referral import create_job_applicant

		referral = frappe.get_doc(
			{
				"doctype": "Employee Referral",
				"first_name": "Ravi",
				"last_name": "Referred",
				"date": today(),
				"status": "Pending",
				"for_designation": self.designation,
				"email": "ravi.referred@example.com",
				"contact_no": "+91-9876500000",
				"referrer": frappe.db.get_value("Employee", {"status": "Active"}, "name"),
				"resume_link": "https://example.com/ravi-resume.pdf",
			}
		).insert()
		referral.submit()

		applicant = create_job_applicant(referral.name)
		self.assertTrue(frappe.db.exists("Job Applicant", applicant.name))
		self.assertEqual(applicant.employee_referral, referral.name)

	def test_guest_sees_only_a_published_opening_title(self):
		self.opening.db_set("publish", 1)
		frappe.set_user("Guest")
		self.assertEqual(get_job_opening_title(self.opening.name), f"{PREFIX} Engineer")
		frappe.set_user("Administrator")

		self.opening.db_set("publish", 0)
		frappe.set_user("Guest")
		self.assertIsNone(get_job_opening_title(self.opening.name))
		self.assertIsNone(get_job_opening_title("no-such-opening"))

	def test_new_opening_points_at_the_form(self):
		self.assertEqual(frappe.new_doc("Job Opening").job_application_route, ROUTE)

	def test_patch_fills_only_openings_without_a_route(self):
		self.opening.db_set("job_application_route", None)
		own = frappe.get_doc(
			{
				"doctype": "Job Opening",
				"job_title": f"{PREFIX} Own Form",
				"designation": self.designation,
				"company": self.company,
				"job_application_route": "some_other_form",
			}
		).insert()

		job_opening_application_route.execute()

		def route(opening):
			return frappe.db.get_value("Job Opening", opening, "job_application_route")

		self.assertEqual(route(self.opening.name), ROUTE)
		self.assertEqual(route(own.name), "some_other_form")

	def test_migrate_keeps_hr_changes_to_the_form(self):
		frappe.db.set_value("Web Form", WEB_FORM_NAME, "success_message", "Thanks, we will call you.")
		# (after_migrate's other steps change the schema, which would commit this test's transaction)
		create_web_form()
		create_web_form()
		self.assertEqual(
			frappe.db.get_value("Web Form", WEB_FORM_NAME, "success_message"), "Thanks, we will call you."
		)
		self.assertEqual(frappe.db.count("Web Form", {"route": ROUTE}), 1)
