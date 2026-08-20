from __future__ import annotations

import frappe
from frappe.utils import nowdate


class ServiceChargeEngine:
	def __init__(self, job):
		self.job = job

	def get_rule(self, charge_type):
		conditions = {"active": 1}
		today = nowdate()
		rows = frappe.get_all(
			"Service Charge Rule",
			filters=conditions,
			fields=[
				"name",
				"service_charge",
				"company",
				"customer",
				"service_zone",
				"ticket_type",
				"job_type",
				"technician_level",
				"effective_from",
				"effective_to",
				"priority",
				"calculation_method",
				"rate",
				"markup_percentage",
			],
			order_by="priority desc, modified desc",
		)
		for row in rows:
			charge = frappe.db.get_value("Service Charge", row.service_charge, "charge_type")
			if charge != charge_type:
				continue
			if row.customer and row.customer != self.job.customer:
				continue
			if row.service_zone and row.service_zone != self.job.service_zone:
				continue
			if row.job_type and row.job_type != self.job.job_type:
				continue
			if row.effective_from and row.effective_from > today:
				continue
			if row.effective_to and row.effective_to < today:
				continue
			return row
		return None

	def calculate_amount(self, charge_type, quantity=1, actual_cost=0):
		rule = self.get_rule(charge_type)
		if not rule:
			return None
		rate = rule.rate or 0
		if rule.calculation_method == "Actual Cost":
			rate = actual_cost
		elif rule.calculation_method == "Cost Plus Percentage":
			rate = actual_cost + (actual_cost * (rule.markup_percentage or 0) / 100)
		return {
			"service_charge": rule.service_charge,
			"quantity": quantity,
			"rate": rate,
			"amount": rate * quantity,
			"calculation_method": rule.calculation_method,
		}
