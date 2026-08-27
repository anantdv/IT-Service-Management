import frappe

from it_service_management.analytics.reporting.reports import RENTAL_FINANCE_ROLES, _require


def execute(filters=None):
	_require(RENTAL_FINANCE_ROLES)
	filters = frappe._dict(filters or {})
	conditions = ["ce.ownership_type in ('Company Rental Asset','Temporary Replacement')"]
	values = {}
	for key, column in (("customer", "ce.customer"), ("rental_contract", "ce.rental_contract"), ("customer_equipment", "ce.name")):
		if filters.get(key): conditions.append(f"{column}=%({key})s"); values[key] = filters[key]
	columns = ["Customer Equipment:Link/Customer Equipment:170", "Asset:Link/Asset:145", "Customer:Link/Customer:165", "Acquisition Cost:Currency:110", "Net Book Value:Currency:110", "Deployment Date:Date:110", "Months Deployed:Int:100", "Base Rental Revenue:Currency:125", "Meter Revenue:Currency:110", "Other Revenue:Currency:105", "Total Revenue:Currency:110", "Service Labour Cost:Currency:120", "Parts Cost:Currency:100", "Expense Cost:Currency:100", "Replacement Count:Int:105", "Downtime Days:Float:95", "Total Direct Cost:Currency:115", "Contribution:Currency:110", "Contribution %:Percent:105", "Payback Ratio:Percent:100"]
	data = frappe.db.sql(f"""
		select ce.name,ce.asset,ce.customer,coalesce(a.gross_purchase_amount,0),coalesce(a.value_after_depreciation,0),ce.rental_deployment_date,timestampdiff(month,ce.rental_deployment_date,coalesce(ce.rental_return_date,curdate())),coalesce(rev.base_revenue,0),coalesce(rev.meter_revenue,0),coalesce(rev.other_revenue,0),coalesce(rev.total_revenue,0),coalesce(cost.labour_cost,0),coalesce(cost.parts_cost,0),coalesce(cost.expense_cost,0),coalesce(rep.replacement_count,0),coalesce(cost.downtime_days,0),coalesce(cost.total_cost,0),coalesce(rev.total_revenue,0)-coalesce(cost.total_cost,0),(coalesce(rev.total_revenue,0)-coalesce(cost.total_cost,0))/nullif(rev.total_revenue,0)*100,coalesce(rev.total_revenue,0)/nullif(a.gross_purchase_amount,0)*100
		from `tabCustomer Equipment` ce left join `tabAsset` a on a.name=ce.asset
		left join (select bc.customer_equipment,sum(case when r.component_type like 'Base Rental%%' then r.amount else 0 end) base_revenue,sum(case when r.component_type in ('B&W Usage','Colour Usage','Meter Usage') then r.amount else 0 end) meter_revenue,sum(case when r.component_type not like 'Base Rental%%' and r.component_type not in ('B&W Usage','Colour Usage','Meter Usage') then r.amount else 0 end) other_revenue,sum(r.amount) total_revenue from `tabRental Billing Reference` r inner join `tabRental Billing Component` bc on bc.billing_reference=r.name inner join `tabSales Invoice` si on si.name=r.invoice and si.docstatus=1 where r.status='Submitted' group by bc.customer_equipment) rev on rev.customer_equipment=ce.name
		left join (select customer_equipment,sum(labour_cost) labour_cost,sum(parts_cost) parts_cost,sum(expense_cost) expense_cost,sum(total_internal_cost) total_cost,sum(total_job_duration_minutes)/1440 downtime_days from `tabService Job` where status='Completed' group by customer_equipment) cost on cost.customer_equipment=ce.name
		left join (select old_customer_equipment,count(*) replacement_count from `tabRental Equipment Replacement` where status='Completed' group by old_customer_equipment) rep on rep.old_customer_equipment=ce.name
		where {' and '.join(conditions)} order by coalesce(rev.total_revenue,0)-coalesce(cost.total_cost,0) desc
	""", values)
	return columns, data
