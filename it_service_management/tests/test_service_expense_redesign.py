from decimal import Decimal
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate


class TestServiceExpenseRedesign(FrappeTestCase):
	def setUp(self):
		self._ensure_uoms()
		self.customer = self._make_customer()
		self.employee = self._make_employee()
		self.zone = self._make_zone()
		self.job = self._make_job(self.zone.name)

	def test_hotel_expense_separates_actual_reimbursement_and_customer_recovery(self):
		expense = self._make_expense("Accommodation", quantity=2, rate=310)
		self.assertEqual(Decimal(str(expense.actual_expense_amount)), Decimal("620"))
		self.assertEqual(Decimal(str(expense.employee_claimed_amount)), Decimal("620"))
		self.assertEqual(Decimal(str(expense.approved_reimbursement_amount)), Decimal("620"))
		self.assertEqual(expense.customer_billing_method, "Service Zone Rate")
		self.assertEqual(Decimal(str(expense.customer_billing_quantity)), Decimal("2"))
		self.assertEqual(Decimal(str(expense.customer_billing_rate)), Decimal("250"))
		self.assertEqual(Decimal(str(expense.customer_billable_amount)), Decimal("500"))

	def test_covered_accommodation_has_no_customer_billable_amount(self):
		self.job.accommodation_covered = 1
		self.job.save()
		expense = self._make_expense("Accommodation", quantity=2, rate=310, coverage_source="AMC")
		self.assertEqual(Decimal(str(expense.actual_expense_amount)), Decimal("620"))
		self.assertEqual(Decimal(str(expense.approved_reimbursement_amount)), Decimal("620"))
		self.assertTrue(expense.covered_by_contract)
		self.assertEqual(expense.customer_billing_method, "Not Billable")
		self.assertEqual(Decimal(str(expense.customer_billable_amount)), Decimal("0"))

	def test_airfare_actual_cost_is_customer_billable(self):
		expense = self._make_expense("Airfare", quantity=2, rate=700)
		self.assertEqual(Decimal(str(expense.actual_expense_amount)), Decimal("1400"))
		self.assertEqual(expense.customer_billing_method, "Actual Cost")
		self.assertEqual(Decimal(str(expense.customer_billable_amount)), Decimal("1400"))

	def test_company_paid_airfare_is_not_reimbursable_but_still_billable(self):
		expense = self._make_expense("Airfare", quantity=2, rate=700, paid_by="Company")
		self.assertFalse(expense.reimbursable_to_employee)
		self.assertEqual(Decimal(str(expense.approved_reimbursement_amount)), Decimal("0"))
		self.assertEqual(Decimal(str(expense.customer_billable_amount)), Decimal("1400"))

	def test_customer_direct_expense_is_not_reimbursable_or_billable(self):
		expense = self._make_expense("Taxi", quantity=1, rate=80, paid_by="Customer Direct")
		self.assertFalse(expense.reimbursable_to_employee)
		self.assertEqual(expense.customer_billing_method, "Not Billable")
		self.assertEqual(Decimal(str(expense.customer_billable_amount)), Decimal("0"))

	def _make_expense(self, expense_type, quantity, rate, paid_by="Employee", **overrides):
		data = {
			"doctype": "Service Expense",
			"service_job": self.job.name,
			"employee": self.employee,
			"expense_date": nowdate(),
			"expense_type": expense_type,
			"uom": {"Accommodation": "Night", "Food": "Day", "Airfare": "Ticket", "Taxi": "Trip"}.get(expense_type, "Each"),
			"quantity": quantity,
			"rate": rate,
			"paid_by": paid_by,
			"reimbursable_to_employee": 1 if paid_by == "Employee" else 0,
			"receipt": "/files/test-service-expense-receipt.pdf",
			"approval_status": "Approved",
		}
		data.update(overrides)
		with patch("it_service_management.service_operations.services.charges.ServiceChargeEngine.get_rule", return_value=None):
			return frappe.get_doc(data).insert(ignore_permissions=True)

	def _make_zone(self):
		return frappe.get_doc(
			{
				"doctype": "Service Zone",
				"zone_name": "ITSM Expense Zone " + frappe.generate_hash(length=8),
				"default_callout_charge": 250,
				"default_travel_charge": 350,
				"per_km_charge": 5,
				"food_billing_method": "Fixed Allowance",
				"food_allowance": 100,
				"food_charge_basis": "Per Technician / Day",
				"accommodation_billing_method": "Fixed Allowance",
				"accommodation_allowance": 250,
				"accommodation_charge_basis": "Per Technician / Night",
				"airfare_billing_method": "Actual Cost",
				"active": 1,
			}
		).insert(ignore_permissions=True)

	def _make_job(self, zone):
		return frappe.get_doc(
			{
				"doctype": "Service Job",
				"customer": self.customer,
				"job_type": "Onsite Support",
				"priority": "Medium",
				"status": "Completed",
				"service_zone": zone,
				"assigned_technician": self.employee,
				"coverage_source": "No Coverage",
				"chargeable_technician_count": 0,
			}
		).insert(ignore_permissions=True)

	def _make_customer(self):
		name = "ITSM Expense Customer " + frappe.generate_hash(length=8)
		return frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company"}).insert(ignore_permissions=True).name

	def _make_employee(self):
		employee_name = "ITSM Expense Tech " + frappe.generate_hash(length=8)
		return frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": employee_name,
				"employee_name": employee_name,
				"status": "Active",
				"date_of_joining": nowdate(),
				"is_service_technician": 1,
				"available_for_assignment": 1,
			}
		).insert(ignore_permissions=True).name

	def _ensure_uoms(self):
		for uom in ("Trip", "KM", "Ticket", "Night", "Day", "Each"):
			if not frappe.db.exists("UOM", uom):
				frappe.get_doc({"doctype": "UOM", "uom_name": uom, "enabled": 1}).insert(ignore_permissions=True)
