frappe.pages["itsm-change-calendar"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("ITSM Change Calendar"),
		single_column: true,
	});
	page.main.html(`<div class="change-calendar"></div>`);
	frappe.call({
		method: "it_service_management.itsm.page.itsm_change_calendar.itsm_change_calendar.get_changes",
		callback: (r) => {
			const rows = r.message || [];
			page.main.find(".change-calendar").html(render_changes(rows));
		},
	});
};

function render_changes(rows) {
	if (!rows.length) return `<p class="text-muted">${__("No scheduled changes")}</p>`;
	return `<div class="list-group">${rows.map((row) => `<a class="list-group-item" href="/app/itsm-change-request/${row.name}"><b>${row.name}</b> ${frappe.utils.escape_html(row.title || "")}<span class="pull-right">${row.status} · ${row.risk_level || ""}</span><br><small>${row.planned_start || ""} → ${row.planned_end || ""}</small></a>`).join("")}</div>`;
}
