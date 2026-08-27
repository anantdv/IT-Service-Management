from __future__ import annotations

from collections import defaultdict

import frappe
from frappe.utils import cint, flt, now_datetime


ACTIVE_REFERENCE_STATUSES = ("Reserved", "Draft Invoiced", "Submitted")
NEGATIVE_ADJUSTMENTS = ("Discount", "Waiver", "Credit Adjustment")


class ServiceBillingBatchEngine:
	def __init__(self, batch):
		self.batch = batch
		self.settings = frappe.get_single("IT Service Settings")
		self.cost_center = self.settings.default_service_cost_center or frappe.db.get_value("Company", self.batch.company, "cost_center")
		self.company_currency = frappe.db.get_value("Company", self.batch.company, "default_currency")

	def prepare(self):
		if self.batch.status not in ("Draft", "Prepared", "Processing", "Completed With Errors"):
			frappe.throw("Only Draft or Prepared service billing batches can be prepared.")
		if frappe.db.exists("Service Billing Reference", {"billing_batch": self.batch.name, "status": ["in", ["Draft Invoiced", "Submitted"]]}):
			frappe.throw("This batch already has invoices. Cancel or delete them before preparing it again.")

		self._release_reservations()
		self.batch.set("details", [])
		self.batch.started_at = now_datetime()
		self.batch.errors_count = 0
		jobs = self._get_jobs()
		self._load_sources(jobs)
		for job in jobs:
			try:
				self._prepare_job(job)
			except Exception:
				self.batch.errors_count += 1
				self.batch.append("details", {
					"service_job": job.name, "service_ticket": job.service_ticket, "customer": job.customer,
					"customer_site": job.customer_site, "customer_equipment": job.customer_equipment,
					"completion_date": job.completion_datetime, "billing_status": job.billing_status,
					"selected": 0, "result_status": "Error", "error_message": frappe.get_traceback()[-2000:],
				})

		self._set_totals()
		self.batch.status = "Completed With Errors" if self.batch.errors_count else "Prepared"
		self.batch.completed_at = now_datetime()
		self.batch.save(ignore_permissions=True)
		self.batch.add_comment("Comment", f"Service billing prepared by {frappe.session.user}: {self.batch.total_jobs} jobs")
		return self.batch

	def _get_jobs(self):
		customer_meta = frappe.get_meta("Customer")
		currency_sql = "coalesce(c.default_currency, %(company_currency)s)" if customer_meta.has_field("default_currency") else "%(company_currency)s"
		tax_category_sql = "c.tax_category" if customer_meta.has_field("tax_category") else "null"
		conditions = [
			"sj.status = 'Completed'", "sj.billing_status = 'Ready for Billing'",
			"date(sj.completion_datetime) between %(from_date)s and %(to_date)s",
			"not exists (select 1 from `tabService Billing Reference` sbr where sbr.service_job = sj.name and sbr.status in ('Reserved', 'Draft Invoiced', 'Submitted'))",
		]
		values = {"from_date": self.batch.service_date_from, "to_date": self.batch.service_date_to}
		for field in ("customer", "service_contract", "service_team", "service_zone"):
			if self.batch.get(field):
				conditions.append(f"sj.{field} = %({field})s")
				values[field] = self.batch.get(field)
		if self.batch.technician:
			conditions.append("sj.assigned_technician = %(technician)s")
			values["technician"] = self.batch.technician
		if self.batch.customer_group:
			conditions.append("c.customer_group = %(customer_group)s")
			values["customer_group"] = self.batch.customer_group
		return frappe.db.sql(
			f"""
			select sj.name, sj.service_ticket, sj.customer, sj.customer_site, sj.customer_equipment,
				sj.completion_datetime, sj.coverage_source, sj.billing_status, sj.service_contract, sc.company contract_company,
				{currency_sql} currency, {tax_category_sql} tax_category, sj.total_internal_cost,
				sj.total_charge_before_coverage, sj.total_covered_amount, sj.total_billable_amount
			from `tabService Job` sj
			inner join `tabCustomer` c on c.name = sj.customer
			left join `tabService Contract` sc on sc.name = sj.service_contract
			where {' and '.join(conditions)}
			order by sj.customer, sj.completion_datetime, sj.name
			""", {**values, "company_currency": self.company_currency}, as_dict=True,
		)

	def _load_sources(self, jobs):
		job_names = [job.name for job in jobs]
		self.charges_by_job = defaultdict(list)
		self.adjustments_by_job = defaultdict(list)
		if not job_names:
			return
		charges = frappe.db.sql(
			"""select c.parent service_job,c.name,c.charge_type,c.service_charge,c.item_code,c.billable_amount,
			sc.item_code service_item_code from `tabService Job Charge` c
			left join `tabService Charge` sc on sc.name=c.service_charge
			where c.parent in %(jobs)s and c.parenttype='Service Job' and c.billable=1 and c.billable_amount>0 and ifnull(c.rental_billed,0)=0""",
			{"jobs": job_names}, as_dict=True,
		)
		adjustments = frappe.db.sql(
			"""select a.service_job,a.name,a.adjustment_type,a.service_charge,a.item_code,a.amount,
			sc.item_code service_item_code from `tabService Billing Adjustment` a
			left join `tabService Charge` sc on sc.name=a.service_charge
			where a.service_job in %(jobs)s and a.approval_status='Approved'""",
			{"jobs": job_names}, as_dict=True,
		)
		for row in charges:
			self.charges_by_job[row.service_job].append(row)
		for row in adjustments:
			self.adjustments_by_job[row.service_job].append(row)

	def _prepare_job(self, job):
		charges = self.charges_by_job[job.name]
		adjustments = self.adjustments_by_job[job.name]
		self._validate_job(job, charges, adjustments)
		for row in charges:
			self._reserve(job.name, row.billable_amount, service_charge_row=row.name)
		for row in adjustments:
			amount = -flt(row.amount) if row.adjustment_type in NEGATIVE_ADJUSTMENTS else flt(row.amount)
			self._reserve(job.name, amount, adjustment=row.name)

		buckets = defaultdict(float)
		for row in charges:
			bucket = "parts" if row.charge_type == "Part" else row.charge_type.lower()
			if bucket not in ("labour", "parts", "travel", "food", "accommodation"):
				bucket = "other"
			buckets[bucket] += flt(row.billable_amount)
		adjustment_total = sum(-flt(row.amount) if row.adjustment_type in NEGATIVE_ADJUSTMENTS else flt(row.amount) for row in adjustments)
		self.batch.append("details", {
			"service_job": job.name, "service_ticket": job.service_ticket, "customer": job.customer,
			"customer_site": job.customer_site, "customer_equipment": job.customer_equipment,
			"currency": job.currency, "tax_category": job.tax_category, "cost_center": self.cost_center,
			"completion_date": job.completion_datetime, "coverage_source": job.coverage_source,
			"labour": buckets["labour"], "parts": buckets["parts"], "travel": buckets["travel"],
			"food": buckets["food"], "accommodation": buckets["accommodation"], "other": buckets["other"] + adjustment_total,
			"internal_cost": job.total_internal_cost, "total_charge": job.total_charge_before_coverage,
			"covered_amount": job.total_covered_amount, "billable_amount": flt(job.total_billable_amount) + adjustment_total,
			"billing_status": job.billing_status, "selected": 1, "result_status": "Prepared",
		})

	def _validate_job(self, job, charges, adjustments):
		if not job.customer:
			frappe.throw(f"Service Job {job.name} has no valid Customer.")
		if not job.coverage_source:
			frappe.throw(f"Service Job {job.name} has not completed coverage evaluation.")
		if job.contract_company and job.contract_company != self.batch.company:
			frappe.throw(f"Service Job {job.name} belongs to Company {job.contract_company}, not {self.batch.company}.")
		if not self.cost_center:
			frappe.throw(f"Configure a Service Cost Center or Company Cost Center before billing {job.name}.")
		missing = []
		for row in charges:
			if not _resolve_service_item(row, self.settings):
				missing.append(row.charge_type)
		for row in adjustments:
			if not row.item_code and not row.service_item_code and not self.settings.default_service_item:
				missing.append(row.adjustment_type)
		if missing:
			frappe.throw(f"Configure ERPNext Items for: {', '.join(sorted(set(missing)))}")

	def _reserve(self, job, amount, service_charge_row=None, adjustment=None):
		key = {"service_job": job, "service_charge_row": service_charge_row} if service_charge_row else {"service_job": job, "adjustment": adjustment}
		existing = frappe.db.get_value("Service Billing Reference", key, ["name", "status"], as_dict=True)
		if existing and existing.status in ACTIVE_REFERENCE_STATUSES:
			return
		values = {**key, "service_charge_row": service_charge_row, "adjustment": adjustment, "amount": amount, "billing_batch": self.batch.name, "status": "Reserved", "invoice": None, "invoice_item": None}
		if existing:
			frappe.db.set_value("Service Billing Reference", existing.name, values, update_modified=False)
		else:
			frappe.get_doc({"doctype": "Service Billing Reference", **values}).insert(ignore_permissions=True)

	def _release_reservations(self):
		for name in frappe.get_all("Service Billing Reference", filters={"billing_batch": self.batch.name, "status": "Reserved"}, pluck="name"):
			frappe.db.set_value("Service Billing Reference", name, "status", "Cancelled", update_modified=False)

	def _set_totals(self):
		valid = [row for row in self.batch.details if row.result_status != "Error"]
		self.batch.total_jobs = len(valid)
		self.batch.total_internal_cost = sum(flt(row.internal_cost) for row in valid)
		self.batch.total_charge = sum(flt(row.total_charge) for row in valid)
		self.batch.total_covered = sum(flt(row.covered_amount) for row in valid)
		self.batch.total_billable = sum(flt(row.billable_amount) for row in valid)


