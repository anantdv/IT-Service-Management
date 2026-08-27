from __future__ import annotations

import frappe
from frappe.utils import add_days, cint, flt, nowdate


FINANCE_ROLES = {"Accounts Manager", "System Manager", "IT Service Analyst", "IT Service Executive", "Service Auditor"}
SERVICE_FINANCE_ROLES = FINANCE_ROLES | {"Service Manager", "Service Billing User", "Service Contract Manager"}
RENTAL_FINANCE_ROLES = FINANCE_ROLES | {"Rental Manager", "Rental Billing User"}


def run(report_name, filters=None):
	filters = frappe._dict(filters or {})
	function = REPORTS.get(report_name)
	if not function:
		frappe.throw(f"Unsupported management report: {report_name}")
	return function(filters)


def _require(roles):
	if not set(frappe.get_roles()).intersection(roles):
		frappe.throw("You are not permitted to view this financial report.", frappe.PermissionError)


def _dates(filters, column, conditions, values):
	if filters.get("from_date"):
		conditions.append(f"{column} >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append(f"{column} <= %(to_date)s")
		values["to_date"] = filters.to_date


def unbilled_service(filters):
	_require(SERVICE_FINANCE_ROLES)
	conditions = ["sj.status='Completed'", "sj.total_billable_amount > 0", "not exists (select 1 from `tabService Billing Reference` r where r.service_job=sj.name and r.status='Submitted')"]
	values = {}
	for key, column in (("customer", "sj.customer"), ("service_contract", "sj.service_contract"), ("company", "sc.company")):
		if filters.get(key): conditions.append(f"{column}=%({key})s"); values[key] = filters[key]
	_dates(filters, "date(sj.completion_datetime)", conditions, values)
	columns = ["Service Job:Link/Service Job:150", "Completion Date:Datetime:150", "Customer:Link/Customer:170", "Customer Site:Link/Customer Site:150", "Equipment:Link/Customer Equipment:160", "Contract:Link/Service Contract:150", "Billable Amount:Currency:120", "Days Unbilled:Int:100", "Age Bucket:Data:90", "Billing Status:Data:130", "Billing Batch:Link/Service Billing Batch:150", "Reason:Data:200"]
	data = frappe.db.sql(f"""
		select sj.name,sj.completion_datetime,sj.customer,sj.customer_site,sj.customer_equipment,sj.service_contract,
		sj.total_billable_amount,datediff(curdate(),date(sj.completion_datetime)),
		case when datediff(curdate(),date(sj.completion_datetime))<=7 then '0-7' when datediff(curdate(),date(sj.completion_datetime))<=15 then '8-15' when datediff(curdate(),date(sj.completion_datetime))<=30 then '16-30' when datediff(curdate(),date(sj.completion_datetime))<=60 then '31-60' else '60+' end,
		sj.billing_status,sj.service_billing_batch,
		case when sj.billing_status='Not Calculated' then 'Billing not calculated' when sj.service_billing_batch is null then 'Not selected for a batch' else 'Invoice not submitted' end
		from `tabService Job` sj left join `tabService Contract` sc on sc.name=sj.service_contract
		where {' and '.join(conditions)} order by sj.completion_datetime
	""", values)
	return columns, data


def service_job_profitability(filters):
	_require(SERVICE_FINANCE_ROLES)
	conditions = ["sj.status='Completed'"]
	values = {}
	for key, column in (("customer", "sj.customer"), ("technician", "sj.assigned_technician"), ("service_team", "sj.service_team"), ("service_contract", "sj.service_contract"), ("customer_equipment", "sj.customer_equipment"), ("job_type", "sj.job_type"), ("coverage_source", "sj.coverage_source"), ("company", "sc.company")):
		if filters.get(key): conditions.append(f"{column}=%({key})s"); values[key] = filters[key]
	_dates(filters, "date(sj.completion_datetime)", conditions, values)
	columns = ["Service Job:Link/Service Job:150", "Customer:Link/Customer:160", "Site:Link/Customer Site:140", "Equipment:Link/Customer Equipment:150", "Contract:Link/Service Contract:140", "Technician:Link/Employee:130", "Completion Date:Datetime:150", "Labour Revenue:Currency:110", "Parts Revenue:Currency:110", "Expense Recharge:Currency:120", "Other Revenue:Currency:110", "Total Revenue:Currency:110", "Labour Cost:Currency:100", "Parts Cost:Currency:100", "Expense Cost:Currency:100", "Total Cost:Currency:100", "Gross Contribution:Currency:125", "Contribution %:Percent:110"]
	data = frappe.db.sql(f"""
		select sj.name,sj.customer,sj.customer_site,sj.customer_equipment,sj.service_contract,sj.assigned_technician,sj.completion_datetime,
		coalesce(ch.labour,0),coalesce(ch.parts,0),coalesce(ch.expense_recharge,0),coalesce(ch.other_revenue,0),coalesce(ch.revenue,0),
		coalesce(sj.labour_cost,0),coalesce(sj.parts_cost,0),coalesce(sj.expense_cost,0),coalesce(sj.total_internal_cost,0),
		coalesce(ch.revenue,0)-coalesce(sj.total_internal_cost,0),(coalesce(ch.revenue,0)-coalesce(sj.total_internal_cost,0))/nullif(ch.revenue,0)*100
		from `tabService Job` sj left join `tabService Contract` sc on sc.name=sj.service_contract
		left join (select parent,sum(case when charge_type='Labour' then billable_amount else 0 end) labour,
		sum(case when charge_type='Part' then billable_amount else 0 end) parts,
		sum(case when source_type='Service Expense' then billable_amount else 0 end) expense_recharge,
		sum(case when charge_type not in ('Labour','Part') and source_type!='Service Expense' then billable_amount else 0 end) other_revenue,
		sum(billable_amount) revenue from `tabService Job Charge` where billable=1 group by parent) ch on ch.parent=sj.name
		where {' and '.join(conditions)} order by sj.completion_datetime desc
	""", values)
	return columns, data


def service_contract_profitability(filters):
	_require(SERVICE_FINANCE_ROLES)
	conditions = ["1=1"]
	values = {}
	for key, column in (("company", "sc.company"), ("customer", "sc.customer"), ("service_contract", "sc.name")):
		if filters.get(key): conditions.append(f"{column}=%({key})s"); values[key] = filters[key]
	job_dates = []
	_dates(filters, "date(sj.completion_datetime)", job_dates, values)
	job_where = " and " + " and ".join(job_dates) if job_dates else ""
	invoice_dates = []
	_dates(filters, "si.posting_date", invoice_dates, values)
	invoice_where = " and " + " and ".join(invoice_dates) if invoice_dates else ""
	columns = ["Contract:Link/Service Contract:160", "Customer:Link/Customer:170", "Plan:Link/Service Plan:140", "Contract Revenue:Currency:120", "Jobs Count:Int:90", "Labour Cost:Currency:100", "Parts Cost:Currency:100", "Expense Cost:Currency:100", "Total Direct Cost:Currency:120", "Contribution:Currency:110", "Contribution %:Percent:110", "Contract Utilisation %:Percent:130"]
	data = frappe.db.sql(f"""
		select sc.name,sc.customer,sc.service_plan,coalesce(rev.revenue,0)+coalesce(srev.revenue,0),coalesce(cost.job_count,0),coalesce(cost.labour_cost,0),coalesce(cost.parts_cost,0),coalesce(cost.expense_cost,0),coalesce(cost.total_cost,0),
		coalesce(rev.revenue,0)+coalesce(srev.revenue,0)-coalesce(cost.total_cost,0),(coalesce(rev.revenue,0)+coalesce(srev.revenue,0)-coalesce(cost.total_cost,0))/nullif(coalesce(rev.revenue,0)+coalesce(srev.revenue,0),0)*100,
		coalesce(ent.used,0)/nullif(ent.included,0)*100
		from `tabService Contract` sc
		left join (select sj.service_contract,count(*) job_count,sum(sj.labour_cost) labour_cost,sum(sj.parts_cost) parts_cost,sum(sj.expense_cost) expense_cost,sum(sj.total_internal_cost) total_cost from `tabService Job` sj where sj.status='Completed'{job_where} group by sj.service_contract) cost on cost.service_contract=sc.name
		left join (select sc2.name service_contract,sum(si.base_net_total) revenue from `tabService Contract` sc2 inner join `tabSales Invoice` si on si.docstatus=1 and (si.name=sc2.sales_invoice or si.subscription=sc2.subscription){invoice_where} group by sc2.name) rev on rev.service_contract=sc.name
		left join (select sj.service_contract,sum(r.amount) revenue from `tabService Billing Reference` r inner join `tabService Job` sj on sj.name=r.service_job inner join `tabSales Invoice` si on si.name=r.invoice and si.docstatus=1 where r.status='Submitted'{invoice_where} group by sj.service_contract) srev on srev.service_contract=sc.name
		left join (select parent,sum(included_quantity) included,sum(used_quantity) used from `tabService Contract Entitlement` group by parent) ent on ent.parent=sc.name
		where {' and '.join(conditions)} order by sc.customer,sc.name
	""", values)
	return columns, data


def contract_utilisation(filters):
	_require(SERVICE_FINANCE_ROLES)
	conditions = ["1=1"]
	values = {}
	for key, column in (("company", "sc.company"), ("customer", "sc.customer")):
		if filters.get(key): conditions.append(f"{column}=%({key})s"); values[key] = filters[key]
	columns = ["Contract:Link/Service Contract:160", "Customer:Link/Customer:170", "Onsite Included:Float:100", "Onsite Used:Float:90", "Onsite Remaining:Float:110", "Remote Hours Included:Float:125", "Remote Hours Used:Float:115", "Remote Hours Remaining:Float:135", "PM Planned:Float:90", "PM Completed:Float:100", "Emergency Calls:Float:105", "Parts Cost:Currency:100", "Labour Hours:Float:95", "Contract Revenue:Currency:115", "Utilisation %:Percent:100", "Flag:Data:110"]
	data = frappe.db.sql(f"""
		select sc.name,sc.customer,coalesce(e.onsite_included,0),coalesce(e.onsite_used,0),coalesce(e.onsite_included-e.onsite_used,0),coalesce(e.remote_included,0),coalesce(e.remote_used,0),coalesce(e.remote_included-e.remote_used,0),coalesce(e.pm_included,0),coalesce(e.pm_used,0),coalesce(e.emergency_used,0),coalesce(j.parts_cost,0),coalesce(j.labour_hours,0),coalesce(sc.billing_amount,0),coalesce(e.used/e.included*100,0),
		case when coalesce(e.used/e.included*100,0) > %(over)s then 'Over Entitlement' when coalesce(e.used/e.included*100,0) >= %(high)s then 'High Utilisation' when coalesce(e.used/e.included*100,0) < 30 then 'Underutilised' else 'Normal' end
		from `tabService Contract` sc left join (select parent,sum(included_quantity) included,sum(used_quantity) used,
		sum(case when entitlement_type='Onsite Visits' then included_quantity else 0 end) onsite_included,sum(case when entitlement_type='Onsite Visits' then used_quantity else 0 end) onsite_used,
		sum(case when entitlement_type='Remote Support Hours' then included_quantity else 0 end) remote_included,sum(case when entitlement_type='Remote Support Hours' then used_quantity else 0 end) remote_used,
		sum(case when entitlement_type='Preventive Maintenance Visits' then included_quantity else 0 end) pm_included,sum(case when entitlement_type='Preventive Maintenance Visits' then used_quantity else 0 end) pm_used,
		sum(case when entitlement_type='Emergency Calls' then used_quantity else 0 end) emergency_used from `tabService Contract Entitlement` group by parent) e on e.parent=sc.name
		left join (select sj.service_contract,sum(sj.parts_cost) parts_cost,sum(l.duration_hours) labour_hours from `tabService Job` sj left join `tabService Job Labour` l on l.parent=sj.name group by sj.service_contract) j on j.service_contract=sc.name
		where {' and '.join(conditions)} order by sc.customer,sc.name
	""", {**values, "high": flt(frappe.db.get_single_value("IT Service Settings", "high_utilisation_percentage") or 80), "over": flt(frappe.db.get_single_value("IT Service Settings", "over_utilisation_percentage") or 100)})
	return columns, data


def contract_over_service(filters):
	columns, rows = service_contract_profitability(filters)
	columns = columns[:4] + ["Service Cost:Currency:110", "Margin:Currency:110", "Entitlement Used %:Percent:120", "Visits Over Limit:Float:110", "Parts Cost:Currency:100", "Recommendation Flag:Data:150"]
	data = []
	for row in rows:
		revenue, total_cost, contribution, utilisation = flt(row[3]), flt(row[8]), flt(row[9]), flt(row[11])
		if total_cost <= revenue and utilisation <= 100:
			continue
		flag = "Contract Loss-Making" if contribution < 0 else "Renewal Price Increase" if utilisation > 100 else "Review Pricing"
		data.append(list(row[:4]) + [total_cost, contribution, utilisation, 0, row[6], flag])
	return columns, data


def renewal_pipeline(filters):
	_require(SERVICE_FINANCE_ROLES | RENTAL_FINANCE_ROLES)
	conditions = ["cro.status='Open'"]
	values = {}
	for key, column in (("renewal_stage", "cro.renewal_stage"), ("assigned_to", "cro.assigned_to"), ("renewal_type", "cro.renewal_type"), ("customer", "cro.customer")):
		if filters.get(key): conditions.append(f"{column}=%({key})s"); values[key] = filters[key]
	columns = ["Contract:Dynamic Link/renewal_type:160", "Type:Data:110", "Customer:Link/Customer:170", "Expiry Date:Date:100", "Days to Expiry:Int:100", "Current Value:Currency:110", "Renewal Stage:Data:130", "Proposed Value:Currency:110", "Probability:Percent:90", "Expected Revenue:Currency:120", "Assigned To:Link/User:140", "Next Follow-Up:Date:110"]
	data = frappe.db.sql(f"""select if(cro.renewal_type='Service Contract',cro.service_contract,cro.rental_contract),cro.renewal_type,cro.customer,cro.current_end_date,datediff(cro.current_end_date,curdate()),cro.current_value,cro.renewal_stage,cro.proposed_value,cro.probability,cro.expected_revenue,cro.assigned_to,cro.next_followup_date from `tabContract Renewal Opportunity` cro where {' and '.join(conditions)} order by cro.current_end_date""", values)
	return columns, data


def renewal_forecast(filters):
	_require(SERVICE_FINANCE_ROLES | RENTAL_FINANCE_ROLES)
	conditions = ["status='Open'"]
	values = {}
	_dates(filters, "proposed_start_date", conditions, values)
	columns = ["Month:Data:100", "Quarter:Data:90", "Contract Type:Data:120", "Assigned User:Link/User:150", "Opportunities:Int:90", "Proposed Value:Currency:120", "Expected Revenue:Currency:120"]
	data = frappe.db.sql(f"""select date_format(coalesce(proposed_start_date,current_end_date),'%%Y-%%m'),concat(year(coalesce(proposed_start_date,current_end_date)),' Q',quarter(coalesce(proposed_start_date,current_end_date))),renewal_type,assigned_to,count(*),sum(proposed_value),sum(expected_revenue) from `tabContract Renewal Opportunity` where {' and '.join(conditions)} group by 1,2,3,4 order by 1,3,4""", values)
	return columns, data


def unbilled_rental(filters):
	_require(RENTAL_FINANCE_ROLES)
	conditions = ["rc.status in ('Active','Expiring','Termination Requested')", "rc.next_billing_date <= curdate()"]
	values = {}
	for key, column in (("company", "rc.company"), ("customer", "rc.customer"), ("rental_contract", "rc.name")):
		if filters.get(key): conditions.append(f"{column}=%({key})s"); values[key] = filters[key]
	columns = ["Contract:Link/Rental Contract:160", "Customer:Link/Customer:170", "Billing Period:Date:110", "Expected Amount:Currency:120", "Billed Amount:Currency:110", "Difference:Currency:110", "Days Overdue:Int:100", "Reason:Data:190"]
	data = frappe.db.sql(f"""
		select rc.name,rc.customer,rc.next_billing_date,coalesce(rc.base_rental_amount,0)+coalesce(extra.amount,0),coalesce(billed.amount,0),coalesce(rc.base_rental_amount,0)+coalesce(extra.amount,0)-coalesce(billed.amount,0),datediff(curdate(),rc.next_billing_date),
		case when billed.amount is null then 'Billing run or invoice missing' else 'Expected amount exceeds submitted billing' end
		from `tabRental Contract` rc
		left join (select rental_contract,sum(amount) amount from `tabRental Ad-Hoc Charge` where status='Approved' and billable=1 group by rental_contract) extra on extra.rental_contract=rc.name
		left join (select rental_contract,billing_period_from,billing_period_to,sum(amount) amount from `tabRental Billing Reference` where status='Submitted' group by rental_contract,billing_period_from,billing_period_to) billed on billed.rental_contract=rc.name and rc.next_billing_date between billed.billing_period_from and billed.billing_period_to
		where {' and '.join(conditions)} and coalesce(rc.base_rental_amount,0)+coalesce(extra.amount,0)>coalesce(billed.amount,0) order by rc.next_billing_date
	""", values)
	return columns, data


def revenue_leakage(filters):
	_require(FINANCE_ROLES | {"Service Manager", "Rental Manager"})
	conditions = []
	values = {}
	if filters.get("customer"):
		conditions.append("customer=%(customer)s")
		values["customer"] = filters.customer
	outer = "where " + " and ".join(conditions) if conditions else ""
	columns = ["Leakage Type:Data:180", "Customer:Link/Customer:170", "Contract:Data:150", "Source Document:Dynamic Link/source_doctype:170", "Source DocType:Data:150", "Date:Date:105", "Estimated Amount:Currency:125", "Days Outstanding:Int:110", "Responsible Department:Data:140"]
	data = frappe.db.sql(f"""
		select leakage_type,customer,contract,source_document,source_doctype,source_date,estimated_amount,datediff(curdate(),source_date),department from (
		select 'Completed Unbilled Service' leakage_type,sj.customer,coalesce(sj.service_contract,sj.rental_contract) contract,sj.name source_document,'Service Job' source_doctype,date(sj.completion_datetime) source_date,sj.total_billable_amount estimated_amount,'Service' department from `tabService Job` sj where sj.status='Completed' and sj.total_billable_amount>0 and not exists(select 1 from `tabService Billing Reference` r where r.service_job=sj.name and r.status='Submitted')
		union all select 'Approved Ad-Hoc Charge',rc.customer,ah.rental_contract,ah.name,'Rental Ad-Hoc Charge',ah.charge_date,ah.amount,'Rental' from `tabRental Ad-Hoc Charge` ah inner join `tabRental Contract` rc on rc.name=ah.rental_contract where ah.status='Approved' and ah.billable=1 and not exists(select 1 from `tabRental Billing Reference` r where r.source_document_type='Rental Ad-Hoc Charge' and r.source_document=ah.name and r.status='Submitted')
		union all select 'Unbilled Meter Usage',rc.customer,mr.rental_contract,mr.name,'Equipment Meter Reading',mr.reading_date,mr.total_meter_charge,'Rental' from `tabEquipment Meter Reading` mr inner join `tabRental Contract` rc on rc.name=mr.rental_contract where mr.total_meter_charge>0 and not exists(select 1 from `tabRental Billing Reference` r where r.source_document_type='Equipment Meter Reading' and r.source_document=mr.name and r.status='Submitted')
		union all select 'Approved Service Expense',sj.customer,coalesce(sj.service_contract,sj.rental_contract),se.name,'Service Expense',se.expense_date,se.customer_billable_amount,'Service' from `tabService Expense` se inner join `tabService Job` sj on sj.name=se.service_job where se.approval_status='Approved' and se.billable_to_customer=1 and se.customer_billable_amount>0 and se.sales_invoice is null
		) leakage {outer} order by source_date
	""", values)
	return columns, data


def service_expense_recovery(filters):
	_require(SERVICE_FINANCE_ROLES)
	conditions = ["se.approval_status='Approved'"]
	values = {}
	for key, column in (("customer", "sj.customer"), ("service_job", "sj.name")):
		if filters.get(key): conditions.append(f"{column}=%({key})s"); values[key] = filters[key]
	_dates(filters, "se.expense_date", conditions, values)
	columns = ["Service Expense:Link/Service Expense:150", "Service Job:Link/Service Job:145", "Customer:Link/Customer:170", "Expense Type:Data:120", "Actual Expense:Currency:110", "Approved Reimbursement:Currency:145", "Customer Billable:Currency:125", "Customer Invoiced:Currency:125", "Recovery Difference:Currency:130", "Recovery %:Percent:100", "Status:Data:110"]
	data = frappe.db.sql(f"""
		select se.name,se.service_job,sj.customer,se.expense_type,
		coalesce(se.actual_expense_amount,se.amount,0),
		coalesce(se.approved_reimbursement_amount,se.approved_amount,0),
		coalesce(se.customer_billable_amount,0),
		coalesce(si.base_net_total,0),
		coalesce(si.base_net_total,se.customer_billable_amount,0)-coalesce(se.actual_expense_amount,se.amount,0),
		coalesce(si.base_net_total,se.customer_billable_amount,0)/nullif(coalesce(se.actual_expense_amount,se.amount,0),0)*100,
		case when si.docstatus=1 then 'Invoiced' when se.sales_invoice is not null then 'Draft' when se.billing_status='Not Billable' then 'Not Billable' when se.billable_to_customer=1 then 'Unbilled' else 'Covered' end
		from `tabService Expense` se
		inner join `tabService Job` sj on sj.name=se.service_job
		left join `tabSales Invoice` si on si.name=se.sales_invoice
		where {' and '.join(conditions)}
		order by se.expense_date desc
	""", values)
	return columns, data


def installation_billing_control(filters):
	_require(SERVICE_FINANCE_ROLES)
	conditions = ["sj.status='Completed'", "sj.job_type='Installation'", "not exists(select 1 from `tabService Billing Reference` r where r.service_job=sj.name and r.status='Submitted')"]
	values = {}
	for key, column in (("customer", "sj.customer"), ("service_zone", "sj.service_zone")):
		if filters.get(key): conditions.append(f"{column}=%({key})s"); values[key] = filters[key]
	_dates(filters, "date(sj.completion_datetime)", conditions, values)
	columns = ["Service Job:Link/Service Job:150", "Customer:Link/Customer:170", "Site:Link/Customer Site:150", "Equipment:Link/Customer Equipment:150", "Service Zone:Link/Service Zone:130", "Installation Charge:Currency:120", "Travel Charge:Currency:110", "Invoice:Link/Sales Invoice:140", "Billing Status:Data:125"]
	data = frappe.db.sql(f"""select sj.name,sj.customer,sj.customer_site,sj.customer_equipment,sj.service_zone,sum(case when c.charge_type='Installation' then c.billable_amount else 0 end),sum(case when c.charge_type='Travel' then c.billable_amount else 0 end),sj.sales_invoice,sj.billing_status from `tabService Job` sj left join `tabService Job Charge` c on c.parent=sj.name where {' and '.join(conditions)} group by sj.name order by sj.completion_datetime""", values)
	return columns, data


def subscription_reconciliation(filters):
	_require(FINANCE_ROLES | {"Service Contract Manager", "Rental Manager"})
	columns = ["Contract Type:Data:120", "Contract:Dynamic Link/contract_type:160", "Customer:Link/Customer:170", "Subscription:Link/Subscription:150", "Billing Frequency:Data:110", "Expected Amount:Currency:115", "Last Subscription Invoice:Link/Sales Invoice:150", "Expected Next Billing Date:Date:125", "Actual Invoice Amount:Currency:120", "Difference:Currency:105", "Status:Data:200"]
	service = frappe.db.sql("""
		select 'Service Contract',sc.name,sc.customer,sc.subscription,sc.billing_method,sc.billing_amount,
		max(si.name),sc.end_date,coalesce(substring_index(group_concat(si.base_net_total order by si.posting_date desc),',',1)+0,0),sc.billing_amount-coalesce(substring_index(group_concat(si.base_net_total order by si.posting_date desc),',',1)+0,0),
		case when sc.subscription is null and sc.auto_create_subscription=1 then 'Subscription Missing'
		when sc.subscription is not null and count(si.name)=0 then 'Invoice Missing'
		when sc.contract_status in ('Active','Expiring') and sub.status in ('Cancelled','Completed') then 'Subscription Cancelled but Contract Active'
		when sc.contract_status in ('Expired','Cancelled') and sub.status='Active' then 'Contract Expired but Subscription Active'
		when abs(sc.billing_amount-coalesce(substring_index(group_concat(si.base_net_total order by si.posting_date desc),',',1)+0,0))>0.01 then 'Amount Difference' else 'OK' end
		from `tabService Contract` sc left join `tabSubscription` sub on sub.name=sc.subscription left join `tabSales Invoice` si on si.docstatus=1 and (si.name=sc.sales_invoice or si.subscription=sc.subscription)
		group by sc.name
	""")
	rental = frappe.db.sql("""
		select 'Rental Contract',rc.name,rc.customer,rc.subscription,rc.billing_frequency,rc.base_rental_amount,
		max(si.name),rc.next_billing_date,coalesce(substring_index(group_concat(si.base_net_total order by si.posting_date desc),',',1)+0,0),rc.base_rental_amount-coalesce(substring_index(group_concat(si.base_net_total order by si.posting_date desc),',',1)+0,0),
		case when rc.use_erpnext_subscription=1 and rc.subscription is null then 'Subscription Missing'
		when rc.subscription is not null and count(si.name)=0 then 'Invoice Missing'
		when rc.status in ('Active','Expiring') and sub.status in ('Cancelled','Completed') then 'Subscription Cancelled but Contract Active'
		when rc.status in ('Expired','Completed','Terminated') and sub.status='Active' then 'Contract Expired but Subscription Active'
		when abs(rc.base_rental_amount-coalesce(substring_index(group_concat(si.base_net_total order by si.posting_date desc),',',1)+0,0))>0.01 then 'Amount Difference' else 'OK' end
		from `tabRental Contract` rc left join `tabSubscription` sub on sub.name=rc.subscription left join `tabSales Invoice` si on si.docstatus=1 and si.subscription=rc.subscription
		group by rc.name
	""")
	if filters.get("contract_type") == "Service Contract":
		return columns, service
	if filters.get("contract_type") == "Rental Contract":
		return columns, rental
	return columns, service + rental


def recurring_billing_control(filters):
	_require(FINANCE_ROLES | {"Service Billing User", "Rental Billing User"})
	columns = ["Contract Type:Data:120", "Contract:Dynamic Link/contract_type:160", "Customer:Link/Customer:170", "Contract Status:Data:120", "Billing Frequency:Data:115", "Expected Billing Date:Date:125", "Expected Base Amount:Currency:125", "Actual Invoice:Link/Sales Invoice:145", "Actual Amount:Currency:110", "Difference:Currency:105", "Billing Status:Data:110"]
	from_date = filters.get("from_date") or nowdate()
	to_date = filters.get("to_date") or nowdate()
	values = {"from_date": from_date, "to_date": to_date, "company": filters.get("company"), "customer": filters.get("customer")}
	service_company = "and sc.company=%(company)s" if filters.get("company") else ""
	rental_company = "and rc.company=%(company)s" if filters.get("company") else ""
	service_customer = "and sc.customer=%(customer)s" if filters.get("customer") else ""
	rental_customer = "and rc.customer=%(customer)s" if filters.get("customer") else ""
	service = frappe.db.sql(f"""select 'Service Contract',sc.name,sc.customer,sc.contract_status,sc.billing_method,sc.end_date,sc.billing_amount,si.name,coalesce(si.base_net_total,0),sc.billing_amount-coalesce(si.base_net_total,0),case when si.name is null then 'Missing' else 'Billed' end from `tabService Contract` sc left join `tabSales Invoice` si on si.docstatus=1 and (si.name=sc.sales_invoice or si.subscription=sc.subscription) and si.posting_date between %(from_date)s and %(to_date)s where sc.contract_status in ('Active','Expiring') and sc.end_date >= %(from_date)s {service_company} {service_customer}""", values)
	rental = frappe.db.sql(f"""select 'Rental Contract',rc.name,rc.customer,rc.status,rc.billing_frequency,rc.next_billing_date,rc.base_rental_amount,si.name,coalesce(si.base_net_total,0),rc.base_rental_amount-coalesce(si.base_net_total,0),case when si.name is null then 'Missing' else 'Billed' end from `tabRental Contract` rc left join `tabSales Invoice` si on si.docstatus=1 and si.custom_rental_contract=rc.name and si.posting_date between %(from_date)s and %(to_date)s where rc.status in ('Active','Expiring','Termination Requested') and rc.next_billing_date between %(from_date)s and %(to_date)s {rental_company} {rental_customer}""", values)
	if filters.get("contract_type") == "Service Contract":
		return columns, service
	if filters.get("contract_type") == "Rental Contract":
		return columns, rental
	return columns, service + rental


def sla_performance(filters):
	_require(SERVICE_FINANCE_ROLES)
	group_map = {"Customer": "st.customer", "Service Contract": "st.service_contract", "Technician": "st.assigned_technician", "Priority": "st.priority", "Service Zone": "cs.service_zone"}
	group_label = filters.get("group_by") or "Customer"
	group = group_map.get(group_label, "st.customer")
	conditions = ["1=1"]
	values = {}
	_dates(filters, "date(st.reported_datetime)", conditions, values)
	columns = [f"{group_label}:Data:180", "Tickets Created:Int:100", "First Response Met:Int:115", "First Response Breached:Int:135", "Resolution Met:Int:105", "Resolution Breached:Int:125", "Average Response Minutes:Float:140", "Average Resolution Minutes:Float:145", "Compliance %:Percent:105"]
	data = frappe.db.sql(f"""select {group},count(*),sum(st.response_sla_status='Met'),sum(st.response_sla_status='Breached'),sum(st.resolution_sla_status='Met'),sum(st.resolution_sla_status='Breached'),avg(timestampdiff(minute,st.reported_datetime,st.first_response_datetime)),avg(timestampdiff(minute,st.reported_datetime,st.resolution_datetime)),(sum(st.response_sla_status='Met')+sum(st.resolution_sla_status='Met'))/nullif(sum(st.response_sla_status in ('Met','Breached'))+sum(st.resolution_sla_status in ('Met','Breached')),0)*100 from `tabService Ticket` st left join `tabCustomer Site` cs on cs.name=st.customer_site where {' and '.join(conditions)} group by {group} order by {group}""", values)
	return columns, data


def technician_productivity(filters):
	_require(SERVICE_FINANCE_ROLES)
	conditions = ["sj.assigned_technician is not null"]
	values = {"repeat_days": cint(frappe.db.get_single_value("IT Service Settings", "repeat_service_window_days") or 7)}
	_dates(filters, "date(coalesce(sj.completion_datetime,sj.creation))", conditions, values)
	columns = ["Technician:Link/Employee:150", "Jobs Assigned:Int:95", "Jobs Completed:Int:100", "Completion %:Percent:100", "Labour Hours:Float:100", "Travel Hours:Float:95", "Average Job Duration:Float:125", "First-Time Fix Count:Int:115", "Repeat Visit Count:Int:105", "SLA Met:Int:80", "SLA Breached:Int:95", "Customer Rating:Float:105", "Internal Labour Cost:Currency:125", "Billable Revenue:Currency:115"]
	data = frappe.db.sql(f"""
		select sj.assigned_technician,count(*),sum(sj.status='Completed'),sum(sj.status='Completed')/count(*)*100,coalesce(sum(l.hours),0),sum(sj.travel_duration_minutes)/60,avg(sj.total_job_duration_minutes)/60,
		sum(sj.status='Completed' and not exists(select 1 from `tabService Job` r where r.customer_equipment=sj.customer_equipment and r.name!=sj.name and r.completion_datetime>sj.completion_datetime and r.completion_datetime<=date_add(sj.completion_datetime,interval %(repeat_days)s day))),
		sum(exists(select 1 from `tabService Job` r where r.customer_equipment=sj.customer_equipment and r.name!=sj.name and r.completion_datetime>sj.completion_datetime and r.completion_datetime<=date_add(sj.completion_datetime,interval %(repeat_days)s day))),
		sum(st.resolution_sla_status='Met'),sum(st.resolution_sla_status='Breached'),avg(sj.customer_rating),sum(sj.labour_cost),sum(sj.total_billable_amount)
		from `tabService Job` sj left join (select parent,sum(duration_hours) hours from `tabService Job Labour` group by parent) l on l.parent=sj.name left join `tabService Ticket` st on st.name=sj.service_ticket
		where {' and '.join(conditions)} group by sj.assigned_technician order by 3 desc
	""", values)
	return columns, data


def equipment_repeat_failure(filters):
	_require(SERVICE_FINANCE_ROLES | RENTAL_FINANCE_ROLES)
	conditions = ["sj.customer_equipment is not null"]
	values = {}
	_dates(filters, "date(sj.completion_datetime)", conditions, values)
	columns = ["Equipment:Link/Customer Equipment:170", "Customer:Link/Customer:170", "Site:Link/Customer Site:145", "Item:Link/Item:130", "Serial No:Link/Serial No:130", "Job Count:Int:85", "Repeat Failures:Int:100", "Parts Cost:Currency:100", "Labour Cost:Currency:105", "Downtime Hours:Float:105", "Current Contract:Data:145", "Recommended Flag:Data:120"]
	data = frappe.db.sql(f"""select ce.name,ce.customer,ce.customer_site,ce.item_code,ce.serial_no,count(*),greatest(count(*)-1,0),sum(sj.parts_cost),sum(sj.labour_cost),sum(sj.total_job_duration_minutes)/60,coalesce(ce.service_contract,ce.rental_contract),case when count(*)>=5 or sum(sj.total_internal_cost)>=5000 then 'Replace' when count(*)>=3 then 'Review Contract' else 'Monitor' end from `tabService Job` sj inner join `tabCustomer Equipment` ce on ce.name=sj.customer_equipment where {' and '.join(conditions)} group by ce.name having count(*)>1 order by count(*) desc,sum(sj.total_internal_cost) desc""", values)
	return columns, data


def high_maintenance_equipment(filters):
	_require(SERVICE_FINANCE_ROLES | RENTAL_FINANCE_ROLES)
	conditions = ["sj.customer_equipment is not null"]
	values = {}
	_dates(filters, "date(sj.completion_datetime)", conditions, values)
	columns = ["Equipment:Link/Customer Equipment:170", "Customer:Link/Customer:170", "Site:Link/Customer Site:145", "Item:Link/Item:130", "Serial No:Link/Serial No:130", "Job Count:Int:85", "Repeat Failures:Int:100", "Parts Cost:Currency:100", "Labour Cost:Currency:105", "Downtime Hours:Float:105", "Current Contract:Data:145", "Recommended Flag:Data:120"]
	data = frappe.db.sql(f"""select ce.name,ce.customer,ce.customer_site,ce.item_code,ce.serial_no,count(*),greatest(count(*)-1,0),sum(sj.parts_cost),sum(sj.labour_cost),sum(sj.total_job_duration_minutes)/60,coalesce(ce.service_contract,ce.rental_contract),case when sum(sj.total_internal_cost)>=5000 then 'Replace' when count(*)>=3 then 'Review Contract' else 'Monitor' end from `tabService Job` sj inner join `tabCustomer Equipment` ce on ce.name=sj.customer_equipment where {' and '.join(conditions)} group by ce.name order by sum(sj.total_internal_cost) desc,count(*) desc""", values)
	return columns, data


def warranty_service_cost(filters):
	_require(SERVICE_FINANCE_ROLES)
	conditions = ["sj.coverage_source='Warranty'"]
	values = {}
	_dates(filters, "date(sj.completion_datetime)", conditions, values)
	columns = ["Customer:Link/Customer:170", "Equipment:Link/Customer Equipment:165", "Serial No:Link/Serial No:135", "Warranty Policy:Link/Warranty Policy:145", "Jobs:Int:80", "Labour Cost:Currency:105", "Parts Cost:Currency:100", "Expense Cost:Currency:105", "Total Warranty Cost:Currency:130"]
	data = frappe.db.sql(f"""select sj.customer,sj.customer_equipment,ce.serial_no,ce.warranty_policy,count(*),sum(sj.labour_cost),sum(sj.parts_cost),sum(sj.expense_cost),sum(sj.total_internal_cost) from `tabService Job` sj left join `tabCustomer Equipment` ce on ce.name=sj.customer_equipment where {' and '.join(conditions)} group by sj.customer,sj.customer_equipment order by sum(sj.total_internal_cost) desc""", values)
	return columns, data


def amc_service_cost(filters):
	columns, rows = service_contract_profitability(filters)
	return [columns[0], columns[1], columns[3], columns[4], columns[5], columns[6], columns[7], columns[8], columns[9], columns[10]], [[row[0], row[1], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10]] for row in rows]


