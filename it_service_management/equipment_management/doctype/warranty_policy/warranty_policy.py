import frappe
from frappe.model.document import Document


class WarrantyPolicy(Document):
	def validate(self):
		if self.duration_months <= 0:
			frappe.throw("Duration Months must be greater than zero.")

		if self.item_code and self.item_group:
			frappe.throw("Set either Item or Item Group, not both.")
