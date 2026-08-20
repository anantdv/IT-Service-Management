from __future__ import annotations

import frappe
from frappe.utils import now_datetime


MANAGER_ROLES = {"Service Manager", "System Manager"}


def require_manager(message):
	if not (frappe.get_roles() and MANAGER_ROLES.intersection(set(frappe.get_roles()))):
		frappe.throw(message, frappe.PermissionError)


def validate_active_technician(employee):
	if not employee:
		frappe.throw("Assigned Technician is required.")
	values = frappe.db.get_value(
		"Employee",
		employee,
		["status", "is_service_technician", "available_for_assignment"],
		as_dict=True,
	)
	if not values:
		frappe.throw(f"Employee {employee} was not found.")
	if values.status and values.status != "Active":
		frappe.throw("Assigned Technician must be an active Employee.")
	if not values.is_service_technician:
		frappe.throw("Assigned Technician must be marked as a service technician.")
	if values.available_for_assignment == 0:
		frappe.throw("Assigned Technician is not available for assignment.")


class ServiceDispatchService:
	def __init__(self, job):
		self.job = job

	def schedule(self):
		self._expect("Draft")
		if not self.job.scheduled_start_datetime:
			frappe.throw("Scheduled Start Datetime is required to schedule a job.")
		self.job.status = "Scheduled"
		self.job.add_comment("Comment", "Job scheduled")
		self.job.save()
		return self.job

	def assign(self, technician=None):
		if self.job.status not in ("Draft", "Scheduled", "Assigned"):
			frappe.throw("Only draft or scheduled jobs can be assigned.")
		if technician:
			self.job.assigned_technician = technician
		validate_active_technician(self.job.assigned_technician)
		self.job.status = "Assigned"
		self.job.assigned_datetime = self.job.assigned_datetime or now_datetime()
		self.job.add_comment("Comment", f"Technician assigned: {self.job.assigned_technician}")
		self.job.save()
		return self.job

	def start_travel(self, latitude=None, longitude=None):
		self._expect("Assigned")
		self.job.travel_start_datetime = self.job.travel_start_datetime or now_datetime()
		self.job.travel_start_latitude = latitude
		self.job.travel_start_longitude = longitude
		self.job.status = "In Transit"
		self.job.gps_capture_status = _gps_status(latitude, longitude, "Travel start")
		self.job.add_comment("Comment", "Travel started")
		self.job.save()
		return self.job

	def mark_arrived(self, latitude=None, longitude=None, manager_override=False):
		if self.job.status != "In Transit" and not manager_override:
			frappe.throw("Cannot mark arrived before travel starts.")
		if manager_override:
			require_manager("Only Service Manager can override arrival sequence.")
		self.job.arrival_datetime = self.job.arrival_datetime or now_datetime()
		self.job.arrival_latitude = latitude
		self.job.arrival_longitude = longitude
		self.job.status = "Arrived"
		self.job.gps_capture_status = _gps_status(latitude, longitude, "Arrival")
		self.job.add_comment("Comment", "Technician arrived")
		self.job.save()
		return self.job

	def start_work(self, manager_override=False):
		onsite = self.job.job_type not in ("Remote Support",)
		if onsite and self.job.status != "Arrived" and not manager_override:
			frappe.throw("Cannot start onsite work before arrival.")
		if manager_override:
			require_manager("Only Service Manager can override start work sequence.")
		if self.job.status not in ("Arrived", "Assigned") and not manager_override:
			frappe.throw("Only arrived or assigned jobs can start work.")
		self.job.work_start_datetime = self.job.work_start_datetime or now_datetime()
		self.job.status = "Work In Progress"
		self.job.add_comment("Comment", "Work started")
		self.job.save()
		return self.job

	def awaiting_parts(self):
		if self.job.status != "Work In Progress":
			frappe.throw("Only work in progress jobs can wait for parts.")
		self.job.status = "Awaiting Parts"
		self.job.add_comment("Comment", "Job awaiting parts")
		self.job.save()
		return self.job

	def awaiting_customer(self):
		if self.job.status != "Work In Progress":
			frappe.throw("Only work in progress jobs can wait for customer.")
		self.job.status = "Awaiting Customer"
		self.job.add_comment("Comment", "Job awaiting customer")
		self.job.save()
		return self.job

	def resume_work(self):
		if self.job.status not in ("Awaiting Parts", "Awaiting Customer", "Awaiting Approval"):
			frappe.throw("Only waiting jobs can resume work.")
		self.job.status = "Work In Progress"
		self.job.add_comment("Comment", "Work resumed")
		self.job.save()
		return self.job

	def complete(self, latitude=None, longitude=None):
		if self.job.status != "Work In Progress":
			frappe.throw("Only work in progress jobs can be completed.")
		self.job.validate_completion_requirements()
		self.job.work_end_datetime = self.job.work_end_datetime or now_datetime()
		self.job.completion_datetime = self.job.completion_datetime or now_datetime()
		self.job.completion_latitude = latitude
		self.job.completion_longitude = longitude
		self.job.status = "Completed"
		self.job.gps_capture_status = _gps_status(latitude, longitude, "Completion")
		self.job.add_comment("Comment", "Job completed")
		self.job.save()
		self.job.update_ticket_after_completion()
		return self.job

	def _expect(self, status):
		if self.job.status != status:
			frappe.throw(f"Expected job status {status}, found {self.job.status}.")


def _gps_status(latitude, longitude, action):
	if latitude is None or longitude is None:
		return f"{action}: GPS unavailable or permission denied"
	return f"{action}: GPS captured"
