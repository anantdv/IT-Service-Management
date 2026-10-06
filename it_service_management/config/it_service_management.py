from frappe import _


def get_data():
	return [
		{
			"label": _("Management"),
			"items": [
				{
					"type": "page",
					"name": "it-service-command-center",
					"label": _("Management Command Center"),
					"description": _("Executive and operational dashboard for IT service management."),
				},
				{
					"type": "page",
					"name": "itsm-service-desk",
					"label": _("ITSM Service Desk"),
					"description": _("Operational incident, request, SLA, and queue console."),
				},
				{
					"type": "page",
					"name": "itsm-change-calendar",
					"label": _("Change Calendar"),
					"description": _("Calendar-style list of scheduled and active changes."),
				},
			],
		},
		{
			"label": _("Service Desk"),
			"items": [
				{
					"type": "doctype",
					"name": "Service Ticket",
					"label": _("Service Tickets"),
					"description": _("Log, triage, and resolve customer service requests."),
				},
				{
					"type": "doctype",
					"name": "Major Incident",
					"label": _("Major Incidents"),
					"description": _("Coordinate high-impact incidents and communications."),
				},
				{
					"type": "doctype",
					"name": "ITSM Problem",
					"label": _("Problems"),
					"description": _("Investigate recurring incidents and root causes."),
				},
				{
					"type": "doctype",
					"name": "ITSM Known Error",
					"label": _("Known Errors"),
					"description": _("Publish known issue workarounds for service desk users."),
				},
				{
					"type": "doctype",
					"name": "ITSM Change Request",
					"label": _("Change Requests"),
					"description": _("Assess, approve, schedule, and validate service changes."),
				},
				{
					"type": "doctype",
					"name": "ITSM Knowledge Article",
					"label": _("Knowledge Articles"),
					"description": _("Capture procedures, workarounds, and troubleshooting guidance."),
				},
				{
					"type": "doctype",
					"name": "Service Job",
					"label": _("Service Jobs"),
					"description": _("Plan technician work, parts, labour, and completion."),
				},
				{
					"type": "doctype",
					"name": "Remote Support Session",
					"label": _("Remote Support Sessions"),
					"description": _("Record remote troubleshooting sessions and outcomes."),
				},
				{
					"type": "doctype",
					"name": "Service Part Request",
					"label": _("Service Part Requests"),
					"description": _("Request and track parts required for service jobs."),
				},
			],
		},
		{
			"label": _("Field Service"),
			"items": [
				{
					"type": "doctype",
					"name": "Service Team",
					"label": _("Service Teams"),
					"description": _("Group technicians into operational service teams."),
				},
				{
					"type": "doctype",
					"name": "Service Zone",
					"label": _("Service Zones"),
					"description": _("Define service territories for dispatch planning."),
				},
				{
					"type": "doctype",
					"name": "Service Expense",
					"label": _("Service Expenses"),
					"description": _("Capture field service travel, material, and incidental costs."),
				},
			],
		},
		{
			"label": _("Contracts"),
			"items": [
				{
					"type": "doctype",
					"name": "Service Contract",
					"label": _("Service Contracts"),
					"description": _("Manage AMC, warranty, SLA, and entitlement coverage."),
				},
				{
					"type": "doctype",
					"name": "Service Plan",
					"label": _("Service Plans"),
					"description": _("Maintain reusable service contract plan templates."),
				},
				{
					"type": "doctype",
					"name": "Warranty Policy",
					"label": _("Warranty Policies"),
					"description": _("Configure warranty coverage and service billing rules."),
				},
				{
					"type": "doctype",
					"name": "Service Charge Rule",
					"label": _("Service Charge Rules"),
					"description": _("Define automatic charge rules for service work."),
				},
			],
		},
		{
			"label": _("Equipment"),
			"items": [
				{
					"type": "doctype",
					"name": "Customer Equipment",
					"label": _("Customer Equipment"),
					"description": _("Track installed and serviceable customer equipment."),
				},
				{
					"type": "doctype",
					"name": "Configuration Item",
					"label": _("Configuration Items"),
					"description": _("Track ITSM service-management context for assets and equipment."),
				},
				{
					"type": "doctype",
					"name": "ITSM Service",
					"label": _("ITSM Services"),
					"description": _("Maintain business and technical service catalog records."),
				},
				{
					"type": "doctype",
					"name": "Service Request Type",
					"label": _("Service Request Types"),
					"description": _("Configure request fulfilment defaults."),
				},
				{
					"type": "doctype",
					"name": "ITSM Assignment Group",
					"label": _("Assignment Groups"),
					"description": _("Route work to service desk and support groups."),
				},
				{
					"type": "doctype",
					"name": "ITSM Priority Matrix",
					"label": _("Priority Matrix"),
					"description": _("Configure impact and urgency to priority mapping."),
				},
				{
					"type": "doctype",
					"name": "Customer Site",
					"label": _("Customer Sites"),
					"description": _("Maintain customer service locations and site details."),
				},
				{
					"type": "doctype",
					"name": "Service Checklist Template",
					"label": _("Service Checklist Templates"),
					"description": _("Build repeatable checklists for service jobs."),
				},
				{
					"type": "doctype",
					"name": "IT Service Settings",
					"label": _("IT Service Settings"),
					"description": _("Configure default warehouses, billing, and SLA behavior."),
				},
			],
		},
		{
			"label": _("Reports"),
			"items": [
				{
					"type": "report",
					"name": "Open Service Tickets",
					"doctype": "Service Ticket",
					"is_query_report": True,
				},
				{
					"type": "report",
					"name": "Incident Summary",
					"doctype": "Service Ticket",
					"is_query_report": True,
				},
				{
					"type": "report",
					"name": "Technician Workload",
					"doctype": "Service Job",
					"is_query_report": True,
				},
				{
					"type": "report",
					"name": "Service SLA Compliance",
					"doctype": "Service Ticket",
					"is_query_report": True,
				},
				{
					"type": "report",
					"name": "Completed Service Jobs Pending Billing",
					"doctype": "Service Job",
					"is_query_report": True,
				},
			],
		},
	]
