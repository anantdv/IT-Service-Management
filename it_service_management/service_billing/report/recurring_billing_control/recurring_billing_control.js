frappe.query_reports["Recurring Billing Control"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("Billing Period From"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("Billing Period To"), fieldtype: "Date", default: frappe.datetime.month_end(), reqd: 1 },
		{ fieldname: "contract_type", label: __("Contract Type"), fieldtype: "Select", options: "\nService Contract\nRental Contract" },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
	],
};
