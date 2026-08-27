from __future__ import annotations

import json
from hashlib import sha256
from dataclasses import dataclass
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_datetime, getdate, now_datetime, today


OPEN_TICKET_STATUSES = ("Open", "Assigned", "Remote Support", "Onsite Required", "Awaiting Parts", "Work In Progress")
ACTIVE_CONTRACT_STATUSES = ("Active", "Expiring")
ACTIVE_RENTAL_STATUSES = ("Active", "Expiring", "Termination Requested")


@dataclass
class DashboardFilters:
	company: str | None
	customer: str | None
	service_zone: str | None
	branch: str | None
	from_date: str
	to_date: str
	period: str


def get_payload(tab="overview", filters=None, force_refresh=False):
	filters = validate_filters(filters or {})
	settings = get_dashboard_settings()
	cache_key = make_cache_key(tab, filters)

	if not force_refresh:
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return cached

	payload = build_payload(tab, filters, settings)
	frappe.cache().set_value(cache_key, payload, expires_in_sec=settings["cache_seconds"])
	return payload


def build_payload(tab, filters, settings):
	builders = {
		"overview": build_overview,
		"service": build_service,
		"rental": build_rental,
		"contracts": build_contracts,
		"equipment": build_equipment,
		"financial": build_financial,
	}
	section_builder = builders.get(tab, build_overview)
	return {
		"tab": tab,
		"filters": filters.__dict__,
		"settings": settings,
		"company_currency": get_currency(filters.company),
		"last_refreshed": now_datetime().strftime("%H:%M"),
		"sections": section_builder(filters, settings),
	}


def validate_filters(raw):
	period = raw.get("period") or get_setting("dashboard_default_period") or "This Month"
	from_date, to_date = get_period_dates(period, raw.get("from_date"), raw.get("to_date"))
	company = raw.get("company") or frappe.defaults.get_user_default("Company")
	customer = raw.get("customer")
	service_zone = raw.get("service_zone")
	branch = raw.get("branch")

	if company and exists("Company", company):
		if not frappe.has_permission("Company", "read", doc=company):
			frappe.throw(_("Not permitted for company {0}").format(company), frappe.PermissionError)
	elif company:
		company = None

	if customer and exists("Customer", customer) and not frappe.has_permission("Customer", "read", doc=customer):
		frappe.throw(_("Not permitted for customer {0}").format(customer), frappe.PermissionError)

	return DashboardFilters(company, customer, service_zone, branch, str(from_date), str(to_date), period)


def get_period_dates(period, custom_from=None, custom_to=None):
	end = getdate(today())
	if period == "Today":
		start = end
	elif period == "This Week":
		start = add_days(end, -end.weekday())
	elif period == "This Month":
		start = end.replace(day=1)
	elif period == "This Quarter":
		month = ((end.month - 1) // 3) * 3 + 1
		start = end.replace(month=month, day=1)
	elif period == "This Fiscal Year":
		fiscal_year = frappe.defaults.get_user_default("fiscal_year")
		if fiscal_year and exists("Fiscal Year", fiscal_year):
			start, end = frappe.db.get_value("Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"])
		else:
			start = end.replace(month=1, day=1)
	elif period == "Last 90 Days":
		start = add_days(end, -89)
	elif period == "Custom" and custom_from and custom_to:
		start, end = getdate(custom_from), getdate(custom_to)
	else:
		start = add_days(end, -29)

	if getdate(end) < getdate(start):
		frappe.throw(_("To Date cannot be before From Date"))
	return getdate(start), getdate(end)


def get_dashboard_settings():
	return {
		"sla_target": flt(get_setting("management_sla_target_percentage") or 95),
		"cache_seconds": max(30, int(get_setting("dashboard_cache_seconds") or 120)),
		"technician_capacity_hours": flt(get_setting("technician_daily_capacity_hours") or 8),
		"critical_ticket_threshold": int(get_setting("critical_ticket_threshold") or 1),
		"contract_expiry_days": int(get_setting("contract_expiry_dashboard_days") or 90),
		"default_period": get_setting("dashboard_default_period") or "This Month",
	}


def get_setting(fieldname):
	if has_field("IT Service Settings", fieldname):
		return frappe.db.get_single_value("IT Service Settings", fieldname)
	return None


def make_cache_key(tab, filters):
	return "it_service_management:command_center:{0}:{1}:{2}".format(
		frappe.session.user,
		tab,
		sha256(json.dumps(filters.__dict__, sort_keys=True).encode()).hexdigest()[:16],
	)


def get_filter_options():
	return {
		"companies": frappe.get_all("Company", pluck="name", order_by="name"),
		"customers": frappe.get_all("Customer", fields=["name", "customer_name"], order_by="customer_name", limit=50),
		"service_zones": frappe.get_all("Service Zone", pluck="name", order_by="name") if doctype_exists("Service Zone") else [],
		"branches": [],
		"default_period": get_setting("dashboard_default_period") or "This Month",
	}


