from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint, getdate, now_datetime

from it_service_management.service_billing.services.batch import (
	ServiceBillingBatchEngine,
	ServiceInvoiceService,
	enqueue_generate_service_invoices,
	enqueue_prepare_service_billing,
)


APPROVER_ROLES = {"Service Manager", "Accounts Manager", "System Manager"}


class ServiceBillingBatch(Document):
	def validate(self):
		if self.service_date_from and self.service_date_to and getdate(self.service_date_to) < getdate(self.service_date_from):
			frappe.throw("Service Date To cannot precede Service Date From.")
		if self.status == "Cancelled" and frappe.db.exists(
			"Sales Invoice", {"custom_service_billing_batch": self.name, "docstatus": 1}
		):
			frappe.throw("Cancel submitted Sales Invoices before cancelling this Service Billing Batch.")

	def on_update(self):
		if self.status == "Cancelled":
			for name in frappe.get_all("Service Billing Reference", filters={"billing_batch": self.name, "status": "Reserved"}, pluck="name"):
				frappe.db.set_value("Service Billing Reference", name, "status", "Cancelled", update_modified=False)

	@frappe.whitelist()
	def prepare_billing(self, background=True):
		self.check_permission("write")
		if self.is_new():
			self.save()
		if cint(background):
			self.db_set({"status": "Processing", "started_at": now_datetime()})
			return enqueue_prepare_service_billing(self.name)
		return ServiceBillingBatchEngine(self).prepare()

	@frappe.whitelist()
	def submit_for_review(self):
		self.check_permission("write")
		if self.status != "Prepared":
			frappe.throw("Prepare the batch before submitting it for review.")
		self.db_set("status", "Under Review")
		self.add_comment("Comment", f"Submitted for billing review by {frappe.session.user}")
		return self

	@frappe.whitelist()
	def approve_for_billing(self):
		if not APPROVER_ROLES.intersection(frappe.get_roles()):
			frappe.throw("Only a Service Manager or Accounts Manager can approve billing.", frappe.PermissionError)
		if self.status not in ("Prepared", "Under Review", "Completed With Errors"):
			frappe.throw("Only a prepared batch can be approved.")
		self.db_set({"status": "Approved for Billing", "approved_by": frappe.session.user, "approved_on": now_datetime()})
		self.add_comment("Comment", f"Approved for billing by {frappe.session.user}")
		return self

	@frappe.whitelist()
	def generate_draft_sales_invoices(self, background=True):
		self.check_permission("write")
		if cint(background):
			if not {"Service Billing User", "Accounts Manager", "Accounts User", "System Manager"}.intersection(frappe.get_roles()):
				frappe.throw("Only Service Billing or Accounts users can generate service invoices.", frappe.PermissionError)
			settings = frappe.get_single("IT Service Settings")
			if cint(settings.require_service_billing_approval) and (self.status not in ("Approved for Billing", "Completed With Errors") or not self.approved_by):
				frappe.throw("Approve this Service Billing Batch before generating invoices.")
			self.db_set({"status": "Processing", "started_at": now_datetime()})
			return enqueue_generate_service_invoices(self.name)
		return ServiceInvoiceService(self).generate()

	@frappe.whitelist()
	def get_review_charges(self):
		self.check_permission("read")
		jobs = [row.service_job for row in self.details]
		if not jobs:
			return []
		charges = frappe.db.sql(
			"""
			select c.parent service_job, 'Service Job Charge' source_type, c.name source_document,
			c.charge_type, c.description, c.amount, c.covered, c.billable_amount
			from `tabService Job Charge` c where c.parent in %(jobs)s
			union all
			select a.service_job, 'Service Billing Adjustment', a.name, a.adjustment_type, a.reason,
			a.amount, 0, case when a.adjustment_type in ('Discount','Waiver','Credit Adjustment') then -a.amount else a.amount end
			from `tabService Billing Adjustment` a where a.service_job in %(jobs)s and a.approval_status='Approved'
			order by service_job, source_type, source_document
			""",
			{"jobs": jobs}, as_dict=True,
		)
		return charges
