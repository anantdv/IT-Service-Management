from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import nowdate


class ServiceExpense(Document):
	def validate(self):
		self.amount = (self.quantity or 0) * (self.rate or 0)
		if not self.expense_date:
			self.expense_date = nowdate()
		if self.service_job and not self.service_ticket:
			self.service_ticket = frappe.db.get_value("Service Job", self.service_job, "service_ticket")
		if self.covered_by_contract:
			self.customer_billable_amount = 0
		elif self.billable_to_customer:
			self.customer_billable_amount = self.approved_amount or self.amount

	@frappe.whitelist()
	def create_expense_claim(self):
		if self.expense_claim:
			frappe.throw("Expense Claim already exists.")
		if self.approval_status != "Approved":
			frappe.throw("Only approved service expenses can create Expense Claim.")
		if not self.reimbursable_to_employee or self.paid_by != "Employee":
			frappe.throw("Only employee-paid reimbursable expenses can create Expense Claim.")
		expense_type = frappe.db.get_value("Expense Claim Type", {"expense_type": self.expense_type}, "name") or self.expense_type
		claim = frappe.get_doc(
			{
				"doctype": "Expense Claim",
				"employee": self.employee,
				"posting_date": nowdate(),
				"expenses": [
					{
						"expense_date": self.expense_date,
						"expense_type": expense_type,
						"description": self.description or self.expense_type,
						"amount": self.approved_amount or self.amount,
						"sanctioned_amount": self.approved_amount or self.amount,
					}
				],
			}
		)
		claim.insert()
		self.expense_claim = claim.name
		self.add_comment("Comment", f"Expense Claim created: {claim.name}")
		self.save()
		return claim.name
