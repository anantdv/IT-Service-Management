from __future__ import annotations

from datetime import date

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class CustomerEquipment(Document):
	def validate(self):
		self.validate_dates()
		self.validate_serial_uniqueness()
		self.update_warranty_status()

	def validate_dates(self):
		if self.warranty_start_date and self.warranty_end_date:
			if getdate(self.warranty_end_date) < getdate(self.warranty_start_date):
				frappe.throw("Warranty End Date cannot be before Warranty Start Date.")

	def validate_serial_uniqueness(self):
		if not self.serial_no:
			return

		existing = frappe.db.exists(
			"Customer Equipment",
			{"serial_no": self.serial_no, "name": ["!=", self.name]},
		)
		if existing:
			frappe.throw(f"Serial No {self.serial_no} is already linked to Customer Equipment {existing}.")

	def update_warranty_status(self):
		if not self.warranty_end_date:
			self.warranty_status = self.warranty_status or "No Warranty"
			return

		self.warranty_status = (
			"Under Warranty" if getdate(self.warranty_end_date) >= getdate(nowdate()) else "Expired"
		)


def _settings_allow_auto_create() -> bool:
	return bool(
		frappe.db.get_single_value(
			"IT Service Settings", "automatically_create_customer_equipment"
		)
	)


def create_from_delivery_note(doc, method=None):
	if not _settings_allow_auto_create():
		return

	for row in doc.get("items", []):
		if not row.get("serial_no") or not row.get("item_code"):
			continue

		for serial_no in _split_serials(row.serial_no):
			if frappe.db.exists("Customer Equipment", {"serial_no": serial_no}):
				continue

			frappe.get_doc(
				{
					"doctype": "Customer Equipment",
					"customer": doc.customer,
					"item_code": row.item_code,
					"serial_no": serial_no,
					"delivery_note": doc.name,
					"ownership_type": "Customer Owned",
					"equipment_status": "Operational",
				}
			).insert(ignore_permissions=True)


def update_from_sales_invoice(doc, method=None):
	for row in doc.get("items", []):
		for serial_no in _split_serials(row.get("serial_no")):
			equipment_name = frappe.db.exists("Customer Equipment", {"serial_no": serial_no})
			if equipment_name:
				frappe.db.set_value("Customer Equipment", equipment_name, "sales_invoice", doc.name)


def _split_serials(serials: str | None) -> list[str]:
	if not serials:
		return []
	return [serial.strip() for serial in serials.replace(",", "\n").splitlines() if serial.strip()]
