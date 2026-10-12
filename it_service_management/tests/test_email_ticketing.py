from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from it_service_management.service_operations.services.email import extract_sender_email, prepare_ticket_from_email


class TestEmailTicketing(FrappeTestCase):
	def test_extract_sender_email_from_display_name(self):
		ticket = frappe._dict({"sender": "Support User <user@example.com>"})
		self.assertEqual(extract_sender_email(ticket), "user@example.com")

	def test_prepare_ticket_sets_email_defaults(self):
		ticket = frappe._dict(
			{
				"sender": "Customer <customer@example.com>",
				"subject": "Printer offline",
				"content": "The printer is offline.",
				"source": None,
				"detection_source": None,
				"ticket_type": None,
				"description": None,
				"customer_complaint": None,
				"contact_email": None,
				"reported_by": None,
				"contact_person": None,
				"customer": "_Test Customer",
			}
		)
		prepare_ticket_from_email(ticket)
		self.assertEqual(ticket.contact_email, "customer@example.com")
		self.assertEqual(ticket.reported_by, "customer@example.com")
		self.assertEqual(ticket.source, "Email")
		self.assertEqual(ticket.ticket_type, "Incident")
