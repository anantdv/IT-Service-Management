from __future__ import annotations

import frappe

from it_service_management.service_operations.services.sla import update_ticket_sla_status


def evaluate_open_incidents():
	names = frappe.get_all(
		"Service Ticket",
		filters={"ticket_type": ["in", ["Incident", "Alert"]], "status": ["not in", ["Resolved", "Closed", "Cancelled"]]},
		pluck="name",
		limit_page_length=500,
	)
	for name in names:
		ticket = frappe.get_doc("Service Ticket", name)
		update_ticket_sla_status(ticket)
		ticket.flags.ignore_permissions = True
		ticket.save(ignore_permissions=True)
