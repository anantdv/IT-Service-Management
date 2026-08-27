frappe.ui.form.on("Service Billing Batch", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (["Draft", "Prepared", "Completed With Errors"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Prepare Billing"), () =>
				frm.call("prepare_billing", { background: 1 }).then(() => frm.refresh())
			);
		}
		if (frm.doc.status === "Prepared") {
			frm.add_custom_button(__("Submit for Review"), () => frm.call("submit_for_review").then(() => frm.refresh()));
		}
		if (["Prepared", "Under Review", "Completed With Errors"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Approve for Billing"), () => frm.call("approve_for_billing").then(() => frm.refresh()));
		}
		if (["Prepared", "Approved for Billing", "Completed With Errors"].includes(frm.doc.status) && (frm.doc.details || []).length) {
			frm.add_custom_button(__("Generate Draft Sales Invoices"), () =>
				frm.call("generate_draft_sales_invoices", { background: 1 }).then(() => frm.refresh())
			);
		}
		if ((frm.doc.details || []).length) {
			frm.add_custom_button(__("Review Charges"), () => {
				frm.call("get_review_charges").then(({ message }) => {
					const dialog = new frappe.ui.Dialog({
						title: __("Billing Source Review"),
						size: "extra-large",
						fields: [{
							fieldname: "charges", fieldtype: "Table", label: __("Charges"), cannot_add_rows: true, cannot_delete_rows: true,
							fields: [
								{ fieldname: "service_job", fieldtype: "Link", options: "Service Job", label: __("Service Job"), in_list_view: 1, read_only: 1 },
								{ fieldname: "source_type", fieldtype: "Data", label: __("Source Type"), in_list_view: 1, read_only: 1 },
								{ fieldname: "source_document", fieldtype: "Data", label: __("Source"), in_list_view: 1, read_only: 1 },
								{ fieldname: "charge_type", fieldtype: "Data", label: __("Charge Type"), in_list_view: 1, read_only: 1 },
								{ fieldname: "amount", fieldtype: "Currency", label: __("Charge"), in_list_view: 1, read_only: 1 },
								{ fieldname: "covered", fieldtype: "Check", label: __("Covered"), in_list_view: 1, read_only: 1 },
								{ fieldname: "billable_amount", fieldtype: "Currency", label: __("Billable"), in_list_view: 1, read_only: 1 },
							],
						}],
					});
					dialog.fields_dict.charges.df.data = message || [];
					dialog.fields_dict.charges.grid.refresh();
					dialog.show();
				});
			});
		}
	},
});
