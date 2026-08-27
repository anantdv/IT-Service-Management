from __future__ import annotations

from it_service_management.services.dashboard.common import get_payload


def get_rental_dashboard(filters=None, force_refresh=False):
	return get_payload("rental", filters, force_refresh)
