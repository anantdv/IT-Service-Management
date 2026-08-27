frappe.query_reports["Rental Equipment Profitability"] = {
	filters: [
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "rental_contract", label: __("Rental Contract"), fieldtype: "Link", options: "Rental Contract" },
		{ fieldname: "customer_equipment", label: __("Customer Equipment"), fieldtype: "Link", options: "Customer Equipment" },
	],
};
