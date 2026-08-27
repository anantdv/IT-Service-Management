from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, add_months, cint, flt, getdate, now_datetime, nowdate

from it_service_management.rental_management.services.asset import ACTIVE_CONTRACT_STATUSES, RentalAssetService
from it_service_management.rental_management.services.subscription import RentalSubscriptionService
from it_service_management.service_billing.services.credit import check_customer_credit


APPROVAL_ROLES = {"Rental Manager", "System Manager"}
COVERAGE_FIELDS = (
	"labour_covered", "parts_covered", "consumables_covered", "travel_covered", "food_covered",
	"accommodation_covered", "installation_covered", "emergency_support_covered",
)


class RentalContract(Document):
	def before_insert(self):
		self.apply_plan_defaults()

	def validate(self):
		self.validate_dates_and_amounts()
		self.validate_customer_site()
		self.validate_status_change()
		self.validate_equipment()
		self.validate_billing_mode()
		self.calculate_operational_values()

	def on_update(self):
		if self.status in ("Approved", "Active", "Expiring"):
			self.reserve_equipment()

	def apply_plan_defaults(self):
		if not self.rental_plan:
			return
		plan = frappe.get_cached_doc("Rental Plan", self.rental_plan)
		for target, source in {
			"company": "company", "billing_frequency": "billing_frequency", "contract_term_months": "standard_term_months",
			"base_rental_amount": "base_rental_rate", "minimum_monthly_charge": "minimum_monthly_charge",
			"security_deposit": "security_deposit", "installation_charge": "installation_charge",
			"included_bw_pages": "included_bw_pages", "included_colour_pages": "included_colour_pages",
			"excess_bw_rate": "excess_bw_rate", "excess_colour_rate": "excess_colour_rate",
			**{field: field for field in COVERAGE_FIELDS},
		}.items():
			if target in COVERAGE_FIELDS and self.coverage_overrides_plan:
				continue
			if self.get(target) in (None, "", 0):
				self.set(target, plan.get(source))
		if not self.end_date and self.start_date and self.contract_term_months:
			self.end_date = add_months(self.start_date, cint(self.contract_term_months))
		settings = frappe.get_single("IT Service Settings")
		self.rental_billing_mode = self.rental_billing_mode or settings.rental_billing_mode
		self.billing_start_rule = self.billing_start_rule or settings.default_billing_start_rule
		self.cost_center = self.cost_center or settings.default_rental_cost_center

	def validate_dates_and_amounts(self):
		if not self.customer:
			frappe.throw("Customer is required.")
		if not self.start_date:
			frappe.throw("Start Date is required.")
		if self.end_date and getdate(self.end_date) < getdate(self.start_date):
			frappe.throw("End Date cannot be before Start Date.")
		if not 1 <= cint(self.billing_day) <= 31:
			frappe.throw("Billing Day must be between 1 and 31.")
		for field in ("base_rental_amount", "minimum_monthly_charge", "included_bw_pages", "included_colour_pages", "excess_bw_rate", "excess_colour_rate"):
			if flt(self.get(field)) < 0:
				frappe.throw(f"{self.meta.get_label(field)} cannot be negative.")

	def validate_customer_site(self):
		if self.customer_site:
			site_customer = frappe.db.get_value("Customer Site", self.customer_site, "customer")
			if site_customer and site_customer != self.customer:
				frappe.throw("Customer Site must belong to the selected Customer.")

	def validate_status_change(self):
		old = self.get_doc_before_save() if not self.is_new() else None
		if old and old.status != self.status and self.status in ("Approved", "Terminated", "Completed"):
			if not APPROVAL_ROLES.intersection(frappe.get_roles()):
				frappe.throw("Only Rental Manager may approve, terminate, or complete a Rental Contract.")
		if self.status == "Approved" and not self.approved_by:
			self.approved_by = frappe.session.user
			self.approved_on = now_datetime()
		if self.status in ("Active", "Expiring"):
			settings = frappe.get_single("IT Service Settings")
			was_approved = old and old.status in ("Approved", "Active", "Suspended", "Expiring", "Termination Requested")
			if not self.approved_by and not was_approved and not settings.allow_activation_without_approval:
				frappe.throw("Rental Contract must be approved before activation.")
			if not old or old.status not in ("Active", "Expiring"):
				check_customer_credit(self.customer, self.company, self.total_contract_value or self.base_rental_amount)
		if self.status == "Completed" and any(row.deployment_status in ("Deployed", "Temporarily Replaced", "Under Repair") for row in self.equipment):
			frappe.throw("All rental equipment must be returned or formally accounted for before completing the contract.")
		if old and old.status == "Expired":
			for row in self.equipment:
				old_row = next((item for item in old.equipment if item.name == row.name), None)
				if row.deployment_status == "Deployed" and (not old_row or old_row.deployment_status != "Deployed"):
					frappe.throw("Expired contracts cannot receive new deployments without an authorized extension.")

	def validate_equipment(self):
		seen_assets = set()
		seen_serials = set()
		for row in self.equipment:
			if row.asset in seen_assets:
				frappe.throw(f"Asset {row.asset} is listed more than once.")
			seen_assets.add(row.asset)
			if row.serial_no and row.serial_no in seen_serials:
				frappe.throw(f"Serial No {row.serial_no} is listed more than once.")
			if row.serial_no:
				seen_serials.add(row.serial_no)
			if row.customer_equipment:
				equipment = frappe.db.get_value("Customer Equipment", row.customer_equipment, ["customer", "asset", "serial_no"], as_dict=True)
				if equipment and equipment.customer != self.customer:
					frappe.throw(f"Customer Equipment {row.customer_equipment} belongs to another Customer.")
			if self.status in ACTIVE_CONTRACT_STATUSES:
				RentalAssetService.validate_asset_for_rental(row.asset, self.customer, self.company, self.name)

	def validate_billing_mode(self):
		if self.use_erpnext_subscription and self.subscription:
			RentalSubscriptionService(self).validate_link()
		if self.rental_billing_mode == "Subscription Plus Supplemental":
			if not self.use_erpnext_subscription:
				frappe.throw("Subscription Plus Supplemental mode requires ERPNext Subscription integration.")
			if not self.subscription:
				frappe.throw("Link an ERPNext Subscription before using Subscription Plus Supplemental mode.")

	def calculate_operational_values(self):
		months = cint(self.contract_term_months)
		frequency_months = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}.get(self.billing_frequency, 1)
		self.monthly_recurring_revenue = flt(self.base_rental_amount) / frequency_months
		self.total_contract_value = flt(self.base_rental_amount) * months + flt(self.installation_charge)
		if self.name and not self.is_new():
			amounts = frappe.db.sql(
				"""select coalesce(sum(grand_total), 0) billed, coalesce(sum(outstanding_amount), 0) outstanding,
				max(posting_date) last_invoice from `tabSales Invoice` where custom_rental_contract=%s and docstatus=1""",
				self.name,
				as_dict=True,
			)[0]
			if amounts:
				self.amount_billed_to_date = amounts.billed
				self.outstanding_amount = amounts.outstanding
				self.last_invoice_date = amounts.last_invoice

	def reserve_equipment(self):
		for row in self.equipment:
			if row.deployment_status == "Reserved" and row.customer_equipment:
				frappe.db.set_value("Customer Equipment", row.customer_equipment, "equipment_status", "Reserved", update_modified=False)

	def get_equipment_billing_start(self, deployment_date=None):
		if self.billing_start_rule == "Contract Start Date":
			return self.start_date
		if self.billing_start_rule in ("Deployment Date", "Installation Completion"):
			return deployment_date
		if self.billing_start_rule == "Explicit Date":
			if not self.billing_start_date:
				frappe.throw("Explicit Billing Start Date is required.")
			return self.billing_start_date
		return self.start_date

	@frappe.whitelist()
	def create_deployment(self):
		if self.status not in ("Approved", "Active", "Expiring"):
			frappe.throw("Rental Contract must be approved before creating a deployment.")
		items = []
		for row in self.equipment:
			if row.deployment_status in ("Reserved", "Ready for Deployment"):
				items.append({"asset": row.asset, "customer_equipment": row.customer_equipment, "item_code": row.item_code, "serial_no": row.serial_no})
		if not items:
			frappe.throw("No equipment is ready for deployment.")
		deployment = frappe.get_doc({"doctype": "Rental Deployment", "rental_contract": self.name, "customer": self.customer, "customer_site": self.customer_site, "installation_charge": self.installation_charge, "items": items})
		deployment.insert()
		return deployment.name

	@frappe.whitelist()
	def request_termination(self, requested_end_date, reason):
		if self.status not in ("Active", "Suspended", "Expiring"):
			frappe.throw("Only an active, suspended, or expiring contract can request termination.")
		self.status = "Termination Requested"
		self.termination_request_date = nowdate()
		self.requested_end_date = requested_end_date
		self.termination_reason = reason
		self.add_comment("Comment", f"Termination requested by {frappe.session.user}: {reason}")
		self.save()
		return self

	@frappe.whitelist()
	def create_renewal(self):
		new_doc = frappe.copy_doc(self)
		new_doc.name = None
		new_doc.status = "Draft"
		new_doc.previous_rental_contract = self.name
		new_doc.renewal_number = cint(self.renewal_number) + 1
		new_doc.start_date = add_days(self.end_date, 1) if self.end_date else nowdate()
		new_doc.end_date = add_months(new_doc.start_date, cint(self.renewal_term_months or self.contract_term_months))
		new_doc.approved_by = None
		new_doc.approved_on = None
		for row in new_doc.equipment:
			row.deployment_status = "Reserved"
			row.deployment_date = None
			row.actual_return_date = None
		new_doc.insert()
		return new_doc.name

	@frappe.whitelist()
	def create_subscription(self):
		if not self.use_erpnext_subscription:
			frappe.throw("Enable ERPNext Subscription integration first.")
		if self.subscription:
			return self.subscription
		settings = frappe.get_single("IT Service Settings")
		if not settings.allow_auto_create_subscription:
			frappe.throw("Automatic Subscription creation is disabled in IT Service Settings.")
		return RentalSubscriptionService(self).create(self.subscription_plan)
