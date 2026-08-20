from __future__ import annotations

import frappe


def execute(filters=None):
	group_by = (filters or {}).get("group_by") or "customer"
	allowed = {
		"Customer": "customer",
		"Service Contract": "service_contract",
		"Priority": "priority",
		"Status": "status",
	}
	column = allowed.get(group_by, group_by if group_by in allowed.values() else "customer")
	columns = [
		f"{column.replace('_', ' ').title()}:Data:180",
		"Tickets:Int:90",
		"Response Met:Int:110",
		"Response Breached:Int:130",
		"Resolution Met:Int:120",
		"Resolution Breached:Int:140",
		"Compliance %:Percent:110",
	]
	data = frappe.db.sql(
		f"""
		select {column}, count(*),
		       sum(response_sla_status = 'Met'),
		       sum(response_sla_status = 'Breached'),
		       sum(resolution_sla_status = 'Met'),
		       sum(resolution_sla_status = 'Breached'),
		       (sum(response_sla_status = 'Met') + sum(resolution_sla_status = 'Met')) / nullif(count(*) * 2, 0) * 100
		from `tabService Ticket`
		group by {column}
		order by {column}
		"""
	)
	return columns, data
