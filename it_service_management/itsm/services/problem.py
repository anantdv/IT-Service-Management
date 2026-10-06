from __future__ import annotations

from frappe.utils import add_days, get_datetime, now_datetime
import frappe


def get_recurring_incident_suggestion(ticket, days: int = 30, threshold: int = 3) -> dict:
	if not ticket.get("configuration_item"):
		return {"recurring": False, "count": 0}
	from_date = add_days(now_datetime(), -days)
	filters = {
		"ticket_type": "Incident",
		"configuration_item": ticket.configuration_item,
		"creation": [">=", get_datetime(from_date)],
	}
	if ticket.get("incident_category"):
		filters["incident_category"] = ticket.incident_category
	if ticket.get("incident_subcategory"):
		filters["incident_subcategory"] = ticket.incident_subcategory
	count = frappe.db.count("Service Ticket", filters)
	return {
		"recurring": count >= threshold,
		"count": count,
		"message": "Possible recurring incident. Consider Problem Management." if count >= threshold else "",
	}
