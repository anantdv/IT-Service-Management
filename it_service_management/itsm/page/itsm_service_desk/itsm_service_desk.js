frappe.pages["itsm-service-desk"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("ITSM Service Desk"),
		single_column: true,
	});
	page.main.html(`
		<div class="itsm-service-desk">
			<div class="itsm-service-desk__toolbar">
				<button class="btn btn-primary btn-sm new-incident">${__("New Incident")}</button>
				<button class="btn btn-default btn-sm new-request">${__("New Service Request")}</button>
				<button class="btn btn-default btn-sm refresh-desk">${__("Refresh")}</button>
			</div>
			<div class="itsm-kpi-grid"></div>
			<div class="itsm-queue-grid"></div>
		</div>
	`);
	page.main.find(".new-incident").on("click", () => frappe.new_doc("Service Ticket", { ticket_type: "Incident" }));
	page.main.find(".new-request").on("click", () => frappe.new_doc("Service Ticket", { ticket_type: "Service Request" }));
	page.main.find(".refresh-desk").on("click", () => load_service_desk(page));
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
		.map((key) => `
			<div class="itsm-kpi-card">
				<span>${labels[key]}</span>
				<strong>${kpis[key] || 0}</strong>
			</div>
		`)
		.join("");
	page.main.find(".itsm-kpi-grid").html(html);
}

function render_queues(page, data) {
	const sections = [
		["my_queue", __("My Queue")],
		["unassigned_queue", __("Unassigned Queue")],
		["critical_incidents", __("Critical Incidents")],
		["sla_at_risk", __("SLA At Risk")],
	];
	const html = sections.map(([key, label]) => `
		<section class="itsm-queue-card">
			<div class="itsm-queue-card__head">
				<h3>${label}</h3>
				<span>${(data[key] || []).length}</span>
			</div>
			${ticket_table(data[key] || [])}
		</section>
	`).join("");
	page.main.find(".itsm-queue-grid").html(html);
}

function ticket_table(rows) {
	if (!rows.length) return `<div class="itsm-empty">${__("No records")}</div>`;
	return `
		<div class="itsm-ticket-list">
			${rows.map((row) => `
				<a class="itsm-ticket-row" href="/app/service-ticket/${row.name}">
					<span>
						<strong>${row.name}</strong>
						<em>${frappe.utils.escape_html(row.subject || "")}</em>
					</span>
					<small class="priority-${frappe.scrub(row.priority || "medium")}">${row.priority || ""}</small>
				</a>
			`).join("")}
		</div>
	`;
}
