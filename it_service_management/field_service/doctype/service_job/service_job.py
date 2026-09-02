from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, now_datetime

from it_service_management.service_contracts.services.entitlement import ServiceEntitlementEngine
from it_service_management.service_billing.services.batch import create_invoice_for_service_job
from it_service_management.service_operations.services.billing import ServiceBillingEngine
from it_service_management.service_operations.services.dispatch import ServiceDispatchService, require_manager, validate_active_technician
from it_service_management.service_operations.services.stock import ServiceStockService


COVERAGE_FIELDS = (
	"labour_covered",
	"parts_covered",
	"travel_covered",
	"callout_covered",
	"accommodation_covered",
	"food_covered",
	"airfare_covered",
	"installation_covered",
	"remote_support_covered",
)

VALID_TRANSITIONS = {
	"Draft": {"Draft", "Scheduled", "Assigned", "Cancelled"},
	"Scheduled": {"Scheduled", "Assigned", "Cancelled"},
	"Assigned": {"Assigned", "In Transit", "Work In Progress", "Cancelled"},
	"In Transit": {"In Transit", "Arrived", "Cancelled"},
	"Arrived": {"Arrived", "Work In Progress", "Cancelled"},
	"Work In Progress": {"Work In Progress", "Awaiting Parts", "Awaiting Customer", "Awaiting Approval", "Completed", "Cancelled"},
	"Awaiting Parts": {"Awaiting Parts", "Work In Progress", "Cancelled"},
	"Awaiting Customer": {"Awaiting Customer", "Work In Progress", "Cancelled"},
	"Awaiting Approval": {"Awaiting Approval", "Work In Progress", "Cancelled"},
	"Completed": {"Completed"},
	"Cancelled": {"Cancelled"},
}


