from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

import frappe
from frappe.utils import getdate


MONEY_QUANTUM = Decimal("0.01")
METER_ALIASES = {
	"BW": "BW",
	"B&W": "BW",
	"BLACK AND WHITE": "BW",
	"COLOUR": "COLOUR",
	"COLOR": "COLOUR",
}


def as_decimal(value) -> Decimal:
	return Decimal(str(value or 0))


class RentalMeterBillingEngine:
	@staticmethod
	def calculate_meter(meter_type, previous, current, included=0, rate=0, reset=None):
		previous_value = as_decimal(previous)
		current_value = as_decimal(current)
		if current_value < previous_value:
			if not reset:
				frappe.throw(f"Current {meter_type} reading cannot be lower than the previous reading without an approved Meter Reset.")
			usage = max(as_decimal(reset["previous_reading"]) - previous_value, Decimal("0"))
			usage += max(current_value - as_decimal(reset["reset_reading"]), Decimal("0"))
		else:
			usage = current_value - previous_value
		included_value = as_decimal(included)
		billable = max(usage - included_value, Decimal("0"))
		amount = (billable * as_decimal(rate)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
		return {
			"meter_type": meter_type,
			"previous": previous_value,
			"current": current_value,
			"usage": usage,
			"included": included_value,
			"billable": billable,
			"rate": as_decimal(rate),
			"amount": amount,
		}

	def calculate_reading(self, reading):
		contract = frappe.get_cached_doc("Rental Contract", reading.rental_contract)
		equipment_terms = frappe.db.get_value(
			"Rental Contract Equipment",
			{"parent": contract.name, "customer_equipment": reading.customer_equipment},
			["included_bw_pages", "included_colour_pages", "excess_bw_rate", "excess_colour_rate"],
			as_dict=True,
		) or {}
		results = []
		for row in reading.details:
			meter_code = METER_ALIASES.get((row.meter_type or "").upper(), (row.meter_type or "").upper())
			previous = self.get_previous_verified(reading, row.meter_type)
			if previous is None:
				fieldname = "latest_bw_meter" if meter_code == "BW" else "latest_colour_meter" if meter_code == "COLOUR" else None
				previous = frappe.db.get_value("Customer Equipment", reading.customer_equipment, fieldname) if fieldname else None
			if previous is None:
				previous = row.current_reading
			included, rate = self.get_terms(contract, equipment_terms, meter_code)
			reset = self.get_reset(reading, row.meter_type, previous) if as_decimal(row.current_reading) < as_decimal(previous) else None
			result = self.calculate_meter(row.meter_type, previous, row.current_reading, included, rate, reset)
			row.previous_reading = result["previous"]
			row.usage = result["usage"]
			row.included_quantity = result["included"]
			row.billable_quantity = result["billable"]
			row.rate = result["rate"]
			row.calculated_amount = result["amount"]
			results.append(result)
		reading.total_meter_charge = sum((item["amount"] for item in results), Decimal("0"))
		return {"customer_equipment": reading.customer_equipment, "billing_period": str(reading.billing_period_from)[:7], "meters": results, "total_meter_charge": reading.total_meter_charge}

	@staticmethod
	def get_terms(contract, equipment_terms, meter_code):
		if meter_code == "BW":
			return equipment_terms.get("included_bw_pages") or contract.included_bw_pages, equipment_terms.get("excess_bw_rate") or contract.excess_bw_rate
		if meter_code == "COLOUR":
			return equipment_terms.get("included_colour_pages") or contract.included_colour_pages, equipment_terms.get("excess_colour_rate") or contract.excess_colour_rate
		return 0, 0

	@staticmethod
	def get_previous_verified(reading, meter_type):
		rows = frappe.db.sql(
			"""
			select detail.current_reading
			from `tabEquipment Meter Reading Detail` detail
			inner join `tabEquipment Meter Reading` reading on reading.name = detail.parent
			where reading.customer_equipment = %s and detail.meter_type = %s and reading.verified = 1
			  and reading.reading_date <= %s and reading.name != %s
			order by reading.reading_date desc, reading.creation desc limit 1
			""",
			(reading.customer_equipment, meter_type, reading.reading_date, reading.name or ""),
		)
		return rows[0][0] if rows else None

	@staticmethod
	def get_reset(reading, meter_type, previous):
		return frappe.db.get_value(
			"Meter Reset",
			{"customer_equipment": reading.customer_equipment, "meter_type": meter_type, "reset_date": ["<=", getdate(reading.reading_date)], "approved_by": ["is", "set"]},
			["previous_reading", "reset_reading"],
			as_dict=True,
			order_by="reset_date desc",
		)
