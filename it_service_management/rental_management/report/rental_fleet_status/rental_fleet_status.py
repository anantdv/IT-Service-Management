import frappe


def execute(filters=None):
	filters = filters or {}; conditions = ["1=1"]; values = {}
	for key, column in (("company", "rc.company"), ("customer", "rc.customer"), ("rental_contract", "rc.name"), ("customer_site", "rc.customer_site"), ("status", "rce.deployment_status")):
		if filters.get(key): conditions.append(f"{column} = %({key})s"); values[key] = filters[key]
	columns = ["Asset:Link/Asset:150", "Serial No:Link/Serial No:140", "Item:Link/Item:140", "Current Status:Data:130", "Customer:Link/Customer:180", "Site:Link/Customer Site:150", "Rental Contract:Link/Rental Contract:150", "Deployment Date:Date:110", "Last Service Date:Date:110", "Last Meter Date:Date:110", "Current B&W Meter:Float:120", "Current Colour Meter:Float:130"]
	data = frappe.db.sql(f"""
	 select rce.asset, rce.serial_no, rce.item_code, rce.deployment_status, rc.customer, rc.customer_site, rc.name,
	 rce.deployment_date, ce.last_service_date, ce.latest_meter_date, ce.latest_bw_meter, ce.latest_colour_meter
	 from `tabRental Contract Equipment` rce inner join `tabRental Contract` rc on rc.name=rce.parent
	 left join `tabCustomer Equipment` ce on ce.name=rce.customer_equipment where {' and '.join(conditions)} order by rce.deployment_status, rc.customer
	""", values)
	return columns, data