class ServiceInvoiceService:
	def __init__(self, batch):
		self.batch = batch
		self.settings = frappe.get_single("IT Service Settings")

	def generate(self):
		if not {"Service Billing User", "Accounts Manager", "Accounts User", "System Manager"}.intersection(frappe.get_roles()):
			frappe.throw("Only Service Billing or Accounts users can generate service invoices.", frappe.PermissionError)
		if cint(self.settings.require_service_billing_approval):
			if self.batch.status not in ("Approved for Billing", "Processing", "Completed With Errors") or not self.batch.approved_by:
				frappe.throw("Approve this Service Billing Batch before generating invoices.")
		elif self.batch.status not in ("Prepared", "Approved for Billing", "Processing", "Completed With Errors"):
			frappe.throw("Prepare this Service Billing Batch before generating invoices.")

		selected = [row for row in self.batch.details if row.selected and not row.invoice]
		groups = defaultdict(list)
		for row in selected:
			key = (row.customer, row.currency, row.tax_category or "", row.cost_center) if self.batch.group_by_customer else (row.service_job,)
			groups[key].append(row)
		self.batch.status = "Processing"
		self.batch.save(ignore_permissions=True)
		created = errors = 0
		for rows in groups.values():
			try:
				invoice = self._create_invoice(rows)
				for row in rows:
					row.invoice = invoice.name
					row.result_status = "Invoice Created"
					row.error_message = None
					frappe.db.set_value("Service Job", row.service_job, {"billing_status": "Draft Invoice Created", "service_billing_batch": self.batch.name, "sales_invoice": invoice.name}, update_modified=False)
				created += 1
			except Exception:
				errors += 1
				for row in rows:
					row.result_status = "Error"
					row.error_message = frappe.get_traceback()[-2000:]
		self.batch.invoices_created = cint(self.batch.invoices_created) + created
		self.batch.errors_count = sum(row.result_status == "Error" for row in self.batch.details)
		self.batch.status = "Completed With Errors" if self.batch.errors_count else "Completed"
		self.batch.completed_at = now_datetime()
		self.batch.save(ignore_permissions=True)
		return self.batch

	def _create_invoice(self, rows):
		jobs = [row.service_job for row in rows]
		references = _get_reserved_references(self.batch.name, jobs)
		if not references:
			frappe.throw("No unbilled source references remain for the selected jobs.")
		missing = [row.source_label for row in references if not row.item_code]
		if missing:
			frappe.throw(f"Configure ERPNext Items for service billing sources: {', '.join(sorted(set(missing)))}")
		cost_center = self.settings.default_service_cost_center or frappe.db.get_value("Company", self.batch.company, "cost_center")
		invoice = frappe.get_doc({
			"doctype": "Sales Invoice", "company": self.batch.company, "customer": rows[0].customer,
			"posting_date": self.batch.posting_date, "custom_service_billing_batch": self.batch.name,
			"currency": rows[0].currency, "tax_category": rows[0].tax_category,
			"custom_service_job": jobs[0] if len(jobs) == 1 else None, "items": [],
		})
		for row in references:
			invoice.append("items", {
				"item_code": row.item_code, "description": f"{row.description}\nSource: {row.source_doctype} {row.source_name}\nService Job: {row.service_job}",
				"qty": 1, "rate": row.amount, "cost_center": cost_center,
			})
		invoice.insert(ignore_permissions=True)
		for reference, item in zip(references, invoice.items):
			frappe.db.set_value("Service Billing Reference", reference.name, {"invoice": invoice.name, "invoice_item": item.name, "status": "Draft Invoiced"}, update_modified=False)
		return invoice


