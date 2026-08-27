from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

import frappe
from frappe.utils import add_months, cint, getdate, now_datetime

from it_service_management.rental_management.services.meter import MONEY_QUANTUM, as_decimal


ACTIVE_REFERENCE_STATUSES = ("Reserved", "Draft Invoiced", "Submitted")


def calculate_proration(amount, period_from, period_to, effective_start=None, effective_end=None, enabled=True):
	period_start = getdate(period_from)
	period_end = getdate(period_to)
	start = max(period_start, getdate(effective_start)) if effective_start else period_start
	end = min(period_end, getdate(effective_end)) if effective_end else period_end
	days_in_period = (period_end - period_start).days + 1
	billable_days = max((end - start).days + 1, 0) if end >= start else 0
	base = as_decimal(amount)
	if not enabled or billable_days == days_in_period:
		result = base if billable_days else Decimal("0")
	else:
		result = (base / Decimal(days_in_period) * Decimal(billable_days)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
	return {"amount": result, "prorated": bool(enabled and 0 < billable_days < days_in_period), "billable_days": billable_days, "days_in_period": days_in_period}


class RentalBillingEngine:
	def __init__(self, billing_run):
		self.run = billing_run
		self.settings = frappe.get_single("IT Service Settings")

	def prepare(self):
		if self.run.status not in ("Draft", "Prepared", "Processing", "Completed With Errors"):
			frappe.throw("Only Draft or Prepared billing runs can be prepared.")
		if getdate(self.run.billing_period_to) < getdate(self.run.billing_period_from):
			frappe.throw("Billing Period To cannot precede Billing Period From.")
		if frappe.db.exists("Rental Billing Reference", {"billing_run": self.run.name, "status": ["in", ["Draft Invoiced", "Submitted"]]}):
			frappe.throw("This Billing Run already has invoices. Cancel or delete them before preparing it again.")
		self._release_run_reservations()
		self.run.set("details", [])
		self.run.set("components", [])
		self.run.started_at = now_datetime()
		self.run.contracts_processed = 0
		self.run.contracts_with_errors = 0

		for contract_name in self._get_contracts():
			try:
				self._prepare_contract(frappe.get_doc("Rental Contract", contract_name))
			except Exception:
				self.run.contracts_with_errors += 1
				contract = frappe.db.get_value("Rental Contract", contract_name, ["customer", "customer_site"], as_dict=True)
				self.run.append("details", {"rental_contract": contract_name, "customer": contract.customer, "customer_site": contract.customer_site, "status": "Error", "error_message": frappe.get_traceback()[-2000:]})
			self.run.contracts_processed += 1

		self._set_totals()
		self.run.status = "Prepared" if not self.run.contracts_with_errors else "Completed With Errors"
		self.run.completed_at = now_datetime()
		self.run.save(ignore_permissions=True)
		self.run.add_comment("Comment", f"Billing prepared by {frappe.session.user}: {len(self.run.components)} components")
		return self.run

	def _get_contracts(self):
		filters = {
			"company": self.run.company,
			"status": ["in", ["Active", "Expiring", "Termination Requested"]],
			"start_date": ["<=", self.run.billing_period_to],
		}
		if self.run.customer:
			filters["customer"] = self.run.customer
		if self.run.rental_contract:
			filters["name"] = self.run.rental_contract
		return frappe.get_all("Rental Contract", filters=filters, pluck="name", order_by="customer, name")

	def _prepare_contract(self, contract):
		if contract.rental_billing_mode != self.run.billing_mode:
			return
		components = []
		if self.run.billing_mode == "Consolidated Billing":
			components.extend(self._base_components(contract))
		components.extend(self._meter_components(contract))
		components.extend(self._ad_hoc_components(contract))
		components.extend(self._service_components(contract))
		if not components:
			return

		totals = defaultdict(Decimal)
		for component in components:
			row = self.run.append("components", component)
			totals[self._detail_bucket(row.component_type)] += as_decimal(row.amount)
		self.run.append(
			"details",
			{
				"rental_contract": contract.name,
				"customer": contract.customer,
				"customer_site": contract.customer_site,
				"base_rental": totals["base_rental"],
				"meter_charge": totals["meter_charge"],
				"ad_hoc_charge": totals["ad_hoc_charge"],
				"service_charge": totals["service_charge"],
				"adjustment": totals["adjustment"],
				"total": sum(totals.values(), Decimal("0")),
				"status": "Prepared",
			},
		)

	def _base_components(self, contract):
		if not self._base_rental_due(contract):
			return []
		rows = [row for row in contract.equipment if row.deployment_status in ("Deployed", "Temporarily Replaced", "Under Repair") and not row.billing_end_date]
		if contract.billing_start_rule in ("Deployment Date", "Installation Completion") and not rows:
			return []
		priced_rows = [row for row in rows if as_decimal(row.monthly_rental_rate) > 0]
		sources = priced_rows or [None]
		components = []
		for row in sources:
			amount = row.monthly_rental_rate if row else max(as_decimal(contract.base_rental_amount), as_decimal(contract.minimum_monthly_charge))
			effective_start = row.billing_start_date if row else contract.billing_start_date or contract.start_date
			effective_end = row.billing_end_date if row else contract.billing_end_date or contract.approved_end_date or contract.end_date
			proration = calculate_proration(amount, self.run.billing_period_from, self.run.billing_period_to, effective_start, effective_end, bool(self.settings.prorate_partial_month and contract.billing_frequency == "Monthly"))
			if not proration["amount"]:
				continue
			key = f"Base Rental:{row.customer_equipment or row.asset}" if row else "Base Rental"
			component = self._reserve_component(
				contract, key, "Rental Contract", contract.name, proration["amount"],
				{"component_type": "Base Rental", "source_date": effective_start, "customer_equipment": row.customer_equipment if row else None, "item_code": self.settings.default_rental_income_item, "description": f"{contract.billing_frequency} Rental - {row.item_name or row.item_code}" if row else f"{contract.billing_frequency} Rental - {contract.name}", "quantity": 1, "rate": proration["amount"], "amount": proration["amount"], "cost_center": contract.cost_center or self.settings.default_rental_cost_center, "project": contract.project, **proration},
			)
			if component:
				components.append(component)
		return components

	def _base_rental_due(self, contract):
		anchor = getdate(contract.billing_start_date or contract.start_date)
		period_end = getdate(self.run.billing_period_to)
		if period_end < anchor:
			return False
		frequency_months = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}.get(contract.billing_frequency, 1)
		month_delta = (period_end.year - anchor.year) * 12 + period_end.month - anchor.month
		return month_delta % frequency_months == 0

	def _meter_components(self, contract):
		filters = {"rental_contract": contract.name, "billing_period_from": [">=", self.run.billing_period_from], "billing_period_to": ["<=", self.run.billing_period_to]}
		if self.settings.require_verified_meter_reading:
			filters["verified"] = 1
		readings = frappe.get_all("Equipment Meter Reading", filters=filters, fields=["name", "customer_equipment", "reading_date"])
		components = []
		for reading in readings:
			for detail in frappe.get_all("Equipment Meter Reading Detail", filters={"parent": reading.name}, fields=["meter_type", "billable_quantity", "rate", "calculated_amount"]):
				if not as_decimal(detail.calculated_amount):
					continue
				code = (detail.meter_type or "").upper()
				component_type = "B&W Usage" if code in ("BW", "B&W", "BLACK AND WHITE") else "Colour Usage" if code in ("COLOUR", "COLOR") else "Meter Usage"
				item_code = self.settings.default_bw_meter_item if component_type == "B&W Usage" else self.settings.default_colour_meter_item if component_type == "Colour Usage" else self.settings.default_rental_adjustment_item
				component = self._reserve_component(contract, component_type, "Equipment Meter Reading", reading.name, detail.calculated_amount, {"component_type": component_type, "source_date": reading.reading_date, "customer_equipment": reading.customer_equipment, "item_code": item_code, "description": f"{detail.meter_type} Excess Usage - {self.run.billing_period_from} to {self.run.billing_period_to}", "quantity": detail.billable_quantity, "rate": detail.rate, "amount": detail.calculated_amount})
				if component:
					components.append(component)
		return components

	def _ad_hoc_components(self, contract):
		charges = frappe.get_all("Rental Ad-Hoc Charge", filters={"rental_contract": contract.name, "status": "Approved", "billable": 1, "charge_date": ["<=", self.run.billing_period_to]}, fields=["name", "charge_date", "customer_equipment", "component_type", "item_code", "description", "quantity", "rate", "amount"])
		components = []
		for charge in charges:
			component = self._reserve_component(contract, charge.component_type or "Ad-Hoc Charge", "Rental Ad-Hoc Charge", charge.name, charge.amount, {"component_type": charge.component_type or "Ad-Hoc Charge", "source_date": charge.charge_date, "customer_equipment": charge.customer_equipment, "item_code": charge.item_code or self._default_item(charge.component_type), "description": charge.description, "quantity": charge.quantity, "rate": charge.rate, "amount": charge.amount})
			if component:
				components.append(component)
		return components

	def _service_components(self, contract):
		rows = frappe.db.sql(
			"""
			select sj.name service_job, sj.customer_equipment, sj.completion_datetime, sjc.charge_type, sum(sjc.billable_amount) amount
			from `tabService Job Charge` sjc inner join `tabService Job` sj on sj.name = sjc.parent
			where sj.rental_contract = %s and sjc.billable = 1 and sjc.billable_amount > 0 and ifnull(sjc.rental_billed, 0) = 0
			group by sj.name, sj.customer_equipment, sj.completion_datetime, sjc.charge_type
			""",
			contract.name,
			as_dict=True,
		)
		components = []
		for row in rows:
			component_type = "Travel" if row.charge_type == "Travel" else "Service Charge"
			key = f"Service Charge:{row.charge_type}"
			component = self._reserve_component(contract, key, "Service Job", row.service_job, row.amount, {"component_type": component_type, "source_date": row.completion_datetime, "customer_equipment": row.customer_equipment, "item_code": self._default_item(component_type), "description": f"{row.charge_type} Charge - {row.service_job}", "quantity": 1, "rate": row.amount, "amount": row.amount, "remarks": row.charge_type})
			if component:
				components.append(component)
		return components

	def _reserve_component(self, contract, reference_type, source_type, source_document, amount, values):
		values["billing_period_from"] = self.run.billing_period_from
		values["billing_period_to"] = self.run.billing_period_to
		values["source_date"] = values.get("source_date") or self.run.billing_period_to
		if values.get("customer_equipment"):
			values["serial_no"] = frappe.db.get_value("Customer Equipment", values["customer_equipment"], "serial_no")
		filters = {"rental_contract": contract.name, "billing_period_from": self.run.billing_period_from, "billing_period_to": self.run.billing_period_to, "component_type": reference_type, "source_document_type": source_type, "source_document": source_document}
		existing = frappe.db.get_value("Rental Billing Reference", filters, ["name", "status"], as_dict=True)
		if existing and existing.status in ACTIVE_REFERENCE_STATUSES:
			return None
		if existing:
			reference = frappe.get_doc("Rental Billing Reference", existing.name)
			reference.billing_run = self.run.name
			reference.amount = amount
			reference.status = "Reserved"
			reference.invoice = None
			reference.invoice_item = None
			reference.save(ignore_permissions=True)
		else:
			reference = frappe.get_doc({"doctype": "Rental Billing Reference", "rental_contract": contract.name, "billing_run": self.run.name, "billing_period_from": self.run.billing_period_from, "billing_period_to": self.run.billing_period_to, "component_type": reference_type, "source_document_type": source_type, "source_document": source_document, "amount": amount, "status": "Reserved"}).insert(ignore_permissions=True)
		values.update({"rental_contract": contract.name, "source_document_type": source_type, "source_document": source_document, "billing_reference": reference.name, "billable": 1, "cost_center": values.get("cost_center") or contract.cost_center or self.settings.default_rental_cost_center, "project": values.get("project") or contract.project})
		return values

	def _release_run_reservations(self):
		for reference in frappe.get_all("Rental Billing Reference", filters={"billing_run": self.run.name, "status": "Reserved"}, pluck="name"):
			frappe.db.set_value("Rental Billing Reference", reference, "status", "Cancelled", update_modified=False)

	def _set_totals(self):
		self.run.total_base_rental = sum(as_decimal(row.amount) for row in self.run.components if row.component_type == "Base Rental")
		self.run.total_meter_charges = sum(as_decimal(row.amount) for row in self.run.components if row.component_type in ("B&W Usage", "Colour Usage", "Meter Usage"))
		self.run.total_ad_hoc_charges = sum(as_decimal(row.amount) for row in self.run.components if row.source_document_type == "Rental Ad-Hoc Charge")
		self.run.total_service_charges = sum(as_decimal(row.amount) for row in self.run.components if row.source_document_type == "Service Job")
		self.run.total_billed = sum(as_decimal(row.amount) for row in self.run.components)

	@staticmethod
	def _detail_bucket(component_type):
		if component_type == "Base Rental": return "base_rental"
		if component_type in ("B&W Usage", "Colour Usage", "Meter Usage"): return "meter_charge"
		if component_type in ("Adjustment", "Credit Adjustment"): return "adjustment"
		return "service_charge" if component_type in ("Service Charge", "Travel") else "ad_hoc_charge"

	def _default_item(self, component_type):
		if component_type == "Damage": return self.settings.default_rental_damage_item
		if component_type == "Installation": return self.settings.default_rental_installation_item
		if component_type in ("Adjustment", "Credit Adjustment"): return self.settings.default_rental_adjustment_item
		return self.settings.default_service_item or self.settings.default_rental_adjustment_item


