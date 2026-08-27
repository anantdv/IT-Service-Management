frappe.ui.form.on("Rental Deployment", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.installation_required && !frm.doc.service_job) {
			frm.add_custom_button(__("Create Installation Job"), () => frm.call("create_installation_job").then((r) => frappe.set_route("Form", "Service Job", r.message)), __("Create"));
		}
		if (["Scheduled", "In Progress"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Complete Deployment"), () => frm.call("complete_deployment").then(() => frm.refresh()));
		}
	},
});
