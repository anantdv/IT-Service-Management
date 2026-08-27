from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime, nowdate

from it_service_management.service_operations.services.charges import ServiceChargeEngine


EXPENSE_COVERAGE_FIELD = {
	"Transportation": "travel_covered",
	"Mileage": "travel_covered",
	"Taxi": "travel_covered",
	"Parking": "travel_covered",
	"Food": "food_covered",
	"Accommodation": "accommodation_covered",
	"Airfare": "airfare_covered",
}

DEFAULT_UOM_BY_EXPENSE_TYPE = {
	"Transportation": "Trip",
	"Mileage": "KM",
	"Airfare": "Ticket",
	"Taxi": "Trip",
	"Accommodation": "Night",
	"Food": "Day",
	"Freight": "Shipment",
	"Parking": "Day",
	"Communication": "Each",
	"Other": "Each",
}

ZONE_METHOD_FIELD = {
	"Food": "food_billing_method",
	"Accommodation": "accommodation_billing_method",
	"Airfare": "airfare_billing_method",
}


class ServiceExpense(Document):
	def validate(self):
		self._populate_from_service_job()
		self._set_defaults()
		self._calculate_actual_amounts()
		self._set_reimbursement_defaults()
		self._evaluate_contract_coverage()
		ServiceExpenseBillingCalculator(self).apply()
		self._validate_amounts()
		self._validate_receipt_policy()
		self._validate_approvals()
		self._validate_references()

	def before_save(self):
		self._stamp_approval_fields()

	@frappe.whitelist()
	def populate_from_service_job(self):
		self._populate_from_service_job()
		self._set_defaults()
		self._evaluate_contract_coverage()
		ServiceExpenseBillingCalculator(self).apply()
		return {
			"service_ticket": self.service_ticket,
			"customer": self.customer,
			"customer_site": self.customer_site,
			"employee": self.employee,
			"company": self.company,
			"service_zone": self.service_zone,
			"currency": self.currency,
			"coverage_source": self.coverage_source,
			"coverage_document": self.coverage_document,
			"covered_by_contract": self.covered_by_contract,
			"customer_billing_method": self.customer_billing_method,
			"customer_billing_quantity": self.customer_billing_quantity,
			"customer_billing_rate": self.customer_billing_rate,
			"customer_billable_amount": self.customer_billable_amount,
			"billing_status": self.billing_status,
		}

	@frappe.whitelist()
	def create_expense_claim(self):
		if self.expense_claim:
			frappe.throw("Expense Claim already exists.")
		if frappe.db.exists("Expense Claim", {"custom_service_expense": self.name}):
			frappe.throw("Expense Claim already exists for this Service Expense.")
		if self.approval_status != "Approved":
			frappe.throw("Only approved service expenses can create Expense Claim.")
		if not self.reimbursable_to_employee or self.paid_by != "Employee":
			frappe.throw("Only employee-paid reimbursable expenses can create Expense Claim.")
		if not flt(self.approved_reimbursement_amount):
			frappe.throw("Approved Reimbursement Amount is required before creating an Expense Claim.")

		expense_type = frappe.db.get_value("Expense Claim Type", {"expense_type": self.expense_type}, "name") or self.expense_type
		expense_row = {
			"expense_date": self.expense_date,
			"expense_type": expense_type,
			"description": self.description or self.expense_type,
			"amount": self.approved_reimbursement_amount,
			"sanctioned_amount": self.approved_reimbursement_amount,
		}
		if frappe.db.has_column("Expense Claim Detail", "custom_service_expense"):
			expense_row["custom_service_expense"] = self.name
		if frappe.db.has_column("Expense Claim Detail", "custom_service_job"):
			expense_row["custom_service_job"] = self.service_job

		claim = frappe.get_doc(
			{
				"doctype": "Expense Claim",
				"employee": self.employee,
				"company": self.company,
				"posting_date": nowdate(),
				"expenses": [expense_row],
			}
		)
		if frappe.db.has_column("Expense Claim", "custom_service_expense"):
			claim.custom_service_expense = self.name
		if frappe.db.has_column("Expense Claim", "custom_service_job"):
			claim.custom_service_job = self.service_job
		claim.insert()
		self.expense_claim = claim.name
		self.add_comment("Comment", f"Expense Claim created: {claim.name}")
		self.save()
		return claim.name

	def _populate_from_service_job(self):
		if not self.service_job:
			return

		job = frappe.get_cached_doc("Service Job", self.service_job)
		self.service_ticket = job.service_ticket
		self.customer = job.customer
		self.customer_site = job.customer_site
		self.service_zone = job.service_zone
		self.coverage_source = job.coverage_source
		self.coverage_document = job.coverage_document
		if not self.employee:
			self.employee = job.assigned_technician

		self.company = self._company_from_job(job)
		if self.company:
			self.currency = frappe.db.get_value("Company", self.company, "default_currency")
		elif not self.currency:
			self.currency = frappe.defaults.get_global_default("currency")

	def _set_defaults(self):
		if not self.expense_date:
			self.expense_date = nowdate()
		if not self.quantity:
			self.quantity = 1
		if not self.paid_by:
			self.paid_by = "Employee"
		if self.expense_type and not self.uom:
			self.uom = self._default_uom(self.expense_type)
		if self.paid_by in ("Company", "Company Credit Card", "Customer Direct"):
			self.reimbursable_to_employee = 0

	def _calculate_actual_amounts(self):
		actual_amount = flt(self.quantity) * flt(self.rate)
		self.actual_expense_amount = actual_amount
		self.amount = actual_amount

	def _set_reimbursement_defaults(self):
		if self.paid_by == "Employee":
			if self.reimbursable_to_employee:
				if not flt(self.employee_claimed_amount):
					self.employee_claimed_amount = self.actual_expense_amount
				if not flt(self.approved_reimbursement_amount):
					self.approved_reimbursement_amount = self.employee_claimed_amount
			else:
				self.employee_claimed_amount = 0
				self.approved_reimbursement_amount = 0
		elif self.paid_by in ("Company", "Company Credit Card", "Customer Direct"):
			self.reimbursable_to_employee = 0
			self.employee_claimed_amount = 0
			self.approved_reimbursement_amount = 0
		self.approved_amount = self.approved_reimbursement_amount

	def _evaluate_contract_coverage(self):
		coverage_field = EXPENSE_COVERAGE_FIELD.get(self.expense_type)
		if not coverage_field or not self.service_job:
			self.covered_by_contract = 0
			return
		self.covered_by_contract = 1 if frappe.db.get_value("Service Job", self.service_job, coverage_field) else 0

	def _validate_amounts(self):
		if not self.service_job:
			frappe.throw("Service Job is required.")
		if self.paid_by == "Employee" and not self.employee:
			frappe.throw("Employee is required when Paid By is Employee.")
		if flt(self.quantity) <= 0:
			frappe.throw("Quantity must be greater than zero.")
		if flt(self.rate) < 0:
			frappe.throw("Actual Rate cannot be negative.")
		if flt(self.actual_expense_amount) != flt(flt(self.quantity) * flt(self.rate)):
			frappe.throw("Actual Expense Amount must equal Quantity multiplied by Actual Rate.")
		if flt(self.customer_billable_amount) < 0:
			frappe.throw("Customer Billable Amount cannot be negative.")
		if self.covered_by_contract and flt(self.customer_billable_amount):
			frappe.throw("Covered expenses cannot also have a Customer Billable Amount.")

	def _validate_receipt_policy(self):
		if not frappe.db.exists("DocType", "IT Service Settings"):
			return
		if not frappe.db.get_single_value("IT Service Settings", "require_service_expense_receipt"):
			return
		threshold = flt(frappe.db.get_single_value("IT Service Settings", "service_expense_receipt_threshold"))
		if flt(self.actual_expense_amount) >= threshold and not self.receipt:
			frappe.throw("Receipt is required for this Service Expense.")

	def _validate_approvals(self):
		if self.approval_status in ("Manager Approval", "Finance Approval", "Approved") and self.employee:
			user_employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
			if user_employee == self.employee:
				frappe.throw("Technicians cannot approve their own Service Expense.")
		if self.expense_claim and frappe.db.exists("Expense Claim", self.expense_claim) is None:
			frappe.throw("Linked Expense Claim does not exist.")
		if self.sales_invoice and self.billing_status not in ("Draft Invoice Created", "Invoiced"):
			frappe.throw("Billing Status must match the linked Sales Invoice.")

	def _validate_references(self):
		if self.currency and not frappe.db.exists("Currency", self.currency):
			frappe.throw("Currency must be valid.")
		if self.service_job and self.customer:
			job_customer = frappe.db.get_value("Service Job", self.service_job, "customer")
			if job_customer and job_customer != self.customer:
				frappe.throw("Service Expense customer must match the Service Job customer.")

	def _stamp_approval_fields(self):
		before = self.get_doc_before_save()
		if not before or before.approval_status == self.approval_status:
			return
		if self.approval_status == "Submitted":
			self.submitted_by = frappe.session.user
		elif self.approval_status == "Manager Approval":
			self.manager_approved_by = frappe.session.user
			self.manager_approved_on = now_datetime()
		elif self.approval_status == "Approved":
			self.finance_approved_by = frappe.session.user
			self.finance_approved_on = now_datetime()

	def _company_from_job(self, job):
		if getattr(job, "service_contract", None):
			company = frappe.db.get_value("Service Contract", job.service_contract, "company")
			if company:
				return company
		if getattr(job, "rental_contract", None) and frappe.db.exists("DocType", "Rental Contract"):
			company = frappe.db.get_value("Rental Contract", job.rental_contract, "company")
			if company:
				return company
		return frappe.defaults.get_user_default("Company")

	def _default_uom(self, expense_type):
		preferred = DEFAULT_UOM_BY_EXPENSE_TYPE.get(expense_type) or "Each"
		if frappe.db.exists("UOM", preferred):
			return preferred
		return frappe.db.get_value("UOM", {"enabled": 1}, "name") or preferred


