from __future__ import annotations

import frappe

from it_service_management.service_operations.services.sla import update_ticket_sla_status


def evaluate_active_ticket_slas():
	tickets = frappe.get_all(
		"Service Ticket",
		filters={"status": ["not in", ["Resolved", "Closed", "Cancelled"]]},
		fields=["name"],
	)
	for row in tickets:
		ticket = frappe.get_doc("Service Ticket", row.name)
		update_ticket_sla_status(ticket)
		_notify_threshold(ticket, "response")
		_notify_threshold(ticket, "resolution")
		ticket.save(ignore_permissions=True)


def _notify_threshold(ticket, kind):
	percentage = ticket.get(f"{kind}_sla_percentage") or 0
	for threshold, field in ((75, f"{kind}_75_notified"), (90, f"{kind}_90_notified"), (100, f"{kind}_breach_notified")):
		if percentage >= threshold and not ticket.get(field):
			ticket.set(field, 1)
			label = "breached" if threshold == 100 else f"{threshold}%"
			ticket.add_comment("Comment", f"{kind.title()} SLA {label}")
