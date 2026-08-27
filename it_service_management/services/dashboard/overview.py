from __future__ import annotations

from it_service_management.services.dashboard.common import get_payload


def get_dashboard_overview(filters=None, force_refresh=False):
	return get_payload("overview", filters, force_refresh)
