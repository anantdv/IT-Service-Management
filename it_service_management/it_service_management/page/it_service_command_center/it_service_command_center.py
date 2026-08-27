from __future__ import annotations

import json

import frappe

from it_service_management.services.dashboard.common import get_filter_options
from it_service_management.services.dashboard.contracts import get_contract_dashboard
from it_service_management.services.dashboard.equipment import get_equipment_dashboard
from it_service_management.services.dashboard.financial import get_financial_dashboard
from it_service_management.services.dashboard.overview import get_dashboard_overview
from it_service_management.services.dashboard.rental import get_rental_dashboard
from it_service_management.services.dashboard.service import get_service_dashboard


ROLE_ALLOWLIST = {
	"System Manager",
	"Service Manager",
	"Rental Manager",
	"Finance Manager",
	"Accounts Manager",
	"Operations Manager",
	"Service Contract Manager",
	"Service Billing User",
	"IT Service Analyst",
	"IT Service Executive",
}


@frappe.whitelist()
def get_dashboard(tab="overview", filters=None, force_refresh=False):
	require_dashboard_access()
	filters = parse_filters(filters)
	force_refresh = bool(int(force_refresh)) if isinstance(force_refresh, str) else bool(force_refresh)

	methods = {
		"overview": get_dashboard_overview,
		"service": get_service_dashboard,
		"rental": get_rental_dashboard,
		"contracts": get_contract_dashboard,
		"equipment": get_equipment_dashboard,
		"financial": get_financial_dashboard,
	}
	return methods.get(tab, get_dashboard_overview)(filters, force_refresh)


@frappe.whitelist()
def get_options():
	require_dashboard_access()
	return get_filter_options()


def parse_filters(filters):
	if not filters:
		return {}
	if isinstance(filters, str):
		return json.loads(filters)
	return filters


def require_dashboard_access():
	user_roles = set(frappe.get_roles(frappe.session.user))
	if user_roles.isdisjoint(ROLE_ALLOWLIST):
		frappe.throw("You are not permitted to view the IT Service Management Command Center.", frappe.PermissionError)
