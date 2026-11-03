# wrenchlog

Track your car's maintenance and see what's due next. Log oil changes, tire rotations, brakes and anything else, and wrenchlog tells you what's overdue, what's coming up, and roughly when, based on how much you actually drive. Everything stays in a small database on your own computer.

```
$ wrenchlog due
civic (2018 Honda Civic) · 78,900 km
  OVERDUE  Wiper blades           2 weeks late (was due 2026-10-20)  · last 2025-10-20
  OVERDUE  Oil and filter change  400 km over or 2 days late (was due 2026-11-01)  · last 2026-05-01 at 70,500 km
  OVERDUE  Tire rotation          in 1,600 km or 2 days late (was due 2026-11-01)  · last 2026-05-01 at 70,500 km
  SOON     Brake inspection       in 1,100 km (about 3 weeks at your pace) or by 2026-12-15  · last 2025-12-15 at 60,000 km
  --       Battery test           no record yet
  ...
```

## Who it's for

Car owners who want to stop guessing when the last oil change was, and people who look after more than one car. Service is due by distance *or* time, whichever comes first, and that's easy to lose track of. Missed maintenance turns cheap jobs into expensive repairs.

## What it does

- **What's due:** every service is checked against its distance and time interval and marked `OVERDUE`, `SOON` (within 30 days or the last 10% of the distance) or `OK`, most urgent first.
- **When, at your pace:** from your odometer readings, wrenchlog estimates when you'll reach the next distance milestone ("about 3 weeks at your pace").
- **History and costs:** every service with date, odometer, cost and notes; spending by year and by service.
- **Your schedule:** ten common services built in, each interval changeable per car, plus any service you add (transmission fluid, timing belt, ...).
- **Several cars,** in kilometres or miles.
- **`--json`** on every report, and `due --fail-if-due` to use it in a script or a daily reminder.

### Built-in schedule

| Service | Every |
|---|---|
| `oil-change` | 8,000 km or 6 months |
| `tire-rotation` | 10,000 km or 6 months |
| `brake-inspection` | 20,000 km or 12 months |
| `cabin-filter` | 20,000 km or 12 months |
| `engine-air-filter` | 30,000 km or 24 months |
| `wiper-blades`, `battery-check` | 12 months |
| `brake-fluid` | 24 months |
| `coolant` | 100,000 km or 60 months |
| `spark-plugs` | 100,000 km |

These are typical values, not your manufacturer's schedule. **Your owner's manual wins**; set its intervals with `wrenchlog interval`. Miles cars get the same intervals converted and rounded (8,000 km → 5,000 mi).

## Privacy

wrenchlog stores a nickname, make, model and year for each car, plus odometer readings and service records. There are no fields for owner names, licence plates, VINs or addresses; a test checks the table has only those columns. The database lives at `~/.wrenchlog/wrenchlog.db` (or wherever `--db` / `WRENCHLOG_DB` points) and never leaves your computer.

## Install and run

Requires Python 3.9+. No other dependencies.

```bash
git clone https://github.com/Ibom1/wrenchlog.git
cd wrenchlog
sh examples/demo.sh            # try it on a made-up car
pip install -e .               # installs the `wrenchlog` command
```

### Everyday use

```bash
wrenchlog add-car civic --make Honda --model Civic --year 2018 --odometer 78900
wrenchlog log oil-change --date 2026-05-01 --odometer 70500 --cost 79.99
wrenchlog odometer 79400                      # whenever you fill up, or once a month
wrenchlog due                                 # what needs doing
wrenchlog history                             # what's been done
wrenchlog costs                               # what it's cost
wrenchlog interval oil-change --every-distance 5000 --every-months 6
wrenchlog interval timing-belt --name "Timing belt" --every-distance 160000
wrenchlog services                            # list services and intervals
```

With one car, `--car` is optional; with several, add `--car <nickname>`.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Done |
| 1 | `due --fail-if-due` found something overdue or due soon |
| 2 | Couldn't do it (unknown car, odometer going backwards, ...) |
| 64 | Wrong usage (bad date, unknown service, ...) |

## Built with

Python standard library only: `sqlite3`, `argparse`, `datetime`. Tests use `unittest` with a fresh database per test:

```bash
python -m unittest
```

## Project layout

```
wrenchlog/schedule.py  built-in services and intervals, km/mi conversion
wrenchlog/store.py     SQLite storage: cars, odometer readings, services, custom intervals
wrenchlog/due.py       what's due, when, and the driving-pace estimate
wrenchlog/cli.py       the commands and their text / JSON output
examples/demo.sh       a demo with a made-up car
tests/                 tests
```

## License

[MIT](LICENSE)
