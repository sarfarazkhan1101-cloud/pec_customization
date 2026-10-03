// Copyright (c) 2026, PEW Engineering & Consultancy Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["PEC DCI Report"] = {
	filters: [
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
			reqd: 1,
			on_change(report) {
				// Scope and Latest Code belong to one Project
				pec_dci_load_codes(report).then(() => {
					const stale = ["scope", "latest_code"].filter((f) => report.get_filter_value(f));
					if (stale.length) {
						// refreshes the report once the last one is cleared
						report.set_filter_value(Object.fromEntries(stale.map((f) => [f, ""])));
					} else {
						report.refresh();
					}
				});
			},
		},
		{
			fieldname: "scope",
			label: __("Scope"),
			fieldtype: "Link",
			options: "Scope",
			get_query() {
				return { filters: { project: frappe.query_report.get_filter_value("project") } };
			},
		},
		{
			fieldname: "engineer",
			label: __("Engineer"),
			fieldtype: "Link",
			options: "User",
		},
		{
			fieldname: "latest_code",
			label: __("Latest Code"),
			fieldtype: "Select",
			options: [""],
		},
		{
			fieldname: "latest_status",
			label: __("Latest Status"),
			fieldtype: "Select",
			options: ["", "Not Submitted", "Awaiting Comments", "Code Received", "Approved"],
		},
	],

	onload(report) {
		pec_dci_load_codes(report);

		// same right as Menu > Export; the server checks it again
		if (frappe.model.can_export("Task")) {
			report.page.add_inner_button(__("Download DCI (Client Format)"), () => {
				const project = report.get_filter_value("project");
				if (!project) {
					frappe.msgprint(__("Select a Project first."));
					return;
				}
				open_url_post(frappe.request.url, {
					cmd: "pew_customizations.api.dci_export.download_dci_xlsx",
					project: project,
					scope: report.get_filter_value("scope") || "",
				});
			});
		}
	},

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "document_name" && data && data.task) {
			return `<a href="${frappe.utils.get_form_link("Task", data.task)}">${value}</a>`;
		}
		return value;
	},
};

// Latest Code offers the selected Project's own Approval Codes
function pec_dci_load_codes(report) {
	const filter = report.get_filter("latest_code");
	const project = report.get_filter_value("project");
	const set_options = (codes) => {
		filter.df.options = ["", ...codes.map((d) => d.code)];
		filter.refresh();
	};

	if (!project) {
		set_options([]);
		return Promise.resolve();
	}
	return frappe
		.xcall("pew_customizations.projects.approval_codes.get_approval_codes", { project })
		.then((codes) => set_options(codes || []))
		.catch(() => set_options([]));
}