def service_coverage_analysis(filters):
	_require(SERVICE_FINANCE_ROLES)
	conditions = ["sj.status='Completed'"]
	values = {}
	_dates(filters, "date(sj.completion_datetime)", conditions, values)
	columns = ["Month:Data:90", "Customer:Link/Customer:170", "Service Type:Data:120", "Total Service Value:Currency:125", "Covered by Warranty:Currency:130", "Covered by AMC:Currency:115", "Covered by Rental:Currency:125", "Customer Billable:Currency:120", "Waived:Currency:100"]
	data = frappe.db.sql(f"""select date_format(sj.completion_datetime,'%%Y-%%m'),sj.customer,sj.job_type,sum(sj.total_charge_before_coverage),sum(case when sj.coverage_source='Warranty' then sj.total_covered_amount else 0 end),sum(case when sj.coverage_source in ('Service Contract','AMC') then sj.total_covered_amount else 0 end),sum(case when sj.coverage_source='Rental Contract' then sj.total_covered_amount else 0 end),sum(sj.total_billable_amount),coalesce(sum(adj.amount),0) from `tabService Job` sj left join (select service_job,sum(amount) amount from `tabService Billing Adjustment` where approval_status='Approved' and adjustment_type in ('Waiver','Discount') group by service_job) adj on adj.service_job=sj.name where {' and '.join(conditions)} group by 1,2,3 order by 1 desc,2,3""", values)
	return columns, data


