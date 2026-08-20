from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, getdate, nowdate


ACTIVE_STATUSES = ("Active", "Expiring")


class ServiceContract(Document):
	def validate(self):
		self.validate_dates()
		self.validate_active_state()
		self.validate_equipment_rows()
		self.recalculate_entitlements()

	def on_update(self):
		if self.contract_status in ACTIVE_STATUSES:
			self.update_customer_equipment_links()

	def validate_dates(self):
		if self.end_date and self.start_date and getdate(self.end_date) < getdate(self.start_date):
			frappe.throw("Contract End Date cannot be before Start Date.")

	def validate_active_state(self):
		if self.contract_status in ACTIVE_STATUSES and getdate(self.end_date) < getdate(nowdate()):
			frappe.throw("Cannot activate an expired Service Contract.")

	def validate_equipment_rows(self):
		seen = set()
		for row in self.covered_equipment:
			if row.customer_equipment in seen:
				frappe.throw(f"Customer Equipment {row.customer_equipment} is listed more than once.")
			seen.add(row.customer_equipment)

			if row.coverage_start and row.coverage_end and getdate(row.coverage_end) < getdate(row.coverage_start):
				frappe.throw(f"Coverage End cannot be before Coverage Start for {row.customer_equipment}.")

			self.validate_no_duplicate_active_coverage(row.customer_equipment)

	def validate_no_duplicate_active_coverage(self, customer_equipment: str):
		if self.contract_status not in ACTIVE_STATUSES or not customer_equipment:
			return

		existing = frappe.db.sql(
			"""
			select parent
			from `tabService Contract Equipment`
			where customer_equipment = %s
			  and parent != %s
			  and active = 1
			  and parenttype = 'Service Contract'
			  and parent in (
			  	select name from `tabService Contract`
			  	where contract_status in ('Active', 'Expiring')
			  	  and start_date <= %s
			  	  and end_date >= %s
			  )
			limit 1
			""",
			(customer_equipment, self.name, self.end_date, self.start_date),
			as_dict=True,
		)
		if existing:
			frappe.throw(
				f"Customer Equipment {customer_equipment} already has active coverage in {existing[0].parent}."
			)

	def recalculate_entitlements(self):
		for row in self.entitlements:
			row.remaining_quantity = max((row.included_quantity or 0) - (row.used_quantity or 0), 0)

	def update_customer_equipment_links(self):
		for row in self.covered_equipment:
			if not row.active:
				continue
			frappe.db.set_value(
				"Customer Equipment",
				row.customer_equipment,
				{
					"service_contract": self.name,
					"service_plan": self.service_plan,
					"coverage_status": "Covered",
				},
				update_modified=False,
			)


def update_contract_statuses():
	today = getdate(nowdate())
	for contract in frappe.get_all(
		"Service Contract",
		filters={"contract_status": ["in", ACTIVE_STATUSES]},
		fields=["name", "end_date"],
	):
		end_date = getdate(contract.end_date)
		new_status = "Expired" if end_date < today else "Expiring" if end_date <= add_days(today, 90) else "Active"
		if new_status != frappe.db.get_value("Service Contract", contract.name, "contract_status"):
			frappe.db.set_value("Service Contract", contract.name, "contract_status", new_status)


def send_contract_expiry_notifications():
	# Notification documents are intentionally deferred; this keeps the scheduled hook harmless in Phase 1.
	return
