import frappe
from frappe.model.document import Document


class ServiceTeam(Document):
	def validate(self):
		primary = [row for row in self.members if row.primary and row.active]
		if len(primary) > 1:
			frappe.throw("Only one active primary member is allowed per Service Team.")
