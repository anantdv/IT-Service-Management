from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime, nowdate


class TestPhase2Operations(FrappeTestCase):
	def setUp(self):
		self.customer = self._make_customer()
		self.item = self._make_item()
		self.equipment = self._make_equipment()

	def test_ticket_creation_populates_equipment_and_sla(self):
		ticket = self._make_ticket()
		self.assertEqual(ticket.customer, self.customer)
		self.assertEqual(ticket.item_code, self.item)
		self.assertEqual(ticket.status, "Open")
		self.assertTrue(ticket.response_due)
		self.assertTrue(ticket.resolution_due)
		self.assertEqual(ticket.coverage_source, "No Coverage")

	def test_ticket_rejects_equipment_for_other_customer(self):
		other_customer = self._make_customer()
		ticket = frappe.get_doc(
			{
				"doctype": "Service Ticket",
				"customer": other_customer,
				"customer_equipment": self.equipment.name,
				"subject": "Wrong customer",
				"ticket_type": "Breakdown",
			}
		)
		self.assertRaises(frappe.ValidationError, ticket.insert)

	def test_ticket_to_job_copies_coverage_snapshot(self):
		ticket = self._make_ticket()
		job_name = ticket.create_service_job()
		job = frappe.get_doc("Service Job", job_name)
		self.assertEqual(job.service_ticket, ticket.name)
		self.assertEqual(job.customer_equipment, self.equipment.name)
		self.assertEqual(job.coverage_source, ticket.coverage_source)

	def test_job_invalid_transition_is_blocked(self):
		job = self._make_job()
		job.status = "Completed"
		self.assertRaises(frappe.ValidationError, job.save)

	def test_job_completion_requires_work_details(self):
		job = self._make_job()
		job.status = "Work In Progress"
		job.billing_status = "Not Applicable"
		self.assertRaises(frappe.ValidationError, job.complete_job)

	def test_billing_marks_covered_and_billable_rows(self):
		job = self._make_job()
		job.labour_covered = 1
		job.parts_covered = 0
		job.append("labour", {"employee": self._make_employee(), "activity_type": "Repair", "duration_hours": 2, "billing_rate": 100, "covered": 1})
		job.append("parts", {"item_code": self.item, "quantity": 1, "valuation_rate": 40, "billing_rate": 75, "covered": 0})
		job.save()
		job.calculate_billing()
		job.reload()
		self.assertEqual(job.total_billable_amount, 75)
		self.assertEqual(job.billing_status, "Ready for Billing")

	def _make_customer(self):
		name = "Test ITSM Ops Customer " + frappe.generate_hash(length=8)
		return frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company"}).insert().name

	def _make_item(self):
		item_code = "ITSM-OPS-" + frappe.generate_hash(length=8)
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"item_group": "All Item Groups",
				"is_stock_item": 0,
			}
		).insert()
		return item_code

	def _make_equipment(self):
		return frappe.get_doc(
			{
				"doctype": "Customer Equipment",
				"customer": self.customer,
				"item_code": self.item,
				"ownership_type": "Customer Owned",
				"equipment_status": "Operational",
				"warranty_end_date": add_days(nowdate(), -1),
			}
		).insert()

	def _make_ticket(self):
		return frappe.get_doc(
			{
				"doctype": "Service Ticket",
				"customer": self.customer,
				"customer_equipment": self.equipment.name,
				"subject": "Printer not printing",
				"ticket_type": "Breakdown",
				"priority": "High",
				"reported_datetime": now_datetime(),
			}
		).insert()

	def _make_job(self):
		ticket = self._make_ticket()
		return frappe.get_doc(
			{
				"doctype": "Service Job",
				"service_ticket": ticket.name,
				"customer": self.customer,
				"customer_equipment": self.equipment.name,
				"job_type": "Onsite Support",
				"priority": "High",
			}
		).insert()

	def _make_employee(self):
		employee_name = "ITSM Ops Tech " + frappe.generate_hash(length=8)
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
		).insert().name
