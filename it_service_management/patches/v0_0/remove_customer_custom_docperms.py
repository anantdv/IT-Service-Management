import frappe


def execute():
	if not frappe.db.exists("DocType", "Custom DocPerm"):
		return

	frappe.db.sql(
		"""
		delete from `tabCustom DocPerm`
		where parent = 'Customer'
		  and role in ('IT Service Analyst', 'IT Service Executive')
		"""
	)
	frappe.clear_cache(doctype="Customer")
