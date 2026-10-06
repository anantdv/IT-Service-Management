from __future__ import annotations

import frappe
from frappe.utils import now_datetime

from it_service_management.services.dashboard.common import get_currency, get_dashboard_settings, validate_filters


def get_itsm_dashboard(filters=None, force_refresh=False):
	dashboard_filters = validate_filters(filters or {})
	settings = get_dashboard_settings()
	from_date, to_date = dashboard_filters.from_date, dashboard_filters.to_date
	return {
		"tab": "itsm",
		"filters": dashboard_filters.__dict__,
		"settings": settings,
		"company_currency": get_currency(dashboard_filters.company),
		"last_refreshed": now_datetime().strftime("%H:%M"),
		"sections": {
			"kpis": [
				_kpi("Open Incidents", _ticket_count({"ticket_type": "Incident", "status": ["not in", ["Resolved", "Closed", "Cancelled"]]}), _doctype_route("Service Ticket", {"ticket_type": "Incident"})),
				_kpi("P1 Incidents", _ticket_count({"ticket_type": "Incident", "priority": "Critical", "status": ["not in", ["Resolved", "Closed", "Cancelled"]]}), _doctype_route("Service Ticket", {"ticket_type": "Incident", "priority": "Critical"}), "danger"),
				_kpi("P2 Incidents", _ticket_count({"ticket_type": "Incident", "priority": "High", "status": ["not in", ["Resolved", "Closed", "Cancelled"]]}), _doctype_route("Service Ticket", {"ticket_type": "Incident", "priority": "High"}), "warning"),
				_kpi("Major Incidents", frappe.db.count("Major Incident", {"status": ["not in", ["Closed"]]}), _doctype_route("Major Incident"), "danger"),
				_kpi("SLA Compliance %", _sla_compliance(from_date, to_date), {"type": "report", "report": "Incident Summary"}, "normal", "percent"),
				_kpi("Open Problems", frappe.db.count("ITSM Problem", {"status": ["not in", ["Closed", "Cancelled"]]}), _doctype_route("ITSM Problem")),
				_kpi("Changes Scheduled", frappe.db.count("ITSM Change Request", {"status": ["in", ["Approved", "Scheduled", "Implementation"]]}), _doctype_route("ITSM Change Request")),
				_kpi("Known Errors", frappe.db.count("ITSM Known Error", {"status": "Published"}), _doctype_route("ITSM Known Error")),
			],
			"charts": {
				"incidents_by_priority": _grouped_ticket_chart("Incidents by Priority", "priority", from_date, to_date),
				"incidents_by_service": _grouped_ticket_chart("Incidents by Service", "affected_service", from_date, to_date),
				"incidents_by_assignment_group": _grouped_ticket_chart("Incidents by Assignment Group", "assignment_group", from_date, to_date),
			},
			"tables": {
				"top_failing_configuration_items": [
					{"configuration_item": row.configuration_item or "Unspecified", "incidents": row.count}
					for row in _top_failing_cis(from_date, to_date)
				],
				"recent_changes": [
					{"change": row.name, "status": row.status, "risk": row.risk_level, "route": _doctype_route("ITSM Change Request", {"name": row.name})}
					for row in frappe.get_all("ITSM Change Request", fields=["name", "status", "risk_level"], order_by="modified desc", limit_page_length=5)
				],
			},
		},
	}


def _kpi(title, value, route=None, status="normal", kind="number"):
	return {"title": title, "value": value, "route": route, "status": status, "kind": kind}


def _doctype_route(doctype, filters=None):
	return {"type": "doctype", "doctype": doctype, "filters": filters or {}}


def _ticket_count(filters):
	return frappe.db.count("Service Ticket", filters)


def _sla_compliance(from_date, to_date):
	row = frappe.db.sql(
		"""
		select
			sum(case when resolution_sla_status = 'Met' then 1 else 0 end) as met,
			count(*) as total
		from `tabService Ticket`
		where ticket_type = 'Incident'
			and status in ('Resolved', 'Closed')
			and date(reported_datetime) between %(from_date)s and %(to_date)s
		""",
		{"from_date": from_date, "to_date": to_date},
		as_dict=True,
	)[0]
	return round((row.met or 0) / row.total * 100, 1) if row.total else 0


def _grouped_ticket_chart(title, fieldname, from_date, to_date):
	rows = frappe.db.sql(
		f"""
		select coalesce({fieldname}, 'Unspecified') as label, count(*) as value
		from `tabService Ticket`
		where ticket_type = 'Incident'
			and date(reported_datetime) between %(from_date)s and %(to_date)s
		group by coalesce({fieldname}, 'Unspecified')
		order by value desc
		limit 8
		""",
		{"from_date": from_date, "to_date": to_date},
		as_dict=True,
	)
	return {"title": title, "type": "bar", "labels": [row.label for row in rows], "values": [row.value for row in rows]}


def _top_failing_cis(from_date, to_date):
	return frappe.db.sql(
		"""
		select configuration_item, count(*) as count
		from `tabService Ticket`
		where ticket_type = 'Incident'
			and date(reported_datetime) between %(from_date)s and %(to_date)s
		group by configuration_item
		order by count desc
		limit 10
		""",
		{"from_date": from_date, "to_date": to_date},
		as_dict=True,
	)
