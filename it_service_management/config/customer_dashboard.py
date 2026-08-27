from erpnext.selling.doctype.customer.customer_dashboard import get_data as get_erpnext_data

from it_service_management.config.dashboard import extend_dashboard


def get_data():
	return extend_dashboard(get_erpnext_data(), [
		{"label": "IT Service", "items": ["Customer Site", "Customer Equipment", "Service Ticket", "Service Job", "Service Contract"]},
		{"label": "Rental", "items": ["Rental Contract", "Rental Deployment", "Equipment Meter Reading"]},
	], {"Rental Deployment": "customer", "Equipment Meter Reading": "customer"})
