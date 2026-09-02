app_name = "it_service_management"
app_title = "IT Service Management"
app_publisher = "IT Service Management"
app_description = "Equipment lifecycle, service contracts, and field service for ERPNext"
app_email = "support@example.com"
app_license = "MIT"

required_apps = ["frappe", "erpnext"]

after_install = "it_service_management.install.after_install"
after_migrate = "it_service_management.install.after_migrate"

add_to_apps_screen = [
	{
		"name": "it_service_management",
		"logo": "/assets/it_service_management/images/it-service-management.svg",
		"title": "IT Service Management",
		"route": "/app/it-service-management",
		"has_permission": "it_service_management.install.has_app_permission",
	}
]

fixtures = [
	{"dt": "Role", "filters": [["role_name", "in", [
		"Service Manager",
		"Service Dispatcher",
		"Service Engineer",
		"Service Technician",
		"Service Billing User",
		"Service Contract Manager",
		"Rental Manager",
		"Rental User",
		"Rental Billing User",
		"Service Auditor",
		"IT Service Analyst",
		"IT Service Executive",
	]]]},
	{"dt": "Workspace", "filters": [["name", "in", ["IT Service Management", "Service Operations", "Rental Management", "Service Command Center", "Rental Command Center", "IT Services Executive"]]]},
	{"dt": "Number Card", "filters": [["module", "=", "IT Service Management"]]},
	{"dt": "Dashboard Chart", "filters": [["module", "=", "IT Service Management"]]},
	{"dt": "Custom Field", "filters": [["dt", "in", ["Employee", "Sales Invoice"]], ["module", "=", "IT Service Management"]]},
	{"dt": "Workflow", "filters": [["name", "in", ["Rental Contract Approval", "Rental Ad-Hoc Charge Approval", "Service Billing Adjustment Approval"]]]},
	{"dt": "Workflow State", "filters": [["workflow_state_name", "in", ["Draft", "Pending Approval", "Approved", "Active", "Suspended", "Expiring", "Expired", "Termination Requested", "Terminated", "Completed", "Cancelled", "Rejected", "Billed"]]]},
	{"dt": "Workflow Action Master", "filters": [["workflow_action_name", "in", ["Request Approval", "Approve", "Activate", "Suspend", "Resume", "Request Termination", "Terminate", "Complete", "Reject", "Cancel"]]]},
	{"dt": "Notification", "filters": [["name", "in", ["Rental Contract Approved", "Rental Contract Activated", "Rental Termination Requested", "Rental Deployment Scheduled", "Rental Deployment Completed", "Rental Billing Run Ready", "Rental Billing Run Error"]]]},
	{"dt": "Custom DocPerm", "filters": [["parent", "in", ["Asset", "Subscription"]], ["role", "in", ["Rental Manager", "Rental User", "Rental Billing User"]]]},
]

doctype_js = {
	"Customer Equipment": "public/js/customer_equipment.js",
	"Service Contract": "public/js/service_contract.js",
	"Service Ticket": "public/js/service_ticket.js",
	"Service Job": "public/js/service_job.js",
	"Remote Support Session": "public/js/remote_support_session.js",
	"Service Expense": "public/js/service_expense.js",
	"Service Part Request": "public/js/service_part_request.js",
	"Rental Contract": "public/js/rental_contract.js",
	"Rental Deployment": "public/js/rental_deployment.js",
	"Equipment Meter Reading": "public/js/equipment_meter_reading.js",
	"Rental Billing Run": "public/js/rental_billing_run.js",
	"Rental Equipment Replacement": "public/js/rental_equipment_replacement.js",
	"Rental Return": "public/js/rental_return.js",
	"Service Billing Batch": "public/js/service_billing_batch.js",
	"Contract Renewal Opportunity": "public/js/contract_renewal_opportunity.js",
}

doc_events = {
	"Delivery Note": {
		"on_submit": "it_service_management.equipment_management.doctype.customer_equipment.customer_equipment.create_from_delivery_note",
	},
	"Sales Invoice": {
		"on_submit": [
			"it_service_management.equipment_management.doctype.customer_equipment.customer_equipment.update_from_sales_invoice",
			"it_service_management.rental_management.services.billing.handle_invoice_submitted",
			"it_service_management.service_billing.services.batch.handle_invoice_submitted",
		],
		"on_cancel": [
			"it_service_management.rental_management.services.billing.handle_invoice_cancelled",
			"it_service_management.service_billing.services.batch.handle_invoice_cancelled",
		],
		"on_trash": [
			"it_service_management.rental_management.services.billing.handle_invoice_deleted",
			"it_service_management.service_billing.services.batch.handle_invoice_deleted",
		],
	},
}

scheduler_events = {
	"hourly": [
		"it_service_management.service_operations.services.notifications.evaluate_active_ticket_slas",
	],
	"daily": [
		"it_service_management.service_contracts.doctype.service_contract.service_contract.update_contract_statuses",
		"it_service_management.service_contracts.doctype.service_contract.service_contract.send_contract_expiry_notifications",
		"it_service_management.rental_management.services.scheduler.run_daily_rental_checks",
		"it_service_management.service_contracts.services.renewal.create_renewal_opportunities",
	],
	"monthly": [
		"it_service_management.rental_management.services.scheduler.prepare_monthly_billing_candidates",
	],
}

permission_query_conditions = {
	"Service Job": "it_service_management.service_operations.services.permissions.service_job_query",
	"Service Ticket": "it_service_management.service_operations.services.permissions.service_ticket_query",
}

has_permission = {
	"Service Job": "it_service_management.service_operations.services.permissions.has_service_job_permission",
}

override_doctype_dashboards = {
	"Customer": "it_service_management.config.customer_dashboard.get_data",
	"Customer Equipment": "it_service_management.config.customer_equipment_dashboard.get_data",
	"Serial No": "it_service_management.config.serial_no_dashboard.get_data",
	"Asset": "it_service_management.config.asset_dashboard.get_data",
}