def build_overview(filters, settings):
	service_revenue = get_service_revenue(filters)
	rental_revenue = get_rental_revenue(filters)
	recurring = get_recurring_revenue(filters)
	open_tickets = count_docs("Service Ticket", {"status": ("in", OPEN_TICKET_STATUSES)}, filters)
	critical_tickets = count_docs("Service Ticket", {"priority": "Critical", "status": ("in", OPEN_TICKET_STATUSES)}, filters)
	sla = get_sla_health(filters)
	unbilled = get_unbilled_revenue(filters)

	return {
		"kpis": [
			kpi("Service Revenue", service_revenue, "currency", route_report("Unbilled Service Revenue"), trend=get_revenue_trend(filters, "service")),
			kpi("Rental Revenue", rental_revenue, "currency", route_report("Rental Revenue"), trend=get_revenue_trend(filters, "rental")),
			kpi("Recurring Revenue", recurring, "currency", route_doctype("Service Contract", {"contract_status": ["in", list(ACTIVE_CONTRACT_STATUSES)]}), context=_("Monthly base")),
			kpi("Open Tickets", open_tickets, "number", route_doctype("Service Ticket", {"status": ["in", list(OPEN_TICKET_STATUSES)]}), context=_("{0} Critical").format(critical_tickets), status="critical" if critical_tickets else "normal"),
			kpi("SLA Compliance", sla["compliance"], "percent", route_report("SLA Performance Analysis"), context=_("Target {0}%").format(settings["sla_target"]), status="warning" if sla["compliance"] < settings["sla_target"] else "success"),
			kpi("Unbilled Revenue", unbilled, "currency", route_report("Service and Rental Revenue Leakage"), context=_("Needs Attention") if unbilled else _("Current"), status="warning" if unbilled else "success"),
		],
		"secondary_kpis": build_secondary_kpis(filters, settings),
		"alerts": ManagementAlertEngine(filters, settings).get_alerts(),
		"charts": {
			"revenue_trend": get_revenue_trend_chart(filters),
			"revenue_mix": get_revenue_mix(filters),
			"ticket_status": get_ticket_status_chart(filters),
			"priority": get_ticket_priority_chart(filters),
		},
		"blocks": {
			"sla": sla,
			"pipeline": get_job_pipeline(filters),
			"technicians": get_technician_workload(filters, settings),
			"rental_fleet": get_rental_fleet(filters),
			"contract_health": get_contract_health(filters, settings),
			"billing": get_billing_control(filters),
			"profitability": get_profitability(filters),
		},
		"tables": {
			"attention_contracts": get_contracts_requiring_attention(filters),
			"high_maintenance": get_high_maintenance_equipment(filters),
			"top_customers": get_top_customers(filters),
		},
	}


def build_service(filters, settings):
	return {
		"kpis": [
			kpi("Open Tickets", count_docs("Service Ticket", {"status": ("in", OPEN_TICKET_STATUSES)}, filters), "number", route_doctype("Service Ticket")),
			kpi("Critical", count_docs("Service Ticket", {"priority": "Critical", "status": ("in", OPEN_TICKET_STATUSES)}, filters), "number", route_doctype("Service Ticket", {"priority": "Critical"}), status="critical"),
			kpi("SLA At Risk", count_docs("Service Ticket", {"response_sla_status": "At Risk"}, filters) + count_docs("Service Ticket", {"resolution_sla_status": "At Risk"}, filters), "number", route_report("SLA Performance Analysis"), status="warning"),
			kpi("Jobs Today", count_docs("Service Job", {"scheduled_date": today()}, filters), "number", route_doctype("Service Job", {"scheduled_date": today()})),
			kpi("Awaiting Parts", count_docs("Service Job", {"status": "Awaiting Parts"}, filters), "number", route_doctype("Service Job", {"status": "Awaiting Parts"}), status="warning"),
			kpi("Unbilled Service", get_unbilled_service(filters), "currency", route_report("Unbilled Service Revenue"), status="warning"),
		],
		"alerts": ManagementAlertEngine(filters, settings).get_alerts(["critical_tickets", "sla", "unbilled_service"]),
		"charts": {
			"ticket_status": get_ticket_status_chart(filters),
			"priority": get_ticket_priority_chart(filters),
			"service_revenue": get_revenue_trend_chart(filters, categories=("Service", "AMC", "Installation", "Other Service")),
		},
		"blocks": {
			"sla": get_sla_health(filters),
			"pipeline": get_job_pipeline(filters),
			"technicians": get_technician_workload(filters, settings),
			"field_metrics": get_field_service_metrics(filters),
		},
		"tables": {"critical_tickets": get_recent_critical_tickets(filters), "high_cost_jobs": get_high_cost_jobs(filters)},
	}


def build_rental(filters, settings):
	return {
		"kpis": [
			kpi("Active Contracts", count_docs("Rental Contract", {"status": ("in", ACTIVE_RENTAL_STATUSES)}, filters), "number", route_doctype("Rental Contract")),
			kpi("Monthly Rental Revenue", sum_field("Rental Contract", "monthly_recurring_revenue", {"status": ("in", ACTIVE_RENTAL_STATUSES)}, filters), "currency", route_doctype("Rental Contract")),
			kpi("Deployed Assets", count_docs("Customer Equipment", {"ownership_type": "Company Rental Asset", "equipment_status": "Deployed"}, filters), "number", route_doctype("Customer Equipment")),
			kpi("Available Assets", count_docs("Customer Equipment", {"ownership_type": "Company Rental Asset", "equipment_status": "Available"}, filters), "number", route_doctype("Customer Equipment")),
			kpi("Meter Pending", get_pending_meter_count(filters), "number", route_report("Pending Meter Readings"), status="warning"),
			kpi("Billing Pending", get_unbilled_rental(filters), "currency", route_report("Unbilled Rental Revenue"), status="warning"),
		],
		"alerts": ManagementAlertEngine(filters, settings).get_alerts(["meter", "rental_billing", "rental_expiry"]),
		"charts": {"fleet": get_rental_fleet(filters), "revenue": get_revenue_trend_chart(filters, categories=("Rental", "Meter Billing"))},
		"blocks": {"meter": get_meter_health(filters), "expiry": get_rental_expiry(filters, settings)},
		"tables": {"high_cost_equipment": get_high_maintenance_equipment(filters), "latest_deployments": get_latest("Rental Deployment", filters), "upcoming_returns": get_latest("Rental Return", filters)},
	}


