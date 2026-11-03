import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from wrenchlog.cli import main, parse_cost
from wrenchlog.due import add_months, due
from wrenchlog.schedule import to_unit
from wrenchlog.store import Store, StoreError

TODAY = "2026-11-03"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out, err = [], []
        code = main(["--db", self.db, "--today", TODAY, *argv], out=out.append, err=err.append)
        return code, "\n".join(out), "\n".join(err)

    def ok(self, *argv):
        code, out, err = self.run_cli(*argv)
        self.assertEqual(code, 0, err)
        return out

    def status(self, kind, car="civic"):
        data = json.loads(self.ok("due", "--car", car, "--json"))
        return next(s for s in data["cars"][0]["services"] if s["kind"] == kind)


class HelperTests(unittest.TestCase):
    def test_add_months_clamps_to_month_end(self):
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(add_months(date(2026, 11, 15), 3), date(2027, 2, 15))

    def test_cost_parsing(self):
        self.assertEqual(parse_cost("79.99"), 7999)
        self.assertEqual(parse_cost("$1,200"), 120000)
        self.assertEqual(parse_cost("30.5"), 3050)

    def test_mile_intervals_are_tidy(self):
        self.assertEqual(to_unit(8000, "mi"), 5000)
        self.assertEqual(to_unit(8000, "km"), 8000)
        self.assertIsNone(to_unit(None, "mi"))


class CarTests(Base):
    def test_add_and_list(self):
        self.ok("add-car", "civic", "--make", "Honda", "--model", "Civic", "--year", "2018", "--odometer", "61000")
        out = self.ok("cars")
        self.assertIn("civic (2018 Honda Civic) · 61,000 km", out)

    def test_duplicate_names_rejected_case_insensitively(self):
        self.ok("add-car", "civic")
        self.assertEqual(self.run_cli("add-car", "CIVIC")[0], 2)

    def test_car_is_optional_with_one_car_required_with_two(self):
        self.ok("add-car", "civic")
        self.ok("odometer", "1000")
        self.ok("add-car", "truck")
        code, _, err = self.run_cli("odometer", "2000")
        self.assertEqual(code, 2)
        self.assertIn("--car", err)

    def test_remove_needs_confirmation(self):
        self.ok("add-car", "civic")
        self.assertEqual(self.run_cli("remove-car", "civic")[0], 64)
        self.ok("remove-car", "civic", "--yes")
        self.assertIn("No cars yet", self.ok("cars"))

    def test_odometer_cannot_go_backwards(self):
        self.ok("add-car", "civic", "--odometer", "50000")
        code, _, err = self.run_cli("odometer", "49000")
        self.assertEqual(code, 2)
        self.assertIn("only go up", err)

    def test_store_has_no_owner_fields(self):
        store = Store(self.db)
        cols = {r[1] for r in store.db.execute("PRAGMA table_info(cars)")}
        store.close()
        self.assertEqual(cols, {"id", "name", "make", "model", "year", "unit"})


class LogTests(Base):
    def setUp(self):
        super().setUp()
        self.ok("add-car", "civic", "--odometer", "60000")

    def test_unknown_service_explains_how_to_add_one(self):
        code, _, err = self.run_cli("log", "flux-capacitor")
        self.assertEqual(code, 64)
        self.assertIn("wrenchlog interval flux-capacitor", err)

    def test_future_date_rejected(self):
        self.assertEqual(self.run_cli("log", "oil-change", "--date", "2027-01-01")[0], 64)

    def test_bad_inputs_are_usage_errors(self):
        self.assertEqual(self.run_cli("log", "oil-change", "--date", "yesterday")[0], 64)
        self.assertEqual(self.run_cli("log", "oil-change", "--cost", "lots")[0], 64)
        self.assertEqual(self.run_cli("log", "oil-change", "--odometer", "-5")[0], 64)

    def test_history_and_delete(self):
        self.ok("log", "oil-change", "--date", "2026-05-01", "--odometer", "70000", "--cost", "80")
        self.assertIn("#1", self.ok("history"))
        self.ok("delete", "1")
        self.assertIn("No services logged", self.ok("history"))
        self.assertEqual(self.run_cli("delete", "1")[0], 2)

    def test_costs_by_year_and_service(self):
        self.ok("log", "oil-change", "--date", "2025-06-01", "--cost", "70")
        self.ok("log", "oil-change", "--date", "2026-06-01", "--cost", "80.50")
        self.ok("log", "wiper-blades", "--date", "2026-07-01", "--cost", "30")
        data = json.loads(self.ok("costs", "--json"))
        self.assertEqual(data["total"], 180.5)
        self.assertEqual(data["by_year"], {"2025": 70.0, "2026": 110.5})
        self.assertEqual(data["by_service"]["oil-change"], 150.5)


