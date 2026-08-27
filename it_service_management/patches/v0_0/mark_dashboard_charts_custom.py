import frappe


def execute():
	if not frappe.db.exists("DocType", "Dashboard Chart"):
		return

	frappe.db.sql(
		"""
		update `tabDashboard Chart`
		set is_standard = 0
		where module = 'IT Service Management'
		  and name like 'ITSM %%'
		"""
	)
