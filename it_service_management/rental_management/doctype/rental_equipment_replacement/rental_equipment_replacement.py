from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from it_service_management.rental_management.services.asset import RentalAssetService


class RentalEquipmentReplacement(Document):
	def before_insert(self):
		self.copy_contract_details()

	def validate(self):
		self.copy_contract_details()
		if self.old_asset == self.new_asset:
			frappe.throw("Replacement Asset must differ from the old Asset.")
		if self.status != "Completed":
			contract = frappe.get_cached_doc("Rental Contract", self.rental_contract)
			RentalAssetService.validate_asset_for_rental(self.new_asset, self.customer, contract.company, self.rental_contract)

	def copy_contract_details(self):
		if not self.rental_contract:
			return
		contract = frappe.get_cached_doc("Rental Contract", self.rental_contract)
		self.customer = contract.customer
		self.customer_site = self.customer_site or contract.customer_site
		if self.old_customer_equipment:
			old = frappe.get_cached_doc("Customer Equipment", self.old_customer_equipment)
			self.old_asset = old.asset
			self.old_serial_no = old.serial_no

	@frappe.whitelist()
	def complete_replacement(self):
		if self.status not in ("Draft", "Scheduled"):
			frappe.throw("Only a draft or scheduled replacement can be completed.")
		if not {"Rental Manager", "Service Manager", "System Manager"}.intersection(frappe.get_roles()):
			frappe.throw("Only Rental Manager or Service Manager may complete a replacement.")
		contract = frappe.get_doc("Rental Contract", self.rental_contract)
		RentalAssetService.validate_asset_for_rental(self.new_asset, self.customer, contract.company, self.rental_contract)
		old_row = next((row for row in contract.equipment if row.customer_equipment == self.old_customer_equipment), None)
		if not old_row:
			frappe.throw("Old equipment is not part of this Rental Contract.")
		old_row.deployment_status = "Temporarily Replaced" if self.temporary_replacement else "Under Repair"
		old_row.billing_end_date = self.replacement_date
		old_equipment = frappe.get_doc("Customer Equipment", self.old_customer_equipment)
		old_equipment.equipment_status = "Temporary Replacement" if self.temporary_replacement else "Under Repair"
		old_equipment.latest_bw_meter = self.old_final_bw_meter or old_equipment.latest_bw_meter
		old_equipment.latest_colour_meter = self.old_final_colour_meter or old_equipment.latest_colour_meter
		old_equipment.latest_meter_date = self.replacement_date
		old_equipment.save(ignore_permissions=True)
		RentalAssetService.record_lifecycle_meter(old_equipment.name, contract.name, self.replacement_date, self.old_final_bw_meter, self.old_final_colour_meter, f"Final meter before replacement {self.name}")

		asset = frappe.get_cached_doc("Asset", self.new_asset)
		new_row = contract.append("equipment", {"asset": self.new_asset, "item_code": asset.item_code, "item_name": asset.get("item_name"), "serial_no": self.new_serial_no or asset.get("serial_no"), "deployment_status": "Reserved", "replacement_for": self.old_customer_equipment, "monthly_rental_rate": 0 if self.temporary_replacement else old_row.monthly_rental_rate, "meter_billing_enabled": old_row.meter_billing_enabled, "included_bw_pages": old_row.included_bw_pages, "included_colour_pages": old_row.included_colour_pages, "excess_bw_rate": old_row.excess_bw_rate, "excess_colour_rate": old_row.excess_colour_rate})
		contract.save(ignore_permissions=True)
		deployment = frappe.get_doc({"doctype": "Rental Deployment", "rental_contract": contract.name, "customer": contract.customer, "customer_site": contract.customer_site, "deployment_date": self.replacement_date, "installation_required": 1, "status": "In Progress", "items": [{"asset": self.new_asset, "item_code": new_row.item_code, "serial_no": new_row.serial_no, "initial_bw_meter": self.new_initial_bw_meter, "initial_colour_meter": self.new_initial_colour_meter}]})
		deployment.insert(ignore_permissions=True)
		deployment.complete_deployment()
		self.new_customer_equipment = deployment.items[0].customer_equipment
		if self.temporary_replacement:
			frappe.db.set_value("Customer Equipment", self.new_customer_equipment, {"ownership_type": "Temporary Replacement", "loan_start": self.replacement_date, "loan_reason": self.reason, "loan_service_job": self.service_job, "equipment_status": "Temporary Replacement"}, update_modified=False)
		self.status = "Completed"
		self.completion_datetime = now_datetime()
		self.save()
		self.add_comment("Comment", f"Replaced {self.old_asset} with {self.new_asset}")
		return self
