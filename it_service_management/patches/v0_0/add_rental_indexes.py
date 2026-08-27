import frappe


def execute():
	indexes = (
		("Rental Contract", ["company", "status", "end_date"], "rental_contract_company_status_end"),
		("Rental Contract", ["customer", "customer_site", "status"], "rental_contract_customer_site_status"),
		("Rental Contract Equipment", ["asset", "deployment_status"], "rental_equipment_asset_status"),
		("Rental Contract Equipment", ["customer_equipment", "deployment_status"], "rental_equipment_customer_status"),
		("Equipment Meter Reading", ["customer_equipment", "billing_period_from", "billing_period_to", "verified"], "meter_equipment_period_verified"),
		("Equipment Meter Reading", ["rental_contract", "reading_date"], "meter_contract_reading_date"),
		("Rental Billing Reference", ["rental_contract", "billing_period_from", "billing_period_to"], "rental_billing_contract_period"),
		("Rental Billing Reference", ["source_document_type", "source_document", "status"], "rental_billing_source_status"),
		("Rental Billing Reference", ["invoice", "status"], "rental_billing_invoice_status"),
	)
	for doctype, fields, name in indexes:
		if frappe.db.exists("DocType", doctype):
			frappe.db.add_index(doctype, fields, index_name=name)

	unique_fields = ["rental_contract", "billing_period_from", "billing_period_to", "component_type", "source_document_type", "source_document"]
	if frappe.db.exists("DocType", "Rental Billing Reference"):
		try:
			frappe.db.add_unique("Rental Billing Reference", unique_fields, constraint_name="unique_rental_billing_source_period")
		except TypeError:
			frappe.db.add_unique("Rental Billing Reference", unique_fields)