def meter_billing_control(filters):
	_require(RENTAL_FINANCE_ROLES)
	conditions = ["ce.meter_based=1", "rc.status in ('Active','Expiring','Termination Requested')"]
	values = {"from_date": filters.get("from_date") or nowdate(), "to_date": filters.get("to_date") or nowdate()}
	if filters.get("company"): conditions.append("rc.company=%(company)s"); values["company"] = filters.company
	columns = ["Billing Period From:Date:115", "Billing Period To:Date:110", "Active Metered Equipment:Int:145", "Reading Expected:Int:105", "Reading Received:Int:105", "Reading Verified:Int:105", "Reading Billed:Int:95", "Reading Pending:Int:100", "Meter Revenue Expected:Currency:140", "Meter Revenue Billed:Currency:130", "Difference:Currency:105"]
	data = frappe.db.sql(f"""select %(from_date)s,%(to_date)s,count(distinct ce.name),count(distinct ce.name),count(distinct mr.name),count(distinct case when mr.verified=1 then mr.name end),count(distinct case when rbr.status='Submitted' then mr.name end),count(distinct ce.name)-count(distinct mr.name),coalesce(sum(distinct mr.total_meter_charge),0),coalesce(sum(case when rbr.status='Submitted' then rbr.amount else 0 end),0),coalesce(sum(distinct mr.total_meter_charge),0)-coalesce(sum(case when rbr.status='Submitted' then rbr.amount else 0 end),0) from `tabCustomer Equipment` ce inner join `tabRental Contract` rc on rc.name=ce.rental_contract left join `tabEquipment Meter Reading` mr on mr.customer_equipment=ce.name and mr.reading_date between %(from_date)s and %(to_date)s left join `tabRental Billing Reference` rbr on rbr.source_document_type='Equipment Meter Reading' and rbr.source_document=mr.name where {' and '.join(conditions)}""", values)
	return columns, data


