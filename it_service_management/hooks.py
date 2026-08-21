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
		"Service Auditor",
	]]]},
	{"dt": "Workspace", "filters": [["name", "in", ["IT Service Management", "Service Operations"]]]},
	{"dt": "Custom Field", "filters": [["dt", "=", "Employee"], ["module", "=", "IT Service Management"]]},
]

doctype_js = {
	"Customer Equipment": "public/js/customer_equipment.js",
	"Service Contract": "public/js/service_contract.js",
	"Service Ticket": "public/js/service_ticket.js",
	"Service Job": "public/js/service_job.js",
	"Remote Support Session": "public/js/remote_support_session.js",
	"Service Expense": "public/js/service_expense.js",
	"Service Part Request": "public/js/service_part_request.js",
}

doc_events = {
	"Delivery Note": {
		"on_submit": "it_service_management.equipment_management.doctype.customer_equipment.customer_equipment.create_from_delivery_note",
	},
	"Sales Invoice": {
		"on_submit": "it_service_management.equipment_management.doctype.customer_equipment.customer_equipment.update_from_sales_invoice",
	},
}

scheduler_events = {
	"hourly": [
		"it_service_management.service_operations.services.notifications.evaluate_active_ticket_slas",
	],
	"daily": [
		"it_service_management.service_contracts.doctype.service_contract.service_contract.update_contract_statuses",
		"it_service_management.service_contracts.doctype.service_contract.service_contract.send_contract_expiry_notifications",
	]
}

permission_query_conditions = {
	"Service Job": "it_service_management.service_operations.services.permissions.service_job_query",
	"Service Ticket": "it_service_management.service_operations.services.permissions.service_ticket_query",
}

has_permission = {
	"Service Job": "it_service_management.service_operations.services.permissions.has_service_job_permission",
}
