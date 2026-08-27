from it_service_management.analytics.reporting.reports import run


def execute(filters=None):
	return run("Service and Rental Revenue Leakage", filters)
