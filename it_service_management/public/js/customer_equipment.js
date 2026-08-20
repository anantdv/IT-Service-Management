frappe.ui.form.on("Customer Equipment", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Service Contract"), () => {
				frappe.set_route("List", "Service Contract", {
					customer: frm.doc.customer,
				});
			}, __("View"));
		}
	},
});
