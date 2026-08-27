frappe.ui.form.on("Rental Contract", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Invoices"), () => frappe.set_route("List", "Sales Invoice", { custom_rental_contract: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Outstanding Invoices"), () => frappe.set_route("List", "Sales Invoice", { custom_rental_contract: frm.doc.name, docstatus: 1, outstanding_amount: [">", 0] }), __("View"));
		frm.add_custom_button(__("Payments"), () => frappe.set_route("List", "Payment Entry", { party_type: "Customer", party: frm.doc.customer, payment_type: "Receive" }), __("View"));
		frm.add_custom_button(__("Renewal Opportunities"), () => frappe.set_route("List", "Contract Renewal Opportunity", { rental_contract: frm.doc.name }), __("View"));
		if (["Approved", "Active", "Expiring"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Create Deployment"), () => frm.call("create_deployment").then((r) => frappe.set_route("Form", "Rental Deployment", r.message)));
		}
		if (frm.doc.use_erpnext_subscription && !frm.doc.subscription) {
			frm.add_custom_button(__("Create Subscription"), () => frm.call("create_subscription").then(() => frm.refresh()), __("Create"));
		}
		if (["Active", "Expiring", "Expired", "Terminated"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Create Renewal"), () => frm.call("create_renewal").then((r) => frappe.set_route("Form", "Rental Contract", r.message)), __("Create"));
		}
		if (["Active", "Suspended", "Expiring"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Request Termination"), () => {
				frappe.prompt([
					{ fieldname: "requested_end_date", fieldtype: "Date", label: __("Requested End Date"), reqd: 1 },
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
				], (values) => frm.call("request_termination", values).then(() => frm.refresh()), __("Request Termination"));
			});
		}
	},
});
