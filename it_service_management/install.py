from __future__ import annotations

import importlib
import json

import frappe


APP_NAME = "it_service_management"
APP_TITLE = "IT Service Management"
APP_ROUTE = "it-service-management"


def after_install():
	ensure_itsm_module()
	ensure_navigation()
	ensure_itsm_defaults()
	run_optional_hook("it_service_management.rental_management.install", "after_install")


def after_migrate():
	ensure_itsm_module()
	ensure_navigation()
	ensure_itsm_defaults()
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


def ensure_itsm_module():
	if not frappe.db.exists("DocType", "Module Def"):
		return
	if frappe.db.exists("Module Def", "ITSM"):
		frappe.db.set_value("Module Def", "ITSM", "app_name", APP_NAME, update_modified=False)
		return
	module = frappe.new_doc("Module Def")
	module.module_name = "ITSM"
	module.app_name = APP_NAME
	module.insert(ignore_permissions=True)


def ensure_itsm_defaults():
	if not frappe.db.exists("DocType", "ITSM Priority Matrix"):
		return
	for impact, urgency, priority, response, resolution in [
		("Low", "Low", "Low", 480, 2880),
		("Low", "Medium", "Low", 480, 2880),
		("Low", "High", "Medium", 240, 1440),
		("Low", "Critical", "Medium", 240, 1440),
		("Medium", "Low", "Low", 480, 2880),
		("Medium", "Medium", "Medium", 240, 1440),
		("Medium", "High", "High", 120, 480),
		("Medium", "Critical", "High", 120, 480),
		("High", "Low", "Medium", 240, 1440),
		("High", "Medium", "High", 120, 480),
		("High", "High", "High", 120, 480),
		("High", "Critical", "Critical", 60, 240),
		("Critical", "Low", "High", 120, 480),
		("Critical", "Medium", "High", 120, 480),
		("Critical", "High", "Critical", 60, 240),
		("Critical", "Critical", "Critical", 60, 240),
	]:
		name = f"{impact}-{urgency}"
		if not frappe.db.exists("ITSM Priority Matrix", name):
			doc = frappe.new_doc("ITSM Priority Matrix")
			doc.impact = impact
			doc.urgency = urgency
			doc.priority = priority
			doc.response_minutes = response
			doc.resolution_minutes = resolution
			doc.active = 1
			doc.insert(ignore_permissions=True)

	if frappe.db.exists("DocType", "Configuration Item Type"):
		for type_name in [
			"Server",
			"Workstation",
			"Laptop",
			"Printer",
			"Firewall",
			"Router",
			"Switch",
			"Access Point",
			"Application",
			"Database",
			"Virtual Machine",
			"Cloud Service",
			"Network Link",
			"Storage",
			"UPS",
			"Business Service",
		]:
			if not frappe.db.exists("Configuration Item Type", type_name):
				doc = frappe.new_doc("Configuration Item Type")
				doc.type_name = type_name
				doc.active = 1
				doc.insert(ignore_permissions=True)


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
		url_shortcut("Management Command Center", "/app/it-service-command-center"),
		url_shortcut("ITSM Service Desk", "/app/itsm-service-desk"),
		url_shortcut("Change Calendar", "/app/itsm-change-calendar"),
		doctype_shortcut("Service Tickets", "Service Ticket"),
		doctype_shortcut("Major Incidents", "Major Incident"),
		doctype_shortcut("Problems", "ITSM Problem"),
		doctype_shortcut("Known Errors", "ITSM Known Error"),
		doctype_shortcut("Change Requests", "ITSM Change Request"),
		doctype_shortcut("Knowledge Articles", "ITSM Knowledge Article"),
		doctype_shortcut("ITSM Services", "ITSM Service"),
		doctype_shortcut("Configuration Items", "Configuration Item"),
		doctype_shortcut("Service Request Types", "Service Request Type"),
		doctype_shortcut("Assignment Groups", "ITSM Assignment Group"),
		doctype_shortcut("Priority Matrix", "ITSM Priority Matrix"),
		doctype_shortcut("Service Jobs", "Service Job"),
		doctype_shortcut("Remote Support Sessions", "Remote Support Session"),
		doctype_shortcut("Part Requests", "Service Part Request"),
		doctype_shortcut("Service Expenses", "Service Expense"),
		doctype_shortcut("Customer Equipment", "Customer Equipment"),
		doctype_shortcut("Customer Sites", "Customer Site"),
		doctype_shortcut("Service Contracts", "Service Contract"),
		doctype_shortcut("Service Plans", "Service Plan"),
		doctype_shortcut("Warranty Policies", "Warranty Policy"),
		doctype_shortcut("Service Teams", "Service Team"),
		doctype_shortcut("Service Zones", "Service Zone"),
		doctype_shortcut("Checklist Templates", "Service Checklist Template"),
		doctype_shortcut("Service Charge Rules", "Service Charge Rule"),
		doctype_shortcut("Service Settings", "IT Service Settings"),
		report_shortcut("Open Service Tickets", "Open Service Tickets"),
		report_shortcut("Incident Summary", "Incident Summary"),
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
			header("management", "Management"),
			shortcut("command-center", "Management Command Center"),
			shortcut("service-desk-console", "ITSM Service Desk"),
			header("service-desk", "Service Desk"),
			shortcut("tickets", "Service Tickets"),
			shortcut("major-incidents", "Major Incidents"),
			shortcut("problems", "Problems"),
			shortcut("known-errors", "Known Errors"),
			shortcut("changes", "Change Requests"),
			shortcut("knowledge", "Knowledge Articles"),
			shortcut("jobs", "Service Jobs"),
			shortcut("remote-support", "Remote Support Sessions"),
			shortcut("part-requests", "Part Requests"),
			header("field-service", "Field Service"),
			shortcut("teams", "Service Teams"),
			shortcut("zones", "Service Zones"),
			shortcut("expenses", "Service Expenses"),
			header("contracts", "Contracts"),
			shortcut("contracts-link", "Service Contracts"),
			shortcut("plans", "Service Plans"),
			shortcut("warranty", "Warranty Policies"),
			header("equipment", "Equipment"),
			shortcut("configuration-items", "Configuration Items"),
			shortcut("equipment-link", "Customer Equipment"),
			shortcut("sites", "Customer Sites"),
			shortcut("checklists", "Checklist Templates"),
			header("reports", "Reports"),
			shortcut("incident-summary", "Incident Summary"),
			shortcut("open-tickets", "Open Service Tickets"),
			shortcut("workload", "Technician Workload"),
			shortcut("sla", "SLA Compliance"),
			header("setup", "Setup"),
			shortcut("services", "ITSM Services"),
			shortcut("request-types", "Service Request Types"),
			shortcut("assignment-groups", "Assignment Groups"),
			shortcut("priority-matrix", "Priority Matrix"),
			shortcut("settings", "Service Settings"),
			shortcut("charge-rules", "Service Charge Rules"),
		),
		"shortcuts": shortcuts,
		"sidebar_items": [
			sidebar_link("Home", APP_TITLE, "Workspace", "house"),
			sidebar_link("Management Command Center", "/app/it-service-command-center", "URL", "dashboard"),
			sidebar_link("ITSM Service Desk", "/app/itsm-service-desk", "URL", "ticket"),
			sidebar_section("Service Desk", "ticket"),
			sidebar_link("Service Tickets", "Service Ticket", "DocType", "ticket", child=1),
			sidebar_link("Major Incidents", "Major Incident", "DocType", "alert-triangle", child=1),
			sidebar_link("Problems", "ITSM Problem", "DocType", "help", child=1),
			sidebar_link("Known Errors", "ITSM Known Error", "DocType", "knowledge-base", child=1),
			sidebar_link("Change Requests", "ITSM Change Request", "DocType", "git-pull-request", child=1),
			sidebar_link("Change Calendar", "/app/itsm-change-calendar", "URL", "calendar", child=1),
			sidebar_link("Knowledge", "ITSM Knowledge Article", "DocType", "knowledge-base", child=1),
			sidebar_link("Service Jobs", "Service Job", "DocType", "assign", child=1),
			sidebar_link("Part Requests", "Service Part Request", "DocType", "stock", child=1),
			sidebar_link("Remote Support", "Remote Support Session", "DocType", "call", child=1),
			sidebar_link("Service Expenses", "Service Expense", "DocType", "expense-claim", child=1),
			sidebar_section("Field Service", "location"),
			sidebar_link("Service Teams", "Service Team", "DocType", "users", child=1),
			sidebar_link("Service Zones", "Service Zone", "DocType", "location", child=1),
			sidebar_link("Checklist Templates", "Service Checklist Template", "DocType", "list", child=1),
			sidebar_section("Contracts", "contract"),
			sidebar_link("Service Contracts", "Service Contract", "DocType", "contract", child=1),
			sidebar_link("Service Plans", "Service Plan", "DocType", "list", child=1),
			sidebar_link("Warranty Policies", "Warranty Policy", "DocType", "verified", child=1),
			sidebar_link("Charge Rules", "Service Charge Rule", "DocType", "rules", child=1),
			sidebar_section("Equipment", "asset"),
			sidebar_link("Configuration Items", "Configuration Item", "DocType", "cluster", child=1),
			sidebar_link("Customer Equipment", "Customer Equipment", "DocType", "asset", child=1),
			sidebar_link("Customer Sites", "Customer Site", "DocType", "organization", child=1),
			sidebar_section("Reports", "table"),
			sidebar_link("Incident Summary", "Incident Summary", "Report", "table", child=1),
			sidebar_link("Open Tickets", "Open Service Tickets", "Report", "table", child=1),
			sidebar_link("Technician Workload", "Technician Workload", "Report", "table", child=1),
			sidebar_link("SLA Compliance", "Service SLA Compliance", "Report", "table", child=1),
			sidebar_link("Jobs Pending Billing", "Completed Service Jobs Pending Billing", "Report", "table", child=1),
			sidebar_section("Setup", "setting"),
			sidebar_link("ITSM Services", "ITSM Service", "DocType", "folder-normal", child=1),
			sidebar_link("Request Types", "Service Request Type", "DocType", "list", child=1),
			sidebar_link("Assignment Groups", "ITSM Assignment Group", "DocType", "users", child=1),
			sidebar_link("CI Types", "Configuration Item Type", "DocType", "cluster", child=1),
			sidebar_link("Priority Matrix", "ITSM Priority Matrix", "DocType", "rules", child=1),
			sidebar_link("Service Settings", "IT Service Settings", "DocType", "setting", child=1),
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
			sidebar_link("Home", APP_TITLE, "Workspace", "house"),
			sidebar_section("Operations", "assign"),
			sidebar_link("New Service Ticket", "Service Ticket", "DocType", "add", child=1),
			sidebar_link("Service Tickets", "Service Ticket", "DocType", "ticket", child=1),
			sidebar_link("Service Jobs", "Service Job", "DocType", "assign", child=1),
			sidebar_link("Part Requests", "Service Part Request", "DocType", "stock", child=1),
			sidebar_link("Remote Support", "Remote Support Session", "DocType", "call", child=1),
			sidebar_link("Expenses", "Service Expense", "DocType", "expense-claim", child=1),
			sidebar_section("Equipment", "asset"),
			sidebar_link("Customer Equipment", "Customer Equipment", "DocType", "asset", child=1),
			sidebar_link("Customer Sites", "Customer Site", "DocType", "organization", child=1),
			sidebar_section("Contracts", "contract"),
			sidebar_link("Service Contracts", "Service Contract", "DocType", "contract", child=1),
			sidebar_link("Warranty Policies", "Warranty Policy", "DocType", "verified", child=1),
			sidebar_section("Reports", "table"),
			sidebar_link("Open Tickets", "Open Service Tickets", "Report", "table", child=1),
			sidebar_link("Technician Workload", "Technician Workload", "Report", "table", child=1),
			sidebar_link("SLA Compliance", "Service SLA Compliance", "Report", "table", child=1),
			sidebar_link("Jobs Pending Billing", "Completed Service Jobs Pending Billing", "Report", "table", child=1),
		],
	}


def doctype_shortcut(label, link_to):
	return {"type": "DocType", "label": label, "link_to": link_to}


def report_shortcut(label, link_to):
	return {"type": "Report", "label": label, "link_to": link_to}


def url_shortcut(label, url):
	return {"type": "URL", "label": label, "url": url}


def sidebar_section(label, icon):
	return {
		"label": label,
		"type": "Section Break",
		"link_type": "DocType",
		"icon": icon,
		"collapsible": 1,
		"child": 0,
		"indent": 0,
		"keep_closed": 0,
		"show_arrow": 0,
	}


def sidebar_link(label, link_to, link_type, icon, child=0):
	return {
		"label": label,
		"type": "Link",
		"link_type": link_type,
		"link_to": link_to,
		"icon": icon,
		"child": child,
		"collapsible": 1,
		"indent": 0,
		"keep_closed": 0,
		"show_arrow": 0,
	}
