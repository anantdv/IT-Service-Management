frappe.ui.form.on("Contract Renewal Opportunity", {
	refresh(frm) {
		if (!frm.is_new() && !frm.doc.renewed_contract && !["Lost", "Not Renewing"].includes(frm.doc.renewal_stage)) {
			frm.add_custom_button(__("Create Renewal Contract"), () => {
				frm.call("create_renewal_contract").then(({ message }) => {
					if (message) frappe.set_route("Form", message.doctype, message.name);
				});
			});
		}
	},
});
