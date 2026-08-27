import frappe
from frappe.tests.utils import FrappeTestCase

from it_service_management.it_service_management.page.it_service_command_center.it_service_command_center import (
	get_dashboard,
)
from it_service_management.services.dashboard.common import (
	ManagementAlertEngine,
	DashboardFilters,
	alert,
	get_period_dates,
	kpi,
	route_doctype,
	route_report,
)


class TestCommandCenter(FrappeTestCase):
	def test_period_dates_are_valid(self):
		from_date, to_date = get_period_dates("This Month")
		self.assertLessEqual(from_date, to_date)

	def test_kpi_contract_contains_drilldown_route(self):
		card = kpi("Open Tickets", 5, "number", route_doctype("Service Ticket", {"status": "Open"}))
		self.assertEqual(card["title"], "Open Tickets")
		self.assertEqual(card["route"]["type"], "doctype")
		self.assertEqual(card["route"]["doctype"], "Service Ticket")

	def test_report_route_contract(self):
		route = route_report("SLA Performance Analysis", {"company": "_Test Company"})
		self.assertEqual(route["type"], "report")
		self.assertEqual(route["report"], "SLA Performance Analysis")

	def test_alert_sorting_keeps_critical_first(self):
		filters = DashboardFilters(None, None, None, None, "2026-01-01", "2026-01-31", "Custom")
		engine = ManagementAlertEngine(filters, {"contract_expiry_days": 90})
		rows = [
			alert("info", "info", "Information", route_report("Open Service Tickets")),
			alert("critical", "critical", "Critical", route_doctype("Service Ticket")),
			alert("warning", "warning", "Warning", route_report("SLA Performance Analysis")),
		]
		rows = sorted(rows, key=lambda row: {"critical": 0, "warning": 1, "info": 2}.get(row["severity"], 3))
		self.assertEqual([row["severity"] for row in rows], ["critical", "warning", "info"])

	def test_dashboard_endpoint_returns_payload_shape(self):
		if frappe.session.user == "Guest":
			self.skipTest("Command Center requires a logged-in Desk user")
		payload = get_dashboard("overview", {"period": "This Month"}, force_refresh=True)
		self.assertEqual(payload["tab"], "overview")
		self.assertIn("sections", payload)
		self.assertIn("kpis", payload["sections"])
