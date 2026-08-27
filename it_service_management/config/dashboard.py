from __future__ import annotations


def extend_dashboard(base, groups, non_standard=None):
	data = base or {}
	data.setdefault("transactions", []).extend(groups)
	if non_standard:
		data.setdefault("non_standard_fieldnames", {}).update(non_standard)
	return data
