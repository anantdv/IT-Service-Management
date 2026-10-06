(function () {
	const TARGET_ROUTE = "it-service-management";
	const TARGET_LABEL = "IT Service Management";

	function is_itsm_workspace() {
		const route = frappe.get_route ? frappe.get_route() : [];
		return route.includes(TARGET_ROUTE) || route.includes(TARGET_LABEL);
	}

	function apply_workspace_theme() {
		const active = is_itsm_workspace();
		document.body.classList.toggle("itsm-workspace-modern", active);
		if (!active) return;

		const $main = $(".layout-main-section");
		if (!$main.length || $main.find(".itsm-workspace-hero").length) return;

		$main.prepend(`
			<section class="itsm-workspace-hero">
				<div>
					<div class="itsm-workspace-eyebrow">${__("Enterprise ITSM")}</div>
					<h1>${__("IT Service Management")}</h1>
					<p>${__("Service desk, incidents, field operations, contracts, equipment, billing, and executive control in one operating hub.")}</p>
				</div>
				<div class="itsm-workspace-actions">
					<button class="btn btn-primary btn-sm itsm-open-command">${__("Command Center")}</button>
					<button class="btn btn-default btn-sm itsm-open-desk">${__("Service Desk")}</button>
					<button class="btn btn-default btn-sm itsm-new-ticket">${__("New Ticket")}</button>
				</div>
			</section>
		`);

		$main.find(".itsm-open-command").on("click", () => frappe.set_route("it-service-command-center"));
		$main.find(".itsm-open-desk").on("click", () => frappe.set_route("itsm-service-desk"));
		$main.find(".itsm-new-ticket").on("click", () => frappe.new_doc("Service Ticket"));
	}

	frappe.router.on("change", () => {
		setTimeout(apply_workspace_theme, 150);
	});

	$(document).on("page-change", () => {
		setTimeout(apply_workspace_theme, 150);
	});
})();
