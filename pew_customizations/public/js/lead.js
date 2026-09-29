// Lead → Create → Opportunity (and the Connections "+") skip ERPNext's Create Opportunity dialog
// (Create Prospect / Prospect Name / Create Contact) and open the standard mapped Opportunity directly.
// This file is appended after erpnext/crm/doctype/lead/lead.js, so it can replace the one controller
// method both entry points call; if ERPNext renames it, the standard dialog simply comes back.

if (erpnext.LeadController) {
	class PEWLeadController extends erpnext.LeadController {
		make_opportunity() {
			frappe.model.open_mapped_doc({
				method: "erpnext.crm.doctype.lead.lead.make_opportunity",
				frm: this.frm,
			});
		}
	}
	extend_cscript(cur_frm.cscript, new PEWLeadController({ frm: cur_frm }));
} else {
	console.warn("[pew] erpnext.LeadController not found; Lead keeps the standard Create Opportunity dialog.");
}