class ServiceJob(Document):
	def before_insert(self):
		self._copy_ticket_details()
		self._populate_checklist()

	def validate(self):
		self._validate_customer()
		self._validate_status_transition()
		if self.assigned_technician:
			validate_active_technician(self.assigned_technician)
			self._default_part_warehouse()
		self._validate_coverage_override()
		self._validate_customer_po()
		self._validate_charging_inputs()
		self._calculate_child_rows()
		self._calculate_durations()

	def _copy_ticket_details(self):
		if not self.service_ticket:
			return
		ticket = frappe.get_cached_doc("Service Ticket", self.service_ticket)
		for field in (
			"customer",
			"customer_site",
			"customer_equipment",
			"item_code",
			"serial_no",
			"asset",
			"priority",
			"service_category",
			"coverage_source",
			"coverage_document",
			"coverage_status",
			"service_contract",
			"rental_contract",
			*CoverageTuple,
		):
			if ticket.get(field) is not None and not self.get(field):
				self.set(field, ticket.get(field))
		self.service_team = self.service_team or ticket.get("routing_service_team")
		self.customer_complaint = self.customer_complaint or ticket.customer_complaint

	def _validate_customer(self):
		if not self.customer:
			frappe.throw("Service Job must link to Customer.")
		if self.customer_equipment:
			equipment_customer = frappe.db.get_value("Customer Equipment", self.customer_equipment, "customer")
			if equipment_customer and equipment_customer != self.customer:
				frappe.throw("Customer Equipment must belong to the selected Customer.")

	def _validate_status_transition(self):
		if self.is_new():
			return
		old = self.get_doc_before_save()
		if not old or old.status == self.status:
			return
		if self.status not in VALID_TRANSITIONS.get(old.status, set()):
			frappe.throw(f"Invalid Service Job status transition: {old.status} to {self.status}.")

	def _validate_coverage_override(self):
		if self.is_new():
			return
		old = self.get_doc_before_save()
		if not old:
			return
		changed = [field for field in COVERAGE_FIELDS if bool(self.get(field)) != bool(old.get(field))]
		if changed and not self.coverage_override_reason:
			frappe.throw("Coverage override requires reason.")
		if changed:
			require_manager("Only Service Manager can override coverage.")
			self.add_comment("Comment", f"Coverage overridden by {frappe.session.user}: {changed}. Reason: {self.coverage_override_reason}")

	def _validate_charging_inputs(self):
		for fieldname in ("chargeable_trips", "chargeable_distance_km", "chargeable_travel_days", "chargeable_nights", "chargeable_technician_count"):
			if flt(self.get(fieldname)) < 0:
				frappe.throw(f"{self.meta.get_label(fieldname)} cannot be negative.")

	def _validate_customer_po(self):
		if self.service_zone and frappe.get_meta("Service Zone").has_field("requires_customer_po"):
			if frappe.db.get_value("Service Zone", self.service_zone, "requires_customer_po"):
				self.po_required = 1
		if not self.po_required:
			self.po_status = "Not Required"
			return
		if not self.po_status or self.po_status == "Not Required":
			self.po_status = "Pending"
		if self.po_status == "Approved":
			old = self.get_doc_before_save()
			if not self.is_new() and old and old.po_status != "Approved":
				require_manager("Only Service Manager can approve a customer PO.")
			if not (self.customer_po_no or self.po_attachment):
				frappe.throw("Customer PO No or PO Attachment is required before approval.")
			self.po_approved_by = self.po_approved_by or frappe.session.user
			self.po_approved_on = self.po_approved_on or now_datetime()
		else:
			self.po_approved_by = None
			self.po_approved_on = None

	def _calculate_child_rows(self):
		employees = {row.employee for row in self.labour if row.employee and not row.internal_hourly_cost}
		employee_costs = {
			row.name: row.hourly_internal_cost
			for row in frappe.get_all("Employee", filters={"name": ["in", list(employees)]}, fields=["name", "hourly_internal_cost"])
		} if employees else {}
		for row in self.labour:
			if row.start_datetime and row.end_datetime:
				row.duration_hours = (get_datetime(row.end_datetime) - get_datetime(row.start_datetime)).total_seconds() / 3600
			row.internal_hourly_cost = row.internal_hourly_cost or employee_costs.get(row.employee) or 0
			row.internal_cost = flt(row.duration_hours) * flt(row.internal_hourly_cost)
			row.billable_amount = 0 if row.covered else flt(row.duration_hours) * flt(row.billing_rate)
		for row in self.parts:
			row.internal_cost = flt(row.quantity) * flt(row.valuation_rate)
			row.billable_amount = 0 if row.covered else flt(row.quantity) * flt(row.billing_rate)
			if row.quantity and row.quantity <= 0:
				frappe.throw("Service part quantity must be greater than zero.")

	def _calculate_durations(self):
		self.travel_duration_minutes = _minutes(self.travel_start_datetime, self.arrival_datetime)
		self.onsite_duration_minutes = _minutes(self.arrival_datetime, self.work_end_datetime or self.completion_datetime)
		self.total_job_duration_minutes = _minutes(self.travel_start_datetime or self.work_start_datetime, self.completion_datetime)

	def _default_part_warehouse(self):
		warehouse = frappe.db.get_value("Employee", self.assigned_technician, "service_warehouse")
		if not warehouse:
			return
		for row in self.parts:
			row.source_warehouse = row.source_warehouse or warehouse

	def _populate_checklist(self):
		if self.checklist or not self.job_type:
			return
		templates = frappe.get_all(
			"Service Checklist Template",
			filters={"job_type": self.job_type, "active": 1},
			fields=["name"],
			limit=1,
		)
		if not templates:
			return
		template = frappe.get_doc("Service Checklist Template", templates[0].name)
		for item in template.items:
			self.append(
				"checklist",
				{
					"sequence": item.sequence,
					"checklist_item": item.checklist_item,
					"mandatory": item.mandatory,
					"requires_comment": item.requires_comment,
					"requires_photo": item.requires_photo,
				},
			)

	def validate_completion_requirements(self):
		if not (self.diagnosis or self.work_performed):
			frappe.throw("Diagnosis or Work Performed is required to complete the job.")
		for row in self.checklist:
			if row.mandatory and not row.completed:
				frappe.throw(f"Mandatory checklist item is incomplete: {row.checklist_item}")
			if row.completed and row.requires_comment and not row.comment:
				frappe.throw(f"Checklist item requires comment: {row.checklist_item}")
			if row.completed and row.requires_photo and not row.attachment:
				frappe.throw(f"Checklist item requires photo: {row.checklist_item}")
		settings = frappe.get_single("IT Service Settings")
		if settings.require_customer_signature and not self.customer_signature and not self.signature_override_reason:
			frappe.throw("Customer signature is required or a manager override reason must be entered.")
		if self.signature_override_reason and not self.customer_signature:
			require_manager("Only Service Manager can override customer signature requirement.")
		self._validate_po_for_completion()
		if not self.coverage_source:
			frappe.throw("Coverage must be evaluated before completion.")
		for row in self.parts:
			if row.item_code and not row.stock_entry:
				frappe.throw("All consumed parts must be processed before completing the job.")

	def _validate_po_for_completion(self):
		if not self.po_required:
			return
		if self.po_status != "Approved":
			frappe.throw("Customer PO approval is required before completing this Service Job.")
		if not (self.customer_po_no or self.po_attachment):
			frappe.throw("Customer PO No or PO Attachment is required before completing this Service Job.")

	def update_ticket_after_completion(self):
		if not self.service_ticket:
			return
		open_jobs = frappe.db.count("Service Job", {"service_ticket": self.service_ticket, "status": ["not in", ["Completed", "Cancelled"]]})
		if open_jobs:
			return
		ticket = frappe.get_doc("Service Ticket", self.service_ticket)
		ticket.status = "Resolved"
		ticket.resolution_datetime = ticket.resolution_datetime or now_datetime()
		ticket.resolved_datetime = ticket.resolved_datetime or ticket.resolution_datetime
		ticket.resolution = ticket.resolution or self.work_performed or self.diagnosis
		ticket.add_comment("Comment", "Ticket Resolved")
		ticket.save()

	def evaluate_coverage(self):
		result = ServiceEntitlementEngine(
			{
				"customer": self.customer,
				"customer_equipment": self.customer_equipment,
				"service_type": self.job_type,
				"service_date": self.scheduled_date,
				"customer_site": self.customer_site,
			}
		).evaluate()
		self.coverage_source = result.get("coverage_source")
		self.coverage_document = result.get("coverage_document")
		for field in COVERAGE_FIELDS:
			self.set(field, result.get(field, 0))

	@frappe.whitelist()
	def schedule_job(self):
		return ServiceDispatchService(self).schedule()

	@frappe.whitelist()
	def assign_technician(self, technician=None):
		return ServiceDispatchService(self).assign(technician)

	@frappe.whitelist()
	def start_travel(self, latitude=None, longitude=None):
		return ServiceDispatchService(self).start_travel(latitude, longitude)

	@frappe.whitelist()
	def mark_arrived(self, latitude=None, longitude=None, manager_override=False):
		return ServiceDispatchService(self).mark_arrived(latitude, longitude, manager_override)

	@frappe.whitelist()
	def start_work(self, manager_override=False):
		return ServiceDispatchService(self).start_work(manager_override)

	@frappe.whitelist()
	def mark_awaiting_parts(self):
		return ServiceDispatchService(self).awaiting_parts()

	@frappe.whitelist()
	def mark_awaiting_customer(self):
		return ServiceDispatchService(self).awaiting_customer()

	@frappe.whitelist()
	def resume_work(self):
		return ServiceDispatchService(self).resume_work()

	@frappe.whitelist()
	def complete_job(self, latitude=None, longitude=None):
		return ServiceDispatchService(self).complete(latitude, longitude)

	@frappe.whitelist()
	def create_service_stock_entry(self):
		return ServiceStockService(self).create_service_stock_entry()

	@frappe.whitelist()
	def calculate_billing(self):
		return ServiceBillingEngine(self).calculate()

	@frappe.whitelist()
	def create_sales_invoice(self):
		return create_invoice_for_service_job(self.name)

	@frappe.whitelist()
	def approve_customer_po(self):
		if not self.po_required:
			frappe.throw("Customer PO Required must be checked before approval.")
		require_manager("Only Service Manager can approve a customer PO.")
		if not (self.customer_po_no or self.po_attachment):
			frappe.throw("Customer PO No or PO Attachment is required before approval.")
		self.po_status = "Approved"
		self.po_approved_by = frappe.session.user
		self.po_approved_on = now_datetime()
		self.add_comment("Comment", "Customer PO approved")
		self.save()
		return self

	@frappe.whitelist()
	def reevaluate_coverage(self):
		require_manager("Only Service Manager can re-evaluate Service Job coverage.")
		self.evaluate_coverage()
		self.add_comment("Comment", "Coverage re-evaluated")
		self.save()
		return self


CoverageTuple = COVERAGE_FIELDS


def _minutes(start, end):
	if not start or not end:
		return 0
	return (get_datetime(end) - get_datetime(start)).total_seconds() / 60
