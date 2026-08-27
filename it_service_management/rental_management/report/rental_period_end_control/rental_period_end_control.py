from it_service_management.analytics.reporting.reports import run


def execute(filters=None):
	return run("Rental Period End Control", filters)
