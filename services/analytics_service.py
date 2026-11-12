
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from models.report import Report


SEVERITY_WEIGHT = {
    "bajo": 1,
    "intermedio": 2,
    "critico": 3,
}


class AnalyticsService:

    def __init__(
        self,
        critical_threshold: int = 5,
        prediction_window_days: int = 7
    ):
        self.critical_threshold = critical_threshold
        self.prediction_window_days = prediction_window_days

    def compute_summary(self, reports: List[Report]) -> Dict:
        if not reports:
            return self._empty_summary()

        zone_name, zone_count, zone_weight = self._critical_zone(reports)

        return {
            "total": len(reports),
            "criticalZoneName": zone_name,
            "criticalZoneInfo": self._describe_zone(zone_count, zone_weight),
            "criticalZoneCount": zone_count,
            "criticalZonePrediction": self._predict_trend(reports, zone_name),
        }

    def _critical_zone(self, reports: List[Report]):
        weighted = defaultdict(int)
        counts = Counter()

        for report in reports:
            weight = SEVERITY_WEIGHT.get(report.severity, 1)
            weighted[report.zone] += weight
            counts[report.zone] += 1

        zone_name = max(weighted, key=weighted.get)

        return zone_name, counts[zone_name], weighted[zone_name]

    def _describe_zone(self, count: int, weight: int) -> str:
        if count >= self.critical_threshold:
            return f"Alta concentración ({count} reportes, peso {weight})"

        if count >= 3:
            return f"Concentración media ({count} reportes)"

        return f"Actividad leve ({count} reportes)"

    def _predict_trend(self, reports: List[Report], zone_name: str) -> str:
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=self.prediction_window_days * 2
        )

        daily = defaultdict(int)

        for report in reports:
            if report.zone != zone_name:
                continue

            try:
                created_at = datetime.fromisoformat(
                    report.created_at.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                continue

            if created_at >= cutoff:
                daily[created_at.date()] += 1

        if len(daily) < 2:
            return self._fallback_prediction(daily, reports)

        return self._linear_prediction(daily)

    def _fallback_prediction(self, daily: dict, reports: List[Report]) -> str:
        zone_total = sum(daily.values()) or 1
        share = (zone_total / len(reports)) * 100

        return f"{min(round(share), 99)}%"

    def _linear_prediction(self, daily: dict) -> str:
        days = sorted(daily.keys())
        xs = list(range(len(days)))
        ys = [daily[day] for day in days]

        n = len(xs)
        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xy = sum(x * y for x, y in zip(xs, ys))
        sum_x2 = sum(x * x for x in xs)

        denominator = n * sum_x2 - sum_x ** 2 or 1
        slope = (n * sum_xy - sum_x * sum_y) / denominator

        next_x = xs[-1] + 1
        intercept = (sum_y - slope * sum_x) / n
        prediction = max(intercept + slope * next_x, 0)

        average = sum(ys) / n

        if average == 0:
            return "0%"

        probability = min(round((prediction / average) * 100), 99)

        return f"{probability}%"

    def _empty_summary(self) -> Dict:
        return {
            "total": 0,
            "criticalZoneName": "--",
            "criticalZoneInfo": "Sin datos suficientes",
            "criticalZoneCount": 0,
            "criticalZonePrediction": "0%",
        }