class RentalInvoiceService:
	def __init__(self, billing_run):
		self.run = billing_run
		self.settings = frappe.get_single("IT Service Settings")

	def generate(self):
		if not {"Rental Billing User", "Accounts Manager", "Accounts User", "System Manager"}.intersection(frappe.get_roles()):
			frappe.throw("Only Rental Billing or Accounts users can generate rental invoices.", frappe.PermissionError)
		if cint(self.settings.require_rental_billing_approval) and (self.run.status not in ("Approved for Billing", "Processing", "Completed With Errors") or not self.run.approved_by):
			frappe.throw("Approve this Rental Billing Run before generating invoices.")
		if not cint(self.settings.require_rental_billing_approval) and self.run.status not in ("Prepared", "Approved for Billing", "Processing", "Completed With Errors"):
			frappe.throw("Prepare Billing before generating invoices.")
		self.run.status = "Processing"
		self.run.save(ignore_permissions=True)
		created = 0
		errors = 0
		for detail in self.run.details:
			if detail.invoice:
				continue
			try:
				detail.error_message = None
				components = [row for row in self.run.components if row.rental_contract == detail.rental_contract and row.billable]
				if not components:
					continue
				invoice = self._create_invoice(detail, components)
				detail.invoice = invoice.name
				detail.status = "Invoice Created"
				created += 1
			except Exception:
				detail.status = "Error"
				detail.error_message = frappe.get_traceback()[-2000:]
				errors += 1
		self.run.invoices_created = created
		self.run.contracts_with_errors = sum(row.status == "Error" for row in self.run.details)
		self.run.status = "Completed With Errors" if self.run.contracts_with_errors else "Completed"
		self.run.completed_at = now_datetime()
		self.run.save(ignore_permissions=True)
		return self.run

	def _create_invoice(self, detail, components):
		contract = frappe.get_cached_doc("Rental Contract", detail.rental_contract)
		missing = [row.component_type for row in components if not row.item_code]
		if missing:
			frappe.throw(f"Configure ERPNext Items for rental billing components: {', '.join(sorted(set(missing)))}")
		invoice = frappe.get_doc({"doctype": "Sales Invoice", "company": self.run.company, "customer": detail.customer, "posting_date": self.run.posting_date, "currency": contract.currency, "selling_price_list": contract.price_list, "tax_category": contract.tax_category, "taxes_and_charges": contract.taxes_and_charges, "custom_rental_contract": contract.name, "custom_rental_billing_run": self.run.name, "custom_billing_period_from": self.run.billing_period_from, "custom_billing_period_to": self.run.billing_period_to, "items": []})
		for row in components:
			invoice.append("items", {"item_code": row.item_code, "description": f"{row.description}\nSource: {row.source_document_type} {row.source_document}", "qty": row.quantity or 1, "rate": row.rate, "cost_center": row.cost_center, "project": row.project, "item_tax_template": row.tax_template})
		invoice.insert(ignore_permissions=True)
		for component, item in zip(components, invoice.items):
			frappe.db.set_value("Rental Billing Reference", component.billing_reference, {"invoice": invoice.name, "invoice_item": item.name, "status": "Draft Invoiced"}, update_modified=False)
			self._mark_source_billed(component)
		if self.settings.allow_auto_submit_rental_invoice:
			invoice.submit()
		frequency_months = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}.get(contract.billing_frequency, 1)
		frappe.db.set_value("Rental Contract", contract.name, {"last_invoice_date": self.run.posting_date, "next_billing_date": add_months(self.run.billing_period_from, frequency_months)}, update_modified=False)
		return invoice

	@staticmethod
	def _mark_source_billed(component):
		if component.source_document_type == "Rental Ad-Hoc Charge":
			frappe.db.set_value("Rental Ad-Hoc Charge", component.source_document, {"status": "Billed", "billing_reference": component.billing_reference}, update_modified=False)
		elif component.source_document_type == "Service Job":
			filters = {"parent": component.source_document, "charge_type": component.remarks} if component.remarks else {"parent": component.source_document}
			for name in frappe.get_all("Service Job Charge", filters=filters, pluck="name"):
				frappe.db.set_value("Service Job Charge", name, {"rental_billed": 1, "rental_billing_reference": component.billing_reference}, update_modified=False)