def build_contracts(filters, settings):
	return {
		"kpis": [
			kpi("Active AMC", count_docs("Service Contract", {"contract_status": ("in", ACTIVE_CONTRACT_STATUSES)}, filters), "number", route_doctype("Service Contract")),
			kpi("Active Rental", count_docs("Rental Contract", {"status": ("in", ACTIVE_RENTAL_STATUSES)}, filters), "number", route_doctype("Rental Contract")),
			kpi("Expiring 30 Days", get_contracts_expiring(filters, 30), "number", route_report("Contract Renewal Pipeline"), status="warning"),
			kpi("Renewal Pipeline", count_docs("Contract Renewal Opportunity", {"status": ("!=", "Lost")}, filters), "number", route_report("Contract Renewal Pipeline")),
			kpi("Weighted Forecast", sum_field("Contract Renewal Opportunity", "expected_revenue", {"status": ("!=", "Lost")}, filters), "currency", route_report("Contract Renewal Forecast")),
			kpi("Loss-Making", len(get_contracts_requiring_attention(filters, limit=50)), "number", route_report("Service Contract Profitability"), status="critical"),
		],
		"charts": {"health": get_contract_health(filters, settings), "pipeline": get_renewal_pipeline(filters), "expiry": get_expiry_timeline(filters, settings)},
		"tables": {"attention_contracts": get_contracts_requiring_attention(filters)},
		"alerts": ManagementAlertEngine(filters, settings).get_alerts(["contract_expiry", "loss_making"]),
	}


def build_equipment(filters, settings):
	return {
		"kpis": [
			kpi("Total Equipment", count_docs("Customer Equipment", {}, filters), "number", route_doctype("Customer Equipment")),
			kpi("Warranty", count_docs("Customer Equipment", {"warranty_status": "Active"}, filters), "number", route_doctype("Customer Equipment", {"warranty_status": "Active"})),
			kpi("AMC Covered", count_docs("Customer Equipment", {"coverage_status": "Covered"}, filters), "number", route_doctype("Customer Equipment")),
			kpi("Rental", count_docs("Customer Equipment", {"ownership_type": "Company Rental Asset"}, filters), "number", route_doctype("Customer Equipment")),
			kpi("Under Service", count_docs("Customer Equipment", {"equipment_status": "Under Service"}, filters), "number", route_doctype("Customer Equipment"), status="warning"),
			kpi("Repeat Failure", get_repeat_failure_count(filters), "number", route_report("Equipment Repeat Failure Analysis"), status="warning"),
		],
		"charts": {"status": get_equipment_status(filters), "product_group": get_equipment_product_group(filters)},
		"tables": {"high_maintenance": get_high_maintenance_equipment(filters)},
		"alerts": ManagementAlertEngine(filters, settings).get_alerts(["equipment"]),
	}


def build_financial(filters, settings):
	receivables = get_receivables(filters)
	profitability = get_profitability(filters)
	return {
		"kpis": [
			kpi("Service Revenue", get_service_revenue(filters), "currency", route_report("Unbilled Service Revenue")),
			kpi("Rental Revenue", get_rental_revenue(filters), "currency", route_report("Rental Revenue")),
			kpi("Recurring Revenue", get_recurring_revenue(filters), "currency", route_doctype("Service Contract")),
			kpi("Unbilled Revenue", get_unbilled_revenue(filters), "currency", route_report("Service and Rental Revenue Leakage"), status="warning"),
			kpi("Outstanding Receivable", receivables["total"], "currency", route_report("Accounts Receivable"), status="warning"),
			kpi("Operational Contribution", profitability["total_contribution"], "currency", route_report("Operational Customer Profitability")),
		],
		"charts": {
			"revenue_trend": get_revenue_trend_chart(filters),
			"revenue_mix": get_revenue_mix(filters),
			"contribution": get_contribution_trend(filters),
		},
		"blocks": {"billing": get_billing_control(filters), "receivables": receivables, "profitability": profitability},
		"tables": {"top_customers": get_top_customers(filters), "attention_contracts": get_contracts_requiring_attention(filters)},
		"alerts": ManagementAlertEngine(filters, settings).get_alerts(["unbilled_service", "rental_billing", "loss_making"]),
	}


def build_secondary_kpis(filters, settings):
	return [
		kpi("Jobs Today", count_docs("Service Job", {"scheduled_date": today()}, filters), "number", route_doctype("Service Job")),
		kpi("Unassigned Jobs", count_docs("Service Job", {"assigned_technician": ("is", "not set"), "status": ("not in", ("Completed", "Cancelled"))}, filters), "number", route_doctype("Service Job"), status="warning"),
		kpi("SLA At Risk", count_docs("Service Ticket", {"response_sla_status": "At Risk"}, filters) + count_docs("Service Ticket", {"resolution_sla_status": "At Risk"}, filters), "number", route_report("SLA Performance Analysis"), status="warning"),
		kpi("Awaiting Parts", count_docs("Service Job", {"status": "Awaiting Parts"}, filters), "number", route_doctype("Service Job", {"status": "Awaiting Parts"}), status="warning"),
		kpi("Active AMC", count_docs("Service Contract", {"contract_status": ("in", ACTIVE_CONTRACT_STATUSES)}, filters), "number", route_doctype("Service Contract")),
		kpi("Active Rentals", count_docs("Rental Contract", {"status": ("in", ACTIVE_RENTAL_STATUSES)}, filters), "number", route_doctype("Rental Contract")),
		kpi("Contracts Expiring", get_contracts_expiring(filters, settings["contract_expiry_days"]), "number", route_report("Contract Renewal Pipeline"), status="warning"),
		kpi("Pending Meter Readings", get_pending_meter_count(filters), "number", route_report("Pending Meter Readings"), status="warning"),
	]


def kpi(title, value, kind, route, context=None, trend=None, status="normal"):
	return {"title": title, "value": flt(value, 2), "kind": kind, "context": context or "", "trend": trend, "status": status, "route": route}


def doctype_exists(doctype):
	return frappe.db.exists("DocType", doctype)


