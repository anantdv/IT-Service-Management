from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from it_service_management.service_contracts.services.entitlement import ServiceEntitlementEngine


class TestServiceEntitlementEngine(FrappeTestCase):
	def setUp(self):
		self.customer = self._make_customer()
		self.company = frappe.defaults.get_user_default("Company") or frappe.get_all("Company", pluck="name")[0]
		self.item = self._make_item()

	def test_no_coverage(self):
		equipment = self._make_equipment()
		result = ServiceEntitlementEngine(
			{"customer": self.customer, "customer_equipment": equipment.name, "service_date": nowdate()}
		).evaluate()

		self.assertEqual(result["coverage_source"], "No Coverage")
		self.assertFalse(result["labour_covered"])

	def test_warranty_coverage(self):
		policy = frappe.get_doc(
			{
				"doctype": "Warranty Policy",
				"policy_name": frappe.generate_hash(length=10),
				"duration_months": 12,
				"item_code": self.item,
				"labour_covered": 1,
				"parts_covered": 1,
				"travel_covered": 0,
			}
		).insert()
		equipment = self._make_equipment(
			warranty_policy=policy.name,
			warranty_start_date=nowdate(),
			warranty_end_date=add_days(nowdate(), 30),
		)

		result = ServiceEntitlementEngine(
			{"customer": self.customer, "customer_equipment": equipment.name, "service_date": nowdate()}
		).evaluate()

		self.assertEqual(result["coverage_source"], "Warranty")
		self.assertTrue(result["labour_covered"])
		self.assertTrue(result["parts_covered"])
		self.assertFalse(result["travel_covered"])

	def test_amc_contract_takes_priority_over_warranty(self):
		policy = frappe.get_doc(
			{
				"doctype": "Warranty Policy",
				"policy_name": frappe.generate_hash(length=10),
				"duration_months": 12,
				"item_code": self.item,
				"labour_covered": 1,
				"parts_covered": 0,
			}
		).insert()
		equipment = self._make_equipment(
			warranty_policy=policy.name,
			warranty_start_date=nowdate(),
			warranty_end_date=add_days(nowdate(), 30),
		)
		plan = frappe.get_doc(
			{
				"doctype": "Service Plan",
				"plan_name": frappe.generate_hash(length=10),
				"plan_type": "AMC",
				"labour_covered": 1,
				"parts_covered": 1,
				"travel_covered": 0,
			}
		).insert()
		contract = frappe.get_doc(
			{
				"doctype": "Service Contract",
				"customer": self.customer,
				"company": self.company,
				"contract_type": "AMC",
				"service_plan": plan.name,
				"start_date": nowdate(),
				"end_date": add_days(nowdate(), 30),
				"contract_status": "Active",
				"covered_equipment": [{"customer_equipment": equipment.name, "active": 1}],
			}
		).insert()

		result = ServiceEntitlementEngine(
			{"customer": self.customer, "customer_equipment": equipment.name, "service_date": nowdate()}
		).evaluate()

		self.assertEqual(result["coverage_source"], "AMC")
		self.assertEqual(result["coverage_document"], contract.name)
		self.assertTrue(result["parts_covered"])

	def test_expired_contract_is_ignored(self):
		equipment = self._make_equipment()
		plan = frappe.get_doc(
			{
				"doctype": "Service Plan",
				"plan_name": frappe.generate_hash(length=10),
				"plan_type": "AMC",
				"labour_covered": 1,
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Service Contract",
				"customer": self.customer,
				"company": self.company,
				"contract_type": "AMC",
				"service_plan": plan.name,
				"start_date": add_days(nowdate(), -60),
				"end_date": add_days(nowdate(), -1),
				"contract_status": "Expired",
				"covered_equipment": [{"customer_equipment": equipment.name, "active": 1}],
			}
		).insert()

		result = ServiceEntitlementEngine(
			{"customer": self.customer, "customer_equipment": equipment.name, "service_date": nowdate()}
		).evaluate()

		self.assertEqual(result["coverage_source"], "No Coverage")

	def _make_customer(self):
		name = "Test ITSM Customer " + frappe.generate_hash(length=8)
		return frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company"}).insert().name

	def _make_item(self):
		item_code = "ITSM-" + frappe.generate_hash(length=8)
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"item_group": "All Item Groups",
				"is_stock_item": 1,
			}
		).insert()
		return item_code

	def _make_equipment(self, **kwargs):
		doc = {
			"doctype": "Customer Equipment",
			"customer": self.customer,
			"item_code": self.item,
			"ownership_type": "Customer Owned",
			"equipment_status": "Operational",
		}
		doc.update(kwargs)
		return frappe.get_doc(doc).insert()
