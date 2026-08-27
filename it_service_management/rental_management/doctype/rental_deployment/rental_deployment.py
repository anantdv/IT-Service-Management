from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime, nowdate

from it_service_management.rental_management.services.asset import RentalAssetService


class RentalDeployment(Document):
	def before_insert(self):
		self.copy_contract_details()

	def validate(self):
		self.copy_contract_details()
		contract = frappe.get_cached_doc("Rental Contract", self.rental_contract)
		if contract.status not in ("Approved", "Active", "Expiring"):
			frappe.throw("Rental Contract must be approved or active for deployment.")
		if self.deployment_date and getdate(self.deployment_date) < getdate(contract.start_date):
			frappe.throw("Deployment Date cannot precede the Rental Contract Start Date.")
		seen = set()
		for row in self.items:
			if row.asset in seen:
				frappe.throw(f"Asset {row.asset} appears more than once in this deployment.")
			seen.add(row.asset)
			RentalAssetService.validate_asset_for_rental(row.asset, self.customer, contract.company, self.rental_contract)

	def copy_contract_details(self):
		if not self.rental_contract:
			return
		contract = frappe.get_cached_doc("Rental Contract", self.rental_contract)
		self.customer = contract.customer
		self.customer_site = self.customer_site or contract.customer_site
		self.installation_charge = self.installation_charge or contract.installation_charge

	@frappe.whitelist()
	def create_installation_job(self):
		if self.service_job:
			return self.service_job
		job = frappe.get_doc({"doctype": "Service Job", "customer": self.customer, "customer_site": self.customer_site, "job_type": "Installation", "priority": "Medium", "rental_contract": self.rental_contract, "customer_complaint": f"Install rental equipment for {self.name}"})
		job.insert()
		self.db_set("service_job", job.name)
		return job.name

	@frappe.whitelist()
	def complete_deployment(self):
		if self.status not in ("Scheduled", "In Progress"):
			frappe.throw("Only a scheduled or in-progress deployment can be completed.")
		if not self.deployment_date:
			self.deployment_date = nowdate()
		settings = frappe.get_single("IT Service Settings")
		if settings.require_customer_signature and not self.customer_signature:
			frappe.throw("Customer signature is required to complete deployment.")
		for row in self.items:
			RentalAssetService.deploy_item(self, row)
		self.status = "Completed"
		self.deployed_by = self.technician
		self.completion_datetime = now_datetime()
		self.save()
		contract = frappe.get_doc("Rental Contract", self.rental_contract)
		if contract.status == "Approved":
			contract.add_comment("Comment", f"Deployment {self.name} completed; contract is ready for Rental Manager activation")
		self.add_comment("Comment", f"Equipment deployed by {frappe.session.user}")
		return self
