"""PEW's Job Application form for Frappe HR (HRMS): what every applicant must tell PEW.

HRMS's own form (/job_application) is a standard Web Form. It can only be edited in developer mode, and
saving it there writes into HRMS's files, so an HRMS update would undo or conflict with the change.
HRMS instead lets each Job Opening name its own application form ("Application Web Form Route",
`job_application_route`), and its Apply button follows that. So this module adds:

- Custom Fields on Job Applicant for what HRMS lacks: current roles, salary details, notice period.
  Name, mobile, email, resume attachment and resume link are HRMS's own fields.
- A Web Form of PEW's own at /job_application_form with every field required except the resume link.
  Frappe checks a Web Form's required fields in the browser and again on the server
  (`WebForm.validate_mandatory`); the rule belongs to the form, not to the doctype.
- Job Opening's route defaulting to that form. patches/job_opening_application_route.py points the
  openings that existed before.

In the desk the same fields are required only when HR creates an applicant: `mandatory_depends_on` is
checked by the desk form alone. HRMS itself saves existing applicants (Job Offer and Interview status
updates) and Employee Referral creates them from code; a plain `reqd` would make those fail for every
applicant without the new fields.

HRMS's form is left as it is. On a site without HRMS nothing is created (see `after_migrate`).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

WEB_FORM_NAME = "pew-job-application"
ROUTE = "job_application_form"

# Required in the desk form for a new applicant only (see the module docstring)
NEW_APPLICANT = "eval:doc.__islocal"

NOTICE_PERIODS = ["Immediate", "15 Days", "30 Days", "45 Days", "60 Days", "90 Days", "More than 90 Days"]

# Created from code rather than exported as a fixture: a fixture for a doctype that does not exist
# would stop `bench migrate` on a site without HRMS.
CUSTOM_FIELDS = {
	"Job Applicant": [
		{
			"fieldname": "pew_current_employment_section",
			"label": "Current Employment & Salary",
			"fieldtype": "Section Break",
			"insert_after": "applicant_rating",
		},
		{
			# "Text" is Frappe's long text box; "Long Text" cannot be used on a Web Form
			"fieldname": "pew_current_roles",
			"label": "Current Roles and Responsibilities",
			"fieldtype": "Text",
			"insert_after": "pew_current_employment_section",
			"mandatory_depends_on": NEW_APPLICANT,
		},
		{
			"fieldname": "pew_notice_period",
			"label": "Notice Period",
			"fieldtype": "Select",
			"options": "\n" + "\n".join(NOTICE_PERIODS),
			"insert_after": "pew_current_roles",
			"in_standard_filter": 1,
			"mandatory_depends_on": NEW_APPLICANT,
		},
		{
			"fieldname": "pew_current_employment_column",
			"fieldtype": "Column Break",
			"insert_after": "pew_notice_period",
		},
		{
			"fieldname": "pew_current_salary",
			"label": "Current Salary (Monthly Gross)",
			"fieldtype": "Currency",
			"options": "currency",
			"insert_after": "pew_current_employment_column",
			"mandatory_depends_on": NEW_APPLICANT,
		},
		{
			"fieldname": "pew_current_ctc",
			"label": "Current CTC (Annual)",
			"fieldtype": "Currency",
			"options": "currency",
			"insert_after": "pew_current_salary",
			"mandatory_depends_on": NEW_APPLICANT,
		},
		{
			"fieldname": "pew_monthly_in_hand",
			"label": "Monthly In-Hand",
			"fieldtype": "Currency",
			"options": "currency",
			"insert_after": "pew_current_ctc",
			"mandatory_depends_on": NEW_APPLICANT,
		},
		{
			"fieldname": "pew_expected_salary",
			"label": "Expected CTC (Annual)",
			"fieldtype": "Currency",
			"options": "currency",
			"insert_after": "pew_monthly_in_hand",
			"mandatory_depends_on": NEW_APPLICANT,
		},
	]
}

# (doctype, fieldname, property, value, property type)
PROPERTY_SETTERS = [
	("Job Applicant", "phone_number", "label", "Mobile Number", "Data"),
	("Job Applicant", "phone_number", "mandatory_depends_on", NEW_APPLICANT, "Code"),
	("Job Applicant", "resume_attachment", "mandatory_depends_on", NEW_APPLICANT, "Code"),
	# New openings' Apply button opens PEW's form
	("Job Opening", "job_application_route", "default", ROUTE, "Text"),
]

# As HRMS's form: show the opening's title rather than its ID, and check the link. HRMS's script asks
# frappe.client.get_value, which a guest may not use ("Not permitted" popup), so the title comes from
# get_job_opening_title below.
CLIENT_SCRIPT = """frappe.web_form.after_load = () => {
	const job_opening = frappe.utils.get_query_params().job_title;
	if (!job_opening) return;

	frappe.call({
		method: "pew_customizations.hr.job_application.get_job_opening_title",
		args: { job_opening },
		callback: (r) => {
			if (!r?.message) return;
			const title = frappe.utils.escape_html(r.message);
			$(frappe.web_form.fields_dict["job_title"].wrapper)
				.find(".control-value")
				.text(title);
		},
	});
};