def operational_customer_profitability(filters):
	_require(FINANCE_ROLES | {"Service Manager", "Rental Manager"})
	conditions = ["c.disabled=0"]
	values = {}
	if filters.get("customer"): conditions.append("c.name=%(customer)s"); values["customer"] = filters.customer
	columns = ["Customer:Link/Customer:180", "Retail Revenue:Currency:105", "Contract Revenue:Currency:115", "Service Revenue:Currency:110", "Rental Revenue:Currency:110", "Meter Revenue:Currency:105", "Total Relevant Revenue:Currency:140", "Service Cost:Currency:105", "Parts Cost:Currency:100", "Expense Cost:Currency:105", "Rental Direct Cost:Currency:120", "Total Direct Cost:Currency:115", "Contribution:Currency:110", "Contribution %:Percent:105", "Open Tickets:Int:90", "Active Contracts:Int:100", "Rental Equipment Count:Int:125", "Outstanding Receivable:Currency:130"]
	data = frappe.db.sql(f"""
		select c.name,coalesce(inv.retail,0),coalesce(inv.contract_revenue,0),coalesce(inv.service_revenue,0),coalesce(inv.rental_revenue,0),coalesce(inv.meter_revenue,0),coalesce(inv.total_revenue,0),coalesce(cost.labour_cost,0),coalesce(cost.parts_cost,0),coalesce(cost.expense_cost,0),coalesce(cost.rental_cost,0),coalesce(cost.total_cost,0),coalesce(inv.total_revenue,0)-coalesce(cost.total_cost,0),(coalesce(inv.total_revenue,0)-coalesce(cost.total_cost,0))/nullif(inv.total_revenue,0)*100,coalesce(t.open_tickets,0),coalesce(con.active_contracts,0),coalesce(eq.equipment_count,0),coalesce(inv.outstanding,0)
		from `tabCustomer` c
		left join (select customer,sum(case when custom_service_job is null and custom_rental_contract is null then base_net_total else 0 end) retail,sum(case when subscription is not null then base_net_total else 0 end) contract_revenue,sum(case when custom_service_billing_batch is not null then base_net_total else 0 end) service_revenue,sum(case when custom_rental_contract is not null then base_net_total else 0 end) rental_revenue,0 meter_revenue,sum(base_net_total) total_revenue,sum(outstanding_amount) outstanding from `tabSales Invoice` where docstatus=1 group by customer) inv on inv.customer=c.name
		left join (select customer,sum(labour_cost) labour_cost,sum(parts_cost) parts_cost,sum(expense_cost) expense_cost,sum(case when rental_contract is not null then total_internal_cost else 0 end) rental_cost,sum(total_internal_cost) total_cost from `tabService Job` where status='Completed' group by customer) cost on cost.customer=c.name
		left join (select customer,count(*) open_tickets from `tabService Ticket` where status not in ('Resolved','Closed','Cancelled') group by customer) t on t.customer=c.name
		left join (select customer,count(*) active_contracts from (select customer from `tabService Contract` where contract_status in ('Active','Expiring') union all select customer from `tabRental Contract` where status in ('Active','Expiring')) x group by customer) con on con.customer=c.name
		left join (select customer,count(*) equipment_count from `tabCustomer Equipment` where ownership_type='Company Rental Asset' group by customer) eq on eq.customer=c.name
		where {' and '.join(conditions)} order by coalesce(inv.total_revenue,0) desc
	""", values)
	return columns, data


