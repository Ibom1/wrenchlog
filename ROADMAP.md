# Roadmap

wrenchlog keeps track of car maintenance and tells you what's due next. It runs locally and stores no personal details.

## Status

| Milestone | Status | Estimate |
|---|---|---|
| v0.1 Track services, see what's due | ✅ done | |
| v0.2 Easier everyday use | not started | 6–8 h |
| v0.3 Smarter schedules | not started | 6–8 h |
| v0.4 Reminders and reports | not started | 7–10 h |
| v1.0 Ready for everyone | not started | 7–10 h |
| **Total planned** | | **26–36 h** |

Each item below is sized to be one or two commits.
Estimates include implementation, testing import and export round trips, and verifying database upgrades and installation across platforms.

## Principles

1. **Your data stays yours.** Local SQLite file, no accounts, no network, no owner details.
2. **Distance or time, whichever comes first,** for every service.
3. **Your manual wins.** Defaults are a starting point; every interval can be changed.
4. **Plain output.** Every line says what's due and why.
5. **Use made-up sample data only.** All examples, demos, screenshots, and tests use fictional data. Never include real personal or customer data.

---

## ✅ v0.1: Track services, see what's due

- [x] Cars with nickname, make, model, year, km or miles
- [x] Odometer readings that can't go backwards
- [x] Log services with date, odometer, cost and note; history; delete by number
- [x] Ten built-in services; change any interval or add new services per car; turn services off
- [x] `due`: overdue / soon / ok / no record, sorted by urgency, with a driving-pace estimate
- [x] Costs by year and by service
- [x] `--json` on reports, `due --fail-if-due`, exit codes 0 / 1 / 2 / 64
- [x] 28 tests, a demo script

## v0.2: Easier everyday use (6–8 h)

- [ ] `wrenchlog edit <id>` to fix a logged service's date, odometer, cost or note
- [ ] Log several services from one visit: `wrenchlog log oil-change tire-rotation --odometer 80000`
- [ ] Short aliases: `oil` for `oil-change`, `tires` for `tire-rotation`
- [ ] `wrenchlog status`: one line per car ("civic: 2 overdue, 1 soon") for a quick look
- [ ] Friendlier dates: `--date yesterday`, `--date 2026-05` (first of the month)
- [ ] Shell completion for bash and zsh

**Done when:** a visit with three services is logged in one command, a mistyped cost is fixed with `edit`, and each new command has tests.

## v0.3: Smarter schedules (6–8 h)

- [ ] **Severe driving** profile per car (towing, short trips, extreme cold) that shortens intervals by a set share
- [ ] **Schedule presets** in a JSON file: `wrenchlog schedule load presets/honda-civic-2018.json`, with a documented format and an example preset of made-up values
- [ ] **EV and hybrid** presets: no oil or spark plugs; tires, cabin filter, brake fluid and coolant remain
- [ ] Better pace: use the last 90 days of readings rather than all history, so a change in driving shows up
- [ ] Warn when the odometer hasn't been updated in 60 days, since distance estimates go stale

**Done when:** an EV preset shows no oil change, the severe profile halves the oil interval in a test, and a stale odometer produces a warning line.

## v0.4: Reminders and reports (7–10 h)

- [ ] `wrenchlog export --csv` and `wrenchlog import --csv` for history, with a sample CSV of made-up records
- [ ] `wrenchlog report --html` : a printable service record (handy when selling the car) grouped by year
- [ ] `wrenchlog remind --ics` : an iCalendar file with an event per upcoming time-based service, importable into any calendar app
- [ ] Monthly cost chart in the HTML report

**Done when:** an export → import round trip gives identical history, and the .ics file opens in a calendar app with one event per due service.

## v1.0: Ready for everyone (7–10 h)

- [ ] Publish to PyPI so `pipx install wrenchlog` works
- [ ] Database migrations: schema version 2 with an upgrade path tested from a v1 file
- [ ] Backups: `wrenchlog backup` copies the database with a date stamp
- [ ] CI on Linux, macOS and Windows, Python 3.9–3.13
- [ ] CHANGELOG and semantic versioning

## Later

- A small local web page (`wrenchlog serve`) for logging from a phone on the same Wi-Fi
- Reading the odometer from a photo of the dashboard

## Out of scope

- Owner details, licence plates, VINs or locations
- Accounts, cloud sync, or sending data anywhere
- Diagnosing problems or replacing a mechanic's advice
