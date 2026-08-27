import frappe
from frappe.utils import add_days, get_first_day, get_last_day, nowdate


@frappe.whitelist()
def get_rental_dashboard_metrics(company=None):
	cache = frappe.cache() if callable(frappe.cache) else frappe.cache
	cache_key = f"itsm:rental-dashboard:{company or 'all'}"
	if cached := cache.get_value(cache_key):
		return cached
	contract_filters = {"status": ["in", ["Active", "Expiring"]]}
	if company:
		contract_filters["company"] = company
	today = nowdate()
	metrics = {
		"active_contracts": frappe.db.count("Rental Contract", contract_filters),
		"monthly_recurring_revenue": frappe.db.sql("select coalesce(sum(monthly_recurring_revenue),0) from `tabRental Contract` where status in ('Active','Expiring')" + (" and company=%s" if company else ""), (company,) if company else None)[0][0],
		"deployed_equipment": frappe.db.count("Rental Contract Equipment", {"deployment_status": "Deployed"}),
		"available_equipment": _available_assets(company),
		"under_repair": frappe.db.count("Rental Contract Equipment", {"deployment_status": "Under Repair"}),
		"contracts_expiring": frappe.db.count("Rental Contract", {**contract_filters, "end_date": ["between", [today, add_days(today, 30)]]}),
		"meter_readings_pending": _pending_meters(),
		"billing_pending": frappe.db.count("Rental Billing Run", {"status": ["in", ["Draft", "Prepared", "Processing"]]}),
		"unbilled_meter_revenue": frappe.db.sql("select coalesce(sum(total_meter_charge),0) from `tabEquipment Meter Reading` emr where verified=1 and not exists (select 1 from `tabRental Billing Reference` rbr where rbr.source_document=emr.name and rbr.status in ('Reserved','Draft Invoiced','Submitted'))")[0][0],
	}
	cache.set_value(cache_key, metrics, expires_in_sec=300)
	return metrics


def _available_assets(company=None):
	values = {"company": company} if company else {}
	condition = "and a.company=%(company)s" if company else ""
	return frappe.db.sql(f"""select count(*) from `tabAsset` a where a.docstatus < 2 and ifnull(a.status,'') not in ('Disposed','Scrapped') {condition} and not exists (select 1 from `tabRental Contract Equipment` rce inner join `tabRental Contract` rc on rc.name=rce.parent where rce.asset=a.name and rc.status in ('Approved','Active','Suspended','Expiring','Termination Requested') and rce.deployment_status in ('Reserved','Ready for Deployment','Deployed','Temporarily Replaced','Under Repair'))""", values)[0][0]


def _pending_meters():
	period_from = get_first_day(nowdate()); period_to = get_last_day(nowdate())
	return frappe.db.sql("""select count(*) from `tabRental Contract Equipment` rce inner join `tabRental Contract` rc on rc.name=rce.parent where rc.status in ('Active','Expiring') and rce.deployment_status='Deployed' and rce.meter_billing_enabled=1 and not exists (select 1 from `tabEquipment Meter Reading` emr where emr.customer_equipment=rce.customer_equipment and emr.billing_period_from=%s and emr.billing_period_to=%s)""", (period_from, period_to))[0][0]