def customer_equipment_financial_summary(filters):
	_require(FINANCE_ROLES | {"Service Manager", "Rental Manager"})
	conditions = ["1=1"]
	values = {}
	for key, column in (("customer", "ce.customer"), ("customer_equipment", "ce.name")):
		if filters.get(key): conditions.append(f"{column}=%({key})s"); values[key] = filters[key]
	columns = ["Equipment:Link/Customer Equipment:170", "Customer:Link/Customer:170", "Original Sale Value:Currency:115", "Rental Revenue:Currency:110", "Service Revenue:Currency:110", "Parts Revenue:Currency:105", "Meter Revenue:Currency:105", "Service Cost:Currency:100", "Parts Cost:Currency:100", "Expense Cost:Currency:100", "Total Revenue:Currency:110", "Total Direct Cost:Currency:115", "Contribution:Currency:110", "Last Invoice:Link/Sales Invoice:145", "Customer Outstanding AR:Currency:135"]
	data = frappe.db.sql(f"""select ce.name,ce.customer,coalesce(sale.base_net_total,0),coalesce(rev.rental,0),coalesce(rev.service,0),coalesce(rev.parts,0),coalesce(rev.meter,0),coalesce(cost.labour_cost,0),coalesce(cost.parts_cost,0),coalesce(cost.expense_cost,0),coalesce(sale.base_net_total,0)+coalesce(rev.total_revenue,0),coalesce(cost.total_cost,0),coalesce(sale.base_net_total,0)+coalesce(rev.total_revenue,0)-coalesce(cost.total_cost,0),rev.last_invoice,coalesce(ar.outstanding,0) from `tabCustomer Equipment` ce left join `tabSales Invoice` sale on sale.name=ce.sales_invoice and sale.docstatus=1 left join (select sj.customer_equipment,sum(case when r.status='Submitted' then r.amount else 0 end) service,0 parts,0 rental,0 meter,sum(case when r.status='Submitted' then r.amount else 0 end) total_revenue,max(r.invoice) last_invoice from `tabService Job` sj left join `tabService Billing Reference` r on r.service_job=sj.name group by sj.customer_equipment) rev on rev.customer_equipment=ce.name left join (select customer_equipment,sum(labour_cost) labour_cost,sum(parts_cost) parts_cost,sum(expense_cost) expense_cost,sum(total_internal_cost) total_cost from `tabService Job` group by customer_equipment) cost on cost.customer_equipment=ce.name left join (select customer,sum(outstanding_amount) outstanding from `tabSales Invoice` where docstatus=1 group by customer) ar on ar.customer=ce.customer where {' and '.join(conditions)} order by ce.customer,ce.name""", values)
	return columns, data


