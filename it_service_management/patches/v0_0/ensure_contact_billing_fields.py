import frappe


def execute():
	if not frappe.db.exists("DocType", "Contact"):
		return

	ensure_check_column("Contact", "is_primary_contact")
	ensure_check_column("Contact", "is_billing_contact")
	frappe.clear_cache(doctype="Contact")


def ensure_check_column(doctype, fieldname):
	if frappe.db.has_column(doctype, fieldname):
		return
	frappe.db.sql(
		"""
		alter table `tab{0}`
		add column `{1}` int(1) not null default 0
		""".format(doctype, fieldname)
	)