frappe.web_form.on("resume_link", (field, value) => {
	if (value && !frappe.utils.is_url(value)) {
		frappe.msgprint(__("Resume link not valid"));
	}
});
"""


@frappe.whitelist(allow_guest=True)
def get_job_opening_title(job_opening: str) -> str | None:
	"""The title the form shows for the opening the applicant came from. Guests may not read Job
	Opening; this gives them only the title of a published opening, which /jobs already shows."""
	return frappe.db.get_value("Job Opening", {"name": job_opening, "publish": 1}, "job_title")


def get_web_form_fields(currency):
	"""The form's fields in PEW's order. `reqd` here applies to this form only."""

	def field(fieldname, fieldtype, label, reqd=1, **kwargs):
		return {"fieldname": fieldname, "fieldtype": fieldtype, "label": label, "reqd": reqd, **kwargs}

	return [
		# Filled from the Apply button's ?job_title=; a Data field as on HRMS's form, so Guest needs no
		# read permission on Job Opening for a Link
		field("job_title", "Data", "Job Opening", reqd=0, read_only=1),
		field("applicant_name", "Data", "Full Name"),
		field("phone_number", "Data", "Mobile Number", options="Phone"),
		field("email_id", "Data", "Email Address", options="Email"),
		field("pew_current_roles", "Text", "Current Roles and Responsibilities"),
		{"fieldtype": "Section Break", "label": "Salary Details"},
		# The amounts' currency; not asked
		field("currency", "Link", "Currency", reqd=0, hidden=1, options="Currency", default=currency),
		field(
			"pew_current_salary",
			"Currency",
			"Current Salary (Monthly Gross)",
			options="currency",
			description="Enter 0 if you are not currently employed.",
		),
		field("pew_current_ctc", "Currency", "Current CTC (Annual)", options="currency"),
		field(
			"pew_monthly_in_hand",
			"Currency",
			"Monthly In-Hand",
			options="currency",
			description="Take-home pay per month, after deductions.",
		),
		field("pew_expected_salary", "Currency", "Expected CTC (Annual)", options="currency"),
		{"fieldtype": "Section Break", "label": "Notice Period & Resume"},
		field("pew_notice_period", "Select", "Notice Period", options="\n" + "\n".join(NOTICE_PERIODS)),
		field("resume_attachment", "Attach", "Resume Attachment"),
		field("resume_link", "Data", "Resume Link", reqd=0),
	]


def after_migrate():
	if not frappe.db.exists("DocType", "Job Applicant"):
		return  # no HRMS on this site

	create_custom_fields(CUSTOM_FIELDS, update=True)
	for doctype, fieldname, prop, value, ptype in PROPERTY_SETTERS:
		_set_property(doctype, fieldname, prop, value, ptype)
	create_web_form()


def _set_property(doctype, fieldname, prop, value, ptype):
	if frappe.db.get_value("Property Setter", f"{doctype}-{fieldname}-{prop}", "value") == value:
		return
	make_property_setter(doctype, fieldname, prop, value, ptype)


def create_web_form():
	"""Created once. It is not a standard Web Form, so HR may adjust it in the desk afterwards (no
	developer mode needed); later migrates leave those changes alone."""
	if frappe.db.exists("Web Form", WEB_FORM_NAME) or frappe.db.exists("Web Form", {"route": ROUTE}):
		return

	web_form = frappe.get_doc(
		{
			"doctype": "Web Form",
			"title": "Job Application",
			"route": ROUTE,
			"doc_type": "Job Applicant",
			"module": "PEW Customizations",
			"is_standard": 0,
			"published": 1,
			# The same settings as HRMS's form: anyone may apply, without an account
			"login_required": 0,
			"allow_edit": 0,
			"allow_multiple": 0,
			"allow_delete": 0,
			"allow_incomplete": 0,
			"show_list": 0,
			"show_sidebar": 1,
			"success_message": "Thank you for applying.",
			"success_url": "/jobs",
			"client_script": CLIENT_SCRIPT,
			"web_form_fields": get_web_form_fields(frappe.db.get_default("currency") or "INR"),
		}
	)
	web_form.insert(ignore_permissions=True, set_name=WEB_FORM_NAME)
