frappe.ui.form.on("Service Expense", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.approval_status === "Approved" && !frm.doc.expense_claim) {
			frm.add_custom_button(__("Create Expense Claim"), () => frm.call("create_expense_claim").then(() => frm.refresh()));
		}
	},
	quantity(frm) {
		frm.set_value("amount", (frm.doc.quantity || 0) * (frm.doc.rate || 0));
	},
	rate(frm) {
		frm.set_value("amount", (frm.doc.quantity || 0) * (frm.doc.rate || 0));
	},
});
