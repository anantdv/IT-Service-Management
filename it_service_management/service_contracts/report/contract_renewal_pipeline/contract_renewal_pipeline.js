frappe.query_reports["Contract Renewal Pipeline"] = {
	filters: [
		{ fieldname: "renewal_type", label: __("Contract Type"), fieldtype: "Select", options: "\nService Contract\nRental Contract" },
		{ fieldname: "renewal_stage", label: __("Renewal Stage"), fieldtype: "Select", options: "\nIdentified\nReview Required\nContact Customer\nProposal Required\nProposal Sent\nNegotiation\nCustomer Approved" },
		{ fieldname: "assigned_to", label: __("Assigned To"), fieldtype: "Link", options: "User" },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
	],
};
