from __future__ import annotations

import re
from email.utils import parseaddr

import frappe
from frappe.utils import cstr


TICKET_ID_PATTERN = re.compile(r"\bST-\d{4}-\d{5}\b", re.IGNORECASE)


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


def find_existing_ticket_for_email(ticket) -> str | None:
	header_match = find_ticket_by_email_headers(ticket)
	if header_match:
		return header_match

	for ticket_name in extract_ticket_names(get_email_search_text(ticket)):
		if ticket_name != ticket.get("name") and frappe.db.exists("Service Ticket", ticket_name):
			return ticket_name
	return None


def append_email_reply_to_ticket(reply_ticket, target_ticket: str) -> None:
	message = get_email_reply_message(reply_ticket)
	source = extract_sender_email(reply_ticket) or reply_ticket.get("reported_by") or "customer"

	target = frappe.get_doc("Service Ticket", target_ticket)
	target.add_comment("Comment", f"<p><b>Email reply received from {source}</b></p>{message}")

	if target.status == "Resolved":
		target.status = "Work In Progress"
		target.add_comment("Comment", "Ticket reopened because the customer replied to the email thread.")

	target.save(ignore_permissions=True)


def extract_ticket_names(text: str | None) -> list[str]:
	if not text:
		return []
	return list(dict.fromkeys(match.upper() for match in TICKET_ID_PATTERN.findall(cstr(text))))


def find_ticket_by_email_headers(ticket) -> str | None:
	if not frappe.db.exists("DocType", "Communication"):
		return None
	required_columns = {"message_id", "reference_doctype", "reference_name"}
	if not all(frappe.db.has_column("Communication", column) for column in required_columns):
		return None

	message_ids = get_email_reference_ids(ticket)
	if not message_ids:
		return None

	communication = frappe.db.get_value(
		"Communication",
		{
			"message_id": ["in", message_ids],
			"reference_doctype": "Service Ticket",
			"reference_name": ["!=", ticket.get("name") or ""],
		},
		"reference_name",
		order_by="creation desc",
	)
	if communication and frappe.db.exists("Service Ticket", communication):
		return communication
	return None


def get_email_reference_ids(ticket) -> list[str]:
	references = []
	for fieldname in ("in_reply_to", "references"):
		value = ticket.get(fieldname)
		if value:
			references.extend(re.findall(r"<[^>]+>|[^\s,]+", cstr(value)))
	return list(dict.fromkeys(references))


def get_email_search_text(ticket) -> str:
	fields = ("subject", "email_subject", "description", "content", "text_content")
	return "\n".join(cstr(ticket.get(fieldname)) for fieldname in fields if ticket.get(fieldname))


def get_email_reply_message(ticket) -> str:
	content = ticket.get("description") or ticket.get("content") or ticket.get("text_content") or ticket.get("subject")
	return cstr(content)[:10000] or "<p>No message body was captured.</p>"


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
