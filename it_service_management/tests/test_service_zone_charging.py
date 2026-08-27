from decimal import Decimal
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, nowdate

from it_service_management.service_operations.services.billing import ServiceBillingEngine


class TestServiceZoneCharging(FrappeTestCase):
	def setUp(self):
		self.customer = self._make_customer()
		self.employee = self._make_employee()

	def test_local_service_zone_charges_are_explicit(self):
		zone = self._make_zone()
		job = self._make_job(zone.name, chargeable_distance_km=20)
		with patch("it_service_management.service_operations.services.charges.ServiceChargeEngine.get_rule", return_value=None):
			ServiceBillingEngine(job).calculate()
		job.reload()
		self.assertEqual(Decimal(str(job.total_charge_before_coverage)), Decimal("800"))
		charges = {row.charge_type: row for row in job.charges}
		self.assertEqual(Decimal(str(charges["Callout"].amount)), Decimal("250"))
		self.assertEqual(Decimal(str(charges["Travel"].amount)), Decimal("350"))
		self.assertEqual(Decimal(str(charges["Mileage"].amount)), Decimal("100"))
		self.assertEqual(Decimal(str(charges["Food"].amount)), Decimal("100"))
		self.assertNotIn("Accommodation", charges)
		self.assertIn("20 KM", charges["Mileage"].description)
		self.assertIn("1 Technicians x 1 Days", charges["Food"].description)

	def test_remote_multi_day_visit_uses_allowances_and_actual_airfare(self):
		zone = self._make_zone()
		job = self._make_job(
			zone.name,
			chargeable_distance_km=48,
			chargeable_travel_days=3,
			chargeable_nights=2,
			chargeable_technician_count=2,
		)
		self._make_expense(job.name, "Airfare", 1400)
		with patch("it_service_management.service_operations.services.charges.ServiceChargeEngine.get_rule", return_value=None):
			ServiceBillingEngine(job).calculate()
		job.reload()
		self.assertEqual(Decimal(str(job.total_charge_before_coverage)), Decimal("3840"))
		charges = {row.charge_type: row for row in job.charges}
		self.assertEqual(Decimal(str(charges["Food"].amount)), Decimal("600"))
		self.assertEqual(Decimal(str(charges["Accommodation"].amount)), Decimal("1000"))
		self.assertEqual(Decimal(str(charges["Airfare"].amount)), Decimal("1400"))
		self.assertIn("2 Technicians x 3 Days", charges["Food"].description)
		self.assertIn("2 Technicians x 2 Nights", charges["Accommodation"].description)

	def test_actual_accommodation_does_not_add_fixed_allowance(self):
		zone = self._make_zone(accommodation_billing_method="Actual Cost")
		job = self._make_job(zone.name, chargeable_nights=2, chargeable_technician_count=2)
		self._make_expense(job.name, "Accommodation", 780)
		with patch("it_service_management.service_operations.services.charges.ServiceChargeEngine.get_rule", return_value=None):
			ServiceBillingEngine(job).calculate()
		job.reload()
		accommodation = [row for row in job.charges if row.charge_type == "Accommodation"]
		self.assertEqual(len(accommodation), 1)
		self.assertEqual(Decimal(str(accommodation[0].amount)), Decimal("780"))

	def test_entitlement_coverage_applies_after_gross_zone_charge(self):
		zone = self._make_zone()
		job = self._make_job(zone.name, chargeable_distance_km=48, chargeable_travel_days=3, chargeable_nights=2, chargeable_technician_count=2)
		job.coverage_source = "AMC"
		job.callout_covered = 1
		job.travel_covered = 1
		self._make_expense(job.name, "Airfare", 1400)
		with patch("it_service_management.service_operations.services.charges.ServiceChargeEngine.get_rule", return_value=None):
			ServiceBillingEngine(job).calculate()
		job.reload()
		charges = {row.charge_type: row for row in job.charges}
		self.assertTrue(charges["Callout"].covered)
		self.assertTrue(charges["Travel"].covered)
		self.assertFalse(charges["Mileage"].covered)
		self.assertFalse(charges["Food"].covered)
		self.assertFalse(charges["Accommodation"].covered)
		self.assertFalse(charges["Airfare"].covered)

	def _make_zone(self, **overrides):
		data = {
			"doctype": "Service Zone",
			"zone_name": "ITSM Zone " + frappe.generate_hash(length=8),
			"default_callout_charge": 250,
			"callout_charge_basis": "Per Visit",
			"default_travel_charge": 350,
			"travel_charge_basis": "Per Trip",
			"default_installation_charge": 500,
			"installation_charge_basis": "Per Installation",
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
		data.update(overrides)
		return frappe.get_doc(data).insert(ignore_permissions=True)

	def _make_job(self, zone, **overrides):
		data = {
			"doctype": "Service Job",
			"customer": self.customer,
			"job_type": "Onsite Support",
			"priority": "Medium",
			"status": "Completed",
			"service_zone": zone,
			"assigned_technician": self.employee,
			"completion_datetime": now_datetime(),
			"coverage_source": "Customer Payable",
			"chargeable_trips": 1,
			"chargeable_distance_km": 0,
			"chargeable_travel_days": 1,
			"chargeable_nights": 0,
			"chargeable_technician_count": 0,
		}
		data.update(overrides)
		return frappe.get_doc(data).insert(ignore_permissions=True)

	def _make_expense(self, service_job, expense_type, amount):
		return frappe.get_doc(
			{
				"doctype": "Service Expense",
				"service_job": service_job,
				"employee": self.employee,
				"expense_date": nowdate(),
				"expense_type": expense_type,
				"quantity": 1,
				"rate": amount,
				"amount": amount,
				"approved_amount": amount,
				"customer_billable_amount": amount,
				"billable_to_customer": 1,
				"approval_status": "Approved",
			}
		).insert(ignore_permissions=True)

	def _make_customer(self):
		name = "ITSM Zone Customer " + frappe.generate_hash(length=8)
		return frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company"}).insert(ignore_permissions=True).name

	def _make_employee(self):
		employee_name = "ITSM Zone Tech " + frappe.generate_hash(length=8)
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
