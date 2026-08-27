from __future__ import annotations

import frappe
from frappe.utils import cint, flt, fmt_money

from it_service_management.service_operations.services.charges import ServiceChargeEngine
from it_service_management.service_billing.services.credit import check_customer_credit


COVERAGE_BY_CHARGE = {
	"Labour": "labour_covered",
	"Part": "parts_covered",
	"Travel": "travel_covered",
	"Food": "food_covered",
	"Accommodation": "accommodation_covered",
	"Callout": "callout_covered",
	"Installation": "installation_covered",
	"Remote Support": "remote_support_covered",
	"Airfare": "airfare_covered",
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
		if self.job.total_billable_amount:
			company = frappe.db.get_value("Service Contract", self.job.service_contract, "company") if self.job.service_contract else frappe.defaults.get_user_default("Company")
			if company:
				check_customer_credit(self.job.customer, company, self.job.total_billable_amount, allow_block=True)
		self.job.billing_status = "Ready for Billing" if self.job.total_billable_amount else "Not Applicable"
		self.job.add_comment("Comment", "Billing calculated")
		self.job.save()
		return self.job

	def _clear_generated_charges(self):
		self.job.set("charges", [row for row in self.job.charges if row.manually_added])

	def _append_expenses(self):
		zone = self._get_service_zone()
		expenses = frappe.get_all(
			"Service Expense",
			filters={"service_job": self.job.name, "approval_status": "Approved"},
			fields=[
				"name",
				"expense_type",
				"amount",
				"actual_expense_amount",
				"approved_amount",
				"approved_reimbursement_amount",
				"customer_billable_amount",
				"customer_billing_method",
				"billing_rule_source",
				"billing_rule_reference",
				"covered_by_contract",
				"billable_to_customer",
			],
		)
		for expense in expenses:
			if not expense.billable_to_customer or not flt(expense.customer_billable_amount):
				continue
			if self._expense_is_handled_by_zone_allowance(expense, zone):
				continue
			charge_type = "Travel" if expense.expense_type in ("Transportation", "Mileage", "Taxi", "Parking") else expense.expense_type
			amount = expense.customer_billable_amount or 0
			internal_cost = expense.actual_expense_amount or expense.amount or expense.approved_reimbursement_amount or expense.approved_amount or 0
			description = self._expense_description(charge_type, expense)
			self._append_charge(charge_type, amount, 1, internal_cost, "Service Expense", expense.name, force_covered=expense.covered_by_contract, description=description)

	def _append_zone_charges(self):
		engine = ServiceChargeEngine(self.job)
		for charge_type, qty in (("Callout", self._callout_quantity()), ("Travel", self._travel_quantity()), ("Installation", self._installation_quantity())):
			calculated = engine.calculate_amount(charge_type, qty)
			if calculated:
				self._append_charge(
					charge_type,
					calculated["rate"],
					calculated["quantity"],
					0,
					"Service Charge Rule",
					calculated["service_charge"],
					service_charge=calculated["service_charge"],
					description=self._calculation_description(charge_type, calculated["quantity"], calculated["rate"], self._basis_for_rule(charge_type)),
				)
			else:
				self._append_service_zone_default(charge_type, qty)

		zone = self._get_service_zone()
		if not zone:
			return
		self._append_zone_amount("Mileage", flt(self.job.get("chargeable_distance_km")), flt(zone.per_km_charge), "KM", engine)
		self._append_food_charge(zone)
		self._append_accommodation_charge(zone)
		self._append_airfare_charge(zone)

	def _append_charge(self, charge_type, rate, quantity, internal_cost, source_type, source_document, item_code=None, service_charge=None, force_covered=None, description=None):
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
				"description": description or f"{charge_type} from {source_type}",
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

	def _get_service_zone(self):
		if not self.job.service_zone or not frappe.db.exists("Service Zone", self.job.service_zone):
			return None
		zone = frappe.get_cached_doc("Service Zone", self.job.service_zone)
		return zone if cint(zone.get("active", 1)) else None

	def _append_service_zone_default(self, charge_type, quantity):
		zone = self._get_service_zone()
		if not zone:
			return
		rate_by_type = {
			"Callout": flt(zone.default_callout_charge),
			"Travel": flt(zone.default_travel_charge),
			"Installation": flt(zone.default_installation_charge),
		}
		rate = rate_by_type.get(charge_type, 0)
		if rate and quantity:
			self._append_charge(
				charge_type,
				rate,
				quantity,
				0,
				"Service Zone",
				zone.name,
				description=self._calculation_description(charge_type, quantity, rate, self._zone_basis(zone, charge_type)),
			)

	def _append_zone_amount(self, charge_type, quantity, rate, basis, engine=None, description=None):
		engine = engine or ServiceChargeEngine(self.job)
		calculated = engine.calculate_amount(charge_type, quantity, actual_cost=rate)
		if calculated:
			self._append_charge(
				charge_type,
				calculated["rate"],
				calculated["quantity"],
				0,
				"Service Charge Rule",
				calculated["service_charge"],
				service_charge=calculated["service_charge"],
				description=description or self._calculation_description(charge_type, calculated["quantity"], calculated["rate"], basis),
			)
			return
		if rate and quantity:
			self._append_charge(charge_type, rate, quantity, 0, "Service Zone", self.job.service_zone, description=description or self._calculation_description(charge_type, quantity, rate, basis))

	def _append_food_charge(self, zone):
		if self._has_approved_expense("Food"):
			return
		method = zone.get("food_billing_method") or "Fixed Allowance"
		if method != "Fixed Allowance":
			return
		basis = zone.get("food_charge_basis") or "Per Technician / Day"
		quantity = self._allowance_quantity(basis, "day")
		description = self._allowance_description("Food Allowance", basis, flt(zone.food_allowance), "day")
		self._append_zone_amount("Food", quantity, flt(zone.food_allowance), basis, description=description)

	def _append_accommodation_charge(self, zone):
		if self._has_approved_expense("Accommodation"):
			return
		method = zone.get("accommodation_billing_method") or "Fixed Allowance"
		if method != "Fixed Allowance":
			return
		rate = flt(zone.get("accommodation_allowance") or zone.get("accommodation_charge"))
		basis = zone.get("accommodation_charge_basis") or "Per Technician / Night"
		quantity = self._allowance_quantity(basis, "night")
		description = self._allowance_description("Accommodation Allowance", basis, rate, "night")
		self._append_zone_amount("Accommodation", quantity, rate, basis, description=description)

	def _append_airfare_charge(self, zone):
		if self._has_approved_expense("Airfare"):
			return
		method = zone.get("airfare_billing_method") or ("Actual Cost" if cint(zone.get("airfare_actual")) else "Not Chargeable")
		if method == "Fixed Charge":
			self._append_zone_amount("Airfare", 1, flt(zone.get("airfare_fixed_charge")), "Fixed Charge")

	def _expense_is_handled_by_zone_allowance(self, expense, zone):
		if not zone or flt(expense.customer_billable_amount):
			return False
		expense_type = expense.expense_type
		if expense_type == "Food":
			return (zone.get("food_billing_method") or "Fixed Allowance") != "Actual Cost"
		if expense_type == "Accommodation":
			return (zone.get("accommodation_billing_method") or "Fixed Allowance") != "Actual Cost"
		if expense_type == "Airfare":
			return (zone.get("airfare_billing_method") or ("Actual Cost" if cint(zone.get("airfare_actual")) else "Not Chargeable")) != "Actual Cost"
		return False

	def _has_approved_expense(self, expense_type):
		return bool(
			frappe.db.exists(
				"Service Expense",
				{
					"service_job": self.job.name,
					"expense_type": expense_type,
					"approval_status": "Approved",
				},
			)
		)

	def _expense_description(self, charge_type, expense):
		method = expense.customer_billing_method or "Actual Cost"
		if expense.billing_rule_source and expense.billing_rule_reference:
			return f"{charge_type} - {expense.billing_rule_source} {expense.billing_rule_reference}: {self._format_money(expense.customer_billable_amount)}"
		if method == "Actual Cost":
			return f"{charge_type} - Actual Cost from approved Service Expense {expense.name}: {self._format_money(expense.customer_billable_amount)}"
		return f"{charge_type} - {method} from approved Service Expense {expense.name}: {self._format_money(expense.customer_billable_amount)}"

	def _callout_quantity(self):
		return 1

	def _travel_quantity(self):
		zone = self._get_service_zone()
		basis = zone.get("travel_charge_basis") if zone else "Per Trip"
		if basis == "Per Technician":
			return self._technician_count()
		return cint(self.job.get("chargeable_trips")) or 1

	def _installation_quantity(self):
		zone = self._get_service_zone()
		basis = zone.get("installation_charge_basis") if zone else "Per Installation"
		if basis == "Per Equipment":
			return 1 if self.job.customer_equipment else 0
		return 1 if self.job.job_type == "Installation" else 0

	def _allowance_quantity(self, basis, unit):
		technicians = self._technician_count()
		if unit == "night":
			units = cint(self.job.get("chargeable_nights"))
		else:
			units = cint(self.job.get("chargeable_travel_days")) or 1
		if basis in ("Per Day", "Per Night", "Per Job"):
			return units if basis != "Per Job" else 1
		return technicians * units

	def _technician_count(self):
		if cint(self.job.get("chargeable_technician_count")):
			return cint(self.job.get("chargeable_technician_count"))
		technicians = {row.employee for row in self.job.labour if row.employee}
		for fieldname in ("assigned_technician", "backup_technician"):
			if self.job.get(fieldname):
				technicians.add(self.job.get(fieldname))
		return len(technicians) or 1

	def _zone_basis(self, zone, charge_type):
		return {
			"Callout": zone.get("callout_charge_basis") or "Per Visit",
			"Travel": zone.get("travel_charge_basis") or "Per Trip",
			"Installation": zone.get("installation_charge_basis") or "Per Installation",
		}.get(charge_type, "")

	def _basis_for_rule(self, charge_type):
		return {"Callout": "Per Visit", "Travel": "Per Trip", "Installation": "Per Installation"}.get(charge_type, "")

	def _calculation_description(self, charge_type, quantity, rate, basis):
		label_by_type = {"Mileage": "Mileage", "Food": "Food Allowance", "Accommodation": "Accommodation Allowance"}.get(charge_type, charge_type)
		return f"{label_by_type}: {flt(quantity):g} {basis} x {self._format_money(rate)}"

	def _allowance_description(self, label, basis, rate, unit):
		technicians = self._technician_count()
		units = cint(self.job.get("chargeable_nights")) if unit == "night" else (cint(self.job.get("chargeable_travel_days")) or 1)
		if basis in ("Per Technician / Day", "Per Technician / Night"):
			unit_label = "Nights" if unit == "night" else "Days"
			return f"{label}: {technicians} Technicians x {units} {unit_label} x {self._format_money(rate)}"
		if basis in ("Per Day", "Per Night"):
			unit_label = "Nights" if unit == "night" else "Days"
			return f"{label}: {units} {unit_label} x {self._format_money(rate)}"
		return f"{label}: 1 Job x {self._format_money(rate)}"

	def _format_money(self, value):
		company = frappe.db.get_value("Service Contract", self.job.service_contract, "company") if self.job.service_contract else frappe.defaults.get_user_default("Company")
		currency = frappe.db.get_value("Company", company, "default_currency") if company else None
		return fmt_money(value, currency=currency)

	def _calculate_totals(self):
		labour_cost = sum((row.internal_cost or 0) for row in self.job.labour)
		parts_cost = self._actual_parts_cost()
		expense_cost = sum(
			(row.actual_expense_amount or row.amount or row.approved_reimbursement_amount or row.approved_amount or 0)
			for row in frappe.get_all("Service Expense", filters={"service_job": self.job.name, "approval_status": "Approved"}, fields=["amount", "actual_expense_amount", "approved_amount", "approved_reimbursement_amount"])
		)
		self.job.labour_cost = labour_cost
		self.job.parts_cost = parts_cost
		self.job.expense_cost = expense_cost
		self.job.other_cost = 0
		self.job.total_internal_cost = labour_cost + parts_cost + expense_cost
		self.job.total_charge_before_coverage = sum((row.amount or 0) for row in self.job.charges)
		self.job.total_covered_amount = sum((row.amount or 0) for row in self.job.charges if row.covered)
		self.job.total_billable_amount = sum((row.billable_amount or 0) for row in self.job.charges)
		self.job.estimated_gross_margin = self.job.total_billable_amount - self.job.total_internal_cost
		self.job.estimated_margin_percentage = (
			(self.job.estimated_gross_margin / self.job.total_billable_amount) * 100 if self.job.total_billable_amount else 0
		)

	def _actual_parts_cost(self):
		stock_entries = sorted({row.stock_entry for row in self.job.parts if row.stock_entry})
		actual = {}
		if stock_entries:
			rows = frappe.db.sql(
				"""
				select sed.parent, sed.item_code, sum(abs(ifnull(sed.basic_amount, 0))) amount
				from `tabStock Entry Detail` sed
				inner join `tabStock Entry` se on se.name = sed.parent and se.docstatus = 1
				where sed.parent in %(stock_entries)s
				group by sed.parent, sed.item_code
				""",
				{"stock_entries": stock_entries},
				as_dict=True,
			)
			actual = {(row.parent, row.item_code): row.amount for row in rows}
		total = 0
		counted_stock_keys = set()
		for row in self.job.parts:
			key = (row.stock_entry, row.item_code)
			if row.stock_entry and key in actual:
				if key not in counted_stock_keys:
					total += actual[key]
					counted_stock_keys.add(key)
			else:
				total += row.internal_cost or 0
		return total
