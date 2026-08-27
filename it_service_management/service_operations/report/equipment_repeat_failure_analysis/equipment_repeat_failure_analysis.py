from it_service_management.analytics.reporting.reports import run


def execute(filters=None):
	return run("Equipment Repeat Failure Analysis", filters)