def exists(doctype, name):
	return bool(doctype_exists(doctype) and frappe.db.exists(doctype, name))


def has_field(doctype, fieldname):
	if not doctype_exists(doctype):
		return False
	return frappe.get_meta(doctype).has_field(fieldname)


def table(doctype):
	return "`tab{0}`".format(doctype.replace("`", ""))


def count_docs(doctype, filters=None, dashboard_filters=None, date_field=None):
	if not doctype_exists(doctype):
		return 0
	conditions, values = build_conditions(doctype, filters or {}, dashboard_filters, date_field)
	return frappe.db.sql("select count(*) from {0} where {1}".format(table(doctype), " and ".join(conditions)), values)[0][0] or 0


def sum_field(doctype, fieldname, filters=None, dashboard_filters=None, date_field=None):
	if not doctype_exists(doctype) or not has_field(doctype, fieldname):
		return 0
	conditions, values = build_conditions(doctype, filters or {}, dashboard_filters, date_field)
	return flt(frappe.db.sql("select sum(coalesce({0}, 0)) from {1} where {2}".format(fieldname, table(doctype), " and ".join(conditions)), values)[0][0])


def grouped_counts(doctype, fieldname, filters=None, dashboard_filters=None, date_field=None, limit=12):
	if not doctype_exists(doctype) or not has_field(doctype, fieldname):
		return []
	conditions, values = build_conditions(doctype, filters or {}, dashboard_filters, date_field)
	return frappe.db.sql(
		"select coalesce({0}, 'Not Set') label, count(*) value from {1} where {2} group by {0} order by value desc limit {3}".format(
			fieldname, table(doctype), " and ".join(conditions), int(limit)
		),
		values,
		as_dict=True,
	)


def build_conditions(doctype, doc_filters, dashboard_filters, date_field=None, alias=None):
	prefix = (alias + ".") if alias else ""
	conditions = ["{0}docstatus < 2".format(prefix)] if has_field(doctype, "docstatus") else ["1=1"]
	values = {}
	for fieldname, value in doc_filters.items():
		if not has_field(doctype, fieldname):
			continue
		key = "f_" + fieldname
		if isinstance(value, tuple):
			op = value[0]
			val = value[1]
			if op in ("in", "not in"):
				conditions.append("{0}{1} {2} %({3})s".format(prefix, fieldname, op, key))
				values[key] = tuple(val)
			elif op == "between":
				conditions.append("{0}{1} between %({2}_from)s and %({2}_to)s".format(prefix, fieldname, key))
				values[key + "_from"] = val[0]
				values[key + "_to"] = val[1]
			elif op == "!=":
				conditions.append("{0}{1} != %({2})s".format(prefix, fieldname, key))
				values[key] = val
			elif op == "is" and val == "not set":
				conditions.append("({0}{1} is null or {0}{1} = '')".format(prefix, fieldname))
			else:
				conditions.append("{0}{1} {2} %({3})s".format(prefix, fieldname, op, key))
				values[key] = val
		else:
			conditions.append("{0}{1} = %({2})s".format(prefix, fieldname, key))
			values[key] = value

	if dashboard_filters:
		if dashboard_filters.company and has_field(doctype, "company"):
			conditions.append("{0}company = %(company)s".format(prefix))
			values["company"] = dashboard_filters.company
		if dashboard_filters.customer and has_field(doctype, "customer"):
			conditions.append("{0}customer = %(customer)s".format(prefix))
			values["customer"] = dashboard_filters.customer
		if dashboard_filters.service_zone and has_field(doctype, "service_zone"):
			conditions.append("{0}service_zone = %(service_zone)s".format(prefix))
			values["service_zone"] = dashboard_filters.service_zone
		if date_field and has_field(doctype, date_field):
			conditions.append("{0}{1} between %(from_date)s and %(to_date)s".format(prefix, date_field))
			values["from_date"] = dashboard_filters.from_date
			values["to_date"] = dashboard_filters.to_date
	return conditions, values


def get_service_revenue(filters):
	if doctype_exists("Service Billing Reference") and has_field("Service Billing Reference", "invoice"):
		return sum_submitted_reference("Service Billing Reference", filters)
	return sum_sales_invoice(filters, "custom_service_billing_batch")


def get_rental_revenue(filters):
	if doctype_exists("Rental Billing Reference") and has_field("Rental Billing Reference", "invoice"):
		return sum_submitted_reference("Rental Billing Reference", filters)
	return sum_sales_invoice(filters, "custom_rental_billing_run")


def sum_submitted_reference(doctype, filters):
	if not doctype_exists(doctype):
		return 0
	conditions = ["r.status = 'Submitted'", "si.docstatus = 1", "si.posting_date between %(from_date)s and %(to_date)s"]
	values = {"from_date": filters.from_date, "to_date": filters.to_date}
	if filters.company and has_field("Sales Invoice", "company"):
		conditions.append("si.company = %(company)s")
		values["company"] = filters.company
	if filters.customer:
		conditions.append("si.customer = %(customer)s")
		values["customer"] = filters.customer
	return flt(frappe.db.sql(
		"select sum(coalesce(r.amount, 0)) from {0} r inner join `tabSales Invoice` si on si.name = r.invoice where {1}".format(table(doctype), " and ".join(conditions)),
		values,
	)[0][0])


def sum_sales_invoice(filters, source_field):
	if not doctype_exists("Sales Invoice") or not has_field("Sales Invoice", source_field):
		return 0
	conditions = ["docstatus = 1", "posting_date between %(from_date)s and %(to_date)s", "{0} is not null".format(source_field), "{0} != ''".format(source_field)]
	values = {"from_date": filters.from_date, "to_date": filters.to_date}
	if filters.company:
		conditions.append("company = %(company)s")
		values["company"] = filters.company
	if filters.customer:
		conditions.append("customer = %(customer)s")
		values["customer"] = filters.customer
	return flt(frappe.db.sql("select sum(base_net_total) from `tabSales Invoice` where {0}".format(" and ".join(conditions)), values)[0][0])


