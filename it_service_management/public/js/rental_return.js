frappe.ui.form.on("Rental Return", {
	refresh(frm) {
		if (!frm.is_new() && ["Draft", "Scheduled", "In Progress"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Complete Return"), () => frm.call("complete_return").then(() => frm.refresh()));
		}
	},
});
