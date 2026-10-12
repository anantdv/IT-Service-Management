from __future__ import annotations

from email.utils import parseaddr

import frappe


def prepare_ticket_from_email(ticket) -> None:
	sender_email = extract_sender_email(ticket)
	if sender_email:
		ticket.contact_email = ticket.contact_email or sender_email
		ticket.reported_by = ticket.reported_by or sender_email

	ticket.source = "Email"
	ticket.detection_source = "Email"
	ticket.ticket_type = ticket.ticket_type or frappe.db.get_single_value("IT Service Settings", "default_email_ticket_type") or "Incident"
	ticket.subject = ticket.subject or ticket.get("email_subject") or "Email Service Request"
	ticket.description = ticket.description or ticket.get("content") or ticket.get("text_content")
	ticket.customer_complaint = ticket.customer_complaint or ticket.subject

	if not ticket.customer and sender_email:
		ticket.customer = find_customer_by_email(sender_email)

	if not ticket.contact_person and sender_email:
		ticket.contact_person = find_contact_by_email(sender_email)

	if not ticket.customer:
		ticket.customer = frappe.db.get_single_value("IT Service Settings", "default_email_ticket_customer")


def extract_sender_email(ticket) -> str | None:
	for fieldname in ("contact_email", "sender", "email_sender", "raised_by", "reported_by"):
		value = ticket.get(fieldname)
		if value:
			email = parseaddr(value)[1] or value
			return email.strip().lower()
	return None


def find_customer_by_email(email: str) -> str | None:
	contact = find_contact_by_email(email)
	if contact:
		customer = frappe.db.get_value(
			"Dynamic Link",
			{"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"},
			"link_name",
		)
		if customer:
			return customer

	if frappe.db.has_column("Customer", "email_id"):
		return frappe.db.get_value("Customer", {"email_id": email}, "name")
	return None


def find_contact_by_email(email: str) -> str | None:
	contact = None
	if frappe.db.has_column("Contact", "email_id"):
		contact = frappe.db.get_value("Contact", {"email_id": email}, "name")
	if contact:
		return contact

	if frappe.db.exists("DocType", "Contact Email"):
		return frappe.db.get_value("Contact Email", {"email_id": email}, "parent")
	return None
