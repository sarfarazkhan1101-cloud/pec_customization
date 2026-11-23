"""Description on Additional Salary (hr/additional_salary.py): the field is there, optional, and HRMS's own
flow (submit, then pick-up by the Salary Slip) runs the same with or without it.

Skipped on a site without HRMS.

Run: CI=1 bench --site <site> run-tests --module pew_customizations.tests.test_additional_salary
Everything is rolled back after the run.
"""

from unittest import SkipTest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, get_first_day, get_year_ending, get_year_start, nowdate

from pew_customizations.hr.additional_salary import DESCRIPTION_FIELD

PREFIX = "PEW Additional Salary Test"


class TestAdditionalSalaryDescription(IntegrationTestCase):
	SHOW_TRANSACTION_COMMIT_WARNINGS = True  # everything here must be rolled back

	@classmethod
	def setUpClass(cls):
		if not frappe.db.exists("DocType", "Additional Salary"):
			raise SkipTest("Frappe HR (hrms) is not installed on this site")
		super().setUpClass()
		cls.enterClassContext(patch("frappe.sendmail"))
		if not frappe.get_meta("Additional Salary").has_field(DESCRIPTION_FIELD):
			raise AssertionError("The Additional Salary Description field is missing: run bench migrate")

	def test_field(self):
		meta = frappe.get_meta("Additional Salary")
		df = meta.get_field(DESCRIPTION_FIELD)
		self.assertEqual(df.label, "Description")
		self.assertFalse(df.reqd)  # HRMS creates Additional Salary from code without it
		self.assertEqual(df.depends_on, "eval:doc.salary_component")
		fields = [f.fieldname for f in meta.fields]
		self.assertEqual(fields.index(DESCRIPTION_FIELD), fields.index("amount") + 1)

	def test_salary_slip_with_and_without_description(self):
		company = frappe.get_all(
			"Company",
			filters={"default_payroll_payable_account": ["is", "set"]},
			fields=["name", "default_currency", "default_payroll_payable_account"],
			limit=1,
		)
		if not company:
			self.skipTest("No company with a Default Payroll Payable Account")
		company = company[0]

		earning = self.make_component("Earning")
		deduction = self.make_component("Deduction")
		employee = self.make_employee(company.name)

		structure = frappe.get_doc(
			{
				"doctype": "Salary Structure",
				"name": f"{PREFIX} Structure",
				"company": company.name,
				"payroll_frequency": "Monthly",
				"currency": company.default_currency,
				"earnings": [
					{"salary_component": earning, "amount_based_on_formula": 1, "formula": "base"}
				],
			}
		).insert()
		structure.submit()
		frappe.get_doc(
			{
				"doctype": "Salary Structure Assignment",
				"employee": employee,
				"salary_structure": structure.name,
				"company": company.name,
				"currency": company.default_currency,
				"from_date": add_days(nowdate(), -100),
				"base": 50000,
				"payroll_payable_account": company.default_payroll_payable_account,
			}
		).insert().submit()

		def additional_salary(component, amount, description=None):
			doc = frappe.get_doc(
				{
					"doctype": "Additional Salary",
					"employee": employee,
					"company": company.name,
					"currency": company.default_currency,
					"salary_component": component,
					"amount": amount,
					"payroll_date": nowdate(),
					DESCRIPTION_FIELD: description,
				}
			).insert()
			doc.submit()
			return doc

		described = additional_salary(earning, 1500, "Overtime for the site audit")
		plain = additional_salary(deduction, 200)
		self.assertEqual(
			frappe.db.get_value("Additional Salary", described.name, DESCRIPTION_FIELD),
			"Overtime for the site audit",
		)

		slip = frappe.get_doc(
			{
				"doctype": "Salary Slip",
				"employee": employee,
				"posting_date": nowdate(),
				"start_date": get_first_day(nowdate()),
				"payroll_frequency": "Monthly",
				"salary_structure": structure.name,
			}
		).insert()
		self.assertIn((earning, 1500, described.name), self.rows(slip.earnings))
		self.assertIn((deduction, 200, plain.name), self.rows(slip.deductions))

	@staticmethod
	def rows(table):
		return [(r.salary_component, r.amount, r.additional_salary) for r in table]

	@staticmethod
	def make_component(component_type):
		return (
			frappe.get_doc(
				{
					"doctype": "Salary Component",
					"salary_component": f"{PREFIX} {component_type}",
					"salary_component_abbr": f"PEWAS{component_type[0]}",
					"type": component_type,
				}
			)
			.insert()
			.name
		)

	@staticmethod
	def make_employee(company):
		holiday_list = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": f"{PREFIX} Holidays",
				"from_date": get_year_start(nowdate()),
				"to_date": get_year_ending(nowdate()),
			}
		).insert()
		employee = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": PREFIX,
				"gender": "Male",
				"date_of_birth": "1990-01-01",
				"date_of_joining": add_days(nowdate(), -400),
				"company": company,
				"status": "Active",
				"holiday_list": holiday_list.name,
			}
		).insert()
		if frappe.db.exists("DocType", "Holiday List Assignment"):  # newer HRMS reads holidays from here
			frappe.get_doc(
				{
					"doctype": "Holiday List Assignment",
					"applicable_for": "Employee",
					"assigned_to": employee.name,
					"holiday_list": holiday_list.name,
					"from_date": holiday_list.from_date,
				}
			).insert().submit()
		return employee.name
