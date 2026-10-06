from __future__ import annotations

import frappe


MANAGER_PERM = {"read": 1, "report": 1, "write": 1, "create": 1}
READER_PERM = {"read": 1, "report": 1}

ITSM_DOCTYPES = (
	"ITSM Priority Matrix",
	"ITSM Assignment Group",
	"ITSM Service",
	"Service Request Type",
	"Configuration Item Type",
	"Configuration Item",
	"Configuration Item Relationship",
	"Major Incident",
	"ITSM Problem",
	"ITSM Known Error",
	"ITSM Change Request",
	"CAB Meeting",
	"ITSM Knowledge Article",
)

READER_ROLES = (
	"Service Dispatcher",
	"Service Technician",
	"IT Service Analyst",
	"IT Service Executive",
	"Service Auditor",
)


def execute():
	for doctype in ITSM_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		ensure_perm(doctype, "Service Manager", MANAGER_PERM)
		for role in READER_ROLES:
			ensure_perm(doctype, role, READER_PERM)
	frappe.clear_cache()


def ensure_perm(doctype, role, values):
	existing = frappe.db.exists("DocPerm", {"parent": doctype, "role": role})
	if existing:
		frappe.db.set_value("DocPerm", existing, values, update_modified=False)
		return

	doc = frappe.new_doc("DocPerm")
	doc.parent = doctype
	doc.parenttype = "DocType"
	doc.parentfield = "permissions"
	doc.role = role
	doc.update(values)
	doc.insert(ignore_permissions=True)
