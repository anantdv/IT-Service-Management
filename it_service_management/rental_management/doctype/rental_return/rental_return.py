from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from it_service_management.rental_management.services.asset import RentalAssetService


class RentalReturn(Document):
	def before_insert(self):
		self.copy_contract_details()

	def validate(self):
		self.copy_contract_details()
		seen = set()
		for row in self.items:
			if row.customer_equipment in seen:
				frappe.throw(f"Customer Equipment {row.customer_equipment} appears more than once.")
			seen.add(row.customer_equipment)
			equipment = frappe.db.get_value("Customer Equipment", row.customer_equipment, ["rental_contract", "asset", "serial_no"], as_dict=True)
			if not equipment or equipment.rental_contract != self.rental_contract:
				frappe.throw(f"Customer Equipment {row.customer_equipment} does not belong to this Rental Contract.")
			row.asset = row.asset or equipment.asset
			row.serial_no = row.serial_no or equipment.serial_no

	def copy_contract_details(self):
		if not self.rental_contract:
			return
		contract = frappe.get_cached_doc("Rental Contract", self.rental_contract)
		self.customer = contract.customer
		self.customer_site = self.customer_site or contract.customer_site

	@frappe.whitelist()
	def complete_return(self):
		if self.status not in ("Draft", "Scheduled", "In Progress"):
			frappe.throw("Only an open Rental Return can be completed.")
		settings = frappe.get_single("IT Service Settings")
		if settings.require_customer_signature and not self.customer_signature:
			frappe.throw("Customer signature is required to complete the return.")
		for row in self.items:
			RentalAssetService.return_item(self, row)
			self._create_return_charges(row)
		self.status = "Completed"
		self.completion_datetime = now_datetime()
		self.save()
		contract = frappe.get_doc("Rental Contract", self.rental_contract)
		if not any(row.deployment_status in ("Deployed", "Temporarily Replaced", "Under Repair") for row in contract.equipment):
			contract.status = "Completed" if contract.status in ("Expired", "Termination Requested", "Terminated") else contract.status
			contract.save(ignore_permissions=True)
		return self

	def _create_return_charges(self, row):
		settings = frappe.get_single("IT Service Settings")
		for component_type, amount, description in (
			("Damage", row.damage_charge, f"Damage found on return of {row.customer_equipment}: {row.damage_found or 'See return inspection'}"),
			("Missing Accessory", row.missing_accessory_charge, f"Missing accessories on return of {row.customer_equipment}: {row.missing_accessories or 'See return inspection'}"),
		):
			if not amount:
				continue
			item = settings.default_rental_damage_item
			frappe.get_doc({"doctype": "Rental Ad-Hoc Charge", "rental_contract": self.rental_contract, "customer": self.customer, "customer_site": self.customer_site, "customer_equipment": row.customer_equipment, "charge_date": self.return_date, "component_type": component_type, "item_code": item, "description": description, "quantity": 1, "rate": amount, "billable": 1, "status": "Approved", "approved_by": frappe.session.user}).insert(ignore_permissions=True)
