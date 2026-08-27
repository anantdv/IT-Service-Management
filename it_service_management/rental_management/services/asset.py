from __future__ import annotations

import frappe
from frappe.utils import add_months, get_first_day, get_last_day


ACTIVE_CONTRACT_STATUSES = ("Approved", "Active", "Suspended", "Expiring", "Termination Requested")
DEPLOYED_STATUSES = ("Deployed", "Temporarily Replaced", "Under Repair")


class RentalAssetService:
	@staticmethod
	def validate_asset_for_rental(asset, customer=None, company=None, rental_contract=None):
		if not asset or not frappe.db.exists("Asset", asset):
			frappe.throw("A valid ERPNext Asset is required for rental deployment.")

		asset_doc = frappe.get_cached_doc("Asset", asset)
		if company and asset_doc.company != company:
			frappe.throw(f"Asset {asset} belongs to {asset_doc.company}, not {company}.")
		if asset_doc.docstatus == 2 or asset_doc.get("status") in ("Disposed", "Scrapped") or asset_doc.get("disposal_date"):
			frappe.throw(f"Asset {asset} is disposed or cancelled and cannot be rented.")

		serial_no = asset_doc.get("serial_no")
		if serial_no and not frappe.db.exists("Serial No", serial_no):
			frappe.throw(f"Serial No {serial_no} linked to Asset {asset} does not exist.")

		conditions = ["rce.asset = %(asset)s", "rc.status in %(statuses)s", "rce.deployment_status in %(deployment_statuses)s"]
		values = {"asset": asset, "statuses": ACTIVE_CONTRACT_STATUSES, "deployment_statuses": DEPLOYED_STATUSES}
		if rental_contract:
			conditions.append("rc.name != %(rental_contract)s")
			values["rental_contract"] = rental_contract
		assigned = frappe.db.sql(
			f"""
			select rc.name rental_contract, rc.customer, rce.customer_equipment, rce.deployment_status
			from `tabRental Contract Equipment` rce
			inner join `tabRental Contract` rc on rc.name = rce.parent
			where {' and '.join(conditions)}
			limit 1
			""",
			values,
			as_dict=True,
		)
		if assigned:
			frappe.throw(f"Asset {asset} is already deployed under Rental Contract {assigned[0].rental_contract}.")

		equipment = frappe.db.get_value(
			"Customer Equipment", {"asset": asset}, ["name", "customer", "equipment_status", "rental_contract"], as_dict=True
		)
		if equipment and equipment.equipment_status in ("Deployed", "Operational", "Temporary Replacement"):
			if equipment.rental_contract and equipment.rental_contract != rental_contract:
				frappe.throw(f"Asset {asset} is already deployed as Customer Equipment {equipment.name}.")

		return {
			"available": True,
			"asset": asset,
			"company": asset_doc.company,
			"item_code": asset_doc.item_code,
			"serial_no": serial_no,
			"customer_equipment": equipment.name if equipment else None,
			"customer": customer,
		}

	@staticmethod
	def deploy_item(deployment, row):
		availability = RentalAssetService.validate_asset_for_rental(
			row.asset,
			customer=deployment.customer,
			company=frappe.db.get_value("Rental Contract", deployment.rental_contract, "company"),
			rental_contract=deployment.rental_contract,
		)
		asset_doc = frappe.get_cached_doc("Asset", row.asset)
		equipment_name = row.customer_equipment or availability.get("customer_equipment")
		if equipment_name:
			equipment = frappe.get_doc("Customer Equipment", equipment_name)
			equipment.customer = deployment.customer
			equipment.customer_site = deployment.customer_site
			equipment.item_code = row.item_code or asset_doc.item_code
			equipment.serial_no = row.serial_no or asset_doc.get("serial_no")
			equipment.asset = row.asset
			equipment.ownership_type = "Company Rental Asset"
			equipment.rental_contract = deployment.rental_contract
			equipment.rental_deployment = deployment.name
			equipment.rental_deployment_date = deployment.deployment_date
			equipment.rental_return_date = None
			equipment.installation_date = deployment.deployment_date
			equipment.installation_status = "Installed" if deployment.installation_required else "Not Required"
			equipment.equipment_status = "Deployed"
			equipment.meter_based = bool(row.initial_bw_meter or row.initial_colour_meter)
			equipment.latest_bw_meter = row.initial_bw_meter
			equipment.latest_colour_meter = row.initial_colour_meter
			equipment.latest_meter_date = deployment.deployment_date
			equipment.save(ignore_permissions=True)
		else:
			equipment = frappe.get_doc(
				{
					"doctype": "Customer Equipment",
					"customer": deployment.customer,
					"customer_site": deployment.customer_site,
					"item_code": row.item_code or asset_doc.item_code,
					"serial_no": row.serial_no or asset_doc.get("serial_no"),
					"asset": row.asset,
					"ownership_type": "Company Rental Asset",
					"rental_contract": deployment.rental_contract,
					"rental_deployment": deployment.name,
					"rental_deployment_date": deployment.deployment_date,
					"installation_date": deployment.deployment_date,
					"installation_status": "Installed" if deployment.installation_required else "Not Required",
					"equipment_status": "Deployed",
					"meter_based": bool(row.initial_bw_meter or row.initial_colour_meter),
					"latest_bw_meter": row.initial_bw_meter,
					"latest_colour_meter": row.initial_colour_meter,
					"latest_meter_date": deployment.deployment_date,
				}
			).insert(ignore_permissions=True)

		row.customer_equipment = equipment.name
		RentalAssetService._update_contract_equipment(deployment, row, equipment.name)
		RentalAssetService._ensure_preventive_maintenance(deployment, equipment.name)
		RentalAssetService.record_lifecycle_meter(
			equipment.name,
			deployment.rental_contract,
			deployment.deployment_date,
			row.initial_bw_meter,
			row.initial_colour_meter,
			"Initial meter recorded at deployment",
			initial=True,
		)
		equipment.add_comment("Comment", f"Deployed under {deployment.name} for Rental Contract {deployment.rental_contract}")
		return equipment.name

	@staticmethod
	def return_item(return_doc, row):
		equipment = frappe.get_doc("Customer Equipment", row.customer_equipment)
		if equipment.rental_contract != return_doc.rental_contract:
			frappe.throw(f"Customer Equipment {equipment.name} does not belong to {return_doc.rental_contract}.")
		equipment.equipment_status = "Returned"
		equipment.rental_return_date = return_doc.return_date
		equipment.latest_bw_meter = row.final_bw_meter or equipment.latest_bw_meter
		equipment.latest_colour_meter = row.final_colour_meter or equipment.latest_colour_meter
		equipment.latest_meter_date = return_doc.return_date
		equipment.save(ignore_permissions=True)
		frappe.db.set_value(
			"Rental Contract Equipment",
			{"parent": return_doc.rental_contract, "customer_equipment": equipment.name},
			{"deployment_status": "Returned", "actual_return_date": return_doc.return_date, "billing_end_date": return_doc.return_date},
			update_modified=False,
		)
		equipment.add_comment("Comment", f"Returned through {return_doc.name}")
		RentalAssetService.record_lifecycle_meter(
			equipment.name,
			return_doc.rental_contract,
			return_doc.return_date,
			row.final_bw_meter,
			row.final_colour_meter,
			f"Final meter recorded at return {return_doc.name}",
		)
		for plan in frappe.get_all("Preventive Maintenance Plan", filters={"customer_equipment": equipment.name, "rental_contract": return_doc.rental_contract, "active": 1}, pluck="name"):
			frappe.db.set_value("Preventive Maintenance Plan", plan, "active", 0, update_modified=False)

	@staticmethod
	def _update_contract_equipment(deployment, row, equipment_name):
		contract = frappe.get_doc("Rental Contract", deployment.rental_contract)
		contract_row = next((item for item in contract.equipment if item.asset == row.asset), None)
		if not contract_row:
			frappe.throw(f"Asset {row.asset} is not reserved on Rental Contract {contract.name}.")
		contract_row.customer_equipment = equipment_name
		contract_row.item_code = row.item_code or contract_row.item_code
		contract_row.serial_no = row.serial_no or contract_row.serial_no
		contract_row.deployment_status = "Deployed"
		contract_row.deployment_date = deployment.deployment_date
		contract_row.billing_start_date = contract.get_equipment_billing_start(deployment.deployment_date)
		contract.save(ignore_permissions=True)

	@staticmethod
	def _ensure_preventive_maintenance(deployment, equipment_name):
		contract = frappe.get_doc("Rental Contract", deployment.rental_contract)
		plan = frappe.get_cached_doc("Rental Plan", contract.rental_plan)
		if not plan.preventive_maintenance_included or not plan.preventive_maintenance_frequency:
			return
		existing = frappe.db.exists("Preventive Maintenance Plan", {"customer_equipment": equipment_name, "rental_contract": contract.name})
		if existing:
			frappe.db.set_value("Preventive Maintenance Plan", existing, {"active": 1, "frequency": plan.preventive_maintenance_frequency}, update_modified=False)
			return
		interval = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}.get(plan.preventive_maintenance_frequency, 3)
		pm = frappe.get_doc({"doctype": "Preventive Maintenance Plan", "customer": contract.customer, "customer_site": contract.customer_site, "customer_equipment": equipment_name, "rental_contract": contract.name, "frequency": plan.preventive_maintenance_frequency, "next_service_date": add_months(deployment.deployment_date, interval), "assigned_service_team": contract.assigned_service_team, "active": 1}).insert(ignore_permissions=True)
		if not contract.preventive_maintenance_plan:
			contract.db_set("preventive_maintenance_plan", pm.name)

	@staticmethod
	def record_lifecycle_meter(equipment_name, rental_contract, reading_date, bw=None, colour=None, remarks=None, initial=False):
		details = []
		if bw is not None:
			details.append({"meter_type": "BW", "current_reading": bw})
		if colour is not None:
			details.append({"meter_type": "COLOUR", "current_reading": colour})
		if not details:
			return None
		period_from = reading_date if initial else get_first_day(reading_date)
		period_to = reading_date if initial else get_last_day(reading_date)
		existing = frappe.db.exists("Equipment Meter Reading", {"customer_equipment": equipment_name, "billing_period_from": period_from, "billing_period_to": period_to})
		if existing:
			billed = frappe.db.exists("Rental Billing Reference", {"source_document_type": "Equipment Meter Reading", "source_document": existing, "status": ["in", ["Reserved", "Draft Invoiced", "Submitted"]]})
			if not billed:
				reading = frappe.get_doc("Equipment Meter Reading", existing)
				for values in details:
					row = next((item for item in reading.details if item.meter_type == values["meter_type"]), None)
					if row:
						row.current_reading = values["current_reading"]
					else:
						reading.append("details", values)
				reading.reading_date = reading_date
				reading.remarks = "\n".join(filter(None, [reading.remarks, remarks]))
				reading.flags.rental_lifecycle = True
				reading.save(ignore_permissions=True)
				return existing
			period_from = period_to = reading_date
			if frappe.db.exists("Equipment Meter Reading", {"customer_equipment": equipment_name, "billing_period_from": period_from, "billing_period_to": period_to}):
				return existing
		reading = frappe.get_doc({"doctype": "Equipment Meter Reading", "customer_equipment": equipment_name, "rental_contract": rental_contract, "reading_date": reading_date, "billing_period_from": period_from, "billing_period_to": period_to, "submission_source": "Technician", "verified": 1, "remarks": remarks, "details": details})
		reading.flags.rental_lifecycle = True
		reading.insert(ignore_permissions=True)
		return reading.name

	@staticmethod
	def create_stock_transfer(item_code, serial_no, source_warehouse, target_warehouse, company):
		if not source_warehouse or not target_warehouse or source_warehouse == target_warehouse:
			return None
		entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Transfer",
				"company": company,
				"items": [{"item_code": item_code, "qty": 1, "s_warehouse": source_warehouse, "t_warehouse": target_warehouse, "serial_no": serial_no}],
			}
		)
		entry.insert(ignore_permissions=True)
		return entry.name
