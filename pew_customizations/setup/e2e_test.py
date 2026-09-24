import frappe
from frappe.model.workflow import apply_workflow


def run():
	frappe.set_user("Administrator")
	results = []
	created = {"users": [], "opportunity": None, "project": None}

	def check(label, condition):
		status = "PASS" if condition else "FAIL"
		results.append((status, label))
		print(f"[{status}] {label}")

	try:
		_run_checks(check, created)
	finally:
		frappe.set_user("Administrator")
		_cleanup(created)
		failures = [r for r in results if r[0] == "FAIL"]
		print(f"\n{len(results) - len(failures)}/{len(results)} checks passed.")
		if failures:
			print("FAILURES:", failures)


def _cleanup(created):
	attach_targets = [v for v in (created.get("opportunity"), created.get("project")) if v]
	if attach_targets:
		for f in frappe.get_all("File", filters={"attached_to_name": ["in", attach_targets]}, fields=["name"]):
			frappe.delete_doc("File", f.name, ignore_permissions=True, force=True, delete_permanently=True)

	if created.get("project") and frappe.db.exists("Project", created["project"]):
		frappe.delete_doc("Project", created["project"], ignore_permissions=True, force=True)
	if created.get("opportunity") and frappe.db.exists("Opportunity", created["opportunity"]):
		frappe.delete_doc("Opportunity", created["opportunity"], ignore_permissions=True, force=True)
	if created.get("opportunity_2") and frappe.db.exists("Opportunity", created["opportunity_2"]):
		frappe.delete_doc("Opportunity", created["opportunity_2"], ignore_permissions=True, force=True)
	for user in created.get("users", []):
		if frappe.db.exists("Drive Settings", user):
			frappe.delete_doc("Drive Settings", user, ignore_permissions=True, force=True)
		if frappe.db.exists("User", user):
			frappe.delete_doc("User", user, ignore_permissions=True, force=True)
	frappe.db.commit()
	print("--- cleaned up all test data ---")


