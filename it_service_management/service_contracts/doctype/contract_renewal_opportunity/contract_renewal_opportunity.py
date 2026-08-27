from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, flt

from it_service_management.service_billing.services.credit import check_customer_credit


class ContractRenewalOpportunity(Document):
	def validate(self):
		if bool(self.service_contract) == bool(self.rental_contract):
			frappe.throw("Select exactly one Service Contract or Rental Contract.")
		self.renewal_type = "Service Contract" if self.service_contract else "Rental Contract"
		self.expected_revenue = flt(self.proposed_value) * flt(self.probability) / 100
		if self.renewal_stage == "Lost" and not self.lost_reason:
			frappe.throw("Lost Reason is required when a renewal is lost.")
		if self.renewal_stage in ("Lost", "Not Renewing"):
			self.status = "Lost" if self.renewal_stage == "Lost" else "Closed"

	@frappe.whitelist()
	def create_renewal_contract(self):
		self.check_permission("write")
		if self.renewed_contract:
			return {"doctype": self.renewed_contract_type, "name": self.renewed_contract}
		source_doctype = "Service Contract" if self.service_contract else "Rental Contract"
		source = frappe.get_doc(source_doctype, self.service_contract or self.rental_contract)
		check_customer_credit(source.customer, source.company, self.proposed_value or self.current_value)
		renewal = frappe.copy_doc(source)
		renewal.name = None
		renewal.docstatus = 0
		if source_doctype == "Service Contract":
			renewal.contract_status = "Draft"
			renewal.previous_service_contract = source.name
		else:
			renewal.status = "Draft"
			renewal.approved_by = None
			renewal.approved_on = None
			renewal.previous_rental_contract = source.name
		renewal.start_date = self.proposed_start_date or add_days(source.end_date, 1)
		renewal.end_date = self.proposed_end_date
		if self.proposed_plan:
			renewal.set("service_plan" if source_doctype == "Service Contract" else "rental_plan", self.proposed_plan)
		if self.proposed_value:
			renewal.set("billing_amount" if source_doctype == "Service Contract" else "base_rental_amount", self.proposed_value)
		renewal.renewal_opportunity = self.name
		renewal.insert()
		self.db_set({"renewed_contract_type": source_doctype, "renewed_contract": renewal.name, "renewal_stage": "Renewed", "status": "Renewed"})
		return {"doctype": source_doctype, "name": renewal.name}
