// Lead → Create → Opportunity (and the Connections "+"): an Opportunity is always made for a Customer
// (crm/opportunity.py refuses one on a Lead), so these go through the standard Customer route instead of
// ERPNext's Create Opportunity dialog. A Lead that already has a Customer opens a new Opportunity for it;
// otherwise the user is offered the standard Create → Customer first.
// This file is appended after erpnext/crm/doctype/lead/lead.js, so it can replace the one controller
// method both entry points call; if ERPNext renames it, the standard dialog comes back and the server
// still refuses the Lead-based Opportunity.

if (erpnext.LeadController) {
	class PEWLeadController extends erpnext.LeadController {
		make_opportunity() {
			frappe.db.get_value("Customer", { lead_name: this.frm.doc.name }, "name").then(({ message }) => {
				const customer = message && message.name;
				if (customer) {
					frappe.model.open_mapped_doc({
						method: "erpnext.selling.doctype.customer.customer.make_opportunity",
						source_name: customer,
					});
					return;
				}
				frappe.confirm(
					__(
						"Opportunities are made for a Customer. Create the Customer from this Lead now? Then use Create → Opportunity on the Customer."
					),
					() => this.make_customer()
				);
			});
		}
	}
	extend_cscript(cur_frm.cscript, new PEWLeadController({ frm: cur_frm }));
} else {
	console.warn("[pew] erpnext.LeadController not found; Lead keeps the standard Create Opportunity dialog.");
}
