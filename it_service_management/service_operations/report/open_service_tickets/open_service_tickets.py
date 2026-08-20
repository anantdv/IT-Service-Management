from __future__ import annotations

import frappe


def execute(filters=None):
	filters = filters or {}
	conditions = ["st.status not in ('Closed', 'Cancelled')"]
	values = {}
	for key, column in {
		"customer": "st.customer",
		"site": "st.customer_site",
		"priority": "st.priority",
		"status": "st.status",
		"sla_status": "st.resolution_sla_status",
	}.items():
		if filters.get(key):
			conditions.append(f"{column} = %({key})s")
			values[key] = filters[key]
	if filters.get("technician"):
		conditions.append("sj.assigned_technician = %(technician)s")
		values["technician"] = filters["technician"]
	if filters.get("from_date"):
		conditions.append("date(st.reported_datetime) >= %(from_date)s")
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("date(st.reported_datetime) <= %(to_date)s")
		values["to_date"] = filters["to_date"]
	columns = [
		"Ticket:Link/Service Ticket:150",
		"Customer:Link/Customer:180",
		"Site:Link/Customer Site:160",
		"Equipment:Link/Customer Equipment:160",
		"Serial No:Link/Serial No:140",
		"Priority:Data:90",
		"Status:Data:130",
		"Technician:Link/Employee:150",
		"Reported Date:Datetime:160",
		"Response Due:Datetime:160",
		"Resolution Due:Datetime:160",
		"SLA Status:Data:120",
		"Coverage Source:Data:130",
	]
	data = frappe.db.sql(
		f"""
		select st.name, st.customer, st.customer_site, st.customer_equipment, st.serial_no, st.priority,
		       st.status, max(sj.assigned_technician), st.reported_datetime, st.response_due,
		       st.resolution_due, st.resolution_sla_status, st.coverage_source
		from `tabService Ticket` st
		left join `tabService Job` sj on sj.service_ticket = st.name
		where {' and '.join(conditions)}
		group by st.name
		order by st.priority, st.reported_datetime
		""",
		values,
	)
	return columns, data
