from __future__ import annotations

import frappe

from it_service_management.service_operations.services.charges import ServiceChargeEngine


COVERAGE_BY_CHARGE = {
	"Labour": "labour_covered",
	"Part": "parts_covered",
	"Travel": "travel_covered",
	"Food": "food_covered",
	"Accommodation": "accommodation_covered",
	"Callout": "callout_covered",
	"Installation": "installation_covered",
	"Remote Support": "remote_support_covered",
}


class ServiceBillingEngine:
	def __init__(self, job):
		self.job = job

	def calculate(self):
		self._clear_generated_charges()
		for row in self.job.labour:
			self._append_charge("Labour", row.billing_rate or 0, row.duration_hours or 0, row.internal_cost or 0, "Labour", row.name)
		for row in self.job.parts:
			self._append_charge("Part", row.billing_rate or row.valuation_rate or 0, row.quantity or 0, row.internal_cost or 0, "Part", row.name, item_code=row.item_code)
		self._append_expenses()
		self._append_zone_charges()
		self._calculate_totals()
		self.job.billing_status = "Ready for Billing" if self.job.total_billable_amount else "Not Applicable"
		self.job.add_comment("Comment", "Billing calculated")
		self.job.save()
		return self.job

	def _clear_generated_charges(self):
		self.job.set("charges", [row for row in self.job.charges if row.manually_added])

	def _append_expenses(self):
		expenses = frappe.get_all(
			"Service Expense",
			filters={"service_job": self.job.name, "approval_status": "Approved"},
			fields=["name", "expense_type", "amount", "approved_amount", "customer_billable_amount", "covered_by_contract", "billable_to_customer"],
		)
		for expense in expenses:
			charge_type = "Travel" if expense.expense_type in ("Transportation", "Mileage", "Taxi", "Parking") else expense.expense_type
			amount = expense.approved_amount or expense.amount or 0
			self._append_charge(charge_type, amount, 1, amount, "Service Expense", expense.name, force_covered=expense.covered_by_contract)

	def _append_zone_charges(self):
		engine = ServiceChargeEngine(self.job)
		for charge_type, qty in (("Callout", 1), ("Travel", 1), ("Installation", 1)):
			calculated = engine.calculate_amount(charge_type, qty)
			if calculated:
				self._append_charge(charge_type, calculated["rate"], calculated["quantity"], 0, "Service Zone", calculated["service_charge"], service_charge=calculated["service_charge"])

	def _append_charge(self, charge_type, rate, quantity, internal_cost, source_type, source_document, item_code=None, service_charge=None, force_covered=None):
		amount = (rate or 0) * (quantity or 0)
		coverage_field = COVERAGE_BY_CHARGE.get(charge_type)
		covered = bool(getattr(self.job, coverage_field, 0)) if force_covered is None else bool(force_covered)
		billable_amount = 0 if covered else amount
		self.job.append(
			"charges",
			{
				"charge_type": charge_type if charge_type in COVERAGE_BY_CHARGE or charge_type in ("Mileage", "Airfare", "Freight", "Other") else "Other",
				"service_charge": service_charge,
				"item_code": item_code,
				"description": f"{charge_type} from {source_type}",
				"quantity": quantity,
				"rate": rate,
				"amount": amount,
				"covered": covered,
				"coverage_source": self.job.coverage_source,
				"billable": not covered,
				"billable_amount": billable_amount,
				"source_type": source_type,
				"source_document": source_document,
				"manually_added": 0,
			},
		)
		return internal_cost

	def _calculate_totals(self):
		labour_cost = sum((row.internal_cost or 0) for row in self.job.labour)
		parts_cost = sum((row.internal_cost or 0) for row in self.job.parts)
		expense_cost = sum(
			(row.approved_amount or row.amount or 0)
			for row in frappe.get_all("Service Expense", filters={"service_job": self.job.name, "approval_status": "Approved"}, fields=["amount", "approved_amount"])
		)
		self.job.total_internal_cost = labour_cost + parts_cost + expense_cost
		self.job.total_charge_before_coverage = sum((row.amount or 0) for row in self.job.charges)
		self.job.total_covered_amount = sum((row.amount or 0) for row in self.job.charges if row.covered)
		self.job.total_billable_amount = sum((row.billable_amount or 0) for row in self.job.charges)
		self.job.estimated_gross_margin = self.job.total_billable_amount - self.job.total_internal_cost
		self.job.estimated_margin_percentage = (
			(self.job.estimated_gross_margin / self.job.total_billable_amount) * 100 if self.job.total_billable_amount else 0
		)
