from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime


PRIORITY_FALLBACKS = {
	"Critical": (60, 240),
	"High": (120, 480),
	"Medium": (240, 1440),
	"Low": (480, 2880),
}


@dataclass
class SLAResult:
	response_due: Any
	resolution_due: Any
	response_minutes: int
	resolution_minutes: int

	def as_dict(self):
		return {
			"response_due": self.response_due,
			"resolution_due": self.resolution_due,
			"response_minutes": self.response_minutes,
			"resolution_minutes": self.resolution_minutes,
		}


class ServiceSLAEngine:
	def __init__(self, ticket):
		self.ticket = ticket
		self.priority = ticket.priority or "Medium"

	def calculate(self) -> dict[str, Any]:
		reported = get_datetime(self.ticket.reported_datetime) if self.ticket.reported_datetime else now_datetime()
		response_minutes, resolution_minutes = self._minutes()
		return SLAResult(
			response_due=add_to_date(reported, minutes=response_minutes),
			resolution_due=add_to_date(reported, minutes=resolution_minutes),
			response_minutes=response_minutes,
			resolution_minutes=resolution_minutes,
		).as_dict()

	def _minutes(self) -> tuple[int, int]:
		contract_minutes = self._contract_minutes()
		plan_minutes = self._plan_minutes()
		settings_minutes = self._settings_minutes()
		return contract_minutes or plan_minutes or settings_minutes or PRIORITY_FALLBACKS[self.priority]

	def _contract_minutes(self):
		if not self.ticket.service_contract:
			return None
		contract = frappe.get_cached_doc("Service Contract", self.ticket.service_contract)
		if not getattr(contract, "override_sla_rules", None):
			return None
		return self._read_priority_fields(contract)

	def _plan_minutes(self):
		plan_name = None
		if self.ticket.service_contract:
			plan_name = frappe.db.get_value("Service Contract", self.ticket.service_contract, "service_plan")
		if not plan_name and self.ticket.customer_equipment:
			plan_name = frappe.db.get_value("Customer Equipment", self.ticket.customer_equipment, "service_plan")
		if not plan_name:
			return None
		return self._read_priority_fields(frappe.get_cached_doc("Service Plan", plan_name))

	def _settings_minutes(self):
		settings = frappe.get_single("IT Service Settings")
		return self._read_priority_fields(settings, response_prefix="default_response_minutes", resolution_prefix="default_resolution_minutes")

	def _read_priority_fields(self, doc, response_prefix="response_time", resolution_prefix="resolution_time"):
		key = (self.priority or "Medium").lower()
		response = getattr(doc, f"{response_prefix}_{key}", None)
		resolution = getattr(doc, f"{resolution_prefix}_{key}", None)
		response = _duration_to_minutes(response)
		resolution = _duration_to_minutes(resolution)
		if response and resolution:
			return int(response), int(resolution)
		if response:
			return int(response), PRIORITY_FALLBACKS[self.priority][1]
		return None


def _duration_to_minutes(value):
	if not value:
		return 0
	try:
		value = float(value)
	except (TypeError, ValueError):
		return 0
	# Frappe Duration stores seconds. Explicit settings fields store minutes.
	if value > 24 * 60:
		return value / 60
	return value


def update_ticket_sla_status(ticket):
	now = now_datetime()
	if ticket.first_response_datetime:
		ticket.response_sla_status = "Met" if ticket.first_response_datetime <= ticket.response_due else "Breached"
	elif ticket.response_due and now > ticket.response_due:
		ticket.response_sla_status = "Breached"
	elif ticket.response_due:
		ticket.response_sla_status = _progress_status(ticket.reported_datetime, ticket.response_due, now)

	if ticket.resolution_datetime:
		ticket.resolution_sla_status = "Met" if ticket.resolution_datetime <= ticket.resolution_due else "Breached"
	elif ticket.resolution_due and now > ticket.resolution_due:
		ticket.resolution_sla_status = "Breached"
	elif ticket.resolution_due:
		ticket.resolution_sla_status = _progress_status(ticket.reported_datetime, ticket.resolution_due, now)

	ticket.response_sla_percentage = _percentage(ticket.reported_datetime, ticket.response_due, now)
	ticket.resolution_sla_percentage = _percentage(ticket.reported_datetime, ticket.resolution_due, now)


def _progress_status(start, due, now):
	pct = _percentage(start, due, now)
	return "At Risk" if pct >= 75 else "Within SLA"


def _percentage(start, due, now):
	if not start or not due:
		return 0
	start = get_datetime(start)
	due = get_datetime(due)
	total = (due - start).total_seconds()
	if total <= 0:
		return 100
	return min(100, max(0, ((now - start).total_seconds() / total) * 100))
