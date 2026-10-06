from __future__ import annotations


RISK_LEVELS = ((0, "Low"), (25, "Medium"), (50, "High"), (75, "Critical"))


def calculate_change_risk(change) -> tuple[int, str]:
	score = 0
	score += _score(change.get("risk_level"), {"Low": 5, "Medium": 20, "High": 35, "Critical": 50})
	score += _score(change.get("impact"), {"Low": 5, "Medium": 15, "High": 25, "Critical": 35})
	score += _score(change.get("urgency"), {"Low": 0, "Medium": 10, "High": 20, "Critical": 30})
	if change.get("downtime_required"):
		score += min(25, int(change.get("expected_downtime_minutes") or 0) // 30 * 5 + 10)
	score = min(score, 100)
	return score, _level(score)


def _score(value, mapping):
	return mapping.get(value, 0)


def _level(score):
	level = "Low"
	for threshold, name in RISK_LEVELS:
		if score >= threshold:
			level = name
	return level
