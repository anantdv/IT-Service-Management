from __future__ import annotations

import frappe
from frappe.utils import cint, flt, nowdate


def check_customer_credit(customer, company, extra_amount=0, allow_block=False):
	settings = frappe.get_single("IT Service Settings")
	if allow_block and cint(settings.block_new_chargeable_service_on_credit_hold):
		from erpnext.selling.doctype.customer.customer import check_credit_limit

		check_credit_limit(customer, company, extra_amount=flt(extra_amount))
	if not cint(settings.warn_on_overdue_customer):
		return 0
	overdue = frappe.db.sql(
		"""select coalesce(sum(outstanding_amount),0) from `tabSales Invoice`
		where customer=%s and company=%s and docstatus=1 and outstanding_amount>0 and due_date<%s""",
		(customer, company, nowdate()),
	)[0][0]
	if overdue and not frappe.flags.in_test:
		frappe.msgprint(f"Customer {customer} has overdue receivables of {frappe.format_value(overdue, {'fieldtype': 'Currency'})}.", indicator="orange", alert=True)
	return overdue
