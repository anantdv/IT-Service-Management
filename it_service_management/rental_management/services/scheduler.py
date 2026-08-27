from __future__ import annotations

import frappe
from frappe.utils import add_days, get_first_day, get_last_day, getdate, nowdate


def run_daily_rental_checks():
	if not frappe.db.exists("DocType", "Rental Contract"):
		return
	update_contract_expiry()
	check_meter_readings_due()
	check_equipment_returns_due()
	check_billing_readiness()
	validate_preventive_maintenance_links()


def update_contract_expiry():
	today = getdate(nowdate())
	settings = frappe.get_single("IT Service Settings")
	days = _notification_days(settings.rental_expiry_notification_days)
	for row in frappe.get_all("Rental Contract", filters={"status": ["in", ["Active", "Expiring", "Suspended"]]}, fields=["name", "end_date", "status"]):
		if not row.end_date:
			continue
		remaining = (getdate(row.end_date) - today).days
		new_status = "Expired" if remaining < 0 else "Expiring" if remaining <= max(days or [90]) else row.status
		if new_status != row.status:
			frappe.db.set_value("Rental Contract", row.name, "status", new_status)
			frappe.get_doc("Rental Contract", row.name).add_comment("Comment", f"Rental Contract status changed to {new_status} by scheduled expiry check")
		if remaining in days:
			_add_once_comment("Rental Contract", row.name, f"rental-expiry-{remaining}-{today}", f"Rental Contract expires in {remaining} days.")


def check_meter_readings_due():
	today = getdate(nowdate())
	settings = frappe.get_single("IT Service Settings")
	due_day = min(max(int(settings.default_meter_reading_due_day or 25), 1), 28)
	if today.day < due_day:
		return
	period_from = get_first_day(today)
	period_to = get_last_day(today)
	for row in frappe.get_all("Rental Contract", filters={"status": ["in", ["Active", "Expiring"]], "meter_billing_enabled": 1}, fields=["name"]):
		for equipment in frappe.get_all("Rental Contract Equipment", filters={"parent": row.name, "deployment_status": "Deployed", "meter_billing_enabled": 1}, fields=["customer_equipment"]):
			if not frappe.db.exists("Equipment Meter Reading", {"customer_equipment": equipment.customer_equipment, "billing_period_from": period_from, "billing_period_to": period_to}):
				_add_once_comment("Rental Contract", row.name, f"meter-due-{equipment.customer_equipment}-{period_from}", f"Meter reading is due for {equipment.customer_equipment} for {period_from} to {period_to}.")


def check_equipment_returns_due():
	today = getdate(nowdate())
	for row in frappe.get_all("Rental Contract Equipment", filters={"expected_return_date": ["<=", add_days(today, 7)], "deployment_status": ["in", ["Deployed", "Temporarily Replaced", "Under Repair"]]}, fields=["parent", "customer_equipment", "expected_return_date"]):
		_add_once_comment("Rental Contract", row.parent, f"return-due-{row.customer_equipment}-{row.expected_return_date}", f"Return is due for {row.customer_equipment} on {row.expected_return_date}.")


def check_billing_readiness():
	today = getdate(nowdate())
	for row in frappe.get_all("Rental Contract", filters={"status": ["in", ["Active", "Expiring"]]}, fields=["name", "billing_day", "next_billing_date"]):
		if row.next_billing_date and getdate(row.next_billing_date) > today:
			continue
		if today.day >= min(max(int(row.billing_day or 1), 1), 28):
			_add_once_comment("Rental Contract", row.name, f"billing-ready-{today:%Y-%m}", f"Rental billing is ready for {today:%B %Y}.")


def validate_preventive_maintenance_links():
	if not frappe.db.exists("DocType", "Preventive Maintenance Plan"):
		return
	today = getdate(nowdate())
	intervals = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}
	for row in frappe.get_all("Preventive Maintenance Plan", filters={"active": 1, "next_service_date": ["<=", today]}, fields=["name", "customer", "customer_site", "customer_equipment", "rental_contract", "frequency", "next_service_date"]):
		equipment_status = frappe.db.get_value("Customer Equipment", row.customer_equipment, "equipment_status")
		contract_status = frappe.db.get_value("Rental Contract", row.rental_contract, "status") if row.rental_contract else None
		if equipment_status in ("Returned", "Retired") or (contract_status and contract_status not in ("Active", "Expiring")):
			frappe.db.set_value("Preventive Maintenance Plan", row.name, "active", 0, update_modified=False)
			continue
		job = frappe.db.exists("Service Job", {"customer_equipment": row.customer_equipment, "job_type": "Preventive Maintenance", "scheduled_date": row.next_service_date, "status": ["!=", "Cancelled"]})
		if not job:
			job_doc = frappe.get_doc({"doctype": "Service Job", "customer": row.customer, "customer_site": row.customer_site, "customer_equipment": row.customer_equipment, "rental_contract": row.rental_contract, "job_type": "Preventive Maintenance", "priority": "Medium", "scheduled_date": row.next_service_date, "customer_complaint": f"Scheduled preventive maintenance from {row.name}"}).insert(ignore_permissions=True)
			job = job_doc.name
		frappe.db.set_value("Preventive Maintenance Plan", row.name, {"last_service_job": job, "next_service_date": frappe.utils.add_months(row.next_service_date, intervals.get(row.frequency, 3))}, update_modified=False)


def prepare_monthly_billing_candidates():
	if not frappe.db.exists("DocType", "Rental Billing Run"):
		return
	today = getdate(nowdate())
	period_from = get_first_day(today)
	period_to = get_last_day(today)
	for company in frappe.get_all("Rental Contract", filters={"status": ["in", ["Active", "Expiring"]]}, distinct=True, pluck="company"):
		if frappe.db.exists("Rental Billing Run", {"company": company, "billing_period_from": period_from, "billing_period_to": period_to, "status": ["!=", "Cancelled"]}):
			continue
		settings = frappe.get_single("IT Service Settings")
		frappe.get_doc({"doctype": "Rental Billing Run", "company": company, "billing_period_from": period_from, "billing_period_to": period_to, "posting_date": today, "billing_mode": settings.rental_billing_mode, "status": "Draft"}).insert(ignore_permissions=True)


def _notification_days(value):
	result = []
	for part in (value or "90,60,30,15,7").split(","):
		try:
			result.append(int(part.strip()))
		except ValueError:
			continue
	return result


def _add_once_comment(reference_doctype, reference_name, marker, message):
	if frappe.db.exists("Comment", {"reference_doctype": reference_doctype, "reference_name": reference_name, "content": ["like", f"%[{marker}]%"]}):
		return
	frappe.get_doc(reference_doctype, reference_name).add_comment("Comment", f"{message} [{marker}]")
