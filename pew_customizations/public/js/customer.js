// "Tender Pipeline" counters on the Customer dashboard. Counts are computed live on load
// (pew_customizations/crm/customer.py); each counter opens the matching Opportunity list.

frappe.ui.form.on("Customer", {
	refresh(frm) {
		const stats = frm.doc.__onload && frm.doc.__onload.pew_opportunity_stats;
		if (frm.is_new() || !stats) return;

		const { counts, stages, active_statuses } = stats;
		const base = { opportunity_from: "Customer", party_name: frm.doc.name };
		const tiles = [
			{ key: "total", label: __("Total Inquiries"), color: "blue", filters: {} },
			{ key: "active", label: __("Active Bids"), color: "orange", filters: {
				status: ["in", active_statuses],
				sales_stage: ["not in", [stages.cold, stages.won]],
			} },
			{ key: "won", label: __("Won"), color: "green", filters: {
				sales_stage: stages.won,
				status: ["!=", "Lost"],
			} },
			{ key: "lost", label: __("Lost"), color: "red", filters: { status: "Lost" } },
			{ key: "cold", label: __("Cold"), color: "gray", filters: {
				sales_stage: stages.cold,
				status: ["!=", "Lost"],
			} },
		];

		const html = `<div class="row">${tiles
			.map(
				(t) => `<div class="col-sm-2 col-xs-6">
					<a class="pew-pipeline-tile" data-key="${t.key}" href="#">
						<div class="h4 mb-1 text-${t.color}">${cint(counts[t.key])}</div>
						<div class="small text-muted">${t.label}</div>
					</a>
				</div>`
			)
			.join("")}</div>`;

		const $section = frm.dashboard.add_section(html, __("Tender Pipeline"));
		$section.on("click", ".pew-pipeline-tile", (e) => {
			e.preventDefault();
			const tile = tiles.find((t) => t.key === $(e.currentTarget).data("key"));
			frappe.set_route("List", "Opportunity", { ...base, ...tile.filters });
		});
		frm.dashboard.show();
	},
});
