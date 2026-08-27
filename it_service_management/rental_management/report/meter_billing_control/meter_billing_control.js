frappe.query_reports["Meter Billing Control"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "from_date", label: __("Billing Period From"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("Billing Period To"), fieldtype: "Date", default: frappe.datetime.month_end(), reqd: 1 },
	],
};