def get_recurring_revenue(filters):
	return sum_field("Service Contract", "billing_amount", {"contract_status": ("in", ACTIVE_CONTRACT_STATUSES)}, filters) + sum_field(
		"Rental Contract", "monthly_recurring_revenue", {"status": ("in", ACTIVE_RENTAL_STATUSES)}, filters
	)


def get_unbilled_service(filters):
	return sum_field("Service Job", "total_billable_amount", {"billing_status": ("!=", "Invoiced"), "status": "Completed"}, filters, "completion_datetime")


def get_unbilled_rental(filters):
	if doctype_exists("Rental Billing Run"):
		return sum_field("Rental Billing Run", "grand_total", {"status": ("not in", ("Completed", "Cancelled"))}, filters)
	return 0


def get_unbilled_revenue(filters):
	return get_unbilled_service(filters) + get_unbilled_rental(filters) + sum_field("Equipment Meter Reading", "total_meter_charge", {"verified": 1}, filters, "reading_date")


def get_sla_health(filters):
	total = count_docs("Service Ticket", {"status": ("!=", "Cancelled")}, filters)
	response_met = count_docs("Service Ticket", {"response_sla_status": "Met"}, filters)
	resolution_met = count_docs("Service Ticket", {"resolution_sla_status": "Met"}, filters)
	response_breached = count_docs("Service Ticket", {"response_sla_status": "Breached"}, filters)
	resolution_breached = count_docs("Service Ticket", {"resolution_sla_status": "Breached"}, filters)
	at_risk = count_docs("Service Ticket", {"response_sla_status": "At Risk"}, filters) + count_docs("Service Ticket", {"resolution_sla_status": "At Risk"}, filters)
	measured = response_met + resolution_met + response_breached + resolution_breached
	compliance = ((response_met + resolution_met) / measured * 100) if measured else 100
	return {
		"compliance": flt(compliance, 1),
		"within": response_met + resolution_met,
		"at_risk": at_risk,
		"breached": response_breached + resolution_breached,
		"response": flt(response_met / (response_met + response_breached) * 100, 1) if response_met + response_breached else 100,
		"resolution": flt(resolution_met / (resolution_met + resolution_breached) * 100, 1) if resolution_met + resolution_breached else 100,
		"total": total,
		"route": route_report("SLA Performance Analysis"),
	}


def get_job_pipeline(filters):
	stages = ["Scheduled", "Assigned", "In Transit", "Working", "Awaiting Parts", "Completed"]
	return [{"label": status, "value": count_docs("Service Job", {"status": status}, filters), "route": route_doctype("Service Job", {"status": status})} for status in stages]


def get_technician_workload(filters, settings):
	if not doctype_exists("Service Job") or not has_field("Service Job", "assigned_technician"):
		return []
	conditions, values = build_conditions("Service Job", {"status": ("not in", ("Completed", "Cancelled"))}, filters)
	rows = frappe.db.sql(
		"""select assigned_technician technician, count(*) jobs, sum(coalesce(total_job_duration_minutes, onsite_duration_minutes, 0)) / 60 hours
		from `tabService Job` where {0} and assigned_technician is not null and assigned_technician != ''
		group by assigned_technician order by jobs desc limit 8""".format(" and ".join(conditions)),
		values,
		as_dict=True,
	)
	for row in rows:
		capacity = settings["technician_capacity_hours"] or 8
		load = flt((row.hours or row.jobs) / capacity * 100, 1)
		row.load = load
		row.status = "Available" if load <= 70 else "Normal" if load <= 90 else "High" if load <= 110 else "Overloaded"
		row.route = route_report("Technician Productivity", {"technician": row.technician})
	return rows


def get_field_service_metrics(filters):
	completed = count_docs("Service Job", {"status": "Completed"}, filters, "completion_datetime")
	first_time_fix = max(0, completed - get_repeat_failure_count(filters))
	avg_onsite = avg_field("Service Job", "onsite_duration_minutes", {"status": "Completed"}, filters, "completion_datetime")
	return {
		"first_time_fix": flt(first_time_fix / completed * 100, 1) if completed else 0,
		"average_onsite_minutes": flt(avg_onsite),
		"repeat_visits": flt(get_repeat_failure_count(filters) / completed * 100, 1) if completed else 0,
		"customer_rating": avg_field("Service Job", "customer_rating", {"status": "Completed"}, filters, "completion_datetime"),
	}


def avg_field(doctype, fieldname, filters_dict, filters, date_field=None):
	if not doctype_exists(doctype) or not has_field(doctype, fieldname):
		return 0
	conditions, values = build_conditions(doctype, filters_dict, filters, date_field)
	return flt(frappe.db.sql("select avg({0}) from {1} where {2}".format(fieldname, table(doctype), " and ".join(conditions)), values)[0][0])


def get_rental_fleet(filters):
	return chart_from_rows("Rental Fleet", grouped_counts("Customer Equipment", "equipment_status", {"ownership_type": "Company Rental Asset"}, filters), "donut")


def get_meter_health(filters):
	pending = get_pending_meter_count(filters)
	received = count_docs("Equipment Meter Reading", {"verified": 1}, filters, "reading_date")
	expected = pending + received
	meter_revenue = sum_field("Equipment Meter Reading", "total_meter_charge", {"verified": 1}, filters, "reading_date")
	return {"expected": expected, "received": received, "pending": pending, "overdue": pending, "expected_revenue": meter_revenue, "billed": get_rental_revenue(filters), "unbilled": get_unbilled_rental(filters), "route": route_report("Pending Meter Readings")}