def enqueue_prepare_billing(run_name):
	frappe.enqueue("it_service_management.rental_management.services.billing.prepare_billing_run", queue="long", run_name=run_name, enqueue_after_commit=True)
	return {"queued": True, "rental_billing_run": run_name}


def prepare_billing_run(run_name):
	return RentalBillingEngine(frappe.get_doc("Rental Billing Run", run_name)).prepare()


def generate_invoices(run_name):
	return RentalInvoiceService(frappe.get_doc("Rental Billing Run", run_name)).generate()


def enqueue_generate_invoices(run_name):
	frappe.enqueue("it_service_management.rental_management.services.billing.generate_invoices", queue="long", run_name=run_name, enqueue_after_commit=True)
	return {"queued": True, "rental_billing_run": run_name}


def handle_invoice_submitted(doc, method=None):
	if doc.get("custom_rental_billing_run"):
		for name in frappe.get_all("Rental Billing Reference", filters={"invoice": doc.name}, pluck="name"):
			frappe.db.set_value("Rental Billing Reference", name, "status", "Submitted", update_modified=False)


def handle_invoice_cancelled(doc, method=None):
	_release_invoice_sources(doc.name)


def handle_invoice_deleted(doc, method=None):
	if doc.docstatus == 0:
		_release_invoice_sources(doc.name)


