import frappe


def execute():
	indexes = (
		("Service Job", ["status", "billing_status", "completion_datetime"], "service_job_billing_completion"),
		("Service Job", ["service_contract", "status", "completion_datetime"], "service_job_contract_completion"),
		("Service Job", ["rental_contract", "status", "completion_datetime"], "service_job_rental_completion"),
		("Service Job", ["customer_equipment", "completion_datetime"], "service_job_equipment_completion"),
		("Service Billing Reference", ["service_job", "status"], "service_billing_job_status"),
		("Service Billing Reference", ["invoice", "status"], "service_billing_invoice_status"),
		("Service Billing Reference", ["billing_batch", "status"], "service_billing_batch_status"),
		("Service Billing Adjustment", ["service_job", "approval_status"], "service_adjustment_job_approval"),
		("Contract Renewal Opportunity", ["service_contract", "status"], "renewal_service_contract_status"),
		("Contract Renewal Opportunity", ["rental_contract", "status"], "renewal_rental_contract_status"),
		("Contract Renewal Opportunity", ["status", "current_end_date", "renewal_stage"], "renewal_status_expiry_stage"),
	)
	for doctype, fields, name in indexes:
		if frappe.db.exists("DocType", doctype):
			frappe.db.add_index(doctype, fields, index_name=name)
