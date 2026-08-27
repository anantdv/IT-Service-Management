from __future__ import annotations

import frappe
from frappe.utils import add_days, cint, flt, nowdate


def create_renewal_opportunities():
	settings = frappe.get_single("IT Service Settings")
	if not cint(settings.auto_create_renewal_opportunity):
		return
	_create_for_service_contracts(cint(settings.service_renewal_opportunity_days) or 90)
	_create_for_rental_contracts(cint(settings.rental_renewal_opportunity_days) or 90)


def _create_for_service_contracts(days):
	contracts = frappe.get_all(
		"Service Contract", filters={"contract_status": ["in", ["Active", "Expiring"]], "end_date": ["between", [nowdate(), add_days(nowdate(), days)]]},
		fields=["name", "customer", "start_date", "end_date", "billing_amount", "service_plan"],
	)
	for contract in contracts:
		_create("Service Contract", contract, "service_contract", "service_plan", contract.billing_amount)


def _create_for_rental_contracts(days):
	contracts = frappe.get_all(
		"Rental Contract", filters={"status": ["in", ["Active", "Expiring"]], "end_date": ["between", [nowdate(), add_days(nowdate(), days)]]},
		fields=["name", "customer", "start_date", "end_date", "total_contract_value", "base_rental_amount", "rental_plan"],
	)
	for contract in contracts:
		_create("Rental Contract", contract, "rental_contract", "rental_plan", contract.total_contract_value or contract.base_rental_amount)


def _create(contract_type, contract, link_field, plan_field, value):
	if frappe.db.exists("Contract Renewal Opportunity", {link_field: contract.name, "status": ["in", ["Open", "Renewed"]]}):
		return
	job_link = "service_contract" if contract_type == "Service Contract" else "rental_contract"
	costs = frappe.db.sql(
		f"""select count(*) job_count, coalesce(sum(total_internal_cost), 0) service_cost,
		coalesce(sum(parts_cost), 0) parts_cost from `tabService Job`
		where {job_link} = %s and status = 'Completed'""",
		contract.name, as_dict=True,
	)[0]
	margin = flt(value) - flt(costs.service_cost)
	indicator = "Loss Making" if margin < 0 else "High Service Cost" if value and flt(costs.service_cost) / flt(value) >= 0.8 else "Maintain Price"
	frappe.get_doc({
		"doctype": "Contract Renewal Opportunity", "renewal_type": contract_type, link_field: contract.name,
		"customer": contract.customer, "current_start_date": contract.start_date, "current_end_date": contract.end_date,
		"current_value": value, "current_plan_doctype": "Service Plan" if contract_type == "Service Contract" else "Rental Plan",
		"current_plan": contract.get(plan_field), "renewal_due_date": contract.end_date, "proposed_value": value,
		"service_cost": costs.service_cost, "existing_margin": margin, "service_job_count": costs.job_count,
		"parts_cost": costs.parts_cost, "suggested_review_indicator": indicator,
	}).insert(ignore_permissions=True)
