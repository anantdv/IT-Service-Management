from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import flt


APPROVER_ROLES = {"Service Manager", "Accounts Manager", "System Manager"}


class ServiceBillingAdjustment(Document):
	def before_insert(self):
		self._set_customer()

	def validate(self):
		self._set_customer()
		if flt(self.amount) <= 0:
			frappe.throw("Adjustment amount must be greater than zero.")

		old = self.get_doc_before_save() if not self.is_new() else None
		if self.approval_status == "Approved" and (not old or old.approval_status != "Approved"):
			self._require_approver()
			self.approved_by = frappe.session.user

	def _set_customer(self):
		if self.service_job:
			self.customer = frappe.db.get_value("Service Job", self.service_job, "customer")

	@staticmethod
	def _require_approver():
		if not APPROVER_ROLES.intersection(frappe.get_roles()):
			frappe.throw("Only a Service Manager or Accounts Manager can approve billing adjustments.", frappe.PermissionError)