def service_period_end(filters):
	_require(SERVICE_FINANCE_ROLES)
	values = {"from_date": filters.get("from_date") or nowdate(), "to_date": filters.get("to_date") or nowdate()}
	columns = ["Completed Jobs:Int:100", "Not Billing Calculated:Int:130", "Ready for Billing:Int:110", "Jobs Invoiced:Int:95", "Unbilled Amount:Currency:115", "Approved Expenses Not Recharged:Currency:170", "Stock Consumption Missing:Int:150", "Missing Signatures:Int:115", "SLA Breaches:Int:95", "Expiring Contracts:Int:110"]
	data = frappe.db.sql("""select count(*),sum(sj.billing_status='Not Calculated'),sum(sj.billing_status='Ready for Billing'),sum(sj.billing_status='Invoiced'),sum(case when sj.billing_status!='Invoiced' then sj.total_billable_amount else 0 end),(select coalesce(sum(customer_billable_amount),0) from `tabService Expense` where approval_status='Approved' and billable_to_customer=1 and sales_invoice is null and expense_date between %(from_date)s and %(to_date)s),sum(exists(select 1 from `tabService Job Part` p where p.parent=sj.name and p.stock_entry is null)),sum(sj.customer_signature is null or sj.customer_signature=''),(select count(*) from `tabService Ticket` where (response_sla_status='Breached' or resolution_sla_status='Breached') and date(reported_datetime) between %(from_date)s and %(to_date)s),(select count(*) from `tabService Contract` where contract_status in ('Active','Expiring') and end_date between %(to_date)s and date_add(%(to_date)s,interval 90 day)) from `tabService Job` sj where sj.status='Completed' and date(sj.completion_datetime) between %(from_date)s and %(to_date)s""", values)
	return columns, data


