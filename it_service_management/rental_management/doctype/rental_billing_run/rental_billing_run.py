from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import getdate

from it_service_management.rental_management.services.billing import RentalBillingEngine, RentalInvoiceService, enqueue_generate_invoices, enqueue_prepare_billing


class RentalBillingRun(Document):
	def validate(self):
		if self.billing_period_from and self.billing_period_to and getdate(self.billing_period_to) < getdate(self.billing_period_from):
			frappe.throw("Billing Period To cannot precede Billing Period From.")
		if self.status == "Cancelled":
			invoices = frappe.get_all("Sales Invoice", filters={"custom_rental_billing_run": self.name, "docstatus": 1}, pluck="name")
			if invoices:
				frappe.throw("Cancel submitted rental invoices before cancelling the Billing Run.")

	def on_update(self):
		if self.status == "Cancelled":
			for name in frappe.get_all("Rental Billing Reference", filters={"billing_run": self.name, "status": "Reserved"}, pluck="name"):
				frappe.db.set_value("Rental Billing Reference", name, "status", "Cancelled", update_modified=False)

	@frappe.whitelist()
	def submit_for_review(self):
		self.check_permission("write")
		if self.status != "Prepared":
			frappe.throw("Prepare the billing run before submitting it for review.")
		self.db_set("status", "Under Review")
		self.add_comment("Comment", f"Submitted for billing review by {frappe.session.user}")
		return self

	@frappe.whitelist()
	def approve_for_billing(self):
		if not {"Rental Manager", "Accounts Manager", "System Manager"}.intersection(frappe.get_roles()):
			frappe.throw("Only a Rental Manager or Accounts Manager can approve rental billing.", frappe.PermissionError)
		if self.status not in ("Prepared", "Under Review", "Completed With Errors"):
			frappe.throw("Only a prepared billing run can be approved.")
		self.db_set({"status": "Approved for Billing", "approved_by": frappe.session.user, "approved_on": frappe.utils.now_datetime()})
		self.add_comment("Comment", f"Approved for billing by {frappe.session.user}")
		return self

	@frappe.whitelist()
	def prepare_billing(self, background=True):
		self.check_permission("write")
		if not self.name or self.is_new():
			self.save()
		if frappe.utils.cint(background):
			self.db_set({"status": "Processing", "started_at": frappe.utils.now_datetime()})
			return enqueue_prepare_billing(self.name)
		return RentalBillingEngine(self).prepare()

	@frappe.whitelist()
	def generate_draft_sales_invoices(self, background=True):
		self.check_permission("write")
		if frappe.utils.cint(background):
			if not {"Rental Billing User", "Accounts Manager", "Accounts User", "System Manager"}.intersection(frappe.get_roles()):
				frappe.throw("Only Rental Billing or Accounts users can generate rental invoices.", frappe.PermissionError)
			settings = frappe.get_single("IT Service Settings")
			if frappe.utils.cint(settings.require_rental_billing_approval) and (self.status not in ("Approved for Billing", "Completed With Errors") or not self.approved_by):
				frappe.throw("Approve this Rental Billing Run before generating invoices.")
			self.db_set({"status": "Processing", "started_at": frappe.utils.now_datetime()})
			return enqueue_generate_invoices(self.name)
		return RentalInvoiceService(self).generate()
