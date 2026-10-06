from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from it_service_management.itsm.services.change_risk import calculate_change_risk
from it_service_management.itsm.services.priority import calculate_priority
from it_service_management.itsm.services.problem import get_recurring_incident_suggestion
from it_service_management.service_operations.services.sla import update_ticket_sla_status


class TestITSMFoundation(FrappeTestCase):
	def test_impact_urgency_priority_fallback(self):
		self.assertEqual(calculate_priority("Critical", "Critical"), "Critical")
		self.assertEqual(calculate_priority("High", "Medium"), "High")
		self.assertEqual(calculate_priority("Low", "Low"), "Low")

	def test_sla_actual_minutes_handles_datetime_strings(self):
		ticket = frappe._dict(
			{
				"reported_datetime": "2026-10-06 10:00:00",
				"first_response_datetime": "2026-10-06 10:30:00",
				"response_due": "2026-10-06 11:00:00",
				"resolution_datetime": "2026-10-06 12:00:00",
				"resolution_due": "2026-10-06 13:00:00",
			}
		)
		update_ticket_sla_status(ticket)
		self.assertEqual(ticket.response_sla_status, "Met")
		self.assertEqual(ticket.actual_response_minutes, 30)
		self.assertGreaterEqual(ticket.actual_resolution_minutes, 0)

	def test_change_risk_calculation(self):
		score, level = calculate_change_risk(
			frappe._dict(
				{
					"risk_level": "High",
					"impact": "High",
					"urgency": "High",
					"downtime_required": 1,
					"expected_downtime_minutes": 120,
				}
			)
		)
		self.assertGreaterEqual(score, 75)
		self.assertEqual(level, "Critical")

	def test_recurring_incident_suggestion_without_ci(self):
		result = get_recurring_incident_suggestion(frappe._dict({"configuration_item": None}))
		self.assertFalse(result["recurring"])
		self.assertEqual(result["count"], 0)
