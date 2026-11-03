"""Command line for wrenchlog."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date

from . import __version__
from .due import DueItem, due, intervals_for
from .schedule import BY_KEY, DEFAULT_SCHEDULE
from .store import Car, Store, StoreError

EXIT_OK, EXIT_DUE, EXIT_ERROR, EXIT_USAGE = 0, 1, 2, 64
KEY_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class UsageError(Exception):
    pass


# ---------- parsing helpers ----------


def parse_date(text: str, today: date) -> date:
    if text == "today":
        return today
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise UsageError(f'"{text}" isn\'t a date. Use YYYY-MM-DD, e.g. 2026-11-03, or "today".') from None


def parse_number(text: str, what: str) -> int:
    clean = text.replace(",", "").replace("_", "").strip()
    if not clean.isdigit():
        raise UsageError(f'{what} must be a whole number, not "{text}".')
    return int(clean)


def parse_cost(text: str) -> int:
    clean = text.replace(",", "").lstrip("$").strip()
    if not re.fullmatch(r"\d+(\.\d{1,2})?", clean):
        raise UsageError(f'Cost must look like 79.99, not "{text}".')
    whole, _, frac = clean.partition(".")
    return int(whole) * 100 + int((frac + "00")[:2])


def money(cents: int) -> str:
    return f"{cents // 100:,}.{cents % 100:02d}"


def num(n: int) -> str:
    return f"{n:,}"


def weeks(days: int) -> str:
    if days < 14:
        return f"{days} day{'s' if days != 1 else ''}"
    if days < 60:
        return f"{round(days / 7)} weeks"
    return f"{round(days / 30)} months"


# ---------- output ----------

LABEL = {"overdue": "OVERDUE", "due-soon": "SOON", "ok": "OK", "no-record": "--", "off": "OFF"}


def describe(item: DueItem, unit: str) -> str:
    if item.status == "no-record":
        return "no record yet"
    if item.status == "off":
        return "not tracked"
    parts = []
    if item.distance_left is not None:
        if item.distance_left < 0:
            parts.append(f"{num(-item.distance_left)} {unit} over")
        else:
            parts.append(f"in {num(item.distance_left)} {unit}")
    elif item.next_odometer is not None:
        parts.append(f"at {num(item.next_odometer)} {unit}")
    if item.days_left is not None:
        if item.days_left < 0:
            parts.append(f"{weeks(-item.days_left)} late (was due {item.next_date})")
        else:
            parts.append(f"by {item.next_date}")
    return " or ".join(parts)


def format_due(car: Car, items: list[DueItem], odometer, today: date) -> str:
    head = car.label
    if odometer is not None:
        head += f" · {num(odometer)} {car.unit}"
    lines = [head]
    width = max(len(i.interval.name) for i in items)
    for it in items:
        text = describe(it, car.unit)
        if it.estimated_date and it.distance_left is not None and it.distance_left > 0:
            days = (it.estimated_date - today).days
            if it.next_date is None or it.estimated_date < it.next_date:
                text = text.replace(f"in {num(it.distance_left)} {car.unit}", f"in {num(it.distance_left)} {car.unit} (about {weeks(days)} at your pace)", 1)
        last = ""
        if it.last_date:
            last = f"  · last {it.last_date}" + (f" at {num(it.last_odometer)} {car.unit}" if it.last_odometer is not None else "")
        lines.append(f"  {LABEL[it.status]:<8} {it.interval.name:<{width}}  {text}{last}")
    return "\n".join(lines)


def due_to_dict(car: Car, items: list[DueItem], odometer) -> dict:
    def d(x):
        return x.isoformat() if x else None
    return {
        "car": car.name,
        "unit": car.unit,
        "odometer": odometer,
        "services": [
            {
                "kind": i.interval.kind, "name": i.interval.name, "status": i.status,
                "every_distance": i.interval.distance, "every_months": i.interval.months,
                "last_date": d(i.last_date), "last_odometer": i.last_odometer,
                "next_date": d(i.next_date), "next_odometer": i.next_odometer,
                "distance_left": i.distance_left, "days_left": i.days_left,
                "estimated_date": d(i.estimated_date),
            }
            for i in items
        ],
    }


# ---------- commands ----------


def cmd_add_car(store: Store, a, today, out):
    year = parse_number(a.year, "Year") if a.year else None
    if year is not None and not 1886 <= year <= today.year + 1:
        raise UsageError(f"{year} doesn't look like a model year.")
    car = store.add_car(a.name, a.unit, a.make, a.model, year)
    if a.odometer is not None:
        store.add_reading(car, parse_number(a.odometer, "Odometer"), today)
    out(f"Added {car.label}.")
    out(f'Next: log a past service, e.g.  wrenchlog log oil-change --car {car.name} --date 2026-06-01 --odometer 80000')
    return EXIT_OK


def cmd_cars(store, a, today, out):
    cars = store.cars()
    if a.json:
        out(json.dumps([{"name": c.name, "make": c.make, "model": c.model, "year": c.year, "unit": c.unit,
                         "odometer": (store.latest_odometer(c) or (None,))[0]} for c in cars], indent=2))
        return EXIT_OK
    if not cars:
        out("No cars yet. Add one with: wrenchlog add-car <nickname> --odometer <reading>")
    for c in cars:
        latest = store.latest_odometer(c)
        out(f"{c.label}" + (f" · {num(latest[0])} {c.unit} on {latest[1]}" if latest else ""))
    return EXIT_OK


def cmd_remove_car(store, a, today, out):
    car = store.car(a.name)
    if not a.yes:
        out(f"This deletes {car.label} and all its records. Run again with --yes to confirm.")
        return EXIT_USAGE
    store.remove_car(car)
    out(f"Removed {car.name}.")
    return EXIT_OK


def cmd_odometer(store, a, today, out):
    car = store.car(a.car)
    reading = parse_number(a.reading, "Odometer")
    when = parse_date(a.date, today)
    store.add_reading(car, reading, when)
    out(f"{car.name}: {num(reading)} {car.unit} on {when}.")
    return EXIT_OK


def cmd_log(store, a, today, out):
    car = store.car(a.car)
    known = {i.kind for i in intervals_for(store, car)}
    if a.kind not in known:
        raise UsageError(
            f'Unknown service "{a.kind}". See the list with: wrenchlog services\n'
            f'To track something new: wrenchlog interval {a.kind} --name "..." --every-months 12'
        )
    when = parse_date(a.date, today)
    if when > today:
        raise UsageError(f"{when} is in the future. Log services after they're done.")
    odo = parse_number(a.odometer, "Odometer") if a.odometer else None
    if odo is not None:
        latest = store.latest_odometer(car)
        if latest and odo < latest[0] and when >= latest[1]:
            raise UsageError(f"{num(odo)} is lower than the last reading ({num(latest[0])} on {latest[1]}).")
    cost = parse_cost(a.cost) if a.cost else None
    sid = store.add_service(car, a.kind, when, odo, cost, a.note)
    name = next(i.name for i in intervals_for(store, car) if i.kind == a.kind)
    out(f"Logged #{sid}: {name} for {car.name} on {when}" + (f" at {num(odo)} {car.unit}" if odo is not None else "") + ".")
    return EXIT_OK


def cmd_due(store, a, today, out):
    cars = [store.car(a.car)] if a.car or len(store.cars()) == 1 else store.cars()
    if not cars:
        store.car(None)  # raises the "no cars yet" message
    reports, blocks, any_due = [], [], False
    for car in cars:
        items = due(store, car, today)
        if not a.all:
            items = [i for i in items if i.status != "off"]
        latest = store.latest_odometer(car)
        odo = latest[0] if latest else None
        any_due |= any(i.status in ("overdue", "due-soon") for i in items)
        reports.append(due_to_dict(car, items, odo))
        blocks.append(format_due(car, items, odo, today))
    out(json.dumps({"today": today.isoformat(), "cars": reports}, indent=2) if a.json else "\n\n".join(blocks))
    return EXIT_DUE if (a.fail_if_due and any_due) else EXIT_OK


def cmd_history(store, a, today, out):
    car = store.car(a.car)
    names = {i.kind: i.name for i in intervals_for(store, car)}
    recs = store.services(car, a.kind)
    if a.json:
        out(json.dumps([{"id": r.id, "kind": r.kind, "date": r.date.isoformat(), "odometer": r.odometer,
                         "cost": r.cost_cents / 100 if r.cost_cents is not None else None, "note": r.note} for r in recs], indent=2))
        return EXIT_OK
    if not recs:
        out(f"No services logged for {car.name} yet.")
        return EXIT_OK
    out(f"{car.label}")
    for r in reversed(recs):
        odo = f"{num(r.odometer)} {car.unit}" if r.odometer is not None else ""
        cost = money(r.cost_cents) if r.cost_cents is not None else ""
        note = f"  {r.note}" if r.note else ""
        out(f"  #{r.id:<4} {r.date}  {names.get(r.kind, r.kind):<24} {odo:>12}  {cost:>9}{note}")
    return EXIT_OK


def cmd_costs(store, a, today, out):
    car = store.car(a.car)
    names = {i.kind: i.name for i in intervals_for(store, car)}
    by_year: dict[int, int] = defaultdict(int)
    by_kind: dict[str, int] = defaultdict(int)
    for r in store.services(car):
        if r.cost_cents is None:
            continue
        by_year[r.date.year] += r.cost_cents
        by_kind[r.kind] += r.cost_cents
    total = sum(by_year.values())
    if a.json:
        out(json.dumps({"car": car.name, "total": total / 100, "by_year": {str(y): c / 100 for y, c in sorted(by_year.items())},
                        "by_service": {k: c / 100 for k, c in sorted(by_kind.items())}}, indent=2))
        return EXIT_OK
    if not total:
        out(f"No costs logged for {car.name} yet. Add --cost to a log entry.")
        return EXIT_OK
    out(f"{car.label}: {money(total)} logged")
    out("  By year:")
    for y, c in sorted(by_year.items()):
        out(f"    {y}  {money(c):>10}")
    out("  By service:")
    for k, c in sorted(by_kind.items(), key=lambda kv: -kv[1]):
        out(f"    {names.get(k, k):<24} {money(c):>10}")
    return EXIT_OK


def cmd_services(store, a, today, out):
    car = store.car(a.car) if (a.car or len(store.cars()) == 1) else None
    unit = car.unit if car else "km"
    ivs = intervals_for(store, car) if car else None
    rows = ivs or [type("I", (), {"kind": s.key, "name": s.name, "distance": s.km, "months": s.months}) for s in DEFAULT_SCHEDULE]
    for iv in rows:
        every = " or ".join(x for x in [
            f"{num(iv.distance)} {unit}" if iv.distance else None,
            f"{iv.months} months" if iv.months else None] if x) or "not tracked"
        out(f"  {iv.kind:<20} {iv.name:<24} every {every}")
    return EXIT_OK


def cmd_interval(store, a, today, out):
    car = store.car(a.car)
    if not KEY_RE.match(a.kind):
        raise UsageError("Service names use lower-case words joined by hyphens, e.g. transmission-fluid.")
    if a.off:
        dist = months = None
    else:
        dist = parse_number(a.every_distance, "--every-distance") if a.every_distance else None
        months = parse_number(a.every_months, "--every-months") if a.every_months else None
        if dist is None and months is None:
            raise UsageError("Give --every-distance, --every-months, or both (or --off to stop tracking it).")
        if dist == 0 or months == 0:
            raise UsageError("Intervals must be greater than zero.")
    if a.kind not in BY_KEY and not a.name and a.kind not in store.custom_intervals(car):
        raise UsageError(f'"{a.kind}" is a new service; give it a name with --name "...".')
    store.set_interval(car, a.kind, dist, months, a.name)
    out(f"{car.name}: {a.kind} " + ("will not be tracked." if a.off else "updated."))
    return EXIT_OK


def cmd_delete(store, a, today, out):
    car = store.car(a.car)
    store.delete_service(car, a.id)
    out(f"Deleted service #{a.id} from {car.name}.")
    return EXIT_OK


# ---------- parser ----------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wrenchlog", description="Track car maintenance and see what's due next.")
    p.add_argument("--version", action="version", version=f"wrenchlog {__version__}")
    p.add_argument("--db", help="database file (default: ~/.wrenchlog/wrenchlog.db, or $WRENCHLOG_DB)")
    p.add_argument("--today", help=argparse.SUPPRESS)  # fixes "today" for tests and demos
    sub = p.add_subparsers(dest="command", required=True)

    def car_opt(sp):
        sp.add_argument("--car", help="car nickname (not needed when you have one car)")

    s = sub.add_parser("add-car", help="add a car")
    s.add_argument("name", help='a nickname, e.g. "civic"')
    s.add_argument("--make"), s.add_argument("--model"), s.add_argument("--year")
    s.add_argument("--unit", choices=["km", "mi"], default="km")
    s.add_argument("--odometer", help="current odometer reading")
    s.set_defaults(fn=cmd_add_car)

    s = sub.add_parser("cars", help="list your cars")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_cars)

    s = sub.add_parser("remove-car", help="delete a car and all its records")
    s.add_argument("name"), s.add_argument("--yes", action="store_true")
    s.set_defaults(fn=cmd_remove_car)

    s = sub.add_parser("odometer", help="record the current odometer reading")
    s.add_argument("reading"), car_opt(s), s.add_argument("--date", default="today")
    s.set_defaults(fn=cmd_odometer)

    s = sub.add_parser("log", help="log a service that was done")
    s.add_argument("kind", help="service, e.g. oil-change (see: wrenchlog services)")
    car_opt(s)
    s.add_argument("--date", default="today"), s.add_argument("--odometer")
    s.add_argument("--cost", help="e.g. 79.99"), s.add_argument("--note")
    s.set_defaults(fn=cmd_log)

    s = sub.add_parser("due", help="show what's due next (all cars when you have several)")
    car_opt(s)
    s.add_argument("--json", action="store_true")
    s.add_argument("--all", action="store_true", help="include services you turned off")
    s.add_argument("--fail-if-due", action="store_true", help="exit 1 when anything is overdue or due soon")
    s.set_defaults(fn=cmd_due)

    s = sub.add_parser("history", help="list logged services, newest first")
    car_opt(s), s.add_argument("--kind"), s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_history)

    s = sub.add_parser("costs", help="spending by year and by service")
    car_opt(s), s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_costs)

    s = sub.add_parser("services", help="list the services wrenchlog tracks and their intervals")
    car_opt(s)
    s.set_defaults(fn=cmd_services)

    s = sub.add_parser("interval", help="change a service's interval, or add a new kind of service")
    s.add_argument("kind"), car_opt(s)
    s.add_argument("--every-distance"), s.add_argument("--every-months")
    s.add_argument("--name"), s.add_argument("--off", action="store_true", help="stop tracking this service")
    s.set_defaults(fn=cmd_interval)

    s = sub.add_parser("delete", help="delete a logged service by its # number")
    s.add_argument("id", type=int), car_opt(s)
    s.set_defaults(fn=cmd_delete)
    return p


def main(argv=None, out=print, err=None) -> int:
    err = err or (lambda m: print(m, file=sys.stderr))
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return EXIT_OK if exc.code == 0 else EXIT_USAGE
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        err("wrenchlog: --today must be YYYY-MM-DD")
        return EXIT_USAGE
    try:
        store = Store(args.db)
    except Exception as exc:
        err(f"wrenchlog: can't open the database: {exc}")
        return EXIT_ERROR
    try:
        return args.fn(store, args, today, out)
    except UsageError as exc:
        err(f"wrenchlog: {exc}")
        return EXIT_USAGE
    except StoreError as exc:
        err(f"wrenchlog: {exc}")
        return EXIT_ERROR
    finally:
        store.close()
