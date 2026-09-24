frappe.ui.form.on("PEC Revision", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus === 1) {
			return;
		}

		const pending = (frm.doc.review_stages || [])
			.filter((row) => row.status === "Pending")
			.sort((a, b) => (a.sequence || 0) - (b.sequence || 0))[0];

		if (pending && pending.reviewer === frappe.session.user) {
			frm.add_custom_button(__("Action My Review Stage"), () => {
				const dialog = new frappe.ui.Dialog({
					title: __("Review Stage: {0}", [pending.stage_name]),
					fields: [
						{
							fieldname: "status",
							fieldtype: "Select",
							label: __("Decision"),
							options: "Approved\nRejected",
							reqd: 1,
						},
						{
							fieldname: "comments",
							fieldtype: "Small Text",
							label: __("Comments"),
						},
					],
					primary_action_label: __("Submit"),
					primary_action(values) {
						frm.call("mark_stage_reviewed", {
							row_name: pending.name,
							status: values.status,
							comments: values.comments,
						}).then(() => {
							dialog.hide();
							frm.reload_doc();
						});
					},
				});
				dialog.show();
			});
		}
	},
});
