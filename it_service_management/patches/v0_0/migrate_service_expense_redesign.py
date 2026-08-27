import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


SERVICE_EXPENSE_UOMS = {
	"Trip": 1,
	"KM": 0,
	"Ticket": 1,
	"Night": 1,
	"Day": 1,
	"Shipment": 1,
	"Each": 1,
}


def execute():
	ensure_uoms()
	ensure_expense_claim_references()
	migrate_service_expense_values()


def ensure_uoms():
	if not frappe.db.exists("DocType", "UOM"):
		return
	for uom_name, whole_number in SERVICE_EXPENSE_UOMS.items():
		if frappe.db.exists("UOM", uom_name):
			continue
		frappe.get_doc(
			{
				"doctype": "UOM",
				"uom_name": uom_name,
				"must_be_whole_number": whole_number,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)


def ensure_expense_claim_references():
	custom_fields = {
		"Expense Claim": [
			{
				"fieldname": "custom_service_expense",
				"fieldtype": "Link",
				"label": "Service Expense",
				"options": "Service Expense",
				"insert_after": "employee",
				"read_only": 1,
				"module": "IT Service Management",
			},
			{
				"fieldname": "custom_service_job",
				"fieldtype": "Link",
				"label": "Service Job",
				"options": "Service Job",
				"insert_after": "custom_service_expense",
				"read_only": 1,
				"module": "IT Service Management",
			},
		],
		"Expense Claim Detail": [
			{
				"fieldname": "custom_service_expense",
				"fieldtype": "Link",
				"label": "Service Expense",
				"options": "Service Expense",
				"insert_after": "description",
				"read_only": 1,
				"module": "IT Service Management",
			},
			{
				"fieldname": "custom_service_job",
				"fieldtype": "Link",
				"label": "Service Job",
				"options": "Service Job",
				"insert_after": "custom_service_expense",
				"read_only": 1,
				"module": "IT Service Management",
			},
		],
	}
	create_custom_fields(custom_fields, update=True)


def migrate_service_expense_values():
	if not frappe.db.exists("DocType", "Service Expense"):
		return

	if frappe.db.has_column("Service Expense", "actual_expense_amount") and frappe.db.has_column("Service Expense", "amount"):
		frappe.db.sql(
			"""
			update `tabService Expense`
			set actual_expense_amount = coalesce(actual_expense_amount, amount, 0)
			where actual_expense_amount is null
			"""
		)

	if frappe.db.has_column("Service Expense", "approved_reimbursement_amount") and frappe.db.has_column("Service Expense", "approved_amount"):
		frappe.db.sql(
			"""
			update `tabService Expense`
			set approved_reimbursement_amount = coalesce(approved_reimbursement_amount, approved_amount, amount, 0)
			where approved_reimbursement_amount is null
			"""
		)

	defaults = {
		"paid_by": "Employee",
		"billing_status": "Not Evaluated",
		"customer_billing_method": "Not Evaluated",
	}
	for fieldname, value in defaults.items():
		if frappe.db.has_column("Service Expense", fieldname):
			frappe.db.sql(
				f"""
				update `tabService Expense`
				set {fieldname} = %s
				where {fieldname} is null or {fieldname} = ''
				""",
				value,
			)

	if frappe.db.has_column("Service Expense", "uom"):
		for expense_type, uom in {
			"Transportation": "Trip",
			"Mileage": "KM",
			"Airfare": "Ticket",
			"Taxi": "Trip",
			"Accommodation": "Night",
			"Food": "Day",
			"Freight": "Shipment",
			"Parking": "Day",
			"Communication": "Each",
			"Other": "Each",
		}.items():
			frappe.db.sql(
				"""
				update `tabService Expense`
				set uom = %s
				where expense_type = %s and (uom is null or uom = '')
				""",
				(uom, expense_type),
			)
