import frappe


def execute(filters=None):
	filters = filters or {}; conditions=["1=1"]; values={}
	for key,column in (("customer","emr.customer"),("rental_contract","emr.rental_contract"),("customer_equipment","emr.customer_equipment")):
		if filters.get(key): conditions.append(f"{column} = %({key})s"); values[key]=filters[key]
	if filters.get("from_date"): conditions.append("emr.billing_period_from >= %(from_date)s"); values["from_date"]=filters["from_date"]
	if filters.get("to_date"): conditions.append("emr.billing_period_to <= %(to_date)s"); values["to_date"]=filters["to_date"]
	columns=["Billing Period:Data:170","Customer:Link/Customer:170","Contract:Link/Rental Contract:150","Equipment:Link/Customer Equipment:160","Previous B&W:Float:110","Current B&W:Float:110","B&W Usage:Float:100","B&W Billable:Float:110","B&W Revenue:Currency:110","Previous Colour:Float:110","Current Colour:Float:110","Colour Usage:Float:100","Colour Billable:Float:110","Colour Revenue:Currency:120"]
	data=frappe.db.sql(f"""select concat(emr.billing_period_from,' to ',emr.billing_period_to),emr.customer,emr.rental_contract,emr.customer_equipment,
	 max(case when upper(d.meter_type) in ('BW','B&W','BLACK AND WHITE') then d.previous_reading end),max(case when upper(d.meter_type) in ('BW','B&W','BLACK AND WHITE') then d.current_reading end),max(case when upper(d.meter_type) in ('BW','B&W','BLACK AND WHITE') then d.usage end),max(case when upper(d.meter_type) in ('BW','B&W','BLACK AND WHITE') then d.billable_quantity end),max(case when upper(d.meter_type) in ('BW','B&W','BLACK AND WHITE') then d.calculated_amount end),
	 max(case when upper(d.meter_type) in ('COLOUR','COLOR') then d.previous_reading end),max(case when upper(d.meter_type) in ('COLOUR','COLOR') then d.current_reading end),max(case when upper(d.meter_type) in ('COLOUR','COLOR') then d.usage end),max(case when upper(d.meter_type) in ('COLOUR','COLOR') then d.billable_quantity end),max(case when upper(d.meter_type) in ('COLOUR','COLOR') then d.calculated_amount end)
	 from `tabEquipment Meter Reading` emr inner join `tabEquipment Meter Reading Detail` d on d.parent=emr.name where {' and '.join(conditions)} group by emr.name order by emr.billing_period_from desc,emr.customer""",values)
	return columns,data