def get_pending_meter_count(filters):
	if not doctype_exists("Rental Contract Equipment") or not doctype_exists("Equipment Meter Reading"):
		return 0
	return count_docs("Rental Contract Equipment", {"deployment_status": "Deployed", "meter_billing_enabled": 1}, None)


def get_rental_expiry(filters, settings):
	return bucket_expiry("Rental Contract", "end_date", "status", ACTIVE_RENTAL_STATUSES, filters, settings["contract_expiry_days"])


def get_expiry_timeline(filters, settings):
	return bucket_expiry("Service Contract", "end_date", "contract_status", ACTIVE_CONTRACT_STATUSES, filters, settings["contract_expiry_days"])


def bucket_expiry(doctype, date_field, status_field, statuses, filters, days):
	buckets = [{"label": "0-30 Days", "from": 0, "to": 30}, {"label": "31-60 Days", "from": 31, "to": 60}, {"label": "61-90 Days", "from": 61, "to": min(90, days)}]
	for bucket in buckets:
		start = add_days(today(), bucket["from"])
		end = add_days(today(), bucket["to"])
		bucket["value"] = count_docs(doctype, {status_field: ("in", statuses), date_field: ("between", (start, end))}, filters)
	return {"labels": [b["label"] for b in buckets], "values": [b["value"] for b in buckets], "route": route_doctype(doctype)}


def get_contracts_expiring(filters, days):
	return count_docs("Service Contract", {"contract_status": ("in", ACTIVE_CONTRACT_STATUSES), "end_date": ("between", (today(), add_days(today(), days)))}, filters) + count_docs(
		"Rental Contract", {"status": ("in", ACTIVE_RENTAL_STATUSES), "end_date": ("between", (today(), add_days(today(), days)))}, filters
	)


def get_contract_health(filters, settings):
	healthy = count_docs("Service Contract", {"contract_status": ("in", ACTIVE_CONTRACT_STATUSES)}, filters)
	expiring = get_contracts_expiring(filters, settings["contract_expiry_days"])
	loss = len(get_contracts_requiring_attention(filters, limit=50))
	values = [max(healthy - expiring - loss, 0), 0, 0, loss, expiring]
	return {"title": "Contract Health", "type": "donut", "labels": ["Healthy", "High Utilisation", "Over Entitlement", "Loss-Making", "Renewal Risk"], "values": values}


def get_renewal_pipeline(filters):
	rows = grouped_sum("Contract Renewal Opportunity", "renewal_stage", "expected_revenue", {"status": ("!=", "Lost")}, filters)
	return chart_from_rows("Renewal Pipeline", rows, "bar")


def get_equipment_status(filters):
	return chart_from_rows("Equipment Status", grouped_counts("Customer Equipment", "equipment_status", {}, filters), "donut")


def get_equipment_product_group(filters):
	return chart_from_rows("Equipment by Product Group", grouped_counts("Customer Equipment", "product_category", {}, filters), "bar")


def grouped_sum(doctype, group_field, sum_fieldname, filters_dict, filters):
	if not doctype_exists(doctype) or not has_field(doctype, group_field) or not has_field(doctype, sum_fieldname):
		return []
	conditions, values = build_conditions(doctype, filters_dict, filters)
	return frappe.db.sql(
		"select coalesce({0}, 'Not Set') label, sum(coalesce({1}, 0)) value from {2} where {3} group by {0} order by value desc".format(
			group_field, sum_fieldname, table(doctype), " and ".join(conditions)
		),
		values,
		as_dict=True,
	)


def get_revenue_mix(filters):
	rows = [
		{"label": "AMC", "value": sum_field("Service Contract", "billing_amount", {"contract_status": ("in", ACTIVE_CONTRACT_STATUSES)}, filters)},
		{"label": "Chargeable Service", "value": get_service_revenue(filters)},
		{"label": "Rental", "value": get_rental_revenue(filters)},
		{"label": "Meter Billing", "value": sum_field("Equipment Meter Reading", "total_meter_charge", {"verified": 1}, filters, "reading_date")},
		{"label": "Installation", "value": 0},
		{"label": "Other", "value": 0},
	]
	return chart_from_rows("Revenue Mix", rows, "donut")


def get_revenue_trend_chart(filters, categories=None):
	categories = categories or ("Service", "AMC", "Rental", "Meter Billing", "Installation", "Other Service")
	return {
		"title": "Revenue Trend",
		"type": "bar",
		"labels": [filters.period],
		"datasets": [{"name": category, "values": [get_category_revenue(category, filters)]} for category in categories],
	}


def get_category_revenue(category, filters):
	if category in ("Service", "Chargeable Service", "Other Service"):
		return get_service_revenue(filters)
	if category == "AMC":
		return sum_field("Service Contract", "billing_amount", {"contract_status": ("in", ACTIVE_CONTRACT_STATUSES)}, filters)
	if category == "Rental":
		return get_rental_revenue(filters)
	if category == "Meter Billing":
		return sum_field("Equipment Meter Reading", "total_meter_charge", {"verified": 1}, filters, "reading_date")
	return 0


def get_revenue_trend(filters, category):
	current = get_service_revenue(filters) if category == "service" else get_rental_revenue(filters)
	previous_filters = previous_period(filters)
	previous = get_service_revenue(previous_filters) if category == "service" else get_rental_revenue(previous_filters)
	if not previous:
		return None
	return {"direction": "up" if current >= previous else "down", "percent": flt((current - previous) / previous * 100, 1)}


def previous_period(filters):
	start = getdate(filters.from_date)
	end = getdate(filters.to_date)
	length = (end - start).days + 1
	prev_end = add_days(start, -1)
	prev_start = add_days(prev_end, -(length - 1))
	return DashboardFilters(filters.company, filters.customer, filters.service_zone, filters.branch, str(prev_start), str(prev_end), filters.period)


