frappe.ui.form.on("Rental Equipment Replacement", {
	refresh(frm) {
		if (!frm.is_new() && ["Draft", "Scheduled"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Complete Replacement"), () => frm.call("complete_replacement").then(() => frm.refresh()));
		}
	},
});
