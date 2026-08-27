frappe.pages["it-service-command-center"].on_page_load = function (wrapper) {
	frappe.it_service_command_center = new CommandCenter(wrapper);
};

class CommandCenter {
	constructor(wrapper) {
		this.wrapper = $(wrapper);
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("IT Service Management"),
			single_column: true,
		});
		this.tabs = ["overview", "service", "rental", "contracts", "equipment", "financial"];
		this.active_tab = "overview";
		this.filters = { period: "This Month" };
		this.currency = frappe.defaults.get_default("currency") || "";
		this.make();
		this.load_options();
		this.refresh();
	}

	make() {
		this.page.set_title(__("IT Service Management"));
		this.page.set_indicator(__("Management Command Center"), "blue");
		this.page.add_inner_button(__("Refresh"), () => this.refresh(true), __("Actions"));
		this.$root = $(`<div class="itsm-command-center"></div>`).appendTo(this.page.main);
		this.make_header();
		this.make_tabs();
		this.$content = $(`<div class="itsm-dashboard-content"></div>`).appendTo(this.$root);
	}

	make_header() {
		this.$header = $(`
			<div class="itsm-hero">
				<div>
					<div class="itsm-eyebrow">${__("ERPNext Command Center")}</div>
					<h2>${__("IT Service Management")}</h2>
					<p>${__("Management Command Center")}</p>
				</div>
				<div class="itsm-filter-grid"></div>
			</div>
		`).appendTo(this.$root);
		this.$filters = this.$header.find(".itsm-filter-grid");
		this.make_filters();
	}

	make_filters() {
		this.controls = {};
		this.controls.company = this.add_control("Link", "Company", "company", { options: "Company" });
		this.controls.customer = this.add_control("Link", "Customer", "customer", { options: "Customer" });
		this.controls.service_zone = this.add_control("Link", "Service Zone", "service_zone", { options: "Service Zone" });
		this.controls.period = this.add_control("Select", "Date Range", "period", {
			options: ["Today", "This Week", "This Month", "This Quarter", "This Fiscal Year", "Last 30 Days", "Last 90 Days", "Custom"].join("\n"),
			default: "This Month",
		});
		this.controls.from_date = this.add_control("Date", "From", "from_date");
		this.controls.to_date = this.add_control("Date", "To", "to_date");
	}

	add_control(fieldtype, label, key, opts = {}) {
		const control = frappe.ui.form.make_control({
			parent: this.$filters,
			df: {
				fieldtype,
				label: __(label),
				fieldname: key,
				onchange: () => {
					this.filters[key] = control.get_value();
					this.refresh();
				},
				...opts,
			},
			render_input: true,
		});
		if (opts.default) {
			control.set_value(opts.default);
		}
		return control;
	}

	make_tabs() {
		this.$tabs = $(`<div class="itsm-tabs" role="tablist"></div>`).appendTo(this.$root);
		this.tabs.forEach((tab) => {
			const $tab = $(`<button class="itsm-tab" role="tab" data-tab="${tab}">${__(frappe.model.unscrub(tab))}</button>`);
			$tab.on("click", () => {
				this.active_tab = tab;
				this.$tabs.find(".itsm-tab").removeClass("active");
				$tab.addClass("active");
				this.refresh();
			});
			this.$tabs.append($tab);
		});
		this.$tabs.find('[data-tab="overview"]').addClass("active");
	}

	load_options() {
		frappe.call({
			method: "it_service_management.it_service_management.page.it_service_command_center.it_service_command_center.get_options",
			callback: (r) => {
				if (r.message && r.message.default_period) {
					this.controls.period.set_value(r.message.default_period);
				}
			},
		});
	}

	refresh(force = false) {
		this.collect_filters();
		this.render_loading();
		frappe.call({
			method: "it_service_management.it_service_management.page.it_service_command_center.it_service_command_center.get_dashboard",
			args: {
				tab: this.active_tab,
				filters: this.filters,
				force_refresh: force ? 1 : 0,
			},
			freeze: false,
			callback: (r) => {
				this.payload = r.message || {};
				this.currency = this.payload.company_currency || this.currency;
				this.render();
			},
			error: () => this.render_error(__("Unable to load dashboard data.")),
		});
	}

	collect_filters() {
		Object.keys(this.controls || {}).forEach((key) => {
			this.filters[key] = this.controls[key].get_value();
		});
	}

	render_loading() {
		this.$content.html(`
			<div class="itsm-skeleton-grid">
				${Array.from({ length: 6 }).map(() => `<div class="itsm-skeleton-card"></div>`).join("")}
			</div>
			<div class="itsm-skeleton-wide"></div>
		`);
	}

	render_error(message) {
		this.$content.html(`
			<div class="itsm-empty-state">
				<h3>${message}</h3>
				<button class="btn btn-primary btn-sm">${__("Refresh")}</button>
			</div>
		`);
		this.$content.find("button").on("click", () => this.refresh(true));
	}

	render() {
		const sections = this.payload.sections || {};
		this.$content.empty();
		this.render_meta();
		this.render_kpis(sections.kpis || [], "primary");
		if (sections.secondary_kpis) this.render_kpis(sections.secondary_kpis, "secondary");
		this.render_alerts(sections.alerts || []);
		this.render_charts(sections.charts || {});
		this.render_blocks(sections.blocks || {});
		this.render_tables(sections.tables || {});
	}

	render_meta() {
		$(`
			<div class="itsm-meta-row">
				<span>${__("Company")}: ${frappe.utils.escape_html(this.filters.company || __("All"))}</span>
				<span>${__("Period")}: ${frappe.utils.escape_html(this.payload.filters?.period || this.filters.period || "")}</span>
				<span>${__("Last refreshed")}: ${frappe.utils.escape_html(this.payload.last_refreshed || "")}</span>
			</div>
		`).appendTo(this.$content);
	}

	render_kpis(kpis, density) {
		const $grid = $(`<div class="itsm-kpi-grid ${density === "secondary" ? "compact" : ""}"></div>`).appendTo(this.$content);
		kpis.forEach((item) => {
			const trend = item.trend ? `<span class="itsm-trend ${item.trend.direction}">${item.trend.direction === "up" ? "Up" : "Down"} ${item.trend.percent}%</span>` : "";
			const $card = $(`
				<button class="itsm-kpi-card ${item.status || "normal"}" type="button">
					<span class="itsm-kpi-title">${frappe.utils.escape_html(item.title)}</span>
					<strong>${this.format_value(item.value, item.kind)}</strong>
					<span class="itsm-kpi-context">${frappe.utils.escape_html(item.context || "")}${trend}</span>
				</button>
			`);
			$card.on("click", () => this.open_route(item.route));
			$grid.append($card);
		});
	}

	render_alerts(alerts) {
		const $panel = $(`<section class="itsm-panel"><div class="itsm-section-head"><h3>${__("Requires Attention")}</h3></div></section>`).appendTo(this.$content);
		if (!alerts.length) {
			$panel.append(`<div class="itsm-empty-line">${__("No management exceptions for the selected filters.")}</div>`);
			return;
		}
		const $list = $(`<div class="itsm-alert-list"></div>`).appendTo($panel);
		alerts.forEach((item) => {
			const $alert = $(`
				<button class="itsm-alert ${item.severity}" type="button">
					<span class="itsm-dot"></span>
					<span>${frappe.utils.escape_html(item.title)}</span>
					${item.amount ? `<strong>${this.format_value(item.amount, "currency")}</strong>` : ""}
				</button>
			`);
			$alert.on("click", () => this.open_route(item.route));
			$list.append($alert);
		});
	}

	render_charts(charts) {
		const entries = Object.entries(charts);
		if (!entries.length) return;
		const $grid = $(`<div class="itsm-chart-grid"></div>`).appendTo(this.$content);
		entries.forEach(([key, chart]) => {
			const $panel = $(`<section class="itsm-panel"><div class="itsm-section-head"><h3>${frappe.utils.escape_html(chart.title || frappe.model.unscrub(key))}</h3></div><div class="itsm-chart" id="itsm-chart-${key}"></div></section>`);
			$grid.append($panel);
			this.make_chart($panel.find(".itsm-chart")[0], chart);
		});
	}

	make_chart(element, chart) {
		const has_data = (chart.values || []).some((value) => cint(value)) || (chart.datasets || []).some((row) => (row.values || []).some((value) => cint(value)));
		if (!has_data) {
			$(element).html(`<div class="itsm-empty-line">${__("No data for this period.")}</div>`);
			return;
		}
		new frappe.Chart(element, {
			data: {
				labels: chart.labels || [],
				datasets: chart.datasets || [{ name: chart.title || __("Value"), values: chart.values || [] }],
			},
			type: chart.type === "donut" ? "donut" : chart.type || "bar",
			height: 260,
			colors: ["#2563eb", "#14b8a6", "#7c3aed", "#f59e0b", "#ef4444", "#64748b"],
			axisOptions: { xAxisMode: "tick", yAxisMode: "tick", xIsSeries: 1 },
			tooltipOptions: { formatTooltipY: (value) => this.format_value(value, "currency") },
		});
	}

	render_blocks(blocks) {
		const $grid = $(`<div class="itsm-block-grid"></div>`).appendTo(this.$content);
		if (blocks.sla) this.render_sla($grid, blocks.sla);
		if (blocks.pipeline) this.render_pipeline($grid, blocks.pipeline);
		if (blocks.technicians) this.render_technicians($grid, blocks.technicians);
		if (blocks.billing) this.render_billing($grid, blocks.billing);
		if (blocks.profitability) this.render_profitability($grid, blocks.profitability);
		if (blocks.meter) this.render_meter($grid, blocks.meter);
		if (blocks.receivables) this.render_receivables($grid, blocks.receivables);
	}

	render_sla($grid, sla) {
		$grid.append(`
			<section class="itsm-panel">
				<div class="itsm-section-head"><h3>${__("SLA Health")}</h3><button class="btn btn-xs btn-default itsm-route">${__("View Report")}</button></div>
				<div class="itsm-big-percent">${flt(sla.compliance, 1)}%</div>
				<div class="itsm-progress"><span style="width:${Math.min(flt(sla.compliance), 100)}%"></span></div>
				<div class="itsm-mini-stats">
					<span>${__("Within SLA")} <strong>${cint(sla.within)}</strong></span>
					<span>${__("At Risk")} <strong>${cint(sla.at_risk)}</strong></span>
					<span>${__("Breached")} <strong>${cint(sla.breached)}</strong></span>
					<span>${__("Response")} <strong>${flt(sla.response, 1)}%</strong></span>
					<span>${__("Resolution")} <strong>${flt(sla.resolution, 1)}%</strong></span>
				</div>
			</section>
		`);
		$grid.find(".itsm-route").last().on("click", () => this.open_route(sla.route));
	}

	render_pipeline($grid, rows) {
		const $panel = $(`<section class="itsm-panel wide"><div class="itsm-section-head"><h3>${__("Service Job Pipeline")}</h3></div><div class="itsm-pipeline"></div></section>`).appendTo($grid);
		rows.forEach((row) => {
			const $stage = $(`<button class="itsm-stage" type="button"><span>${frappe.utils.escape_html(row.label)}</span><strong>${cint(row.value)}</strong></button>`);
			$stage.on("click", () => this.open_route(row.route));
			$panel.find(".itsm-pipeline").append($stage);
		});
	}

	render_technicians($grid, rows) {
		const $panel = $(`<section class="itsm-panel"><div class="itsm-section-head"><h3>${__("Technician Workload")}</h3></div></section>`).appendTo($grid);
		if (!rows.length) return $panel.append(`<div class="itsm-empty-line">${__("No active technician workload.")}</div>`);
		rows.forEach((row) => {
			const load = Math.min(flt(row.load), 140);
			$panel.append(`
				<div class="itsm-workload-row">
					<div><strong>${frappe.utils.escape_html(row.technician || __("Unassigned"))}</strong><span>${cint(row.jobs)} ${__("jobs")} - ${flt(row.hours, 1)} ${__("hrs")}</span></div>
					<div class="itsm-capacity"><span style="width:${load}%"></span></div>
					<em>${frappe.utils.escape_html(row.status || "")}</em>
				</div>
			`);
		});
	}

	render_billing($grid, billing) {
		this.render_metric_panel($grid, __("Billing & Revenue Control"), [
			["Completed Service Not Billed", billing.completed_service_not_billed, "currency"],
			["Rental Billing Pending", billing.rental_billing_pending, "currency"],
			["Meter Charges Unbilled", billing.meter_charges_unbilled, "currency"],
			["Approved Expenses Not Recharged", billing.approved_expenses_not_recharged, "currency"],
			["Estimated Revenue Leakage", billing.estimated_revenue_leakage, "currency"],
		], billing.route);
	}

	render_profitability($grid, p) {
		this.render_metric_panel($grid, __("Operational Profitability"), [
			["Service Contribution", p.service_contribution, "currency"],
			["Service Margin", p.service_margin, "percent"],
			["Rental Contribution", p.rental_contribution, "currency"],
			["Rental Margin", p.rental_margin, "percent"],
			["AMC Contribution", p.amc_contribution, "currency"],
		]);
	}

	render_meter($grid, meter) {
		this.render_metric_panel($grid, __("Meter Billing"), [
			["Metered Devices", meter.expected, "number"],
			["Readings Received", meter.received, "number"],
			["Pending", meter.pending, "number"],
			["Expected Meter Revenue", meter.expected_revenue, "currency"],
			["Unbilled", meter.unbilled, "currency"],
		], meter.route);
	}

	render_receivables($grid, receivables) {
		this.render_metric_panel($grid, __("Service & Rental Receivables"), [["Outstanding", receivables.total, "currency"], ...(receivables.buckets || []).map((row) => [row.label, row.value, "currency"])], receivables.route);
	}

	render_metric_panel($grid, title, metrics, route) {
		const $panel = $(`<section class="itsm-panel"><div class="itsm-section-head"><h3>${title}</h3>${route ? `<button class="btn btn-xs btn-default">${__("View")}</button>` : ""}</div><div class="itsm-metric-list"></div></section>`).appendTo($grid);
		metrics.forEach(([label, value, kind]) => {
			$panel.find(".itsm-metric-list").append(`<div><span>${__(label)}</span><strong>${this.format_value(value, kind)}</strong></div>`);
		});
		if (route) $panel.find("button").on("click", () => this.open_route(route));
	}

	render_tables(tables) {
		Object.entries(tables).forEach(([key, rows]) => {
			const title = frappe.model.unscrub(key);
			const $panel = $(`<section class="itsm-panel wide"><div class="itsm-section-head"><h3>${__(title)}</h3></div></section>`).appendTo(this.$content);
			if (!rows || !rows.length) {
				$panel.append(`<div class="itsm-empty-line">${__("No records to show.")}</div>`);
				return;
			}
			const keys = Object.keys(rows[0]).filter((name) => name !== "route");
			const $table = $(`<div class="itsm-table-wrap"><table class="table table-sm"><thead><tr>${keys.map((name) => `<th>${__(frappe.model.unscrub(name))}</th>`).join("")}</tr></thead><tbody></tbody></table></div>`);
			rows.forEach((row) => {
				const $tr = $(`<tr>${keys.map((name) => `<td>${this.cell_value(row[name])}</td>`).join("")}</tr>`);
				$tr.on("click", () => this.open_route(row.route));
				$table.find("tbody").append($tr);
			});
			$panel.append($table);
		});
	}

	cell_value(value) {
		if (value === null || value === undefined) return "";
		return frappe.utils.escape_html(String(value));
	}

	format_value(value, kind) {
		if (kind === "currency") return format_currency(value || 0, this.currency);
		if (kind === "percent") return `${flt(value || 0, 1)}%`;
		return frappe.format(value || 0, { fieldtype: "Int" });
	}

	open_route(route) {
		if (!route) return;
		if (route.type === "doctype") {
			frappe.set_route("List", route.doctype, route.filters || {});
		} else if (route.type === "report") {
			frappe.set_route("query-report", route.report, route.filters || {});
		}
	}
}
