# timetrack – CLI companion (Python)

A single-file Python command line tool that reads and writes the **same SQLite
database** as the Time Tracker Flutter app (`app_tracker.sqlite`, managed by
Drift). Track time from a terminal, produce reports and generate invoices
without opening the GUI.

Only the Python standard library is used – no `pip install` required
(Python 3.10+).

## Quick start

```sh
cd tools/timetrack_cli

# create a fresh database (or point --db at the one the app uses)
python3 timetrack.py --db ~/timetrack.sqlite init

python3 timetrack.py client add "ACME Corp" --email billing@acme.test --currency EUR
python3 timetrack.py project add "Website relaunch" --client 1 --rate 95 --limit 40

python3 timetrack.py start 1 "Fixing the checkout flow"
python3 timetrack.py status
python3 timetrack.py stop

python3 timetrack.py log 1 "Code review" --duration 45m --at "yesterday 16:00"
python3 timetrack.py report summary --period month --group project
python3 timetrack.py invoice create --client 1 --period last-month --due 21
```

Set `TIMETRACK_DB` to avoid passing `--db` every time. Without it the tool
guesses the platform path the Flutter app uses (`getApplicationSupportDirectory`).

## Commands

| Command | What it does |
| --- | --- |
| `init` | Create the database file and all tables |
| `client add/list/rm` | Manage clients (delete cascades to projects and entries) |
| `project add/list` | Manage projects, hourly rates and monthly time limits |
| `start` / `stop` / `status` | Live timer; `--force` switches from a running one |
| `log` | Record a finished entry by duration (`90m`, `1h30m`, `1:30`) |
| `entry list/rm/flag` | Inspect entries, delete them, toggle billable/billed/logged |
| `expense add/list` | Expenses, including mileage (`--distance` × `--cost-per-unit`) |
| `todo add/list/done` | The to-do list, with deadlines, priorities and estimates |
| `report summary` | Aggregate by project, client, category, day, week or month |
| `report budget` | How much of each monthly time limit is already used |
| `invoice create/list/show/status` | Invoice unbilled work; `--dry-run` previews it |
| `export entries\|expenses\|invoices` | CSV or JSON, to stdout or `--out FILE` |
| `info` | Database path, size and row counts |

### Periods

Every listing and report accepts `--period today|yesterday|week|last-week|
month|last-month|year|last-year|30d|all`, or an explicit `--from`/`--to` pair
(`YYYY-MM-DD`, `DD.MM.YYYY`, `today`, `-3d`, …).

## How it maps onto the app's schema

The DDL in `SCHEMA_STATEMENTS` mirrors `lib/database/database.dart` column by
column, including the cascade rules. `DateTime` columns are stored the way
Drift stores them (seconds since the Unix epoch); reading also tolerates the
textual storage mode. Invoice line items are serialised exactly like
`lib/models/line_item.dart` (`description` / `quantity` / `unitPrice`), so an
invoice created here opens and prints correctly in the Flutter app.

Creating an invoice picks up every **billable, not yet billed, finished** entry
of the client in the period, groups it per project at the project's hourly
rate, appends unbilled expenses as single line items, then marks all of them
billed so the next invoice only sees new work.

## Tests

```sh
cd tools/timetrack_cli
python3 -m unittest test_timetrack -v
```

46 tests cover the parsing helpers, the repositories, reporting, invoicing,
exports and the CLI end to end (against a temporary database – your data is
never touched).