def _run_checks(check, created):
	# This dev site has no outgoing Email Account configured, which would make
	# core ERPNext's Project.send_welcome_email() (unrelated to our automation)
	# raise when a user is added to the `users` table. Stub it out for this test only.
	frappe.sendmail = lambda *a, **k: None

	company = frappe.defaults.get_global_default("company")
	customer = frappe.get_all("Customer", limit_page_length=1)[0].name

	# 1. Create Opportunity, still Open
	opp = frappe.new_doc("Opportunity")
	opp.opportunity_from = "Customer"
	opp.party_name = customer
	opp.title = "PEW E2E Test Tender"
	opp.company = company
	opp.status = "Open"
	opp.submitted_bid_value = 5_000_000
	opp.expected_closing = frappe.utils.add_days(frappe.utils.today(), 30)
	opp.insert(ignore_permissions=True)
	created["opportunity"] = opp.name

	# 2. Attach two files with different document_category (real content, so
	# File.before_insert()'s disk read succeeds like a real upload would)
	tech_file = frappe.new_doc("File")
	tech_file.file_name = "technical_scope.txt"
	tech_file.content = b"dummy technical scope content"
	tech_file.attached_to_doctype = "Opportunity"
	tech_file.attached_to_name = opp.name
	tech_file.document_category = "Technical Scope"
	tech_file.insert(ignore_permissions=True)

	price_file = frappe.new_doc("File")
	price_file.file_name = "pricing.xlsx"
	price_file.content = b"dummy pricing content"
	price_file.attached_to_doctype = "Opportunity"
	price_file.attached_to_name = opp.name
	price_file.document_category = "Pricing"
	price_file.insert(ignore_permissions=True)

	# 3. Close the Opportunity -> should trigger Server Script
	opp.reload()
	opp.status = "Closed"
	opp.save(ignore_permissions=True)

	project_name = frappe.db.get_value("Project", {"source_opportunity": opp.name}, "name")
	check("Project auto-created on Closed", bool(project_name))
	created["project"] = project_name

	if project_name:
		project = frappe.get_doc("Project", project_name)
		check("Project.pending_review == 1", project.pending_review == 1)
		check("Project.estimated_costing == submitted_bid_value", project.estimated_costing == 5_000_000)
		check("Project.customer == Opportunity customer", project.customer == customer)

		copied_files = frappe.get_all(
			"File", filters={"attached_to_doctype": "Project", "attached_to_name": project_name}, fields=["document_category"]
		)
		check("Exactly 1 File copied to Project", len(copied_files) == 1)
		check(
			"Copied File is Technical Scope (not Pricing)",
			len(copied_files) == 1 and copied_files[0].document_category == "Technical Scope",
		)

		# 4. Idempotency: save again, should not create a second Project
		opp.save(ignore_permissions=True)
		project_count = frappe.db.count("Project", {"source_opportunity": opp.name})
		check("No duplicate Project on second save", project_count == 1)

		check("Workflow auto-assigned initial state 'Pending'", project.workflow_state == "Pending")

		# 5. Add a team member BEFORE approval -> should NOT get file share yet
		test_user = "test_execution_engineer@example.com"
		if not frappe.db.exists("User", test_user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": test_user,
					"first_name": "Test Execution Engineer",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		created["users"].append(test_user)

		project.reload()
		project.append("users", {"user": test_user})
		project.save(ignore_permissions=True)

		shared_before = frappe.db.exists("DocShare", {"share_doctype": "File", "user": test_user})
		check("No File share before approval", not shared_before)

		# 6. A user WITHOUT Projects Manager role must be denied the Approve transition
		non_manager = "test_non_manager@example.com"
		if not frappe.db.exists("User", non_manager):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": non_manager,
					"first_name": "Test Non Manager",
					"send_welcome_email": 0,
					"roles": [{"role": "Projects User"}] if frappe.db.exists("Role", "Projects User") else [],
				}
			).insert(ignore_permissions=True)
		created["users"].append(non_manager)

		frappe.set_user(non_manager)
		denied = False
		try:
			apply_workflow(project.as_dict(), "Approve")
		except Exception:
			denied = True
		frappe.set_user("Administrator")
		check("Non-manager denied the Approve transition", denied)

		# 7. Approve as Administrator (has all roles) -> pending_review should flip to 0
		project.reload()
		apply_workflow(project.as_dict(), "Approve")
		project.reload()
		check("pending_review == 0 after Approved transition", project.pending_review == 0)

		# 8. Add ANOTHER team member AFTER approval -> should get file share now
		test_user_2 = "test_execution_engineer_2@example.com"
		if not frappe.db.exists("User", test_user_2):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": test_user_2,
					"first_name": "Test Execution Engineer 2",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		created["users"].append(test_user_2)

		project.reload()
		project.append("users", {"user": test_user_2})
		project.save(ignore_permissions=True)

		shared_after = frappe.db.exists("DocShare", {"share_doctype": "File", "user": test_user_2})
		check("File shared with team member added after approval", bool(shared_after))

	# 9. Lost Reason required + freeze-after-Lost, on a separate Opportunity
	lost_opp = frappe.new_doc("Opportunity")
	lost_opp.opportunity_from = "Customer"
	lost_opp.party_name = customer
	lost_opp.title = "PEW E2E Test Tender (Lost)"
	lost_opp.company = company
	lost_opp.status = "Open"
	lost_opp.insert(ignore_permissions=True)
	created["opportunity_2"] = lost_opp.name

	if not frappe.db.exists("Opportunity Lost Reason", "Price Too High"):
		frappe.get_doc({"doctype": "Opportunity Lost Reason", "lost_reason": "Price Too High"}).insert(
			ignore_permissions=True
		)

	blocked_without_reason = False
	try:
		lost_opp.status = "Lost"
		lost_opp.save(ignore_permissions=True)
	except frappe.ValidationError:
		blocked_without_reason = True
	check("Marking Lost without a Lost Reason is blocked", blocked_without_reason)

	lost_opp.reload()
	lost_opp.status = "Lost"
	lost_opp.append("lost_reasons", {"lost_reason": "Price Too High"})
	lost_opp.save(ignore_permissions=True)
	check("Marking Lost with a Lost Reason succeeds", frappe.db.get_value("Opportunity", lost_opp.name, "status") == "Lost")

	frozen = False
	try:
		lost_opp.title = "Trying to edit a Lost Opportunity"
		lost_opp.save(ignore_permissions=True)
	except frappe.ValidationError:
		frozen = True
	check("Lost Opportunity is frozen (no further edits)", frozen)
