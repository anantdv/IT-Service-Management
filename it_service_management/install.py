from __future__ import annotations

import importlib
import json

import frappe


APP_NAME = "it_service_management"
APP_TITLE = "IT Service Management"
APP_ROUTE = "it-service-management"


def after_install():
	ensure_navigation()
	run_optional_hook("it_service_management.rental_management.install", "after_install")


def after_migrate():
	ensure_navigation()
	run_optional_hook("it_service_management.rental_management.install", "after_migrate")


def has_app_permission():
	return True


def run_optional_hook(module_path, method_name):
	try:
		module = importlib.import_module(module_path)
	except ImportError:
		return

	method = getattr(module, method_name, None)
	if method:
		method()


def ensure_navigation():
	if not frappe.db.exists("DocType", "Workspace"):
		return

	ensure_workspace("IT Service Management", build_main_workspace())
	ensure_workspace("Service Operations", build_operations_workspace())
	frappe.clear_cache()


def ensure_workspace(name, data):
	doc = frappe.get_doc("Workspace", name) if frappe.db.exists("Workspace", name) else frappe.new_doc("Workspace")
	doc.update(data)

	if name != doc.name:
		doc.name = name

	set_if_field_exists(doc, "app", APP_NAME)
	set_if_field_exists(doc, "module", data.get("module") or "IT Service Management")
	set_if_field_exists(doc, "type", "Workspace")
	set_if_field_exists(doc, "standard", 1)
	set_if_field_exists(doc, "is_standard", 1)
	set_if_field_exists(doc, "public", 1)
	set_if_field_exists(doc, "is_hidden", 0)
	set_if_field_exists(doc, "for_user", "")
	set_if_field_exists(doc, "parent_page", "")

	reset_child_table(doc, "shortcuts", data.get("shortcuts", []))
	reset_child_table(doc, "sidebar_items", data.get("sidebar_items", []))

	doc.flags.ignore_permissions = True
	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)


def set_if_field_exists(doc, fieldname, value):
	if doc.meta.has_field(fieldname):
		doc.set(fieldname, value)


def reset_child_table(doc, fieldname, rows):
	if not doc.meta.has_field(fieldname):
		return

	doc.set(fieldname, [])
	for row in rows:
		doc.append(fieldname, row)


def content(*blocks):
	return json.dumps(blocks, separators=(",", ":"))


def header(block_id, text):
	return {"id": block_id, "type": "header", "data": {"text": text}}


def shortcut(block_id, label, col=3):
	return {"id": block_id, "type": "shortcut", "data": {"shortcut_name": label, "col": col}}


def build_main_workspace():
	shortcuts = [
		doctype_shortcut("Service Tickets", "Service Ticket"),
		doctype_shortcut("Service Jobs", "Service Job"),
		doctype_shortcut("Customer Equipment", "Customer Equipment"),
		doctype_shortcut("Customer Sites", "Customer Site"),
		doctype_shortcut("Service Contracts", "Service Contract"),
		doctype_shortcut("Service Teams", "Service Team"),
		doctype_shortcut("Service Expenses", "Service Expense"),
		doctype_shortcut("Service Settings", "IT Service Settings"),
		report_shortcut("Open Service Tickets", "Open Service Tickets"),
		report_shortcut("Technician Workload", "Technician Workload"),
		report_shortcut("SLA Compliance", "Service SLA Compliance"),
		report_shortcut("Jobs Pending Billing", "Completed Service Jobs Pending Billing"),
	]

	return {
		"doctype": "Workspace",
		"name": APP_TITLE,
		"label": APP_TITLE,
		"title": APP_TITLE,
		"module": "IT Service Management",
		"icon": "tool",
		"route": APP_ROUTE,
		"content": content(
			header("service-desk", "Service Desk"),
			shortcut("tickets", "Service Tickets"),
			shortcut("jobs", "Service Jobs"),
			shortcut("equipment", "Customer Equipment"),
			shortcut("sites", "Customer Sites"),
			header("contracts", "Contracts"),
			shortcut("contracts-link", "Service Contracts"),
			shortcut("settings", "Service Settings"),
			header("reports", "Reports"),
			shortcut("open-tickets", "Open Service Tickets"),
			shortcut("workload", "Technician Workload"),
			shortcut("sla", "SLA Compliance"),
		),
		"shortcuts": shortcuts,
		"sidebar_items": [
			sidebar_section("Service Desk", "ticket"),
			sidebar_link("Service Tickets", "Service Ticket", "DocType", "ticket", child=1),
			sidebar_link("Service Jobs", "Service Job", "DocType", "assign", child=1),
			sidebar_link("Part Requests", "Service Part Request", "DocType", "stock", child=1),
			sidebar_section("Field Service", "location"),
			sidebar_link("Service Teams", "Service Team", "DocType", "users", child=1),
			sidebar_link("Service Zones", "Service Zone", "DocType", "location", child=1),
			sidebar_link("Service Expenses", "Service Expense", "DocType", "expense-claim", child=1),
			sidebar_section("Contracts", "contract"),
			sidebar_link("Service Contracts", "Service Contract", "DocType", "contract", child=1),
			sidebar_link("Service Plans", "Service Plan", "DocType", "list", child=1),
			sidebar_link("Warranty Policies", "Warranty Policy", "DocType", "verified", child=1),
			sidebar_section("Equipment", "asset"),
			sidebar_link("Customer Equipment", "Customer Equipment", "DocType", "asset", child=1),
			sidebar_link("Customer Sites", "Customer Site", "DocType", "organization", child=1),
			sidebar_link("Service Settings", "IT Service Settings", "DocType", "setting", child=1),
			sidebar_section("Reports", "table"),
			sidebar_link("Open Tickets", "Open Service Tickets", "Report", "table", child=1),
			sidebar_link("Technician Workload", "Technician Workload", "Report", "table", child=1),
			sidebar_link("SLA Compliance", "Service SLA Compliance", "Report", "table", child=1),
		],
	}


