frappe.ui.form.on("Service Part Request", {
	refresh(frm) {
		if (!frm.is_new() && ["Approved", "Partially Issued"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Create Stock Entry"), () => frm.call("create_stock_entry").then(() => frm.refresh()));
		}
	},
});
