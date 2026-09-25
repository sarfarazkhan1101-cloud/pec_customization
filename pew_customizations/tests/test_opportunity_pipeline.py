"""Tender pipeline on Opportunity: gates, Lost freeze, handoff, access, email linking, dashboard.

Run: bench --site <site> run-tests --module pew_customizations.tests.test_opportunity_pipeline
Everything is rolled back after the run; files are remote URLs so nothing is written to disk.
"""

from unittest.mock import patch

import frappe
from frappe.client import set_value
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, now_datetime, today

from pew_customizations.crm import config
from pew_customizations.crm.customer import onload as customer_onload
from pew_customizations.crm.file import has_permission as file_has_permission
from pew_customizations.crm.opportunity import get_missing_items

SALES_USER = "pew.test.sales@example.com"
SALES_MANAGER = "pew.test.manager@example.com"
ENGINEER = "pew.test.engineer@example.com"
STAGES = config.PIPELINE_STAGES


def _user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
	return email


def _customer(name):
	return frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company"}).insert(
		ignore_permissions=True
	)


class TestOpportunityPipeline(IntegrationTestCase):
	SHOW_TRANSACTION_COMMIT_WARNINGS = True  # everything here must be rolled back

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# no outgoing Email Account on dev sites; welcome emails and notifications must not fail tests
		cls.enterClassContext(patch("frappe.sendmail"))
		cls.company = frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
		cls.currency = frappe.get_cached_value("Company", cls.company, "default_currency")
		cls.customer = _customer("PEW Pipeline Test Customer")
		cls.contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "Tender",
				"last_name": "Contact",
				"designation": "Procurement Head",
				"email_ids": [{"email_id": "tender.contact@pewclient.example.com", "is_primary": 1}],
				"links": [{"link_doctype": "Customer", "link_name": cls.customer.name}],
			}
		).insert(ignore_permissions=True)
		_user(SALES_USER, ["Sales User"])
		_user(SALES_MANAGER, ["Sales User", "Sales Manager"])
		_user(ENGINEER, ["Projects User"])

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	# helpers -----------------------------------------------------------------------------------

	def new_opportunity(self, **values):
		opp = frappe.get_doc(
			{
				"doctype": "Opportunity",
				"opportunity_from": "Customer",
				"party_name": self.customer.name,
				"company": self.company,
				"currency": self.currency,
				"title": "Pipeline test tender",
				**values,
			}
		)
		return opp.insert(ignore_permissions=True)

	def file(self, opp, name, **values):
		url = f"https://files.pewclient.example.com/{opp.name}/{name}"
		frappe.get_doc(
			{
				"doctype": "File",
				"file_url": url,
				"file_name": name,
				"attached_to_doctype": "Opportunity",
				"attached_to_name": opp.name,
				**values,
			}
		).insert(ignore_permissions=True)
		return url

	def complete(self, opp, stage_index):
		"""Fill in everything the gates need to put `opp` at `stage_index`."""
		if stage_index > config.INQUIRY:
			opp.contact_person = self.contact.name
			opp.pew_organization_type = "Private Sector"
			opp.market_segment = frappe.get_all("Market Segment", pluck="name", limit=1)[0]
			opp.utm_source = "Tender Portal"
			opp.opportunity_owner = "Administrator"
			opp.pew_inquiry_received_on = today()
			if not frappe.db.exists("ToDo", {"reference_type": "Opportunity", "reference_name": opp.name}):
				frappe.get_doc(
					{
						"doctype": "ToDo",
						"allocated_to": "Administrator",
						"reference_type": "Opportunity",
						"reference_name": opp.name,
						"description": "Estimate",
					}
				).insert(ignore_permissions=True)
		if stage_index > config.QUALIFICATION and not opp.pew_tender_documents:
			opp.append(
				"pew_tender_documents",
				{"document_type": "Tender / RFQ Document", "file": self.file(opp, "rfq.pdf")},
			)
			opp.pew_bid_submission_deadline = add_to_date(now_datetime(), days=10)
			opp.pew_nda_status = "Not Required"
			opp.pew_go_no_go = "Go"
		if stage_index > config.QUERIES:
			opp.pew_queries_clarified = 1
			opp.pew_scope_locked = 1
		if stage_index >= config.PROPOSAL:
			opp.pew_submitted_bid_value = 1_000_000
			opp.pew_bid_validity_expiry = add_days(today(), 90)
			opp.pew_final_proposal = opp.pew_final_proposal or self.file(opp, "proposal.pdf")
			opp.pew_emd_status = "Submitted"
		if stage_index >= config.EVALUATION:
			opp.pew_evaluation_substage = "Price Bid Review"
		if stage_index >= config.WON:
			opp.pew_loi_date = today()
			opp.pew_final_contract_value = 950_000
			opp.pew_project_start_date = add_days(today(), 15)
			opp.pew_project_end_date = add_days(today(), 200)
			opp.pew_work_order_file = opp.pew_work_order_file or self.file(opp, "work-order.pdf")

	def advance(self, opp, stage_index):
		for idx in range(opp.pew_stage_index + 1, stage_index + 1):
			self.complete(opp, idx)
			opp.sales_stage = STAGES[idx - 1]
			opp.save(ignore_permissions=True)
		return opp

	# configuration -----------------------------------------------------------------------------

	def test_gate_fields_match_mandatory_depends_on(self):
		meta = frappe.get_meta("Opportunity")
		for gates, offset in ((config.EXIT_GATES, 1), (config.ENTRY_GATES, 0)):
			for stage_idx, stage_gates in gates.items():
				for gate in stage_gates:
					if not gate.fieldname or gate.when:
						continue
					df = meta.get_field(gate.fieldname)
					if df.fieldtype == "Check":
						continue  # checkboxes are only enforced by the server gate
					self.assertEqual(
						df.mandatory_depends_on, config.stage_from(stage_idx + offset), gate.fieldname
					)

	def test_form_scripts_and_layout(self):
		from frappe.desk.form.meta import get_meta

		opportunity = get_meta("Opportunity", cached=False)
		self.assertIn("pew_link_emails_dialog", opportunity.get("__js") or "")
		self.assertIn("pew_opportunity_stats", get_meta("Customer", cached=False).get("__js") or "")

		order = [df.fieldname for df in opportunity.fields]
		after_header = order[order.index("probability") + 1 :]
		self.assertEqual(after_header[:2], ["lost_detail_section", "lost_reasons"])
		# the stages live on the last tab, after Connections
		tabs = [df.fieldname for df in opportunity.fields if df.fieldtype == "Tab Break"]
		self.assertEqual(tabs[-2:], ["dashboard_tab", "pew_pipeline_tab"])
		self.assertLess(order.index("pew_pipeline_tab"), order.index("pew_stage1_section"))
		self.assertLess(order.index("pew_stage2_section"), order.index("contact_person"))
		self.assertLess(order.index("contact_person"), order.index("pew_stage3_section"))
		self.assertTrue(opportunity.track_changes)

	def test_sales_stages_are_ordered(self):
		for stage, order in config.SALES_STAGE_ORDER.items():
			self.assertEqual(frappe.db.get_value("Sales Stage", stage, "pew_stage_order"), order)

	# stages and gates --------------------------------------------------------------------------

	def test_new_opportunity_starts_cold(self):
		opp = self.new_opportunity()
		self.assertEqual(opp.sales_stage, "Cold")
		self.assertEqual(opp.pew_stage_index, 1)

	def test_non_pipeline_stage_rejected(self):
		if not frappe.db.exists("Sales Stage", "PEW Test Legacy Stage"):
			frappe.get_doc({"doctype": "Sales Stage", "stage_name": "PEW Test Legacy Stage"}).insert()
		with self.assertRaises(frappe.ValidationError):
			self.new_opportunity(sales_stage="PEW Test Legacy Stage")

	def test_gate_blocks_form_and_kanban_moves(self):
		opp = self.new_opportunity()
		opp.sales_stage = STAGES[config.INQUIRY - 1]
		opp.save()  # leaving Cold needs nothing

		opp.sales_stage = STAGES[config.QUALIFICATION - 1]
		with self.assertRaises(frappe.ValidationError):
			opp.save()

		# Kanban drags call frappe.set_value -> the same gate applies
		with self.assertRaises(frappe.ValidationError):
			set_value("Opportunity", opp.name, "sales_stage", STAGES[config.QUALIFICATION - 1])

		opp.reload()
		missing = [label for _stage, label in get_missing_items(opp, config.QUALIFICATION)]
		self.assertIn("Assigned to the estimation team", missing)
		self.assertIn("Contact Person", missing)

	def test_conditional_gates(self):
		opp = self.new_opportunity()
		self.advance(opp, config.INQUIRY)
		self.complete(opp, config.QUALIFICATION)
		opp.pew_organization_type = "Government"  # tender ref becomes required
		opp.sales_stage = STAGES[config.QUALIFICATION - 1]
		with self.assertRaises(frappe.ValidationError):
			opp.save()

		opp.reload()  # a rejected save leaves the in-memory timestamp ahead of the DB
		self.complete(opp, config.QUALIFICATION)
		opp.pew_organization_type = "Government"
		opp.pew_tender_ref_no = "GOV/2026/117"
		opp.sales_stage = STAGES[config.QUALIFICATION - 1]
		opp.save()

		self.complete(opp, config.QUERIES)
		opp.pew_go_no_go = "No-Go"
		opp.sales_stage = STAGES[config.QUERIES - 1]
		with self.assertRaises(frappe.ValidationError):
			opp.save()

	def test_skipping_needs_every_intermediate_checklist(self):
		opp = self.new_opportunity()
		self.advance(opp, config.QUALIFICATION)
		opp.sales_stage = STAGES[config.PROPOSAL - 1]
		with self.assertRaises(frappe.ValidationError):
			opp.save()  # stage 3 and 4 checklists incomplete
		opp.reload()
		self.complete(opp, config.PROPOSAL)
		opp.sales_stage = STAGES[config.PROPOSAL - 1]
		opp.save()
		self.assertEqual(opp.pew_stage_index, config.PROPOSAL)

	def test_backward_move_allowed(self):
		opp = self.advance(self.new_opportunity(), config.QUERIES)
		opp.sales_stage = STAGES[config.QUALIFICATION - 1]
		opp.save()
		self.assertEqual(opp.pew_stage_index, config.QUALIFICATION)

	def test_only_manager_moves_to_won(self):
		opp = self.advance(self.new_opportunity(), config.EVALUATION)
		self.complete(opp, config.WON)
		opp.save()
		frappe.set_user(SALES_USER)
		opp = frappe.get_doc("Opportunity", opp.name)
		opp.sales_stage = config.WON_STAGE
		with self.assertRaises(frappe.ValidationError):
			opp.save()

	# Lost ----------------------------------------------------------------------------------------

	def declare_lost(self, opp):
		opp.declare_enquiry_lost(
			[{"lost_reason": "Outbid on Price"}], [], detailed_reason="L2 on price bid"
		)
		opp.reload()
		return opp

	def test_declare_lost_keeps_stage_and_tags(self):
		opp = self.advance(self.new_opportunity(), config.QUALIFICATION)
		opp = self.declare_lost(opp)
		self.assertEqual(opp.status, "Lost")
		self.assertEqual(opp.sales_stage, STAGES[config.QUALIFICATION - 1])
		self.assertEqual(str(opp.pew_lost_on), today())
		self.assertIn(config.LOST_TAG, (opp.get("_user_tags") or "").split(","))

	def test_lost_needs_reason(self):
		opp = self.new_opportunity()
		opp.status = "Lost"
		with self.assertRaises(frappe.ValidationError):
			opp.save()

	def test_lost_is_frozen_for_sales_user_but_manager_can_reopen(self):
		opp = self.declare_lost(self.advance(self.new_opportunity(), config.INQUIRY))

		frappe.set_user(SALES_USER)
		frozen = frappe.get_doc("Opportunity", opp.name)
		frozen.pew_cold_notes = "trying to edit"
		with self.assertRaises(frappe.ValidationError):
			frozen.save()

		frappe.set_user(SALES_MANAGER)
		reopened = frappe.get_doc("Opportunity", opp.name)
		reopened.set("lost_reasons", [])
		reopened.status = "Open"
		reopened.save()
		reopened.reload()
		self.assertEqual(reopened.status, "Open")
		self.assertIsNone(reopened.pew_lost_on)
		self.assertNotIn(config.LOST_TAG, (reopened.get("_user_tags") or "").split(","))

	def test_won_cannot_be_declared_lost(self):
		opp = self.advance(self.new_opportunity(), config.WON)
		with self.assertRaises(frappe.ValidationError):
			self.declare_lost(opp)

	def test_closed_blocked_for_sales_user(self):
		opp = self.new_opportunity()
		frappe.set_user(SALES_USER)
		opp = frappe.get_doc("Opportunity", opp.name)
		opp.status = "Closed"
		with self.assertRaises(frappe.ValidationError):
			opp.save()

	# documents and handoff ----------------------------------------------------------------------

	def test_document_rows_are_classified(self):
		opp = self.advance(self.new_opportunity(), config.QUALIFICATION)
		opp.append("pew_clarification_documents", {"document_type": "Addendum / Corrigendum", "file": self.file(opp, "add1.pdf")})
		opp.append("pew_commercial_documents", {"document_type": "Pricing / BOQ", "file": self.file(opp, "boq.xlsx")})
		opp.save()
		self.assertEqual(opp.pew_clarification_documents[0].document_class, "Technical")
		self.assertEqual(opp.pew_commercial_documents[0].document_class, "Commercial")
		self.assertEqual(opp.pew_commercial_documents[0].stage, STAGES[config.QUALIFICATION - 1])
		self.assertEqual(
			frappe.db.get_value("File", {"file_url": opp.pew_commercial_documents[0].file}, "document_category"),
			"Pricing / BOQ",
		)

	def test_won_creates_one_project_with_technical_documents_only(self):
		opp = self.advance(self.new_opportunity(), config.EVALUATION)
		opp.append("pew_clarification_documents", {"document_type": "Minutes of Meeting", "file": self.file(opp, "mom.pdf")})
		opp.append("pew_commercial_documents", {"document_type": "Pricing / BOQ", "file": self.file(opp, "boq.xlsx")})
		opp.save()
		self.advance(opp, config.WON)
		opp.reload()

		self.assertEqual(opp.status, "Converted")
		self.assertTrue(opp.pew_project)
		project = frappe.get_doc("Project", opp.pew_project)
		self.assertEqual(project.source_opportunity, opp.name)
		self.assertEqual(project.customer, self.customer.name)
		self.assertEqual(project.workflow_state, "Pending")
		self.assertEqual(project.pew_contract_value, 950_000)
		self.assertEqual(str(project.expected_start_date), str(opp.pew_project_start_date))
		self.assertTrue(project.name.startswith("PEC-"))

		project_files = set(
			frappe.get_all(
				"File",
				filters={"attached_to_doctype": "Project", "attached_to_name": project.name},
				pluck="file_name",
			)
		)
		self.assertEqual(project_files, {"rfq.pdf", "mom.pdf"})  # no proposal, BOQ or work order

		# saving again, or moving back and forth, never creates a second Project
		opp.save()
		opp.sales_stage = STAGES[config.EVALUATION - 1]
		opp.save()
		opp.sales_stage = config.WON_STAGE
		opp.save()
		self.assertEqual(frappe.db.count("Project", {"source_opportunity": opp.name}), 1)

		# the database refuses a duplicate as a last line of defence
		duplicate = frappe.copy_doc(project)
		duplicate.project_name = f"{project.project_name} copy"
		duplicate.source_opportunity = opp.name
		with self.assertRaises(frappe.UniqueValidationError):
			duplicate.insert(ignore_permissions=True)

	def test_sales_user_cannot_move_back_after_handoff(self):
		opp = self.advance(self.new_opportunity(), config.WON)
		frappe.set_user(SALES_USER)
		opp = frappe.get_doc("Opportunity", opp.name)
		opp.sales_stage = STAGES[config.EVALUATION - 1]
		with self.assertRaises(frappe.ValidationError):
			opp.save()

	def test_work_order_file_restricted_to_managers(self):
		opp = self.new_opportunity()
		po = frappe.get_doc(
			{
				"doctype": "File",
				"file_url": f"https://files.pewclient.example.com/{opp.name}/po.pdf",
				"file_name": "po.pdf",
				"attached_to_doctype": "Opportunity",
				"attached_to_name": opp.name,
				"attached_to_field": config.WORK_ORDER_FIELD,
			}
		).insert(ignore_permissions=True)
		self.assertFalse(file_has_permission(po, "read", SALES_USER))
		self.assertTrue(file_has_permission(po, "read", SALES_MANAGER))
		self.assertFalse(frappe.has_permission("File", "read", doc=po, user=SALES_USER))

		meta = frappe.get_meta("Opportunity")
		self.assertEqual(meta.get_field(config.WORK_ORDER_FIELD).permlevel, 1)

	def test_public_work_order_rejected(self):
		opp = self.new_opportunity()
		opp.pew_work_order_file = "/files/po.pdf"
		with self.assertRaises(frappe.ValidationError):
			opp.save()

	# Execution Team access -----------------------------------------------------------------------

	def test_execution_team_gets_access_after_approval(self):
		opp = self.advance(self.new_opportunity(), config.WON)
		project = frappe.get_doc("Project", opp.reload().pew_project)
		filters = {"allow": "Project", "for_value": project.name, "user": ENGINEER}

		project.append("users", {"user": ENGINEER})
		project.save(ignore_permissions=True)
		self.assertFalse(frappe.db.exists("User Permission", filters))  # still pending review

		apply_workflow(project.as_dict(), "Approve")
		self.assertTrue(frappe.db.exists("User Permission", filters))

		project.reload()
		project.set("users", [])
		project.save(ignore_permissions=True)
		self.assertFalse(frappe.db.exists("User Permission", filters))

	# email ---------------------------------------------------------------------------------------

	def test_incoming_email_linked_by_subject_tag(self):
		opp = self.new_opportunity()
		comm = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"communication_medium": "Email",
				"sent_or_received": "Received",
				"subject": f"RE: Revised BOQ (#{opp.name})",
				"sender": "tender.contact@pewclient.example.com",
				"content": "Please find the revised BOQ.",
			}
		).insert(ignore_permissions=True)
		self.assertEqual((comm.reference_doctype, comm.reference_name), ("Opportunity", opp.name))

	def test_orphan_email_linked_from_opportunity(self):
		from pew_customizations.crm.api import get_unlinked_emails, link_emails

		opp = self.new_opportunity()
		comm = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"communication_medium": "Email",
				"sent_or_received": "Received",
				"subject": "Site visit schedule",
				"sender": "tender.contact@pewclient.example.com",
				"content": "Can we visit on Monday?",
			}
		).insert(ignore_permissions=True)
		self.assertFalse(comm.reference_name)

		self.assertIn(comm.name, [e.name for e in get_unlinked_emails(opp.name)])
		self.assertEqual(link_emails(opp.name, [comm.name]), 1)
		comm.reload()
		self.assertEqual((comm.reference_doctype, comm.reference_name), ("Opportunity", opp.name))

	# Customer --------------------------------------------------------------------------------------

	def test_customer_pipeline_counts(self):
		party = _customer("PEW Pipeline Counts Customer").name
		self.new_opportunity(party_name=party)
		self.advance(self.new_opportunity(party_name=party), config.QUALIFICATION)
		self.declare_lost(self.advance(self.new_opportunity(party_name=party), config.INQUIRY))
		self.advance(self.new_opportunity(party_name=party), config.WON)

		customer = frappe.get_doc("Customer", party)
		customer_onload(customer)
		counts = customer.get_onload().pew_opportunity_stats["counts"]
		self.assertEqual(counts, {"total": 4, "won": 1, "lost": 1, "cold": 1, "active": 1})

	def test_customer_created_from_opportunity_takes_it_over(self):
		lead = frappe.get_doc({"doctype": "Lead", "lead_name": "Walk-in Prospect", "company_name": "Prospect Co"}).insert(
			ignore_permissions=True
		)
		opp = frappe.get_doc(
			{"doctype": "Opportunity", "opportunity_from": "Lead", "party_name": lead.name, "company": self.company}
		).insert(ignore_permissions=True)

		from erpnext.crm.doctype.opportunity.opportunity import make_customer

		customer = make_customer(opp.name)
		customer.customer_name = "Prospect Co PEW"
		customer.insert(ignore_permissions=True)
		opp.reload()
		self.assertEqual((opp.opportunity_from, opp.party_name), ("Customer", customer.name))