def _release_invoice_sources(invoice_name):
	references = frappe.get_all("Rental Billing Reference", filters={"invoice": invoice_name}, fields=["name", "billing_run", "rental_contract", "billing_period_from"])
	for row in references:
		ref = frappe.get_doc("Rental Billing Reference", row.name)
		ref.status = "Cancelled"
		ref.invoice = None
		ref.invoice_item = None
		ref.save(ignore_permissions=True)
		if ref.source_document_type == "Rental Ad-Hoc Charge" and frappe.db.exists("Rental Ad-Hoc Charge", ref.source_document):
			frappe.db.set_value("Rental Ad-Hoc Charge", ref.source_document, {"status": "Approved", "billing_reference": None}, update_modified=False)
		elif ref.source_document_type == "Service Job" and frappe.db.exists("Service Job", ref.source_document):
			for name in frappe.get_all("Service Job Charge", filters={"parent": ref.source_document, "rental_billing_reference": ref.name}, pluck="name"):
				frappe.db.set_value("Service Job Charge", name, {"rental_billed": 0, "rental_billing_reference": None}, update_modified=False)
		frappe.db.set_value("Rental Contract", row.rental_contract, "next_billing_date", row.billing_period_from, update_modified=False)
	for run_name in {row.billing_run for row in references if row.billing_run}:
		run = frappe.get_doc("Rental Billing Run", run_name)
		for detail in run.details:
			if detail.invoice == invoice_name:
				detail.invoice = None
				detail.status = "Prepared"
				detail.error_message = None
		run.status = "Prepared"
		run.save(ignore_permissions=True)
