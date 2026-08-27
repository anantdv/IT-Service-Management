from erpnext.assets.doctype.asset.asset_dashboard import get_data as get_erpnext_data

from it_service_management.config.dashboard import extend_dashboard


def get_data():
	return extend_dashboard(get_erpnext_data(), [
		{"label": "IT Service and Rental", "items": ["Customer Equipment", "Service Job", "Rental Equipment Replacement"]},
	], {"Customer Equipment": "asset", "Service Job": "asset", "Rental Equipment Replacement": "old_asset"})
