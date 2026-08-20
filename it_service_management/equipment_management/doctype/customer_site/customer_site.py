import frappe
from frappe.model.document import Document


class CustomerSite(Document):
	def validate(self):
		if self.service_window_from and self.service_window_to:
			if self.service_window_from >= self.service_window_to:
				frappe.throw("Service Window To must be after Service Window From.")
