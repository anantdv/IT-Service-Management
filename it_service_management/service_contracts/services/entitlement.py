from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import frappe
from frappe.utils import getdate, nowdate


COVERAGE_FIELDS = (
	"labour_covered",
	"parts_covered",
	"consumables_covered",
	"travel_covered",
	"food_covered",
	"accommodation_covered",
	"airfare_covered",
	"remote_support_covered",
	"callout_covered",
	"installation_covered",
	"emergency_support_covered",
)


@dataclass(frozen=True)
class EntitlementRequest:
	customer: str
	customer_equipment: str | None = None
	service_type: str | None = None
	service_date: str | None = None
	customer_site: str | None = None


class ServiceEntitlementEngine:
	"""Resolve coverage in the required priority: Rental, AMC, Warranty, No Coverage."""

	def __init__(self, request: EntitlementRequest | dict[str, Any]):
		if isinstance(request, dict):
			request = EntitlementRequest(**request)
		self.request = request
		self.service_date = getdate(request.service_date or nowdate())

	def evaluate(self) -> dict[str, Any]:
		return (
			self._active_rental_coverage()
			or self._active_service_contract_coverage()
			or self._active_warranty_coverage()
			or self._no_coverage()
		)

	def _active_rental_coverage(self) -> dict[str, Any] | None:
		if not self.request.customer_equipment or not frappe.db.exists("DocType", "Rental Contract"):
			return None

		rows = frappe.db.sql(
			"""
			select rc.name
			from `tabRental Contract Equipment` rce
			inner join `tabRental Contract` rc on rc.name = rce.parent
			where rce.customer_equipment = %s
			  and rc.customer = %s
			  and rc.status in ('Active', 'Expiring', 'Termination Requested')
			  and rce.deployment_status in ('Deployed', 'Temporarily Replaced', 'Under Repair')
			  and rc.start_date <= %s
			  and (rc.end_date is null or rc.end_date >= %s)
			order by rc.start_date desc
			limit 1
			""",
			(
				self.request.customer_equipment,
				self.request.customer,
				self.service_date,
				self.service_date,
			),
			as_dict=True,
		)
		if not rows:
			return None

		contract = frappe.get_doc("Rental Contract", rows[0].name)
		source_doc = contract
		if contract.rental_plan and not contract.coverage_overrides_plan:
			source_doc = frappe.get_cached_doc("Rental Plan", contract.rental_plan)
		return self._coverage_result("Rental Contract", contract.name, source_doc)

	def _active_service_contract_coverage(self) -> dict[str, Any] | None:
		if not self.request.customer_equipment:
			return None

		rows = frappe.db.sql(
			"""
			select sc.name, sc.service_plan
			from `tabService Contract Equipment` sce
			inner join `tabService Contract` sc on sc.name = sce.parent
			where sce.customer_equipment = %s
			  and sc.customer = %s
			  and sc.contract_status in ('Active', 'Expiring')
			  and sc.start_date <= %s
			  and sc.end_date >= %s
			  and sce.active = 1
			  and (sce.coverage_start is null or sce.coverage_start <= %s)
			  and (sce.coverage_end is null or sce.coverage_end >= %s)
			order by sc.start_date desc
			limit 1
			""",
			(
				self.request.customer_equipment,
				self.request.customer,
				self.service_date,
				self.service_date,
				self.service_date,
				self.service_date,
			),
			as_dict=True,
		)
		if not rows:
			return None

		contract = rows[0]
		plan = frappe.get_cached_doc("Service Plan", contract.service_plan)
		return self._coverage_result("AMC", contract.name, plan)

	def _active_warranty_coverage(self) -> dict[str, Any] | None:
		if not self.request.customer_equipment:
			return None

		equipment = frappe.get_cached_doc("Customer Equipment", self.request.customer_equipment)
		if not equipment.warranty_end_date or getdate(equipment.warranty_end_date) < self.service_date:
			return None

		policy = self._get_warranty_policy(equipment)
		if not policy:
			return self._coverage_result("Warranty", equipment.name, {})

		return self._coverage_result("Warranty", policy.name, policy)

	def _get_warranty_policy(self, equipment):
		if equipment.warranty_policy:
			return frappe.get_cached_doc("Warranty Policy", equipment.warranty_policy)

		if equipment.item_code:
			policy_name = frappe.db.get_value("Warranty Policy", {"item_code": equipment.item_code}, "name")
			if policy_name:
				return frappe.get_cached_doc("Warranty Policy", policy_name)

		item_group = equipment.product_category or frappe.db.get_value("Item", equipment.item_code, "item_group")
		if item_group:
			policy_name = frappe.db.get_value("Warranty Policy", {"item_group": item_group}, "name")
			if policy_name:
				return frappe.get_cached_doc("Warranty Policy", policy_name)

		return None

	def _coverage_result(self, source: str, document: str, source_doc) -> dict[str, Any]:
		result = {
			"coverage_source": source,
			"coverage_document": document,
		}
		for field in COVERAGE_FIELDS:
			result[field] = bool(getattr(source_doc, field, False))

		if source == "AMC":
			result["callout_covered"] = result["labour_covered"]
			result["remote_support_covered"] = result["remote_support_covered"] or result["labour_covered"]
		elif source == "Rental Contract":
			result["callout_covered"] = result["emergency_support_covered"]
			result["remote_support_covered"] = result["labour_covered"]

		return result

	def _no_coverage(self) -> dict[str, Any]:
		result = {"coverage_source": "No Coverage", "coverage_document": None}
		result.update({field: False for field in COVERAGE_FIELDS})
		return result


@frappe.whitelist()
def evaluate_entitlement(customer: str, customer_equipment: str | None = None, service_type: str | None = None, service_date: str | None = None, customer_site: str | None = None):
	engine = ServiceEntitlementEngine(
		{
			"customer": customer,
			"customer_equipment": customer_equipment,
			"service_type": service_type,
			"service_date": service_date,
			"customer_site": customer_site,
		}
	)
	return engine.evaluate()
