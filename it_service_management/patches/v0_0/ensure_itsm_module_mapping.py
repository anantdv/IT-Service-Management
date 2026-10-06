from __future__ import annotations

import frappe


ITSM_MODULE = "ITSM"
APP_NAME = "it_service_management"

ITSM_DOCTYPES = (
	"ITSM Priority Matrix",
	"ITSM Assignment Group",
	"Assignment Group Member",
	"ITSM Service",
	"Service Offering",
	"Service Request Type",
	"Configuration Item Type",
	"Configuration Item",
	"Configuration Item Relationship",
	"Major Incident",
	"Major Incident Linked Ticket",
	"Major Incident Update",
	"PIR Action Item",
	"ITSM Problem",
	"Problem Incident",
	"ITSM Known Error",
	"ITSM Change Request",
	"Change Configuration Item",
	"CAB Meeting",
	"CAB Change Review",
	"ITSM Knowledge Article",
)

ITSM_PAGES = ("itsm-service-desk", "itsm-change-calendar")
ITSM_REPORTS = ("Incident Summary",)


def execute():
	ensure_module_def()
	set_module("DocType", ITSM_DOCTYPES)
	set_module("Page", ITSM_PAGES)
	set_module("Report", ITSM_REPORTS)
	frappe.clear_cache()


def ensure_module_def():
	if frappe.db.exists("Module Def", ITSM_MODULE):
		frappe.db.set_value("Module Def", ITSM_MODULE, "app_name", APP_NAME, update_modified=False)
		return

	module = frappe.new_doc("Module Def")
	module.module_name = ITSM_MODULE
	module.app_name = APP_NAME
	module.insert(ignore_permissions=True)


def set_module(doctype, names):
	for name in names:
		if frappe.db.exists(doctype, name):
			frappe.db.set_value(doctype, name, "module", ITSM_MODULE, update_modified=False)
