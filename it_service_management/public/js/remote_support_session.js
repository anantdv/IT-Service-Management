frappe.ui.form.on("Remote Support Session", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.onsite_required && !frm.doc.service_job) {
			frm.add_custom_button(__("Create Service Job"), () => {
				frm.call("create_service_job").then((r) => {
					if (r.message) frappe.set_route("Form", "Service Job", r.message);
				});
			});
		}
	},
});
