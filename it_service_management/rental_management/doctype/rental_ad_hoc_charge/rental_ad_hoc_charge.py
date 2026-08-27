import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


class RentalAdHocCharge(Document):
	def before_insert(self):
		self.copy_contract_details()

	def validate(self):
		self.copy_contract_details()
		if flt(self.quantity) <= 0:
			frappe.throw("Quantity must be greater than zero.")
		if flt(self.rate) < 0:
			frappe.throw("Rate cannot be negative.")
		self.amount = flt(self.quantity) * flt(self.rate)
		old = self.get_doc_before_save() if not self.is_new() else None
		if self.status == "Approved" and (not old or old.status != "Approved"):
			if not {"Rental Manager", "Service Manager", "System Manager"}.intersection(frappe.get_roles()):
				frappe.throw("Only Rental Manager or Service Manager may approve an ad-hoc charge.")
			self.approved_by = frappe.session.user
			self.approval_datetime = now_datetime()

	def copy_contract_details(self):
		if not self.rental_contract:
			return
		contract = frappe.get_cached_doc("Rental Contract", self.rental_contract)
		self.customer = contract.customer
		self.customer_site = self.customer_site or contract.customer_site
