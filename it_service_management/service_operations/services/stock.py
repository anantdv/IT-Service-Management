from __future__ import annotations

import frappe
from erpnext.stock.utils import get_stock_balance


class ServiceStockService:
	def __init__(self, job):
		self.job = job

	def create_service_stock_entry(self):
		settings = frappe.get_single("IT Service Settings")
		target = settings.default_service_consumption_warehouse
		if not target:
			frappe.throw("Set Default Service Consumption Warehouse in IT Service Settings.")

		rows = [row for row in self.job.parts if row.item_code and not row.stock_entry]
		if not rows:
			frappe.throw("No unprocessed service parts found.")

		stock_entry = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Transfer", "items": []})
		for row in rows:
			self._validate_part(row)
			stock_entry.append(
				"items",
				{
					"item_code": row.item_code,
					"qty": row.quantity,
					"s_warehouse": row.source_warehouse,
					"t_warehouse": target,
					"serial_no": row.serial_no,
					"batch_no": row.batch_no,
					"uom": row.uom,
				},
			)
		stock_entry.insert()
		stock_entry.submit()
		for row in rows:
			row.stock_entry = stock_entry.name
		self.job.add_comment("Comment", f"Part consumption Stock Entry created: {stock_entry.name}")
		self.job.save()
		return stock_entry.name

	def _validate_part(self, row):
		if not row.quantity or row.quantity <= 0:
			frappe.throw("Service part quantity must be greater than zero.")
		if not row.source_warehouse:
			frappe.throw(f"Source warehouse is required for {row.item_code}.")
		item = frappe.get_cached_doc("Item", row.item_code)
		if item.has_serial_no and not row.serial_no:
			frappe.throw(f"Serial number is required for {row.item_code}.")
		if item.has_batch_no and not row.batch_no:
			frappe.throw(f"Batch number is required for {row.item_code}.")
		available = get_stock_balance(row.item_code, row.source_warehouse)
		if available < row.quantity:
			frappe.throw(f"Insufficient stock for {row.item_code} in {row.source_warehouse}. Available: {available}")
