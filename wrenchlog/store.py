"""SQLite storage. One small database file holds every car and its records.

Only car details (nickname, make, model, year), odometer readings and service
records are stored. There is no place for owner names, plates, VINs or
addresses, on purpose.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cars (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    make TEXT, model TEXT, year INTEGER,
    unit TEXT NOT NULL CHECK (unit IN ('km', 'mi'))
);
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY,
    car_id INTEGER NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    odometer INTEGER NOT NULL CHECK (odometer >= 0)
);
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY,
    car_id INTEGER NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    date TEXT NOT NULL,
    odometer INTEGER CHECK (odometer IS NULL OR odometer >= 0),
    cost_cents INTEGER CHECK (cost_cents IS NULL OR cost_cents >= 0),
    note TEXT
);
CREATE TABLE IF NOT EXISTS intervals (
    car_id INTEGER NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    name TEXT,
    distance INTEGER,
    months INTEGER,
    PRIMARY KEY (car_id, kind)
);
"""


class StoreError(Exception):
    """Something the person asked for can't be done (unknown car, duplicate name, ...)."""


@dataclass
class Car:
    id: int
    name: str
    make: str | None
    model: str | None
    year: int | None
    unit: str

    @property
    def label(self) -> str:
        parts = [str(self.year) if self.year else None, self.make, self.model]
        desc = " ".join(p for p in parts if p)
        return f"{self.name} ({desc})" if desc else self.name


@dataclass
class ServiceRecord:
    id: int
    kind: str
    date: date
    odometer: int | None
    cost_cents: int | None
    note: str | None


def default_path() -> Path:
    env = os.environ.get("WRENCHLOG_DB")
    if env:
        return Path(env)
    return Path.home() / ".wrenchlog" / "wrenchlog.db"


class Store:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        row = self.db.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()
        if row is None:
            self.db.execute("INSERT INTO meta VALUES ('schema', ?)", (str(SCHEMA_VERSION),))
            self.db.commit()
        elif int(row[0]) > SCHEMA_VERSION:
            self.db.close()
            raise StoreError(f"{self.path} was made by a newer version of wrenchlog; please upgrade.")

    def close(self) -> None:
        self.db.close()

    # ---------- cars ----------

    def add_car(self, name: str, unit: str = "km", make=None, model=None, year=None) -> Car:
        name = name.strip()
        if not name:
            raise StoreError("A car needs a nickname, e.g. \"civic\".")
        try:
            cur = self.db.execute(
                "INSERT INTO cars (name, make, model, year, unit) VALUES (?, ?, ?, ?, ?)",
                (name, make, model, year, unit),
            )
        except sqlite3.IntegrityError:
            raise StoreError(f'You already have a car called "{name}".') from None
        self.db.commit()
        return self.car(name) if cur.lastrowid else None

    def cars(self) -> list[Car]:
        rows = self.db.execute("SELECT id, name, make, model, year, unit FROM cars ORDER BY name COLLATE NOCASE")
        return [Car(*r) for r in rows]

    def car(self, name: str | None) -> Car:
        """Find a car by nickname. With no name, the only car (if there is exactly one)."""
        if name is None:
            cars = self.cars()
            if len(cars) == 1:
                return cars[0]
            if not cars:
                raise StoreError('No cars yet. Add one with: wrenchlog add-car <nickname> --odometer <reading>')
            raise StoreError("You have more than one car; say which with --car <nickname>.")
        row = self.db.execute(
            "SELECT id, name, make, model, year, unit FROM cars WHERE name = ? COLLATE NOCASE", (name.strip(),)
        ).fetchone()
        if row is None:
            known = ", ".join(c.name for c in self.cars()) or "none yet"
            raise StoreError(f'No car called "{name}". Your cars: {known}.')
        return Car(*row)

    def remove_car(self, car: Car) -> None:
        self.db.execute("DELETE FROM cars WHERE id = ?", (car.id,))
        self.db.commit()

    # ---------- odometer ----------

    def add_reading(self, car: Car, odometer: int, when: date) -> None:
        latest = self.latest_odometer(car)
        if latest and odometer < latest[0] and when >= latest[1]:
            raise StoreError(
                f"{odometer:,} is lower than the last reading ({latest[0]:,} on {latest[1]}). "
                "Odometers only go up; check the number."
            )
        self.db.execute("INSERT INTO readings (car_id, date, odometer) VALUES (?, ?, ?)", (car.id, when.isoformat(), odometer))
        self.db.commit()

    def latest_odometer(self, car: Car) -> tuple[int, date] | None:
        """Highest known odometer reading, from readings and services alike."""
        row = self.db.execute(
            """SELECT odometer, date FROM (
                   SELECT odometer, date FROM readings WHERE car_id = ?
                   UNION ALL
                   SELECT odometer, date FROM services WHERE car_id = ? AND odometer IS NOT NULL
               ) ORDER BY odometer DESC, date DESC LIMIT 1""",
            (car.id, car.id),
        ).fetchone()
        return (row[0], date.fromisoformat(row[1])) if row else None

    def readings(self, car: Car) -> list[tuple[date, int]]:
        rows = self.db.execute(
            """SELECT date, odometer FROM readings WHERE car_id = ?
               UNION ALL
               SELECT date, odometer FROM services WHERE car_id = ? AND odometer IS NOT NULL
               ORDER BY date, odometer""",
            (car.id, car.id),
        )
        return [(date.fromisoformat(d), o) for d, o in rows]

    # ---------- services ----------

    def add_service(self, car: Car, kind: str, when: date, odometer=None, cost_cents=None, note=None) -> int:
        cur = self.db.execute(
            "INSERT INTO services (car_id, kind, date, odometer, cost_cents, note) VALUES (?, ?, ?, ?, ?, ?)",
            (car.id, kind, when.isoformat(), odometer, cost_cents, note),
        )
        self.db.commit()
        return cur.lastrowid

    def services(self, car: Car, kind: str | None = None) -> list[ServiceRecord]:
        sql = "SELECT id, kind, date, odometer, cost_cents, note FROM services WHERE car_id = ?"
        args: list = [car.id]
        if kind:
            sql += " AND kind = ?"
            args.append(kind)
        sql += " ORDER BY date, id"
        return [
            ServiceRecord(i, k, date.fromisoformat(d), o, c, n)
            for i, k, d, o, c, n in self.db.execute(sql, args)
        ]

    def delete_service(self, car: Car, service_id: int) -> None:
        cur = self.db.execute("DELETE FROM services WHERE id = ? AND car_id = ?", (service_id, car.id))
        if cur.rowcount == 0:
            raise StoreError(f"No service #{service_id} for {car.name}. See the numbers with: wrenchlog history")
        self.db.commit()

    # ---------- intervals ----------

    def set_interval(self, car: Car, kind: str, distance, months, name=None) -> None:
        self.db.execute(
            """INSERT INTO intervals (car_id, kind, name, distance, months) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (car_id, kind) DO UPDATE SET
                   name = COALESCE(excluded.name, intervals.name),
                   distance = excluded.distance, months = excluded.months""",
            (car.id, kind, name, distance, months),
        )
        self.db.commit()

    def custom_intervals(self, car: Car) -> dict[str, tuple[str | None, int | None, int | None]]:
        rows = self.db.execute("SELECT kind, name, distance, months FROM intervals WHERE car_id = ?", (car.id,))
        return {k: (n, d, m) for k, n, d, m in rows}
