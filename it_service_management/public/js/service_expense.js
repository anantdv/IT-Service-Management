const SERVICE_EXPENSE_UOM = {
	Transportation: "Trip",
	Mileage: "KM",
	Airfare: "Ticket",
	Taxi: "Trip",
	Accommodation: "Night",
	Food: "Day",
	Freight: "Shipment",
	Parking: "Day",
	Communication: "Each",
	Other: "Each",
};

frappe.ui.form.on("Service Expense", {
	refresh(frm) {
		set_field_visibility(frm);
		if (
			!frm.is_new()
			&& frm.doc.approval_status === "Approved"
			&& frm.doc.reimbursable_to_employee
			&& frm.doc.paid_by === "Employee"
			&& !frm.doc.expense_claim
		) {
			frm.add_custom_button(__("Create Expense Claim"), () => frm.call("create_expense_claim").then(() => frm.refresh()));
		}
	},
	service_job(frm) {
		if (!frm.doc.service_job) {
			return;
		}
		frm.call("populate_from_service_job").then((result) => {
			if (!result.message) {
				return;
			}
			for (const [fieldname, value] of Object.entries(result.message)) {
				frm.set_value(fieldname, value);
			}
		});
	},
	expense_type(frm) {
		if (frm.doc.expense_type && !frm.doc.uom && SERVICE_EXPENSE_UOM[frm.doc.expense_type]) {
			frm.set_value("uom", SERVICE_EXPENSE_UOM[frm.doc.expense_type]);
		}
	},
	quantity(frm) {
		update_actual_amount(frm);
	},
	rate(frm) {
		update_actual_amount(frm);
	},
	paid_by(frm) {
		if (frm.doc.paid_by === "Employee") {
			frm.set_value("reimbursable_to_employee", 1);
			frm.set_value("employee_claimed_amount", frm.doc.actual_expense_amount || frm.doc.amount || 0);
			frm.set_value("approved_reimbursement_amount", frm.doc.employee_claimed_amount || frm.doc.actual_expense_amount || frm.doc.amount || 0);
		} else if (["Company", "Company Credit Card", "Customer Direct"].includes(frm.doc.paid_by)) {
			frm.set_value("reimbursable_to_employee", 0);
			frm.set_value("employee_claimed_amount", 0);
			frm.set_value("approved_reimbursement_amount", 0);
		}
		set_field_visibility(frm);
	},
	reimbursable_to_employee(frm) {
		if (!frm.doc.reimbursable_to_employee) {
			frm.set_value("employee_claimed_amount", 0);
			frm.set_value("approved_reimbursement_amount", 0);
		} else if (frm.doc.paid_by === "Employee") {
			frm.set_value("employee_claimed_amount", frm.doc.employee_claimed_amount || frm.doc.actual_expense_amount || 0);
			frm.set_value("approved_reimbursement_amount", frm.doc.approved_reimbursement_amount || frm.doc.employee_claimed_amount || frm.doc.actual_expense_amount || 0);
		}
		set_field_visibility(frm);
	},
	customer_billing_method(frm) {
		set_field_visibility(frm);
	},
});

function update_actual_amount(frm) {
	const amount = flt(frm.doc.quantity) * flt(frm.doc.rate);
	frm.set_value("actual_expense_amount", amount);
	frm.set_value("amount", amount);
	if (frm.doc.paid_by === "Employee" && frm.doc.reimbursable_to_employee && !flt(frm.doc.employee_claimed_amount)) {
		frm.set_value("employee_claimed_amount", amount);
	}
}

function set_field_visibility(frm) {
	const reimbursable = Boolean(frm.doc.reimbursable_to_employee);
	frm.toggle_display("employee_claimed_amount", reimbursable);
	frm.toggle_display("approved_reimbursement_amount", reimbursable);

	const billable = frm.doc.customer_billing_method && frm.doc.customer_billing_method !== "Not Billable";
	frm.toggle_display("customer_billing_quantity", billable);
	frm.toggle_display("customer_billing_rate", billable);
	frm.toggle_display("billing_rule_source", billable);
	frm.toggle_display("billing_rule_reference", billable);
}
