frappe.listview_settings["Scope"] = {
	formatters: {
		progress(value) {
			const percent = Math.min(100, Math.max(0, Math.round(flt(value))));
			return `
				<div class="scope-progress-bar" title="${__("Progress")}: ${percent}%">
					<div class="scope-progress-bar-fill" style="width: ${percent}%;"></div>
				</div>
			`;
		},
	},
};
