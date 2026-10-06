from __future__ import annotations

import frappe


DEFAULT_PRIORITY_MATRIX = {
	("Low", "Low"): "Low",
	("Low", "Medium"): "Low",
	("Low", "High"): "Medium",
	("Low", "Critical"): "Medium",
	("Medium", "Low"): "Low",
	("Medium", "Medium"): "Medium",
	("Medium", "High"): "High",
	("Medium", "Critical"): "High",
	("High", "Low"): "Medium",
	("High", "Medium"): "High",
	("High", "High"): "High",
	("High", "Critical"): "Critical",
	("Critical", "Low"): "High",
	("Critical", "Medium"): "High",
	("Critical", "High"): "Critical",
	("Critical", "Critical"): "Critical",
}

PRIORITY_ALIASES = {
	"P1": "Critical",
	"P1 Critical": "Critical",
	"P2": "High",
	"P2 High": "High",
	"P3": "Medium",
	"P3 Medium": "Medium",
	"P4": "Low",
	"P4 Low": "Low",
}

OVERRIDE_ROLES = {"System Manager", "Service Manager", "ITSM Service Manager", "ITSM Administrator"}


def calculate_priority(impact: str | None, urgency: str | None) -> str:
	impact = impact or "Medium"
	urgency = urgency or "Medium"
	configured = _get_configured_priority(impact, urgency)
	return normalize_priority(configured or DEFAULT_PRIORITY_MATRIX.get((impact, urgency), "Medium"))


def normalize_priority(priority: str | None) -> str:
	if not priority:
		return "Medium"
	return PRIORITY_ALIASES.get(priority, priority)


def apply_ticket_priority(ticket) -> None:
	if not ticket.get("impact") or not ticket.get("urgency"):
		ticket.priority = normalize_priority(ticket.priority)
		return

	calculated = calculate_priority(ticket.impact, ticket.urgency)
	current = normalize_priority(ticket.priority)
	if current == calculated:
		ticket.priority = calculated
		return

	if ticket.get("override_reason"):
		if set(frappe.get_roles()).intersection(OVERRIDE_ROLES):
			ticket.priority = current
			return
		frappe.throw("Only an ITSM Service Manager or System Manager can override calculated priority.")

	ticket.priority = calculated


def _get_configured_priority(impact: str, urgency: str) -> str | None:
	if not frappe.db.exists("DocType", "ITSM Priority Matrix"):
		return None
	matrix = frappe.db.get_value(
		"ITSM Priority Matrix",
		{"impact": impact, "urgency": urgency, "active": 1},
		"priority",
		order_by="modified desc",
	)
	return matrix
