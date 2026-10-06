from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class MajorIncident(Document):
	def before_insert(self):
		self.detected_at = self.detected_at or now_datetime()

	def validate(self):
		if self.status == "Closed":
			self._validate_pir_before_close()

	def _validate_pir_before_close(self):
		required = ("incident_summary", "business_impact", "timeline_summary", "root_cause")
		missing = [field for field in required if not self.get(field)]
		if missing:
			frappe.throw("Complete PIR fields before closing Major Incident: " + ", ".join(missing))
		open_actions = [row.action for row in self.get("pir_action_items", []) if row.status not in ("Completed", "Cancelled")]
		if open_actions:
			frappe.throw("Complete or cancel PIR action items before closing Major Incident.")

	@frappe.whitelist()
	def publish_status_update(self, message, audience="Internal", status=None):
		self.append(
			"updates",
			{
				"timestamp": now_datetime(),
				"status": status or self.status,
				"audience": audience,
				"message": message,
				"published_by": frappe.session.user,
			},
		)
		self.save()
		return self.name
