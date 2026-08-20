from __future__ import annotations

import frappe
from frappe.utils import nowdate


def execute(filters=None):
	columns = [
		"Technician:Link/Employee:180",
		"Assigned Jobs:Int:110",
		"Scheduled Today:Int:120",
		"In Progress:Int:100",
		"Awaiting Parts:Int:110",
		"Completed Today:Int:120",
		"Overdue Jobs:Int:100",
		"Critical Jobs:Int:100",
		"Total Planned Hours:Float:130",
	]
	today = nowdate()
	data = frappe.db.sql(
		"""
		select assigned_technician,
		       sum(status not in ('Completed','Cancelled')) assigned_jobs,
		       sum(scheduled_date = %(today)s) scheduled_today,
		       sum(status = 'Work In Progress') in_progress,
		       sum(status = 'Awaiting Parts') awaiting_parts,
		       sum(status = 'Completed' and date(completion_datetime) = %(today)s) completed_today,
		       sum(scheduled_end_datetime < now() and status not in ('Completed','Cancelled')) overdue_jobs,
		       sum(priority = 'Critical' and status not in ('Completed','Cancelled')) critical_jobs,
		       sum(timestampdiff(minute, scheduled_start_datetime, scheduled_end_datetime) / 60) total_planned_hours
		from `tabService Job`
		where assigned_technician is not null and assigned_technician != ''
		group by assigned_technician
		order by assigned_technician
		""",
		{"today": today},
	)
	return columns, data
