from frappe.model.document import Document
import frappe


class ServicePartRequest(Document):
	def validate(self):
		for row in self.items:
			if not row.quantity or row.quantity <= 0:
				frappe.throw("Service Part Request quantity must be greater than zero.")
		if self.status == "Requested" and self.service_job:
			frappe.db.set_value("Service Job", self.service_job, "status", "Awaiting Parts")

	@frappe.whitelist()
	def create_stock_entry(self):
		if self.status not in ("Approved", "Partially Issued"):
			frappe.throw("Only approved part requests can be issued.")
		stock_entry = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Transfer", "items": []})
		for row in self.items:
			stock_entry.append(
				"items",
				{
					"item_code": row.item_code,
					"qty": row.quantity,
					"s_warehouse": self.source_warehouse,
					"t_warehouse": self.required_warehouse,
					"serial_no": row.serial_no,
				},
			)
		stock_entry.insert()
		stock_entry.submit()
		self.status = "Issued"
		self.add_comment("Comment", f"Part Issued via Stock Entry {stock_entry.name}")
		self.save()
		return stock_entry.name
