from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from it_service_management.service_contracts.services.entitlement import ServiceEntitlementEngine
from it_service_management.service_operations.services.sla import ServiceSLAEngine, update_ticket_sla_status


VALID_TRANSITIONS = {
	None: {"Open"},
	"": {"Open"},
	"Open": {"Assigned", "Remote Support", "Onsite Required", "Awaiting Customer", "Cancelled", "Open"},
	"Assigned": {"Remote Support", "Scheduled", "Work In Progress", "Awaiting Customer", "Cancelled", "Assigned"},
	"Remote Support": {"Remote Resolved", "Onsite Required", "Awaiting Customer", "Cancelled", "Remote Support"},
	"Remote Resolved": {"Resolved", "Onsite Required", "Remote Resolved"},
	"Onsite Required": {"Scheduled", "Assigned", "Cancelled", "Onsite Required"},
	"Scheduled": {"Work In Progress", "Awaiting Parts", "Awaiting Customer", "Resolved", "Cancelled", "Scheduled"},
	"Awaiting Customer": {"Assigned", "Remote Support", "Work In Progress", "Resolved", "Cancelled", "Awaiting Customer"},
	"Awaiting Parts": {"Scheduled", "Work In Progress", "Resolved", "Cancelled", "Awaiting Parts"},
	"Work In Progress": {"Awaiting Customer", "Awaiting Parts", "Resolved", "Cancelled", "Work In Progress"},
	"Resolved": {"Closed", "Work In Progress", "Resolved"},
	"Closed": {"Closed"},
	"Cancelled": {"Cancelled"},
}

COVERAGE_FIELDS = (
	"labour_covered",
	"parts_covered",
	"travel_covered",
	"callout_covered",
	"accommodation_covered",
	"food_covered",
	"installation_covered",
	"remote_support_covered",
)


class ServiceTicket(Document):
	def before_insert(self):
		self.reported_datetime = self.reported_datetime or now_datetime()

	def after_insert(self):
		self.add_comment("Comment", "Ticket Created")

	def validate(self):
		self._validate_customer()
		self._populate_from_equipment()
		self._validate_status_transition()
		if not self.coverage_source:
			self.evaluate_coverage(add_comment=False)
		self.calculate_sla()
		update_ticket_sla_status(self)

	def _validate_customer(self):
		if not self.customer:
			frappe.throw("Service Ticket requires Customer.")
		if self.customer_equipment:
			equipment_customer = frappe.db.get_value("Customer Equipment", self.customer_equipment, "customer")
			if equipment_customer and equipment_customer != self.customer:
				frappe.throw("Customer Equipment must belong to the ticket customer.")

	def _populate_from_equipment(self):
		if not self.customer_equipment:
			return
		equipment = frappe.get_cached_doc("Customer Equipment", self.customer_equipment)
		if not self.customer:
			self.customer = equipment.customer
		self.customer_site = self.customer_site or equipment.customer_site
		self.item_code = self.item_code or equipment.item_code
		self.item_name = self.item_name or equipment.item_name
		self.serial_no = self.serial_no or equipment.serial_no
		self.asset = self.asset or equipment.asset
		self.warranty_active = equipment.warranty_status == "Under Warranty"
		self.service_contract = self.service_contract or equipment.service_contract

	def _validate_status_transition(self):
		if self.is_new():
			return
		old = self.get_doc_before_save()
		if not old or old.status == self.status:
			return
		if self.status not in VALID_TRANSITIONS.get(old.status, set()):
			frappe.throw(f"Invalid Service Ticket status transition: {old.status} to {self.status}.")

	def evaluate_coverage(self, add_comment=True):
		old = self._coverage_snapshot()
		result = ServiceEntitlementEngine(
			{
				"customer": self.customer,
				"customer_equipment": self.customer_equipment,
				"service_type": self.ticket_type,
				"service_date": self.reported_datetime,
				"customer_site": self.customer_site,
			}
		).evaluate()
		self.coverage_source = result.get("coverage_source")
		self.coverage_document = result.get("coverage_document")
		self.service_contract = result.get("coverage_document") if result.get("coverage_source") == "AMC" else self.service_contract
		self.rental_contract = result.get("coverage_document") if result.get("coverage_source") == "Rental Contract" else None
		for field in COVERAGE_FIELDS:
			self.set(field, result.get(field, 0))
		self.coverage_status = "Covered" if all(self.get(f) for f in ("labour_covered", "parts_covered")) else ("Partial" if any(self.get(f) for f in COVERAGE_FIELDS) else "Not Covered")
		if add_comment and old != self._coverage_snapshot():
			self.add_comment("Comment", f"Coverage re-evaluated from {old} to {self._coverage_snapshot()}")

	def calculate_sla(self):
		result = ServiceSLAEngine(self).calculate()
		reported = get_datetime(self.reported_datetime)
		if result["response_due"] < reported or result["resolution_due"] < reported:
			frappe.throw("SLA deadlines must not precede ticket creation.")
		self.response_due = result["response_due"]
		self.resolution_due = result["resolution_due"]

	def _coverage_snapshot(self):
		return {field: self.get(field) for field in ("coverage_source", "coverage_document", *COVERAGE_FIELDS)}

	@frappe.whitelist()
	def reevaluate_coverage(self):
		if not set(frappe.get_roles()).intersection({"Service Manager", "Service Contract Manager", "System Manager"}):
			frappe.throw("Only Service Manager or Service Contract Manager can re-evaluate coverage.", frappe.PermissionError)
		self.evaluate_coverage(add_comment=True)
		self.save()
		return self

	@frappe.whitelist()
	def create_service_job(self, job_type=None):
		job = frappe.new_doc("Service Job")
		job.service_ticket = self.name
		job.customer = self.customer
		job.customer_site = self.customer_site
		job.customer_equipment = self.customer_equipment
		job.item_code = self.item_code
		job.serial_no = self.serial_no
		job.asset = self.asset
		job.job_type = job_type or ("Remote Support" if self.ticket_type == "Remote Support" else "Onsite Support")
		job.priority = self.priority
		for field in COVERAGE_FIELDS + ("coverage_source", "coverage_document", "coverage_status", "service_contract", "rental_contract"):
			job.set(field, self.get(field))
		job.insert()
		self.status = "Scheduled" if job.job_type != "Remote Support" else "Remote Support"
		self.add_comment("Comment", f"Service Job created: {job.name}")
		self.save()
		return job.name

	@frappe.whitelist()
	def close_ticket(self):
		if self.status != "Resolved":
			frappe.throw("Only resolved tickets can be closed.")
		if not self.resolution:
			frappe.throw("Resolution is required before closing a ticket.")
		open_jobs = frappe.db.count("Service Job", {"service_ticket": self.name, "status": ["not in", ["Completed", "Cancelled"]]})
		if open_jobs:
			frappe.throw("Cannot close ticket while open Service Jobs exist.")
		self.closed_datetime = now_datetime()
		self.closed_by = frappe.session.user
		self.status = "Closed"
		self.add_comment("Comment", "Ticket Closed")
		self.save()
		return self.name
