from __future__ import annotations

import frappe


@frappe.whitelist()
def get_changes():
	return frappe.get_all(
		"ITSM Change Request",
		filters={"status": ["in", ["Approved", "Scheduled", "Implementation"]]},
		fields=["name", "title", "status", "affected_service", "primary_configuration_item", "risk_level", "change_owner", "planned_start", "planned_end", "downtime_required"],
		order_by="planned_start asc",
		limit_page_length=100,
	)