def get_ticket_status_chart(filters):
	return chart_from_rows("Ticket Status", grouped_counts("Service Ticket", "status", {}, filters), "donut")


def get_ticket_priority_chart(filters):
	return chart_from_rows("Priority Breakdown", grouped_counts("Service Ticket", "priority", {}, filters), "bar")


def chart_from_rows(title, rows, chart_type):
	return {"title": title, "type": chart_type, "labels": [r.get("label") for r in rows], "values": [flt(r.get("value")) for r in rows]}


def get_billing_control(filters):
	return {
		"completed_service_not_billed": get_unbilled_service(filters),
		"rental_billing_pending": get_unbilled_rental(filters),
		"meter_charges_unbilled": sum_field("Equipment Meter Reading", "total_meter_charge", {"verified": 1}, filters, "reading_date"),
		"approved_expenses_not_recharged": sum_field("Service Expense", "customer_billable_amount", {"approval_status": "Approved", "billable_to_customer": 1}, filters, "expense_date"),
		"estimated_revenue_leakage": get_unbilled_revenue(filters),
		"route": route_report("Service and Rental Revenue Leakage"),
	}


def get_profitability(filters):
	service_revenue = get_service_revenue(filters)
	service_cost = sum_field("Service Job", "total_internal_cost", {"status": "Completed"}, filters, "completion_datetime")
	rental_revenue = get_rental_revenue(filters)
	rental_cost = 0
	service_contribution = service_revenue - service_cost
	rental_contribution = rental_revenue - rental_cost
	total = service_contribution + rental_contribution
	return {
		"service_contribution": service_contribution,
		"service_margin": flt(service_contribution / service_revenue * 100, 1) if service_revenue else 0,
		"rental_contribution": rental_contribution,
		"rental_margin": flt(rental_contribution / rental_revenue * 100, 1) if rental_revenue else 0,
		"amc_contribution": sum_field("Service Contract", "billing_amount", {"contract_status": ("in", ACTIVE_CONTRACT_STATUSES)}, filters),
		"total_contribution": total,
		"label": "Operational Contribution",
	}


def get_contribution_trend(filters):
	p = get_profitability(filters)
	return {"title": "Contribution Trend", "type": "bar", "labels": [filters.period], "datasets": [{"name": "Service", "values": [p["service_contribution"]]}, {"name": "AMC", "values": [p["amc_contribution"]]}, {"name": "Rental", "values": [p["rental_contribution"]]}]}


def get_receivables(filters):
	if not doctype_exists("Sales Invoice"):
		return {"total": 0, "buckets": []}
	conditions = ["docstatus = 1", "outstanding_amount > 0"]
	values = {}
	if filters.company:
		conditions.append("company = %(company)s")
		values["company"] = filters.company
	if filters.customer:
		conditions.append("customer = %(customer)s")
		values["customer"] = filters.customer
	rows = frappe.db.sql(
		"""select sum(outstanding_amount) total,
		sum(case when datediff(curdate(), due_date) <= 0 then outstanding_amount else 0 end) current_amount,
		sum(case when datediff(curdate(), due_date) between 1 and 30 then outstanding_amount else 0 end) d30,
		sum(case when datediff(curdate(), due_date) between 31 and 60 then outstanding_amount else 0 end) d60,
		sum(case when datediff(curdate(), due_date) between 61 and 90 then outstanding_amount else 0 end) d90,
		sum(case when datediff(curdate(), due_date) > 90 then outstanding_amount else 0 end) d90plus
		from `tabSales Invoice` where {0}""".format(" and ".join(conditions)),
		values,
		as_dict=True,
	)[0]
	return {"total": flt(rows.total), "buckets": [{"label": "Current", "value": flt(rows.current_amount)}, {"label": "1-30", "value": flt(rows.d30)}, {"label": "31-60", "value": flt(rows.d60)}, {"label": "61-90", "value": flt(rows.d90)}, {"label": "90+", "value": flt(rows.d90plus)}], "route": route_report("Accounts Receivable")}


def get_contracts_requiring_attention(filters, limit=10):
	rows = []
	if doctype_exists("Service Contract"):
		conditions, values = build_conditions("Service Contract", {"contract_status": ("in", ACTIVE_CONTRACT_STATUSES)}, filters)
		rows.extend(frappe.db.sql(
			"""select customer, name contract, 'Service Contract' type, billing_amount revenue, 0 cost,
			billing_amount margin, 0 utilisation, end_date expiry
			from `tabService Contract` where {0} order by end_date asc limit {1}""".format(" and ".join(conditions), int(limit)),
			values,
			as_dict=True,
		))
	for row in rows:
		row.status = "Review" if getdate(row.expiry) <= add_days(today(), 30) else "Monitor"
		row.route = route_doctype(row.type, {"name": row.contract})
	return rows[:limit]


def get_high_maintenance_equipment(filters, limit=8):
	if not doctype_exists("Service Job") or not has_field("Service Job", "customer_equipment"):
		return []
	conditions, values = build_conditions("Service Job", {"status": ("!=", "Cancelled")}, filters, "completion_datetime")
	return frappe.db.sql(
		"""select customer_equipment equipment, customer, item_code model, count(*) jobs,
		sum(coalesce(parts_cost, 0)) parts_cost, sum(coalesce(total_internal_cost, 0)) service_cost,
		sum(coalesce(total_job_duration_minutes, 0)) downtime, 'Review' status
		from `tabService Job` where {0} and customer_equipment is not null and customer_equipment != ''
		group by customer_equipment, customer, item_code order by jobs desc, service_cost desc limit {1}""".format(" and ".join(conditions), int(limit)),
		values,
		as_dict=True,
	)