def _get_reserved_references(batch_name, jobs):
	settings = frappe.get_single("IT Service Settings")
	references = frappe.db.sql(
		"""
		select r.name,r.service_job,r.service_charge_row,r.adjustment,r.amount,
		case when r.service_charge_row is not null then 'Service Job Charge' else 'Service Billing Adjustment' end source_doctype,
		coalesce(r.service_charge_row,r.adjustment) source_name,
		coalesce(c.charge_type,a.adjustment_type) source_label,
		case when r.service_charge_row is not null then coalesce(c.description,c.charge_type) else concat(a.adjustment_type,': ',a.reason) end description,
		coalesce(c.item_code,a.item_code,sc.item_code,sa.item_code) item_code,
		c.charge_type
		from `tabService Billing Reference` r
		left join `tabService Job Charge` c on c.name=r.service_charge_row
		left join `tabService Billing Adjustment` a on a.name=r.adjustment
		left join `tabService Charge` sc on sc.name=c.service_charge
		left join `tabService Charge` sa on sa.name=a.service_charge
		where r.billing_batch=%(batch)s and r.service_job in %(jobs)s and r.status='Reserved'
		order by r.service_job,r.creation,r.name
		""",
		{"batch": batch_name, "jobs": jobs}, as_dict=True,
	)
	for ref in references:
		if ref.service_charge_row and not ref.item_code:
			ref.item_code = _resolve_service_item(ref, settings)
		elif ref.adjustment and not ref.item_code:
			ref.item_code = settings.default_service_item
	return references


