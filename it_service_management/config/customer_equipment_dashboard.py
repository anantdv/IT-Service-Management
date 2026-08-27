def get_data():
	return {
		"fieldname": "customer_equipment",
		"non_standard_fieldnames": {"Sales Invoice": "custom_customer_equipment", "Rental Equipment Replacement": "old_customer_equipment"},
		"transactions": [
			{"label": "Service", "items": ["Service Ticket", "Service Job"]},
			{"label": "Rental", "items": ["Equipment Meter Reading", "Rental Equipment Replacement"]},
			{"label": "Billing", "items": ["Sales Invoice"]},
		],
	}
