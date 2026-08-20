frappe.ui.form.on("Service Contract", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Recalculate Entitlements"), () => {
				frm.call("recalculate_entitlements").then(() => frm.reload_doc());
			});
		}
	},
});
