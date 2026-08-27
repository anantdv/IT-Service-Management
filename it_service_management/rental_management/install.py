import frappe


def after_install():
	seed_meter_types()


def after_migrate():
	seed_meter_types()


def seed_meter_types():
	if not frappe.db.exists("DocType", "Equipment Meter Type"):
		return
	for code, name in (("BW", "B&W"), ("COLOUR", "Colour")):
		if not frappe.db.exists("Equipment Meter Type", code):
			frappe.get_doc({"doctype": "Equipment Meter Type", "meter_code": code, "meter_name": name, "cumulative": 1, "active": 1}).insert(ignore_permissions=True)
