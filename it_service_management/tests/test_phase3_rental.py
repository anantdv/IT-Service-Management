from __future__ import annotations

from decimal import Decimal

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, get_first_day, get_last_day, nowdate

from it_service_management.rental_management.services.billing import RentalBillingEngine, RentalInvoiceService, calculate_proration
from it_service_management.rental_management.services.meter import RentalMeterBillingEngine
from it_service_management.service_contracts.services.entitlement import ServiceEntitlementEngine


class TestRentalCalculations(FrappeTestCase):
	def test_meter_allowance_boundaries(self):
		below = RentalMeterBillingEngine.calculate_meter("BW", 1000, 1500, 1000, "0.08")
		equal = RentalMeterBillingEngine.calculate_meter("BW", 1000, 2000, 1000, "0.08")
		above = RentalMeterBillingEngine.calculate_meter("BW", 100000, 116822, 10000, "0.08")
		self.assertEqual(below["amount"], Decimal("0.00"))
		self.assertEqual(equal["billable"], Decimal("0"))
		self.assertEqual(above["billable"], Decimal("6822"))
		self.assertEqual(above["amount"], Decimal("545.76"))

	def test_bw_and_colour_example(self):
		bw = RentalMeterBillingEngine.calculate_meter("BW", 100000, 116822, 10000, "0.08")
		colour = RentalMeterBillingEngine.calculate_meter("COLOUR", 20000, 22480, 2000, "0.45")
		self.assertEqual(bw["amount"] + colour["amount"], Decimal("761.76"))

	def test_meter_reset_accounts_for_both_sides(self):
		result = RentalMeterBillingEngine.calculate_meter("BW", 9900, 250, 0, 1, {"previous_reading": 9999, "reset_reading": 0})
		self.assertEqual(result["usage"], Decimal("349"))

	def test_lower_meter_without_reset_is_rejected(self):
		self.assertRaises(frappe.ValidationError, RentalMeterBillingEngine.calculate_meter, "BW", 1000, 10, 0, 1)

	def test_proration_full_and_partial_periods(self):
		full = calculate_proration(1850, "2026-08-01", "2026-08-31", "2026-08-01", "2026-08-31", True)
		partial = calculate_proration(1850, "2026-08-01", "2026-08-30", "2026-08-16", "2026-08-30", True)
		final = calculate_proration(1850, "2026-08-01", "2026-08-31", "2026-08-01", "2026-08-15", True)
		self.assertEqual(full["amount"], Decimal("1850"))
		self.assertEqual(partial["amount"], Decimal("925.00"))
		self.assertEqual(final["billable_days"], 15)


