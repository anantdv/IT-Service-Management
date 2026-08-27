import frappe

from it_service_management.analytics.reporting.reports import RENTAL_FINANCE_ROLES, _require


def execute(filters=None):
	_require(RENTAL_FINANCE_ROLES)
	filters = frappe._dict(filters or {})
	conditions = ["1=1"]
	values = {}
	for key, column in (("company", "rc.company"), ("customer", "rc.customer"), ("rental_contract", "rc.name")):
		if filters.get(key): conditions.append(f"{column}=%({key})s"); values[key] = filters[key]
	invoice_dates = []
	if filters.get("from_date"): invoice_dates.append("si.posting_date >= %(from_date)s"); values["from_date"] = filters.from_date
	if filters.get("to_date"): invoice_dates.append("si.posting_date <= %(to_date)s"); values["to_date"] = filters.to_date
	date_sql = " and " + " and ".join(invoice_dates) if invoice_dates else ""
	columns = ["Contract:Link/Rental Contract:160", "Customer:Link/Customer:170", "Equipment Count:Int:100", "Contract Revenue:Currency:120", "Meter Revenue:Currency:110", "Service Revenue:Currency:110", "Other Revenue:Currency:105", "Total Revenue:Currency:110", "Depreciation:Currency:105", "Labour Cost:Currency:100", "Parts Cost:Currency:100", "Expense Cost:Currency:100", "Total Direct Cost:Currency:120", "Contribution:Currency:110", "Contribution %:Percent:105", "Revenue per Equipment:Currency:130", "Cost per Equipment:Currency:120"]
	data = frappe.db.sql(f"""
		select rc.name,rc.customer,coalesce(eq.equipment_count,0),coalesce(rev.base_revenue,0),coalesce(rev.meter_revenue,0),coalesce(rev.service_revenue,0),coalesce(rev.other_revenue,0),coalesce(rev.total_revenue,0),coalesce(eq.depreciation,0),coalesce(cost.labour_cost,0),coalesce(cost.parts_cost,0),coalesce(cost.expense_cost,0),coalesce(eq.depreciation,0)+coalesce(cost.total_cost,0),coalesce(rev.total_revenue,0)-coalesce(eq.depreciation,0)-coalesce(cost.total_cost,0),(coalesce(rev.total_revenue,0)-coalesce(eq.depreciation,0)-coalesce(cost.total_cost,0))/nullif(rev.total_revenue,0)*100,coalesce(rev.total_revenue,0)/nullif(eq.equipment_count,0),(coalesce(eq.depreciation,0)+coalesce(cost.total_cost,0))/nullif(eq.equipment_count,0)
		from `tabRental Contract` rc
		left join (select r.rental_contract,sum(case when r.component_type like 'Base Rental%%' then r.amount else 0 end) base_revenue,sum(case when r.component_type in ('B&W Usage','Colour Usage','Meter Usage') then r.amount else 0 end) meter_revenue,sum(case when r.source_document_type='Service Job' then r.amount else 0 end) service_revenue,sum(case when r.component_type not like 'Base Rental%%' and r.component_type not in ('B&W Usage','Colour Usage','Meter Usage') and r.source_document_type!='Service Job' then r.amount else 0 end) other_revenue,sum(r.amount) total_revenue from `tabRental Billing Reference` r inner join `tabSales Invoice` si on si.name=r.invoice and si.docstatus=1 where r.status='Submitted'{date_sql} group by r.rental_contract) rev on rev.rental_contract=rc.name
		left join (select rce.parent,count(*) equipment_count,sum(greatest(coalesce(a.gross_purchase_amount,0)-coalesce(a.value_after_depreciation,0),0)) depreciation from `tabRental Contract Equipment` rce left join `tabAsset` a on a.name=rce.asset group by rce.parent) eq on eq.parent=rc.name
		left join (select rental_contract,sum(labour_cost) labour_cost,sum(parts_cost) parts_cost,sum(expense_cost) expense_cost,sum(total_internal_cost) total_cost from `tabService Job` where status='Completed' group by rental_contract) cost on cost.rental_contract=rc.name
		where {' and '.join(conditions)} order by rc.customer,rc.name
	""", values)
	return columns, data