def rental_period_end(filters):
	_require(RENTAL_FINANCE_ROLES)
	values = {"from_date": filters.get("from_date") or nowdate(), "to_date": filters.get("to_date") or nowdate()}
	columns = ["Active Contracts:Int:100", "Contracts Due for Billing:Int:130", "Billing Runs Prepared:Int:120", "Invoices Created:Int:100", "Missing Meter Readings:Int:130", "Unverified Meter Readings:Int:140", "Approved Ad-Hoc Unbilled:Int:145", "Service Charges Unbilled:Int:135", "Contracts Expiring:Int:110", "Equipment Due for Return:Int:140", "Equipment Under Repair:Int:125", "Rental Revenue Variance:Currency:135"]
	data = frappe.db.sql("""select (select count(*) from `tabRental Contract` where status in ('Active','Expiring')),(select count(*) from `tabRental Contract` where status in ('Active','Expiring') and next_billing_date<=%(to_date)s),(select count(*) from `tabRental Billing Run` where status in ('Prepared','Under Review','Approved for Billing') and billing_period_to between %(from_date)s and %(to_date)s),(select count(*) from `tabSales Invoice` where docstatus<2 and custom_rental_billing_run is not null and posting_date between %(from_date)s and %(to_date)s),(select count(*) from `tabCustomer Equipment` ce where ce.meter_based=1 and ce.rental_contract is not null and not exists(select 1 from `tabEquipment Meter Reading` mr where mr.customer_equipment=ce.name and mr.reading_date between %(from_date)s and %(to_date)s)),(select count(*) from `tabEquipment Meter Reading` where verified=0 and reading_date between %(from_date)s and %(to_date)s),(select count(*) from `tabRental Ad-Hoc Charge` where status='Approved' and billable=1),(select count(*) from `tabService Job Charge` where billable=1 and rental_billed=0),(select count(*) from `tabRental Contract` where status in ('Active','Expiring') and end_date between %(to_date)s and date_add(%(to_date)s,interval 90 day)),(select count(*) from `tabRental Contract Equipment` where billing_end_date between %(from_date)s and %(to_date)s),(select count(*) from `tabCustomer Equipment` where ownership_type='Company Rental Asset' and equipment_status='Under Repair'),0""", values)
	return columns, data


