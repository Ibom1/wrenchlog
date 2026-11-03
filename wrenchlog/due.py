"""Work out what each car needs next."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from .schedule import DEFAULT_SCHEDULE, to_unit
from .store import Car, Store

SOON_DAYS = 30  # "due soon" when the date is this close...
SOON_SHARE = 0.10  # ...or the distance is within this share of the interval
MIN_SPAN_DAYS = 14  # need readings at least this far apart to estimate driving pace


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


@dataclass
class Interval:
    kind: str
    name: str
    distance: int | None  # in the car's unit
    months: int | None


@dataclass
class DueItem:
    interval: Interval
    status: str  # "overdue", "due-soon", "ok", "no-record", "off"
    last_date: date | None = None
    last_odometer: int | None = None
    next_date: date | None = None
    next_odometer: int | None = None
    distance_left: int | None = None  # negative when overdue
    days_left: int | None = None  # negative when overdue
    estimated_date: date | None = None  # when the distance will likely be reached


def intervals_for(store: Store, car: Car) -> list[Interval]:
    custom = store.custom_intervals(car)
    out = []
    for s in DEFAULT_SCHEDULE:
        name, dist, months = s.name, to_unit(s.km, car.unit), s.months
        if s.key in custom:
            cname, dist, months = custom[s.key]
            name = cname or name
        out.append(Interval(s.key, name, dist, months))
    for kind, (cname, dist, months) in sorted(custom.items()):
        if kind not in {s.key for s in DEFAULT_SCHEDULE}:
            out.append(Interval(kind, cname or kind.replace("-", " ").capitalize(), dist, months))
    return out


def daily_pace(store: Store, car: Car) -> float | None:
    """Average distance per day from the first to the latest odometer reading."""
    pts = store.readings(car)
    if len(pts) < 2:
        return None
    (d0, o0), (d1, o1) = pts[0], max(pts, key=lambda p: (p[1], p[0]))
    span = (d1 - d0).days
    if span < MIN_SPAN_DAYS or o1 <= o0:
        return None
    return (o1 - o0) / span


def due(store: Store, car: Car, today: date) -> list[DueItem]:
    latest = store.latest_odometer(car)
    odometer = latest[0] if latest else None
    pace = daily_pace(store, car)
    items = []
    for iv in intervals_for(store, car):
        if iv.distance is None and iv.months is None:
            items.append(DueItem(iv, "off"))
            continue
        records = store.services(car, iv.kind)
        if not records:
            items.append(DueItem(iv, "no-record"))
            continue
        last = records[-1]
        item = DueItem(iv, "ok", last.date, last.odometer)
        overdue = soon = False

        if iv.months is not None:
            item.next_date = add_months(last.date, iv.months)
            item.days_left = (item.next_date - today).days
            overdue |= item.days_left < 0
            soon |= item.days_left <= SOON_DAYS

        if iv.distance is not None and last.odometer is not None:
            item.next_odometer = last.odometer + iv.distance
            if odometer is not None:
                item.distance_left = item.next_odometer - odometer
                overdue |= item.distance_left < 0
                soon |= item.distance_left <= iv.distance * SOON_SHARE
                if pace and item.distance_left > 0:
                    item.estimated_date = date.fromordinal(today.toordinal() + round(item.distance_left / pace))

        item.status = "overdue" if overdue else "due-soon" if soon else "ok"
        items.append(item)

    order = {"overdue": 0, "due-soon": 1, "ok": 2, "no-record": 3, "off": 4}
    items.sort(key=lambda i: (order[i.status], i.days_left if i.days_left is not None else 10**6, i.interval.name))
    return items
