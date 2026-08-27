import frappe
from frappe.utils import get_first_day, get_last_day, getdate, nowdate


def execute(filters=None):
	today = getdate(nowdate()); period_from = get_first_day(today); period_to = get_last_day(today)
	columns = ["Rental Contract:Link/Rental Contract:150", "Customer:Link/Customer:180", "Site:Link/Customer Site:150", "Equipment:Link/Customer Equipment:160", "Serial No:Link/Serial No:140", "Last Reading Date:Date:110", "Last Meter:Float:100", "Current Billing Period:Data:150", "Reading Due Date:Date:110", "Days Overdue:Int:100"]
	due_day = min(max(int(frappe.db.get_single_value("IT Service Settings", "default_meter_reading_due_day") or 25), 1), 28)
	data = frappe.db.sql("""
	 select rc.name, rc.customer, rc.customer_site, rce.customer_equipment, rce.serial_no, ce.latest_meter_date,
	 greatest(ifnull(ce.latest_bw_meter,0),ifnull(ce.latest_colour_meter,0)), %(period)s,
	 date_add(%(period_from)s, interval %(due_offset)s day), greatest(datediff(curdate(), date_add(%(period_from)s, interval %(due_offset)s day)),0)
	 from `tabRental Contract` rc inner join `tabRental Contract Equipment` rce on rce.parent=rc.name
	 left join `tabCustomer Equipment` ce on ce.name=rce.customer_equipment
	 where rc.status in ('Active','Expiring') and rc.meter_billing_enabled=1 and rce.deployment_status='Deployed' and rce.meter_billing_enabled=1
	 and not exists (select 1 from `tabEquipment Meter Reading` emr where emr.customer_equipment=rce.customer_equipment and emr.billing_period_from=%(period_from)s and emr.billing_period_to=%(period_to)s)
	 order by rc.customer, rce.customer_equipment
	""", {"period": f"{period_from} to {period_to}", "period_from": period_from, "period_to": period_to, "due_offset": due_day - 1})
	return columns, data
