import frappe


def execute(filters=None):
	filters = filters or {}
	conditions = ["rbr.status = 'Submitted'", "si.docstatus = 1"]
	values = {}
	for key, column in (("company", "si.company"), ("customer", "rc.customer"), ("rental_contract", "rc.name"), ("customer_site", "rc.customer_site")):
		if filters.get(key): conditions.append(f"{column} = %({key})s"); values[key] = filters[key]
	if filters.get("from_date"): conditions.append("si.posting_date >= %(from_date)s"); values["from_date"] = filters["from_date"]
	if filters.get("to_date"): conditions.append("si.posting_date <= %(to_date)s"); values["to_date"] = filters["to_date"]
	columns = ["Rental Contract:Link/Rental Contract:160", "Customer:Link/Customer:180", "Base Rental:Currency:120", "Meter Revenue:Currency:120", "Ad-Hoc Revenue:Currency:120", "Service Revenue:Currency:120", "Total Revenue:Currency:130"]
	data = frappe.db.sql(f"""
		select rc.name, rc.customer,
		 sum(case when rbr.component_type like 'Base Rental%%' then rbr.amount else 0 end),
		 sum(case when rbr.component_type in ('B&W Usage','Colour Usage','Meter Usage') then rbr.amount else 0 end),
		 sum(case when rbr.source_document_type = 'Rental Ad-Hoc Charge' then rbr.amount else 0 end),
		 sum(case when rbr.source_document_type = 'Service Job' then rbr.amount else 0 end), sum(rbr.amount)
		from `tabRental Billing Reference` rbr inner join `tabRental Contract` rc on rc.name = rbr.rental_contract
		inner join `tabSales Invoice` si on si.name = rbr.invoice where {' and '.join(conditions)} group by rc.name order by rc.customer, rc.name
	""", values)
	return columns, data
