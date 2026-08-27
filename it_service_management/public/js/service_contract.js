frappe.ui.form.on("Service Contract", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Recalculate Entitlements"), () => {
				frm.call("recalculate_entitlements").then(() => frm.reload_doc());
			});
			const invoice_filters = frm.doc.subscription ? { subscription: frm.doc.subscription } : { name: frm.doc.sales_invoice || "" };
			frm.add_custom_button(__("Invoices"), () => frappe.set_route("List", "Sales Invoice", invoice_filters), __("View"));
			frm.add_custom_button(__("Outstanding Invoices"), () => frappe.set_route("List", "Sales Invoice", { ...invoice_filters, docstatus: 1, outstanding_amount: [">", 0] }), __("View"));
			frm.add_custom_button(__("Payments"), () => frappe.set_route("List", "Payment Entry", { party_type: "Customer", party: frm.doc.customer, payment_type: "Receive" }), __("View"));
			frm.add_custom_button(__("Renewal Opportunities"), () => frappe.set_route("List", "Contract Renewal Opportunity", { service_contract: frm.doc.name }), __("View"));
		}
	},
});