def build_operations_workspace():
	shortcuts = [
		doctype_shortcut("New Service Ticket", "Service Ticket"),
		doctype_shortcut("Service Tickets", "Service Ticket"),
		doctype_shortcut("Service Jobs", "Service Job"),
		doctype_shortcut("Service Part Requests", "Service Part Request"),
		doctype_shortcut("Service Expenses", "Service Expense"),
		doctype_shortcut("Customer Equipment", "Customer Equipment"),
		doctype_shortcut("Service Contracts", "Service Contract"),
		report_shortcut("Open Service Tickets", "Open Service Tickets"),
		report_shortcut("Technician Workload", "Technician Workload"),
		report_shortcut("Service SLA Compliance", "Service SLA Compliance"),
		report_shortcut("Completed Jobs Pending Billing", "Completed Service Jobs Pending Billing"),
	]

	return {
		"doctype": "Workspace",
		"name": "Service Operations",
		"label": "Service Operations",
		"title": "Service Operations",
		"module": "IT Service Management",
		"icon": "assign",
		"route": "service-operations",
		"content": content(
			header("operations", "Service Operations"),
			shortcut("new-ticket", "New Service Ticket"),
			shortcut("tickets", "Service Tickets"),
			shortcut("jobs", "Service Jobs"),
			shortcut("parts", "Service Part Requests"),
			shortcut("expenses", "Service Expenses"),
			header("reports", "Reports"),
			shortcut("open-tickets", "Open Service Tickets"),
			shortcut("workload", "Technician Workload"),
			shortcut("sla", "Service SLA Compliance"),
		),
		"shortcuts": shortcuts,
		"sidebar_items": [
			sidebar_section("Operations", "assign"),
			sidebar_link("New Service Ticket", "Service Ticket", "DocType", "add", child=1),
			sidebar_link("Service Tickets", "Service Ticket", "DocType", "ticket", child=1),
			sidebar_link("Service Jobs", "Service Job", "DocType", "assign", child=1),
			sidebar_link("Part Requests", "Service Part Request", "DocType", "stock", child=1),
			sidebar_link("Expenses", "Service Expense", "DocType", "expense-claim", child=1),
			sidebar_section("Reports", "table"),
			sidebar_link("Open Tickets", "Open Service Tickets", "Report", "table", child=1),
			sidebar_link("Technician Workload", "Technician Workload", "Report", "table", child=1),
			sidebar_link("SLA Compliance", "Service SLA Compliance", "Report", "table", child=1),
		],
	}


def doctype_shortcut(label, link_to):
	return {"type": "DocType", "label": label, "link_to": link_to}


def report_shortcut(label, link_to):
	return {"type": "Report", "label": label, "link_to": link_to}


def sidebar_section(label, icon):
	return {
		"label": label,
		"type": "Section Break",
		"icon": icon,
		"collapsible": 1,
	}


def sidebar_link(label, link_to, link_type, icon, child=0):
	return {
		"label": label,
		"type": "Link",
		"link_type": link_type,
		"link_to": link_to,
		"icon": icon,
		"child": child,
	}
