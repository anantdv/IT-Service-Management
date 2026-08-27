frappe.ui.form.on("Customer Equipment", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Service Contract"), () => {
				frappe.set_route("List", "Service Contract", {
					customer: frm.doc.customer,
				});
			}, __("View"));
			frm.add_custom_button(__("Service Jobs"), () => frappe.set_route("List", "Service Job", { customer_equipment: frm.doc.name }), __("View"));
			frm.add_custom_button(__("Service Tickets"), () => frappe.set_route("List", "Service Ticket", { customer_equipment: frm.doc.name }), __("View"));
			frm.add_custom_button(__("Meter Readings"), () => frappe.set_route("List", "Equipment Meter Reading", { customer_equipment: frm.doc.name }), __("View"));
			frm.add_custom_button(__("Invoices"), () => frappe.set_route("List", "Sales Invoice", { custom_customer_equipment: frm.doc.name }), __("View"));
		}
	},
});
