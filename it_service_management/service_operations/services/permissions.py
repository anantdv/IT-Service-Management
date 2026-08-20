from __future__ import annotations

import frappe


def get_employee_for_user(user=None):
	user = user or frappe.session.user
	return frappe.db.get_value("Employee", {"user_id": user}, "name")


def service_job_query(user=None):
	user = user or frappe.session.user
	if "Service Manager" in frappe.get_roles(user) or "Service Dispatcher" in frappe.get_roles(user):
		return ""
	employee = get_employee_for_user(user)
	if not employee:
		return "1=0"
	return f"`tabService Job`.assigned_technician = {frappe.db.escape(employee)}"


def service_ticket_query(user=None):
	user = user or frappe.session.user
	if "Service Manager" in frappe.get_roles(user) or "Service Dispatcher" in frappe.get_roles(user):
		return ""
	employee = get_employee_for_user(user)
	if not employee:
		return "1=0"
	return (
		"`tabService Ticket`.name in (select service_ticket from `tabService Job` "
		f"where assigned_technician = {frappe.db.escape(employee)} and service_ticket is not null)"
	)


def has_service_job_permission(doc, user=None, permission_type=None):
	if not user:
		user = frappe.session.user
	if "Service Manager" in frappe.get_roles(user) or "Service Dispatcher" in frappe.get_roles(user):
		return True
	employee = get_employee_for_user(user)
	return bool(employee and doc.assigned_technician == employee)
