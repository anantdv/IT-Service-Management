from __future__ import annotations

import frappe


def execute(filters=None):
	columns = [
		"Service Job:Link/Service Job:150",
		"Customer:Link/Customer:180",
		"Site:Link/Customer Site:160",
		"Equipment:Link/Customer Equipment:160",
		"Completion Date:Datetime:160",
		"Coverage Source:Data:130",
		"Internal Cost:Currency:120",
		"Billable Amount:Currency:130",
		"Billing Status:Data:130",
	]
	data = frappe.db.sql(
		"""
		select name, customer, customer_site, customer_equipment, completion_datetime, coverage_source,
		       total_internal_cost, total_billable_amount, billing_status
		from `tabService Job`
		where status = 'Completed'
		  and billing_status in ('Ready for Billing', 'Pending Review', 'Not Calculated')
		order by completion_datetime desc
		"""
	)
	return columns, data