def _resolve_service_item(source, settings):
	defaults = {
		"Labour": settings.default_labour_item or settings.default_service_item,
		"Installation": settings.default_installation_item or settings.default_service_item,
		"Travel": settings.default_travel_item or settings.default_service_item,
		"Accommodation": settings.default_accommodation_item or settings.default_service_item,
		"Food": settings.default_food_item or settings.default_service_item,
		"Remote Support": settings.default_remote_support_item or settings.default_service_item,
	}
	return source.item_code or source.get("service_item_code") or defaults.get(source.charge_type) or settings.default_service_item


def enqueue_prepare_service_billing(batch_name):
	frappe.enqueue("it_service_management.service_billing.services.batch.prepare_service_billing", queue="long", batch_name=batch_name, enqueue_after_commit=True)
	return {"queued": True, "service_billing_batch": batch_name}


def prepare_service_billing(batch_name):
	return ServiceBillingBatchEngine(frappe.get_doc("Service Billing Batch", batch_name)).prepare()


def enqueue_generate_service_invoices(batch_name):
	frappe.enqueue("it_service_management.service_billing.services.batch.generate_service_invoices", queue="long", batch_name=batch_name, enqueue_after_commit=True)
	return {"queued": True, "service_billing_batch": batch_name}


def generate_service_invoices(batch_name):
	return ServiceInvoiceService(frappe.get_doc("Service Billing Batch", batch_name)).generate()


def handle_invoice_submitted(doc, method=None):
	if not doc.get("custom_service_billing_batch"):
		return
	for ref in frappe.get_all("Service Billing Reference", filters={"invoice": doc.name}, fields=["name", "service_job"]):
		frappe.db.set_value("Service Billing Reference", ref.name, "status", "Submitted", update_modified=False)
		frappe.db.set_value("Service Job", ref.service_job, "billing_status", "Invoiced", update_modified=False)


def handle_invoice_cancelled(doc, method=None):
	_release_invoice_sources(doc.name)


def handle_invoice_deleted(doc, method=None):
	if doc.docstatus == 0:
		_release_invoice_sources(doc.name)


def _release_invoice_sources(invoice_name):
	references = frappe.get_all("Service Billing Reference", filters={"invoice": invoice_name}, fields=["name", "service_job", "billing_batch"])
	for ref in references:
		frappe.db.set_value("Service Billing Reference", ref.name, {"status": "Cancelled", "invoice": None, "invoice_item": None}, update_modified=False)
		frappe.db.set_value("Service Job", ref.service_job, {"billing_status": "Ready for Billing", "service_billing_batch": None, "sales_invoice": None}, update_modified=False)
	for batch_name in {row.billing_batch for row in references if row.billing_batch}:
		batch = frappe.get_doc("Service Billing Batch", batch_name)
		for detail in batch.details:
			if detail.invoice == invoice_name:
				detail.invoice = None
				detail.result_status = "Prepared"
				detail.error_message = None
		batch.status = "Approved for Billing" if cint(frappe.get_single("IT Service Settings").require_service_billing_approval) else "Prepared"
		batch.save(ignore_permissions=True)
