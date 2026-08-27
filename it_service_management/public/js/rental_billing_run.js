frappe.ui.form.on("Rental Billing Run", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (["Draft", "Prepared", "Completed With Errors"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Prepare Billing"), () => frm.call("prepare_billing", { background: 1 }).then(() => frm.refresh()));
		}
		if (frm.doc.status === "Prepared") {
			frm.add_custom_button(__("Submit for Review"), () => frm.call("submit_for_review").then(() => frm.refresh()));
		}
		if (["Prepared", "Under Review", "Completed With Errors"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Approve for Billing"), () => frm.call("approve_for_billing").then(() => frm.refresh()));
		}
		if (["Prepared", "Approved for Billing", "Completed With Errors"].includes(frm.doc.status) && (frm.doc.components || []).length) {
			frm.add_custom_button(__("Generate Draft Sales Invoices"), () => frm.call("generate_draft_sales_invoices", { background: 1 }).then(() => frm.refresh()));
		}
	},
});
