from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime


class RemoteSupportSession(Document):
	def validate(self):
		if self.start_datetime and self.end_datetime:
			self.duration_minutes = (get_datetime(self.end_datetime) - get_datetime(self.start_datetime)).total_seconds() / 60
		if self.covered:
			self.billable_amount = 0
		elif self.billable:
			self.billable_amount = (self.duration_minutes or 0) / 60 * (self.billing_rate or 0)

	@frappe.whitelist()
	def create_service_job(self):
		if not self.onsite_required:
			frappe.throw("Onsite Required must be checked before creating a Service Job.")
		ticket = frappe.get_doc("Service Ticket", self.service_ticket)
		job_name = ticket.create_service_job(job_type="Onsite Support")
		self.service_job = job_name
		self.add_comment("Comment", f"Service Job created for onsite support: {job_name}")
		self.save()
		return job_name
