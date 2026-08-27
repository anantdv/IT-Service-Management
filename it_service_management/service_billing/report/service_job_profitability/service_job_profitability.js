frappe.query_reports["Service Job Profitability"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.year_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "technician", label: __("Technician"), fieldtype: "Link", options: "Employee" },
		{ fieldname: "service_team", label: __("Service Team"), fieldtype: "Link", options: "Service Team" },
		{ fieldname: "service_contract", label: __("Contract"), fieldtype: "Link", options: "Service Contract" },
		{ fieldname: "customer_equipment", label: __("Equipment"), fieldtype: "Link", options: "Customer Equipment" },
		{ fieldname: "job_type", label: __("Job Type"), fieldtype: "Data" },
		{ fieldname: "coverage_source", label: __("Coverage Source"), fieldtype: "Data" },
	],
};
