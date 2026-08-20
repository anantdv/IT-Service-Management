from frappe import _


def get_data():
	return [
		{
			"module_name": "IT Service Management",
			"category": "Modules",
			"label": _("IT Service Management"),
			"color": "#2563eb",
			"icon": "octicon octicon-tools",
			"type": "module",
			"link": "it-service-management",
			"description": _("IT service, equipment lifecycle, and contracts"),
		}
	]
