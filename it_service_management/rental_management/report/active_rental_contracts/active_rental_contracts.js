frappe.query_reports["Active Rental Contracts"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "rental_contract", label: __("Rental Contract"), fieldtype: "Link", options: "Rental Contract" },
		{ fieldname: "customer_site", label: __("Customer Site"), fieldtype: "Link", options: "Customer Site" },
	],
};
