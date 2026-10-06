from __future__ import annotations

import frappe


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"label": "Priority", "fieldname": "priority", "fieldtype": "Data", "width": 120},
		{"label": "Open", "fieldname": "open_count", "fieldtype": "Int", "width": 100},
		{"label": "Resolved", "fieldname": "resolved_count", "fieldtype": "Int", "width": 100},
		{"label": "Breached SLA", "fieldname": "breached_count", "fieldtype": "Int", "width": 120},
	]
	conditions = ["ticket_type = 'Incident'"]
	values = {}
	if filters.get("from_date"):
		conditions.append("date(reported_datetime) >= %(from_date)s")
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("date(reported_datetime) <= %(to_date)s")
		values["to_date"] = filters["to_date"]

	data = frappe.db.sql(
		f"""
		select
			coalesce(priority, 'Medium') as priority,
			sum(case when status not in ('Resolved', 'Closed', 'Cancelled') then 1 else 0 end) as open_count,
			sum(case when status in ('Resolved', 'Closed') then 1 else 0 end) as resolved_count,
			sum(case when resolution_sla_status = 'Breached' then 1 else 0 end) as breached_count
		from `tabService Ticket`
		where {" and ".join(conditions)}
		group by coalesce(priority, 'Medium')
		order by field(priority, 'Critical', 'High', 'Medium', 'Low')
		""",
		values,
		as_dict=True,
	)
	return columns, data
