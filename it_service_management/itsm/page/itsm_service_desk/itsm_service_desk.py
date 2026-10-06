from __future__ import annotations

import frappe


@frappe.whitelist()
def get_service_desk():
	return {
		"kpis": {
			"new": _ticket_count({"status": ["in", ["New", "Open"]]}),
			"unassigned": _ticket_count({"assigned_to": ["in", ["", None]], "status": ["not in", ["Closed", "Cancelled"]]}),
			"p1": _ticket_count({"priority": "Critical", "status": ["not in", ["Closed", "Cancelled"]]}),
			"p2": _ticket_count({"priority": "High", "status": ["not in", ["Closed", "Cancelled"]]}),
			"sla_at_risk": _ticket_count({"resolution_sla_status": "At Risk", "status": ["not in", ["Closed", "Cancelled"]]}),
			"sla_breached": _ticket_count({"resolution_sla_status": "Breached", "status": ["not in", ["Closed", "Cancelled"]]}),
			"major_incidents": frappe.db.count("Major Incident", {"status": ["not in", ["Closed"]]}),
			"waiting": _ticket_count({"status": ["in", ["Pending", "Awaiting Customer", "Awaiting Parts"]]}),
		},
		"my_queue": _tickets({"assigned_to": frappe.session.user}),
		"unassigned_queue": _tickets({"assigned_to": ["in", ["", None]]}),
		"critical_incidents": _tickets({"ticket_type": "Incident", "priority": "Critical"}),
		"sla_at_risk": _tickets({"resolution_sla_status": "At Risk"}),
	}


def _ticket_count(filters):
	return frappe.db.count("Service Ticket", filters)


def _tickets(filters):
	filters = dict(filters)
	filters["status"] = ["not in", ["Closed", "Cancelled"]]
	return frappe.get_all(
		"Service Ticket",
		filters=filters,
		fields=["name", "subject", "customer", "priority", "status", "resolution_due"],
		order_by="modified desc",
		limit_page_length=10,
	)
