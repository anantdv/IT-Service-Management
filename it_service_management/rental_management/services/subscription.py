from __future__ import annotations

import frappe


class RentalSubscriptionService:
	def __init__(self, contract):
		self.contract = contract

	def validate_link(self):
		if not self.contract.subscription:
			return None
		subscription = frappe.get_cached_doc("Subscription", self.contract.subscription)
		party = subscription.get("party") or subscription.get("customer")
		if party and party != self.contract.customer:
			frappe.throw("ERPNext Subscription customer does not match the Rental Contract.")
		if subscription.get("company") and subscription.company != self.contract.company:
			frappe.throw("ERPNext Subscription company does not match the Rental Contract.")
		return subscription

	def create(self, subscription_plan):
		if not frappe.db.exists("DocType", "Subscription") or not frappe.db.exists("DocType", "Subscription Plan"):
			frappe.throw("ERPNext Subscription is not available on this site.")
		if not subscription_plan:
			frappe.throw("An ERPNext Subscription Plan is required for automatic subscription creation.")
		doc = frappe.get_doc(
			{
				"doctype": "Subscription",
				"party_type": "Customer",
				"party": self.contract.customer,
				"company": self.contract.company,
				"start_date": self.contract.billing_start_date or self.contract.start_date,
				"end_date": self.contract.billing_end_date or self.contract.end_date,
				"plans": [{"plan": subscription_plan, "qty": max(len(self.contract.equipment), 1)}],
			}
		).insert(ignore_permissions=True)
		self.contract.db_set({"subscription": doc.name, "subscription_status": doc.get("status") or "Draft"})
		return doc.name