class TestPhase3RentalLifecycle(FrappeTestCase):
	def setUp(self):
		self.company = frappe.defaults.get_user_default("Company") or frappe.get_all("Company", pluck="name")[0]
		self.currency = frappe.db.get_value("Company", self.company, "default_currency")
		self.customer = self._make_customer()
		self.site = frappe.get_doc({"doctype": "Customer Site", "customer": self.customer, "site_name": "Head Office " + frappe.generate_hash(length=6)}).insert().name
		self.asset_category = self._get_asset_category()
		self.location = self._get_location()
		self.item = self._make_fixed_asset_item()
		self.asset = self._make_asset()
		self.plan = self._make_plan()
		self._ensure_meter_types()

	def test_invalid_contract_dates(self):
		doc = self._contract_doc()
		doc["end_date"] = add_days(doc["start_date"], -1)
		self.assertRaises(frappe.ValidationError, frappe.get_doc(doc).insert)

	def test_deployment_creates_customer_equipment_and_blocks_duplicate_asset(self):
		contract = self._make_active_contract()
		deployment = self._deploy(contract)
		equipment = frappe.get_doc("Customer Equipment", deployment.items[0].customer_equipment)
		self.assertEqual(equipment.asset, self.asset)
		self.assertEqual(equipment.ownership_type, "Company Rental Asset")
		self.assertEqual(equipment.rental_contract, contract.name)
		duplicate = self._contract_doc()
		duplicate["status"] = "Active"
		duplicate["approved_by"] = "Administrator"
		duplicate["equipment"] = [{"asset": self.asset, "item_code": self.item, "deployment_status": "Deployed"}]
		self.assertRaises(frappe.ValidationError, frappe.get_doc(duplicate).insert)

	def test_rental_entitlement_precedes_warranty(self):
		contract = self._make_active_contract()
		deployment = self._deploy(contract)
		equipment = frappe.get_doc("Customer Equipment", deployment.items[0].customer_equipment)
		equipment.warranty_start_date = nowdate()
		equipment.warranty_end_date = add_days(nowdate(), 30)
		equipment.save()
		result = ServiceEntitlementEngine({"customer": self.customer, "customer_equipment": equipment.name, "service_date": nowdate()}).evaluate()
		self.assertEqual(result["coverage_source"], "Rental Contract")
		self.assertTrue(result["labour_covered"])
		self.assertTrue(result["parts_covered"])
		self.assertFalse(result["travel_covered"])

	def test_meter_reading_and_duplicate_period(self):
		contract = self._make_active_contract()
		deployment = self._deploy(contract)
		equipment = deployment.items[0].customer_equipment
		period_from = get_first_day(nowdate())
		period_to = get_last_day(nowdate())
		reading = frappe.get_doc({"doctype": "Equipment Meter Reading", "customer_equipment": equipment, "rental_contract": contract.name, "reading_date": period_to, "billing_period_from": period_from, "billing_period_to": period_to, "submission_source": "Service Desk", "verified": 1, "details": [{"meter_type": "BW", "current_reading": 116822}, {"meter_type": "COLOUR", "current_reading": 22480}]}).insert()
		self.assertEqual(Decimal(str(reading.total_meter_charge)), Decimal("761.76"))
		duplicate = frappe.copy_doc(reading)
		self.assertRaises(frappe.ValidationError, duplicate.insert)

	def test_billing_run_is_idempotent_and_matches_manual_scenario(self):
		contract = self._make_active_contract()
		deployment = self._deploy(contract)
		equipment = deployment.items[0].customer_equipment
		period_from = get_first_day(nowdate()); period_to = get_last_day(nowdate())
		frappe.get_doc({"doctype": "Equipment Meter Reading", "customer_equipment": equipment, "rental_contract": contract.name, "reading_date": period_to, "billing_period_from": period_from, "billing_period_to": period_to, "submission_source": "Service Desk", "verified": 1, "details": [{"meter_type": "BW", "current_reading": 116822}, {"meter_type": "COLOUR", "current_reading": 22480}]}).insert()
		frappe.get_doc({"doctype": "Rental Ad-Hoc Charge", "rental_contract": contract.name, "customer": self.customer, "customer_equipment": equipment, "description": "Additional Toner", "component_type": "Consumables", "quantity": 1, "rate": 320, "status": "Approved"}).insert()
		frappe.get_doc({"doctype": "Service Job", "customer": self.customer, "customer_site": self.site, "customer_equipment": equipment, "rental_contract": contract.name, "job_type": "Rental Support", "priority": "Medium", "charges": [{"charge_type": "Travel", "description": "Travel", "quantity": 1, "rate": 80, "amount": 80, "billable": 1, "billable_amount": 80, "manually_added": 1}]}).insert()
		run = frappe.get_doc({"doctype": "Rental Billing Run", "company": self.company, "billing_period_from": period_from, "billing_period_to": period_to, "posting_date": period_to, "billing_mode": "Consolidated Billing"}).insert()
		RentalBillingEngine(run).prepare()
		run.reload()
		self.assertEqual(Decimal(str(run.total_billed)), Decimal("3011.76"))
		first_count = frappe.db.count("Rental Billing Reference", {"billing_run": run.name, "status": "Reserved"})
		RentalBillingEngine(run).prepare()
		run.reload()
		self.assertEqual(frappe.db.count("Rental Billing Reference", {"billing_run": run.name, "status": "Reserved"}), first_count)
		self.assertEqual(Decimal(str(run.total_billed)), Decimal("3011.76"))

	def _contract_doc(self):
		return {"doctype": "Rental Contract", "company": self.company, "customer": self.customer, "customer_site": self.site, "rental_plan": self.plan, "start_date": get_first_day(nowdate()), "end_date": add_days(get_first_day(nowdate()), 365), "contract_term_months": 12, "currency": self.currency, "billing_frequency": "Monthly", "billing_day": 1, "billing_start_rule": "Deployment Date", "base_rental_amount": 1850, "meter_billing_enabled": 1, "included_bw_pages": 10000, "included_colour_pages": 2000, "excess_bw_rate": "0.08", "excess_colour_rate": "0.45", "status": "Draft", "equipment": [{"asset": self.asset, "item_code": self.item, "deployment_status": "Reserved", "meter_billing_enabled": 1, "included_bw_pages": 10000, "included_colour_pages": 2000, "excess_bw_rate": "0.08", "excess_colour_rate": "0.45"}]}

	def _make_active_contract(self):
		values = self._contract_doc(); values.update({"status": "Active", "approved_by": "Administrator"})
		return frappe.get_doc(values).insert()

	def _deploy(self, contract):
		deployment = frappe.get_doc({"doctype": "Rental Deployment", "rental_contract": contract.name, "customer": self.customer, "customer_site": self.site, "deployment_date": get_first_day(nowdate()), "status": "In Progress", "items": [{"asset": self.asset, "item_code": self.item, "initial_bw_meter": 100000, "initial_colour_meter": 20000}]}).insert()
		deployment.complete_deployment()
		return deployment

	def _make_customer(self):
		name = "ITSM Rental " + frappe.generate_hash(length=8)
		return frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company"}).insert().name

	def _get_asset_category(self):
		existing = frappe.get_all("Asset Category", pluck="name", limit=1)
		if existing: return existing[0]
		name = "ITSM Rental Assets " + frappe.generate_hash(length=6)
		return frappe.get_doc({"doctype": "Asset Category", "asset_category_name": name}).insert().name

	def _get_location(self):
		existing = frappe.get_all("Location", pluck="name", limit=1)
		if existing: return existing[0]
		return frappe.get_doc({"doctype": "Location", "location_name": "ITSM Rental " + frappe.generate_hash(length=6)}).insert().name

	def _make_fixed_asset_item(self):
		code = "ITSM-RENT-" + frappe.generate_hash(length=8)
		frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": "All Item Groups", "is_stock_item": 0, "is_fixed_asset": 1, "auto_create_assets": 0, "asset_category": self.asset_category}).insert()
		return code

	def _make_asset(self):
		return frappe.get_doc({"doctype": "Asset", "asset_name": "ITSM Rental Asset " + frappe.generate_hash(length=8), "item_code": self.item, "asset_category": self.asset_category, "company": self.company, "purchase_date": nowdate(), "available_for_use_date": nowdate(), "gross_purchase_amount": 10000, "location": self.location, "is_existing_asset": 1, "calculate_depreciation": 0}).insert().name

	def _make_plan(self):
		name = "ITSM Rental Plan " + frappe.generate_hash(length=8)
		return frappe.get_doc({"doctype": "Rental Plan", "plan_name": name, "company": self.company, "billing_frequency": "Monthly", "standard_term_months": 12, "base_rental_rate": 1850, "included_bw_pages": 10000, "included_colour_pages": 2000, "excess_bw_rate": "0.08", "excess_colour_rate": "0.45", "labour_covered": 1, "parts_covered": 1, "travel_covered": 0, "active": 1}).insert().name

	def _ensure_meter_types(self):
		for code, name in (("BW", "B&W"), ("COLOUR", "Colour")):
			if not frappe.db.exists("Equipment Meter Type", code):
				frappe.get_doc({"doctype": "Equipment Meter Type", "meter_code": code, "meter_name": name, "cumulative": 1, "active": 1}).insert()