def data_quality(filters):
	_require(SERVICE_FINANCE_ROLES | RENTAL_FINANCE_ROLES)
	columns = ["Issue Type:Data:220", "Document Type:Data:170", "Document:Dynamic Link/document_type:170", "Customer:Link/Customer:170", "Severity:Data:90", "Recommended Action:Data:260"]
	data = frappe.db.sql("""
		select 'Equipment missing serial number','Customer Equipment',name,customer,'High','Record the equipment serial number' from `tabCustomer Equipment` where (serial_no is null or serial_no='') and ownership_type in ('Company Rental Asset','Customer Owned')
		union all select 'Equipment missing customer site','Customer Equipment',name,customer,'Medium','Assign the equipment to a customer site' from `tabCustomer Equipment` where customer_site is null
		union all select 'Rental equipment missing asset','Rental Contract',parent,null,'High','Link an ERPNext Asset to the rental equipment row' from `tabRental Contract Equipment` where asset is null
		union all select 'Active service contract has invalid dates','Service Contract',name,customer,'Critical','Correct contract start and end dates' from `tabService Contract` where contract_status in ('Active','Expiring') and end_date<start_date
		union all select 'Active rental contract has invalid dates','Rental Contract',name,customer,'Critical','Correct contract start and end dates' from `tabRental Contract` where status in ('Active','Expiring') and end_date<start_date
		union all select 'Metered rental equipment missing meter configuration','Customer Equipment',ce.name,ce.customer,'High','Configure meter allowances and rates on the rental contract' from `tabCustomer Equipment` ce inner join `tabRental Contract` rc on rc.name=ce.rental_contract where ce.meter_based=1 and rc.meter_billing_enabled=0
		union all select 'Completed job has invalid billing status','Service Job',name,customer,'High','Calculate billing or mark the job not applicable' from `tabService Job` where status='Completed' and (billing_status is null or billing_status in ('','Not Calculated'))
		union all select 'Customer site missing service zone','Customer Site',name,customer,'Medium','Assign a service zone' from `tabCustomer Site` where service_zone is null
		union all select 'Service technician missing warehouse','Employee',name,null,'Medium','Assign a technician service warehouse' from `tabEmployee` where is_service_technician=1 and service_warehouse is null
		order by 5 desc,1,3
	""")
	return columns, data


REPORTS = {
	"Subscription Billing Reconciliation": subscription_reconciliation,
	"Recurring Billing Control": recurring_billing_control,
	"Unbilled Service Revenue": unbilled_service,
	"Unbilled Rental Revenue": unbilled_rental,
	"Service and Rental Revenue Leakage": revenue_leakage,
	"Customer Equipment Financial Summary": customer_equipment_financial_summary,
	"Service Job Profitability": service_job_profitability,
	"Service Contract Profitability": service_contract_profitability,
	"Service Contract Utilisation": contract_utilisation,
	"Contract Over-Service Analysis": contract_over_service,
	"Operational Customer Profitability": operational_customer_profitability,
	"Contract Renewal Pipeline": renewal_pipeline,
	"Contract Renewal Forecast": renewal_forecast,
	"SLA Performance Analysis": sla_performance,
	"Technician Productivity": technician_productivity,
	"Equipment Repeat Failure Analysis": equipment_repeat_failure,
	"High Maintenance Equipment": high_maintenance_equipment,
	"Warranty Service Cost": warranty_service_cost,
	"AMC Service Cost": amc_service_cost,
	"Service Coverage Analysis": service_coverage_analysis,
	"Service Expense Recovery": service_expense_recovery,
	"Installation Billing Control": installation_billing_control,
	"Meter Billing Control": meter_billing_control,
	"Service Period End Control": service_period_end,
	"Rental Period End Control": rental_period_end,
	"IT Service Data Quality": data_quality,
}
