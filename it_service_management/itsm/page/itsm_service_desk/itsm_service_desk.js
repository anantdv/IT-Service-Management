frappe.pages["itsm-service-desk"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("ITSM Service Desk"),
		single_column: true,
	});
	page.main.html(`<div class="itsm-service-desk"><div class="kpis"></div><div class="queues row"></div></div>`);
	load_service_desk(page);
};

function load_service_desk(page) {
	frappe.call({
		method: "it_service_management.itsm.page.itsm_service_desk.itsm_service_desk.get_service_desk",
		callback: (r) => {
			const data = r.message || {};
			render_kpis(page, data.kpis || {});
			render_queues(page, data);
		},
	});
}

function render_kpis(page, kpis) {
	const labels = {
		new: __("New"),
		unassigned: __("Unassigned"),
		p1: __("P1"),
		p2: __("P2"),
		sla_at_risk: __("SLA At Risk"),
		sla_breached: __("SLA Breached"),
		major_incidents: __("Major Incidents"),
		waiting: __("Waiting"),
	};
	const html = Object.keys(labels)
		.map((key) => `<div class="number-card-widget-box"><div class="widget-head"><span>${labels[key]}</span></div><div class="widget-body"><div class="widget-content"><div class="number">${kpis[key] || 0}</div></div></div></div>`)
		.join("");
	page.main.find(".kpis").html(`<div class="number-card-container">${html}</div>`);
}

function render_queues(page, data) {
	const sections = [
		["my_queue", __("My Queue")],
		["unassigned_queue", __("Unassigned Queue")],
		["critical_incidents", __("Critical Incidents")],
		["sla_at_risk", __("SLA At Risk")],
	];
	const html = sections.map(([key, label]) => `<div class="col-md-6"><h4>${label}</h4>${ticket_table(data[key] || [])}</div>`).join("");
	page.main.find(".queues").html(html);
}

function ticket_table(rows) {
	if (!rows.length) return `<p class="text-muted">${__("No records")}</p>`;
	return `<div class="list-group">${rows.map((row) => `<a class="list-group-item" href="/app/service-ticket/${row.name}"><b>${row.name}</b> ${frappe.utils.escape_html(row.subject || "")}<span class="pull-right">${row.priority || ""}</span></a>`).join("")}</div>`;
}