class ServiceExpenseBillingCalculator:
	def __init__(self, expense):
		self.expense = expense
		self.job = frappe.get_cached_doc("Service Job", expense.service_job) if expense.service_job else None
		self.zone = frappe.get_cached_doc("Service Zone", expense.service_zone) if expense.service_zone and frappe.db.exists("Service Zone", expense.service_zone) else None

	def apply(self):
		self._reset_customer_billing()
		if not self.job:
			return
		if self.expense.paid_by == "Customer Direct" or self.expense.covered_by_contract:
			self._set_not_billable()
			return

		rule = ServiceChargeEngine(self.job).calculate_amount(self._charge_type(), self._expense_quantity(), actual_cost=self._actual_unit_rate())
		if rule:
			method = rule["calculation_method"] if rule["calculation_method"] in ("Actual Cost", "Cost Plus Percentage") else "Service Charge Rule"
			self._set_billable(method, rule["quantity"], rule["rate"], "Service Charge Rule", rule["service_charge"])
			return

		if self._apply_service_zone_method():
			return

		self._set_actual_cost()

	def _reset_customer_billing(self):
		self.expense.customer_billing_method = "Not Evaluated"
		self.expense.billing_rule_source = None
		self.expense.billing_rule_reference = None
		self.expense.customer_billing_quantity = 0
		self.expense.customer_billing_rate = 0
		self.expense.customer_billable_amount = 0
		self.expense.billable_to_customer = 0
		self.expense.billing_status = "Not Evaluated"

	def _set_not_billable(self):
		self.expense.customer_billing_method = "Not Billable"
		self.expense.billing_status = "Not Billable"

	def _set_actual_cost(self):
		self._set_billable("Actual Cost", 1, self.expense.actual_expense_amount, None, None)

	def _set_billable(self, method, quantity, rate, source, reference):
		amount = flt(quantity) * flt(rate)
		self.expense.customer_billing_method = method
		self.expense.customer_billing_quantity = quantity
		self.expense.customer_billing_rate = rate
		self.expense.customer_billable_amount = amount
		self.expense.billable_to_customer = 1 if amount else 0
		self.expense.billing_status = "Ready for Billing" if self.expense.approval_status == "Approved" and amount else "Not Evaluated"
		self.expense.billing_rule_source = source
		self.expense.billing_rule_reference = reference

	def _apply_service_zone_method(self):
		if not self.zone:
			return False
		method_field = ZONE_METHOD_FIELD.get(self.expense.expense_type)
		method = self.zone.get(method_field) if method_field else None

		if method == "Not Chargeable":
			self._set_not_billable()
			return True
		if method == "Actual Cost":
			self._set_actual_cost()
			return True
		if method == "Fixed Charge" and self.expense.expense_type == "Airfare":
			self._set_billable("Fixed Allowance", 1, flt(self.zone.get("airfare_fixed_charge")), "Service Zone", self.zone.name)
			return True
		if method == "Fixed Allowance" and self.expense.expense_type == "Food":
			self._apply_zone_allowance("Food", self.zone.get("food_charge_basis") or "Per Technician / Day", flt(self.zone.get("food_allowance")))
			return True
		if method == "Fixed Allowance" and self.expense.expense_type == "Accommodation":
			rate = flt(self.zone.get("accommodation_allowance") or self.zone.get("accommodation_charge"))
			self._apply_zone_allowance("Accommodation", self.zone.get("accommodation_charge_basis") or "Per Technician / Night", rate)
			return True
		if self.expense.expense_type == "Mileage" and flt(self.zone.get("per_km_charge")):
			self._set_billable("Service Zone Rate", self._expense_quantity(), flt(self.zone.get("per_km_charge")), "Service Zone", self.zone.name)
			return True
		return False

	def _apply_zone_allowance(self, label, basis, rate):
		quantity = self._expense_quantity()
		if basis in ("Per Technician / Day", "Per Technician / Night"):
			quantity *= self._technician_count()
		elif basis == "Per Job":
			quantity = 1
		self._set_billable("Service Zone Rate", quantity, rate, "Service Zone", self.zone.name)

	def _charge_type(self):
		if self.expense.expense_type in ("Transportation", "Mileage", "Taxi", "Parking"):
			return "Travel"
		return self.expense.expense_type

	def _expense_quantity(self):
		return flt(self.expense.quantity) or 1

	def _actual_unit_rate(self):
		quantity = self._expense_quantity()
		return flt(self.expense.actual_expense_amount) / quantity if quantity else flt(self.expense.actual_expense_amount)

	def _technician_count(self):
		if self.job and flt(self.job.get("chargeable_technician_count")):
			return flt(self.job.get("chargeable_technician_count"))
		technicians = {row.employee for row in self.job.labour if row.employee} if self.job else set()
		for fieldname in ("assigned_technician", "backup_technician"):
			if self.job and self.job.get(fieldname):
				technicians.add(self.job.get(fieldname))
		return len(technicians) or 1
