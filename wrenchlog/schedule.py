"""Default service schedule.

Intervals are typical values for a modern petrol car under normal driving.
They are a starting point, not a manufacturer's schedule: every car's owner's
manual wins, and each interval can be changed per car with `wrenchlog interval`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Service:
    key: str  # stable id used on the command line, e.g. "oil-change"
    name: str  # shown to people
    km: int | None  # distance interval in kilometres (None = time only)
    months: int | None  # time interval (None = distance only)


DEFAULT_SCHEDULE: list[Service] = [
    Service("oil-change", "Oil and filter change", 8_000, 6),
    Service("tire-rotation", "Tire rotation", 10_000, 6),
    Service("brake-inspection", "Brake inspection", 20_000, 12),
    Service("cabin-filter", "Cabin air filter", 20_000, 12),
    Service("engine-air-filter", "Engine air filter", 30_000, 24),
    Service("wiper-blades", "Wiper blades", None, 12),
    Service("battery-check", "Battery test", None, 12),
    Service("brake-fluid", "Brake fluid flush", None, 24),
    Service("coolant", "Coolant replacement", 100_000, 60),
    Service("spark-plugs", "Spark plugs", 100_000, None),
]

BY_KEY = {s.key: s for s in DEFAULT_SCHEDULE}

KM_PER_MILE = 1.609344


def to_unit(km: int | None, unit: str) -> int | None:
    """Convert a km interval to the car's unit, rounded to a tidy number."""
    if km is None or unit == "km":
        return km
    miles = km / KM_PER_MILE
    step = 500 if miles >= 2_000 else 100
    return int(round(miles / step) * step)
