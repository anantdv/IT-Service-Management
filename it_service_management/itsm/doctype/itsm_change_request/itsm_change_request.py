from __future__ import annotations

from frappe.model.document import Document
from frappe.utils import now_datetime

from it_service_management.itsm.services.change_risk import calculate_change_risk


class ITSMChangeRequest(Document):
	def validate(self):
		if not self.override_risk_level:
			self.risk_score, self.risk_level = calculate_change_risk(self)

	def start_implementation(self):
		self.actual_start = self.actual_start or now_datetime()
		self.status = "Implementation"

	def complete_implementation(self):
		self.actual_end = self.actual_end or now_datetime()
		self.status = "Validation"

	def mark_failed(self):
		self.actual_end = self.actual_end or now_datetime()
		self.status = "Failed"

	def initiate_rollback(self):
		self.status = "Rolled Back"
