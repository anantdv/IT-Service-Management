import frappe
from frappe.model.document import Document


class MeterReset(Document):
	def validate(self):
		if not {"Rental Manager", "Service Manager", "System Manager"}.intersection(frappe.get_roles()):
			frappe.throw("Only Rental Manager or Service Manager may authorize a meter reset.")
		if self.previous_reading < 0 or self.reset_reading < 0:
			frappe.throw("Meter readings cannot be negative.")
		self.approved_by = frappe.session.user
