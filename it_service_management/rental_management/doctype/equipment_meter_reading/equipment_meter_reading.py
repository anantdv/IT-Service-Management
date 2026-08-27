from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime

from it_service_management.rental_management.services.meter import RentalMeterBillingEngine


class EquipmentMeterReading(Document):
	def before_insert(self):
		self.submitted_by = frappe.session.user
		self.copy_equipment_details()

	def validate(self):
		self.copy_equipment_details()
		self.validate_dates_and_contract()
		self.validate_duplicate_period()
		self.validate_verification()
		RentalMeterBillingEngine().calculate_reading(self)

	def on_update(self):
		if self.verified:
			values = {"latest_meter_date": self.reading_date}
			for row in self.details:
				code = (row.meter_type or "").upper()
				if code in ("BW", "B&W", "BLACK AND WHITE"):
					values["latest_bw_meter"] = row.current_reading
				elif code in ("COLOUR", "COLOR"):
					values["latest_colour_meter"] = row.current_reading
			frappe.db.set_value("Customer Equipment", self.customer_equipment, values, update_modified=False)

	def copy_equipment_details(self):
		if not self.customer_equipment:
			return
		equipment = frappe.get_cached_doc("Customer Equipment", self.customer_equipment)
		self.customer = equipment.customer
		self.customer_site = equipment.customer_site
		self.asset = equipment.asset
		self.serial_no = equipment.serial_no
		self.rental_contract = self.rental_contract or equipment.rental_contract

	def validate_dates_and_contract(self):
		if getdate(self.billing_period_to) < getdate(self.billing_period_from):
			frappe.throw("Billing Period To cannot precede Billing Period From.")
		row = frappe.db.get_value("Rental Contract Equipment", {"parent": self.rental_contract, "customer_equipment": self.customer_equipment}, ["deployment_date", "deployment_status"], as_dict=True)
		if not row:
			frappe.throw("Customer Equipment does not belong to the selected Rental Contract.")
		if row.deployment_date and getdate(self.reading_date) < getdate(row.deployment_date):
			frappe.throw("Reading Date cannot precede the equipment Deployment Date.")

	def validate_duplicate_period(self):
		existing = frappe.db.exists("Equipment Meter Reading", {"customer_equipment": self.customer_equipment, "billing_period_from": self.billing_period_from, "billing_period_to": self.billing_period_to, "name": ["!=", self.name]})
		if existing:
			frappe.throw(f"Meter Reading {existing} already exists for this equipment and billing period.")

	def validate_verification(self):
		old = self.get_doc_before_save() if not self.is_new() else None
		if self.verified and (not old or not old.verified):
			if not self.flags.get("rental_lifecycle") and not {"Rental Manager", "Service Manager", "System Manager"}.intersection(frappe.get_roles()):
				frappe.throw("Only Rental Manager or Service Manager may verify meter readings.")
			self.verified_by = frappe.session.user
			self.verification_datetime = now_datetime()
