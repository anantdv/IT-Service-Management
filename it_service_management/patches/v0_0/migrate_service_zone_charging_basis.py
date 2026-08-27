import frappe


def execute():
	if not frappe.db.exists("DocType", "Service Zone"):
		return

	if frappe.db.has_column("Service Zone", "accommodation_charge") and frappe.db.has_column("Service Zone", "accommodation_allowance"):
		frappe.db.sql(
			"""
			update `tabService Zone`
			set accommodation_allowance = coalesce(accommodation_allowance, accommodation_charge)
			where accommodation_charge is not null
			"""
		)

	defaults = {
		"callout_charge_basis": "Per Visit",
		"travel_charge_basis": "Per Trip",
		"installation_charge_basis": "Per Installation",
		"food_billing_method": "Fixed Allowance",
		"food_charge_basis": "Per Technician / Day",
		"accommodation_billing_method": "Fixed Allowance",
		"accommodation_charge_basis": "Per Technician / Night",
		"airfare_billing_method": "Actual Cost",
	}
	for fieldname, value in defaults.items():
		if frappe.db.has_column("Service Zone", fieldname):
			frappe.db.sql(
				f"""
				update `tabService Zone`
				set {fieldname} = %s
				where {fieldname} is null or {fieldname} = ''
				""",
				value,
			)

	if frappe.db.has_column("Service Zone", "airfare_actual") and frappe.db.has_column("Service Zone", "airfare_billing_method"):
		frappe.db.sql(
			"""
			update `tabService Zone`
			set airfare_billing_method = 'Actual Cost'
			where airfare_actual = 1
			"""
		)

	if frappe.db.exists("DocType", "Service Job"):
		job_defaults = {"chargeable_trips": 1, "chargeable_travel_days": 1, "chargeable_nights": 0, "chargeable_distance_km": 0, "chargeable_technician_count": 0}
		for fieldname, value in job_defaults.items():
			if frappe.db.has_column("Service Job", fieldname):
				frappe.db.sql(
					f"""
					update `tabService Job`
					set {fieldname} = %s
					where {fieldname} is null
					""",
					value,
				)
