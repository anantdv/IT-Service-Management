from __future__ import annotations

import frappe
from frappe.model.document import Document


class ConfigurationItem(Document):
	@frappe.whitelist()
	def open_incident_count(self):
		return frappe.db.count(
			"Service Ticket",
			{"configuration_item": self.name, "status": ["not in", ["Closed", "Cancelled"]]},
		)
