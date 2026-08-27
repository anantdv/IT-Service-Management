from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime, nowdate

from it_service_management.analytics.reporting.reports import revenue_leakage
from it_service_management.rental_management.services.billing import RentalInvoiceService
from it_service_management.service_billing.services.batch import ServiceBillingBatchEngine, ServiceInvoiceService
from it_service_management.service_contracts.services.renewal import create_renewal_opportunities
from it_service_management.service_operations.services.billing import ServiceBillingEngine


class TestPhase4FinanceControls(FrappeTestCase):
	def setUp(self):
		self.company = frappe.defaults.get_user_default("Company") or frappe.get_all("Company", pluck="name")[0]
		self.cost_center = frappe.db.get_value("Company", self.company, "cost_center") or frappe.get_all("Cost Center", filters={"company": self.company}, pluck="name", limit=1)[0]
		self.customer = self._make_customer()
		self.item = self._make_service_item()
		settings = frappe.get_single("IT Service Settings")
		settings.default_service_item = self.item
		settings.default_travel_item = self.item
		settings.default_accommodation_item = self.item
		settings.default_food_item = self.item
		settings.default_service_cost_center = self.cost_center
		settings.require_service_billing_approval = 1
		settings.require_rental_billing_approval = 1
		settings.auto_create_renewal_opportunity = 1
		settings.service_renewal_opportunity_days = 90
		settings.save(ignore_permissions=True)

	def test_service_batch_is_eligible_and_idempotent(self):
		job = self._make_job("Travel", 100)
		batch = self._make_batch()
		ServiceBillingBatchEngine(batch).prepare()
		batch.reload()
		self.assertEqual(batch.total_jobs, 1)
		self.assertEqual(Decimal(str(batch.total_billable)), Decimal("100"))
		first = frappe.db.count("Service Billing Reference", {"billing_batch": batch.name, "status": "Reserved"})
		ServiceBillingBatchEngine(batch).prepare()
		batch.reload()
		self.assertEqual(len(batch.details), 1)
		self.assertEqual(frappe.db.count("Service Billing Reference", {"billing_batch": batch.name, "status": "Reserved"}), first)
		self.assertEqual(batch.details[0].service_job, job.name)

	def test_service_invoice_requires_approval_and_cancel_reopens_job(self):
		job = self._make_job("Travel", 100)
		batch = self._make_batch()
		ServiceBillingBatchEngine(batch).prepare()
		batch.reload()
		self.assertRaises(frappe.ValidationError, ServiceInvoiceService(batch).generate)
		batch.status = "Approved for Billing"
		batch.approved_by = "Administrator"
		batch.approved_on = now_datetime()
		batch.save(ignore_permissions=True)
		ServiceInvoiceService(batch).generate()
		batch.reload()
		invoice = frappe.get_doc("Sales Invoice", batch.details[0].invoice)
		self.assertEqual(invoice.docstatus, 0)
		self.assertEqual(invoice.custom_service_billing_batch, batch.name)
		self.assertEqual(frappe.db.get_value("Service Job", job.name, "billing_status"), "Draft Invoice Created")
		invoice.delete()
		self.assertEqual(frappe.db.get_value("Service Job", job.name, "billing_status"), "Ready for Billing")
		self.assertFalse(frappe.db.exists("Service Billing Reference", {"service_job": job.name, "status": ["in", ["Reserved", "Draft Invoiced", "Submitted"]]}))

	def test_grouping_by_customer_creates_one_draft_invoice(self):
		self._make_job("Travel", 100)
		self._make_job("Accommodation", 350)
		batch = self._make_batch()
		ServiceBillingBatchEngine(batch).prepare()
		batch.reload()
		batch.status = "Approved for Billing"
		batch.approved_by = "Administrator"
		batch.approved_on = now_datetime()
		batch.save(ignore_permissions=True)
		ServiceInvoiceService(batch).generate()
		batch.reload()
		self.assertEqual(batch.invoices_created, 1)
		self.assertEqual(len({row.invoice for row in batch.details}), 1)

	def test_rental_billing_is_blocked_before_approval(self):
		run = frappe.get_doc({
			"doctype": "Rental Billing Run", "company": self.company, "billing_period_from": nowdate(),
			"billing_period_to": nowdate(), "posting_date": nowdate(), "billing_mode": "Consolidated Billing", "status": "Prepared",
		}).insert(ignore_permissions=True)
		self.assertRaises(frappe.ValidationError, RentalInvoiceService(run).generate)
		run.status = "Approved for Billing"
		run.approved_by = "Administrator"
		run.approved_on = now_datetime()
		run.save(ignore_permissions=True)
		RentalInvoiceService(run).generate()
		self.assertEqual(run.status, "Completed")

	def test_renewal_opportunity_is_created_once_and_creates_draft_contract(self):
		plan_name = "Phase 4 Plan " + frappe.generate_hash(length=8)
		plan = frappe.get_doc({"doctype": "Service Plan", "plan_name": plan_name, "plan_type": "AMC", "billing_frequency": "Yearly"}).insert()
		contract = frappe.get_doc({
			"doctype": "Service Contract", "customer": self.customer, "company": self.company, "contract_type": "AMC",
			"service_plan": plan.name, "start_date": add_days(nowdate(), -305), "end_date": add_days(nowdate(), 60),
			"contract_status": "Active", "billing_method": "Annual", "billing_amount": 24000,
		}).insert()
		create_renewal_opportunities()
		create_renewal_opportunities()
		self.assertEqual(frappe.db.count("Contract Renewal Opportunity", {"service_contract": contract.name}), 1)
		opportunity = frappe.get_doc("Contract Renewal Opportunity", {"service_contract": contract.name})
		opportunity.proposed_end_date = add_days(contract.end_date, 365)
		opportunity.save()
		result = opportunity.create_renewal_contract()
		renewal = frappe.get_doc(result["doctype"], result["name"])
		self.assertEqual(renewal.previous_service_contract, contract.name)
		self.assertEqual(renewal.contract_status, "Draft")
		self.assertEqual(frappe.db.get_value("Service Contract", contract.name, "contract_status"), "Active")

	def test_unbilled_service_is_reported_as_leakage(self):
		job = self._make_job("Travel", 80)
		columns, data = revenue_leakage(frappe._dict())
		self.assertTrue(columns)
		self.assertIn(job.name, [row[3] for row in data if row[0] == "Completed Unbilled Service"])

	def test_stock_valuation_is_not_counted_twice_for_duplicate_item_rows(self):
		job = frappe._dict(parts=[
			frappe._dict(stock_entry="STE-TEST", item_code="PART-1", internal_cost=40),
			frappe._dict(stock_entry="STE-TEST", item_code="PART-1", internal_cost=60),
		])
		actual = [frappe._dict(parent="STE-TEST", item_code="PART-1", amount=100)]
		with patch.object(frappe.db, "sql", return_value=actual):
			self.assertEqual(ServiceBillingEngine(job)._actual_parts_cost(), 100)

	def _make_customer(self):
		name = "ITSM Phase 4 " + frappe.generate_hash(length=8)
		return frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company"}).insert().name

	def _make_service_item(self):
		code = "ITSM-SVC-" + frappe.generate_hash(length=8)
		return frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": "All Item Groups", "is_stock_item": 0, "is_sales_item": 1}).insert().name

	def _make_job(self, charge_type, amount):
		return frappe.get_doc({
			"doctype": "Service Job", "customer": self.customer, "job_type": "Onsite Support", "priority": "Medium",
			"status": "Completed", "completion_datetime": now_datetime(), "coverage_source": "Customer Payable",
			"billing_status": "Ready for Billing", "total_charge_before_coverage": amount, "total_billable_amount": amount,
			"charges": [{"charge_type": charge_type, "item_code": self.item, "description": charge_type, "quantity": 1,
				"rate": amount, "amount": amount, "billable": 1, "billable_amount": amount, "manually_added": 1}],
		}).insert()

	def _make_batch(self):
		return frappe.get_doc({
			"doctype": "Service Billing Batch", "company": self.company, "billing_date": nowdate(),
			"service_date_from": nowdate(), "service_date_to": nowdate(), "posting_date": nowdate(), "group_by_customer": 1,
		}).insert()