class DueTests(Base):
    def setUp(self):
        super().setUp()
        self.ok("add-car", "civic", "--odometer", "70000")

    def test_never_serviced_is_no_record(self):
        self.assertEqual(self.status("oil-change")["status"], "no-record")

    def test_ok_soon_and_overdue_by_distance(self):
        self.ok("log", "oil-change", "--date", "2026-10-01", "--odometer", "70000")
        self.assertEqual(self.status("oil-change")["status"], "ok")
        self.ok("odometer", "77300")  # 700 left of 8,000: within 10%
        self.assertEqual(self.status("oil-change")["status"], "due-soon")
        self.ok("odometer", "78100")
        s = self.status("oil-change")
        self.assertEqual(s["status"], "overdue")
        self.assertEqual(s["distance_left"], -100)

    def test_overdue_by_time_even_with_low_distance(self):
        self.ok("log", "oil-change", "--date", "2026-04-01", "--odometer", "70000")
        s = self.status("oil-change")
        self.assertEqual(s["status"], "overdue")
        self.assertEqual(s["next_date"], "2026-10-01")

    def test_time_only_service(self):
        self.ok("log", "wiper-blades", "--date", "2025-11-20")
        s = self.status("wiper-blades")
        self.assertEqual(s["status"], "due-soon")
        self.assertIsNone(s["next_odometer"])

    def test_latest_record_wins(self):
        self.ok("log", "oil-change", "--date", "2025-01-01", "--odometer", "50000")
        self.ok("log", "oil-change", "--date", "2026-10-01", "--odometer", "70000")
        self.assertEqual(self.status("oil-change")["status"], "ok")

    def test_custom_interval_and_new_service(self):
        self.ok("interval", "oil-change", "--every-distance", "5000", "--every-months", "6")
        self.ok("log", "oil-change", "--date", "2026-10-01", "--odometer", "66000")
        self.assertEqual(self.status("oil-change")["next_odometer"], 71000)  # 66,000 + 5,000, not + 8,000
        self.ok("odometer", "71500")
        self.assertEqual(self.status("oil-change")["status"], "overdue")
        self.ok("interval", "transmission-fluid", "--name", "Transmission fluid", "--every-distance", "60000")
        self.ok("log", "transmission-fluid", "--date", "2026-01-01", "--odometer", "10000")
        self.assertEqual(self.status("transmission-fluid")["status"], "overdue")

    def test_new_service_needs_a_name(self):
        self.assertEqual(self.run_cli("interval", "mystery-part", "--every-months", "6")[0], 64)

    def test_turned_off_service_is_hidden(self):
        self.ok("interval", "spark-plugs", "--off")
        kinds = [s["kind"] for s in json.loads(self.ok("due", "--json"))["cars"][0]["services"]]
        self.assertNotIn("spark-plugs", kinds)

    def test_pace_estimate(self):
        store = Store(self.db)
        car = store.car("civic")
        store.add_reading(car, 70000, date(2026, 1, 1))  # same as add-car's, earlier date
        store.add_reading(car, 76000, date(2026, 11, 3))
        store.add_service(car, "oil-change", date(2026, 9, 1), 70500)
        item = next(i for i in due(store, car, date(2026, 11, 3)) if i.interval.kind == "oil-change")
        store.close()
        # 6,000 km over 306 days ≈ 19.6 km/day; 2,500 km left ≈ 128 days
        self.assertEqual(item.distance_left, 2500)
        self.assertTrue(120 <= (item.estimated_date - date(2026, 11, 3)).days <= 135)

    def test_fail_if_due_exit_code(self):
        self.ok("log", "oil-change", "--date", "2026-01-01", "--odometer", "60000")
        self.assertEqual(self.run_cli("due")[0], 0)
        self.assertEqual(self.run_cli("due", "--fail-if-due")[0], 1)

    def test_miles_car_uses_mile_intervals(self):
        self.ok("add-car", "truck", "--unit", "mi", "--odometer", "40000")
        self.ok("log", "oil-change", "--car", "truck", "--date", "2026-10-01", "--odometer", "40000")
        self.assertEqual(self.status("oil-change", car="truck")["next_odometer"], 45000)


class ErrorTests(Base):
    def test_usage_errors_exit_64(self):
        self.assertEqual(self.run_cli()[0], 64)
        self.assertEqual(self.run_cli("fly")[0], 64)

    def test_no_cars_message(self):
        code, _, err = self.run_cli("due")
        self.assertEqual(code, 2)
        self.assertIn("add-car", err)

    def test_newer_database_is_refused(self):
        s = Store(self.db)
        s.db.execute("UPDATE meta SET value = '99' WHERE key = 'schema'")
        s.db.commit()
        s.close()
        with self.assertRaises(StoreError):
            Store(self.db)


if __name__ == "__main__":
    unittest.main()
