from erpnext.stock.doctype.serial_no.serial_no_dashboard import get_data as get_erpnext_data

from it_service_management.config.dashboard import extend_dashboard


def get_data():
	return extend_dashboard(get_erpnext_data(), [
		{"label": "IT Service", "items": ["Customer Equipment", "Service Job", "Equipment Meter Reading"]},
	], {"Customer Equipment": "serial_no", "Service Job": "serial_no", "Equipment Meter Reading": "serial_no"})
