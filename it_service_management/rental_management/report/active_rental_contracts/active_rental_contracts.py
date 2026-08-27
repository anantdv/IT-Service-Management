import frappe


def execute(filters=None):
	filters = filters or {}
	conditions = ["rc.status in ('Active','Expiring','Suspended','Termination Requested')"]
	values = {}
	for key, column in (("company", "rc.company"), ("customer", "rc.customer"), ("rental_contract", "rc.name"), ("customer_site", "rc.customer_site")):
		if filters.get(key):
			conditions.append(f"{column} = %({key})s")
			values[key] = filters[key]
	columns = ["Rental Contract:Link/Rental Contract:160", "Customer:Link/Customer:180", "Site:Link/Customer Site:160", "Start Date:Date:100", "End Date:Date:100", "Contract Term:Int:100", "Equipment Count:Int:110", "Monthly Rental:Currency:130", "Meter Billing:Check:100", "Next Billing Date:Date:120", "Contract Status:Data:130", "Days to Expiry:Int:110"]
	data = frappe.db.sql(f"""
		select rc.name, rc.customer, rc.customer_site, rc.start_date, rc.end_date, rc.contract_term_months,
		       count(rce.name), rc.monthly_recurring_revenue, rc.meter_billing_enabled, rc.next_billing_date,
		       rc.status, datediff(rc.end_date, curdate())
		from `tabRental Contract` rc left join `tabRental Contract Equipment` rce on rce.parent = rc.name
		where {' and '.join(conditions)} group by rc.name order by rc.end_date, rc.customer
	""", values)
	return columns, data