def get_recent_critical_tickets(filters):
	if not doctype_exists("Service Ticket"):
		return []
	conditions, values = build_conditions("Service Ticket", {"priority": "Critical", "status": ("in", OPEN_TICKET_STATUSES)}, filters)
	rows = frappe.db.sql(
		"""select name ticket, customer, customer_equipment equipment, priority, status, assigned_technician technician,
		resolution_due from `tabService Ticket` where {0} order by reported_datetime desc limit 10""".format(" and ".join(conditions)),
		values,
		as_dict=True,
	)
	for row in rows:
		row.sla_remaining = format_sla_remaining(row.resolution_due)
		row.route = route_doctype("Service Ticket", {"name": row.ticket})
	return rows


def format_sla_remaining(value):
	if not value:
		return ""
	delta = get_datetime(value) - now_datetime()
	minutes = int(delta.total_seconds() / 60)
	prefix = "Breached by " if minutes < 0 else ""
	minutes = abs(minutes)
	return "{0}{1}h {2}m".format(prefix, minutes // 60, minutes % 60)


def get_high_cost_jobs(filters):
	if not doctype_exists("Service Job"):
		return []
	conditions, values = build_conditions("Service Job", {"status": "Completed"}, filters, "completion_datetime")
	return frappe.db.sql(
		"""select name job, customer, customer_equipment equipment, total_internal_cost cost, total_billable_amount billable,
		estimated_margin_percentage margin, billing_status from `tabService Job` where {0}
		order by total_internal_cost desc limit 10""".format(" and ".join(conditions)),
		values,
		as_dict=True,
	)


def get_top_customers(filters):
	if not doctype_exists("Sales Invoice"):
		return []
	conditions = ["docstatus = 1", "posting_date between %(from_date)s and %(to_date)s"]
	values = {"from_date": filters.from_date, "to_date": filters.to_date}
	if filters.company:
		conditions.append("company = %(company)s")
		values["company"] = filters.company
	if filters.customer:
		conditions.append("customer = %(customer)s")
		values["customer"] = filters.customer
	rows = frappe.db.sql(
		"""select customer, sum(base_net_total) revenue, sum(base_net_total) contribution, count(*) tickets
		from `tabSales Invoice` where {0} group by customer order by revenue desc limit 10""".format(" and ".join(conditions)),
		values,
		as_dict=True,
	)
	for row in rows:
		row.route = route_doctype("Customer", {"name": row.customer})
	return rows


def get_latest(doctype, filters):
	if not doctype_exists(doctype):
		return []
	return frappe.get_all(doctype, fields=["name", "customer", "status", "modified"], order_by="modified desc", limit=8)


def get_repeat_failure_count(filters):
	return count_docs("Service Ticket", {"priority": ("in", ("Critical", "High"))}, filters)


class ManagementAlertEngine:
	def __init__(self, filters, settings):
		self.filters = filters
		self.settings = settings

	def get_alerts(self, include=None):
		include = set(include or ["critical_tickets", "sla", "unbilled_service", "meter", "contract_expiry", "loss_making", "equipment"])
		alerts = []
		if "critical_tickets" in include:
			count = count_docs("Service Ticket", {"priority": "Critical", "status": ("in", OPEN_TICKET_STATUSES)}, self.filters)
			if count:
				alerts.append(alert("critical", "critical_tickets", _("{0} critical tickets currently open").format(count), route_doctype("Service Ticket", {"priority": "Critical"})))
		if "sla" in include:
			breached = count_docs("Service Ticket", {"resolution_sla_status": "Breached"}, self.filters)
			at_risk = count_docs("Service Ticket", {"resolution_sla_status": "At Risk"}, self.filters)
			if breached:
				alerts.append(alert("critical", "sla", _("{0} tickets have breached SLA").format(breached), route_report("SLA Performance Analysis")))
			if at_risk:
				alerts.append(alert("warning", "sla", _("{0} tickets are at SLA risk").format(at_risk), route_report("SLA Performance Analysis")))
		if "unbilled_service" in include:
			amount = get_unbilled_service(self.filters)
			if amount:
				alerts.append(alert("warning", "unbilled_service", _("Completed services remain unbilled"), route_report("Unbilled Service Revenue"), amount))
		if "meter" in include:
			pending = get_pending_meter_count(self.filters)
			if pending:
				alerts.append(alert("warning", "meter", _("{0} meter readings are pending").format(pending), route_report("Pending Meter Readings")))
		if "contract_expiry" in include or "rental_expiry" in include:
			expiring = get_contracts_expiring(self.filters, 30)
			if expiring:
				alerts.append(alert("info", "contract_expiry", _("{0} contracts expire within 30 days").format(expiring), route_report("Contract Renewal Pipeline")))
		if "loss_making" in include:
			loss = len(get_contracts_requiring_attention(self.filters, limit=25))
			if loss:
				alerts.append(alert("warning", "loss_making", _("{0} contracts require management review").format(loss), route_report("Service Contract Profitability")))
		if "equipment" in include:
			repeat = get_repeat_failure_count(self.filters)
			if repeat:
				alerts.append(alert("info", "equipment", _("{0} high-priority equipment incidents need review").format(repeat), route_report("Equipment Repeat Failure Analysis")))
		return sorted(alerts, key=lambda row: {"critical": 0, "warning": 1, "info": 2}.get(row["severity"], 3))[:8]


def alert(severity, alert_type, title, route, amount=None):
	return {"severity": severity, "type": alert_type, "title": title, "amount": flt(amount), "route": route}


def route_doctype(doctype, filters=None):
	return {"type": "doctype", "doctype": doctype, "filters": filters or {}}


def route_report(report, filters=None):
	return {"type": "report", "report": report, "filters": filters or {}}


def get_currency(company=None):
	if company and doctype_exists("Company"):
		return frappe.db.get_value("Company", company, "default_currency")
	return frappe.defaults.get_global_default("currency") or "USD"
