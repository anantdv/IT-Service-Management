import frappe
from frappe.model.document import Document


class ServiceBillingReference(Document):
	def validate(self):
		if bool(self.service_charge_row) == bool(self.adjustment):
			frappe.throw("A billing reference must identify exactly one service charge row or adjustment.")
		filters = {"service_job": self.service_job, "status": ["in", ["Reserved", "Draft Invoiced", "Submitted"]]}
		filters["service_charge_row" if self.service_charge_row else "adjustment"] = self.service_charge_row or self.adjustment
		duplicate = frappe.db.exists("Service Billing Reference", filters)
		if duplicate and duplicate != self.name:
			frappe.throw("This source is already reserved or invoiced.")
