#!/usr/bin/env python3
"""timetrack - a command line companion for the Time Tracker Flutter app.

The Flutter application stores everything in a single SQLite file managed by
Drift (``app_tracker.sqlite``).  This script speaks the exact same schema, so
it can be used to track time from a terminal, produce reports and generate
invoices without opening the GUI.

Everything here is standard library only: no third party dependency is needed.

Usage examples::

    timetrack.py init
    timetrack.py client add "ACME Corp" --email billing@acme.test --currency EUR
    timetrack.py project add "Website relaunch" --client 1 --rate 95
    timetrack.py start 1 "Fixing the checkout flow" --category Development
    timetrack.py status
    timetrack.py stop
    timetrack.py log 1 "Code review" --duration 45m --at "yesterday 16:00"
    timetrack.py report summary --period month --group project
    timetrack.py invoice create --client 1 --period last-month --due 14
    timetrack.py export entries --format csv --out entries.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable, Sequence

__version__ = "1.0.0"

APP_DB_FILENAME = "app_tracker.sqlite"
DEFAULT_CATEGORY = "Development"
DEFAULT_CURRENCY = "USD"
DEFAULT_PAYMENT_TERMS_DAYS = 14

CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "BRL": "R$",
    "CHF": "CHF ",
    "JPY": "¥",
}

INVOICE_STATUSES = ("Draft", "Sent", "Paid", "Overdue")
TODO_PRIORITIES = ("Low", "Medium", "High")
PROJECT_STATUSES = ("Active", "Archived")


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------
class AppError(Exception):
    """Raised for every problem that is the user's to fix (bad input, ...)."""


class NotFound(AppError):
    """Raised when a referenced row does not exist."""


# --------------------------------------------------------------------------
# Schema (mirrors lib/database/database.dart)
# --------------------------------------------------------------------------
SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT,
        address TEXT,
        currency TEXT NOT NULL DEFAULT 'USD'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL REFERENCES clients (id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        hourly_rate REAL NOT NULL,
        monthly_time_limit INTEGER,
        status TEXT NOT NULL DEFAULT 'Active'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS time_entries (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
        description TEXT NOT NULL,
        start_time INTEGER NOT NULL,
        end_time INTEGER,
        category TEXT NOT NULL,
        is_billable INTEGER NOT NULL DEFAULT 1 CHECK (is_billable IN (0, 1)),
        is_billed INTEGER NOT NULL DEFAULT 0 CHECK (is_billed IN (0, 1)),
        is_logged INTEGER NOT NULL DEFAULT 0 CHECK (is_logged IN (0, 1))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        description TEXT NOT NULL,
        project_id INTEGER REFERENCES projects (id) ON DELETE CASCADE,
        client_id INTEGER REFERENCES clients (id) ON DELETE CASCADE,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        date INTEGER NOT NULL,
        distance REAL,
        cost_per_unit REAL,
        is_billed INTEGER NOT NULL DEFAULT 0 CHECK (is_billed IN (0, 1))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        invoice_id_string TEXT NOT NULL,
        client_id INTEGER NOT NULL REFERENCES clients (id) ON DELETE CASCADE,
        issue_date INTEGER NOT NULL,
        due_date INTEGER NOT NULL,
        total_amount REAL NOT NULL,
        status TEXT NOT NULL,
        notes TEXT,
        line_items_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS todos (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        project_id INTEGER NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
        category TEXT NOT NULL,
        deadline INTEGER NOT NULL,
        priority TEXT NOT NULL,
        is_completed INTEGER NOT NULL DEFAULT 0 CHECK (is_completed IN (0, 1)),
        start_time INTEGER NOT NULL,
        estimated_hours REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS company_settings (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        company_name TEXT NOT NULL,
        company_address TEXT NOT NULL,
        logo_path TEXT,
        show_letterhead INTEGER NOT NULL DEFAULT 1 CHECK (show_letterhead IN (0, 1))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_time_entries_project ON time_entries (project_id)",
    "CREATE INDEX IF NOT EXISTS idx_time_entries_start ON time_entries (start_time)",
    "CREATE INDEX IF NOT EXISTS idx_expenses_project ON expenses (project_id)",
    "CREATE INDEX IF NOT EXISTS idx_todos_project ON todos (project_id)",
)


# --------------------------------------------------------------------------
# Date / duration helpers
# --------------------------------------------------------------------------
_DURATION_RE = re.compile(
    r"^(?:(?P<hours>\d+(?:\.\d+)?)\s*h)?\s*(?:(?P<minutes>\d+(?:\.\d+)?)\s*m(?:in)?)?"
    r"\s*(?:(?P<seconds>\d+(?:\.\d+)?)\s*s)?$",
    re.IGNORECASE,
)
_CLOCK_RE = re.compile(r"^(?P<hours>\d{1,3}):(?P<minutes>\d{2})(?::(?P<seconds>\d{2}))?$")
_TIME_ONLY_RE = re.compile(r"^(?P<hours>\d{1,2}):(?P<minutes>\d{2})$")


def now() -> datetime:
    """Current local time, timezone aware (so arithmetic never surprises us)."""
    return datetime.now().astimezone()


def parse_duration(text: str) -> timedelta:
    """Parse ``2h``, ``90m``, ``1h30m``, ``1:30``, ``1.5h`` or a bare minute count."""
    raw = (text or "").strip()
    if not raw:
        raise AppError("empty duration")

    clock = _CLOCK_RE.match(raw)
    if clock:
        return timedelta(
            hours=int(clock.group("hours")),
            minutes=int(clock.group("minutes")),
            seconds=int(clock.group("seconds") or 0),
        )

    if re.fullmatch(r"\d+(?:\.\d+)?", raw):
        return timedelta(minutes=float(raw))

    match = _DURATION_RE.match(raw)
    if not match or not any(match.groupdict().values()):
        raise AppError(f"cannot read duration {text!r} (try 90m, 1h30m or 1:30)")

    return timedelta(
        hours=float(match.group("hours") or 0),
        minutes=float(match.group("minutes") or 0),
        seconds=float(match.group("seconds") or 0),
    )


def format_duration(value: timedelta | float | int) -> str:
    """Render a duration as ``7h 05m`` (or ``12m`` when below one hour)."""
    seconds = int(value.total_seconds()) if isinstance(value, timedelta) else int(value)
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours:
        return f"{sign}{hours}h {minutes:02d}m"
    return f"{sign}{minutes}m"


def format_hours(seconds: float) -> str:
    return f"{seconds / 3600:.2f}"


def parse_date(text: str, *, reference: date | None = None) -> date:
    """Parse ``today``, ``yesterday``, ``tomorrow``, ``-3d`` or ``2026-08-22``."""
    today = reference or now().date()
    raw = (text or "").strip().lower()
    if raw in {"today", "hoje"}:
        return today
    if raw in {"yesterday", "ontem"}:
        return today - timedelta(days=1)
    if raw in {"tomorrow", "amanha", "amanhã"}:
        return today + timedelta(days=1)

    offset = re.fullmatch(r"([+-]\d+)\s*d", raw)
    if offset:
        return today + timedelta(days=int(offset.group(1)))

    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    raise AppError(f"cannot read date {text!r} (try 2026-08-22, today or yesterday)")


def parse_datetime(text: str, *, reference: datetime | None = None) -> datetime:
    """Parse ``now``, ``14:30``, ``yesterday 16:00`` or a full ISO timestamp."""
    ref = reference or now()
    raw = (text or "").strip()
    if not raw or raw.lower() in {"now", "agora"}:
        return ref

    clock = _TIME_ONLY_RE.match(raw)
    if clock:
        moment = time(int(clock.group("hours")), int(clock.group("minutes")))
        return datetime.combine(ref.date(), moment).replace(tzinfo=ref.tzinfo)

    parts = raw.split()
    if len(parts) == 2 and _TIME_ONLY_RE.match(parts[1]):
        day = parse_date(parts[0], reference=ref.date())
        clock = _TIME_ONLY_RE.match(parts[1])
        assert clock is not None  # guarded by the condition above
        moment = time(int(clock.group("hours")), int(clock.group("minutes")))
        return datetime.combine(day, moment).replace(tzinfo=ref.tzinfo)

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return datetime.combine(parse_date(raw, reference=ref.date()), time(0, 0)).replace(
            tzinfo=ref.tzinfo
        )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ref.tzinfo)
    return parsed


def start_of_day(value: date, *, tzinfo=None) -> datetime:
    return datetime.combine(value, time(0, 0)).replace(tzinfo=tzinfo or now().tzinfo)


def end_of_day(value: date, *, tzinfo=None) -> datetime:
    return datetime.combine(value, time(23, 59, 59, 999999)).replace(
        tzinfo=tzinfo or now().tzinfo
    )


def month_bounds(anchor: date) -> tuple[date, date]:
    first = anchor.replace(day=1)
    if first.month == 12:
        next_first = first.replace(year=first.year + 1, month=1)
    else:
        next_first = first.replace(month=first.month + 1)
    return first, next_first - timedelta(days=1)


def resolve_period(
    name: str | None,
    since: str | None,
    until: str | None,
    *,
    reference: date | None = None,
) -> tuple[datetime | None, datetime | None, str]:
    """Turn ``--period``/``--from``/``--to`` into a concrete datetime window.

    Returns ``(start, end, label)``; ``None`` bounds mean "unbounded".
    """
    today = reference or now().date()

    if since or until:
        start = start_of_day(parse_date(since, reference=today)) if since else None
        end = end_of_day(parse_date(until, reference=today)) if until else None
        if start and end and start > end:
            raise AppError("--from must not be after --to")
        label = f"{start.date() if start else '...'} → {end.date() if end else '...'}"
        return start, end, label

    period = (name or "all").strip().lower()
    if period == "all":
        return None, None, "all time"
    if period == "today":
        return start_of_day(today), end_of_day(today), str(today)
    if period == "yesterday":
        day = today - timedelta(days=1)
        return start_of_day(day), end_of_day(day), str(day)
    if period in {"week", "this-week"}:
        first = today - timedelta(days=today.weekday())
        return start_of_day(first), end_of_day(first + timedelta(days=6)), f"week of {first}"
    if period == "last-week":
        first = today - timedelta(days=today.weekday() + 7)
        return start_of_day(first), end_of_day(first + timedelta(days=6)), f"week of {first}"
    if period in {"month", "this-month"}:
        first, last = month_bounds(today)
        return start_of_day(first), end_of_day(last), first.strftime("%B %Y")
    if period == "last-month":
        first, _ = month_bounds(today)
        first, last = month_bounds(first - timedelta(days=1))
        return start_of_day(first), end_of_day(last), first.strftime("%B %Y")
    if period in {"year", "this-year"}:
        first = date(today.year, 1, 1)
        return start_of_day(first), end_of_day(date(today.year, 12, 31)), str(today.year)
    if period == "last-year":
        year = today.year - 1
        return start_of_day(date(year, 1, 1)), end_of_day(date(year, 12, 31)), str(year)

    days = re.fullmatch(r"(\d+)\s*d", period)
    if days:
        span = int(days.group(1))
        first = today - timedelta(days=span - 1)
        return start_of_day(first), end_of_day(today), f"last {span} days"

    raise AppError(f"unknown period {name!r}")


def to_db_timestamp(value: datetime) -> int:
    """Drift stores ``DateTime`` columns as seconds since the Unix epoch."""
    if value.tzinfo is None:
        value = value.astimezone()
    return int(value.timestamp())


def from_db_timestamp(value: Any) -> datetime | None:
    """Read a Drift timestamp, tolerating the textual storage mode as well."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).astimezone()
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise AppError(f"unreadable timestamp in database: {value!r}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc).astimezone()


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    """``plural(1, 'entry', 'entries')`` -> ``'1 entry'``."""
    word = singular if count == 1 else (plural_form or f"{singular}s")
    return f"{count} {word}"


def format_money(amount: float, currency: str = DEFAULT_CURRENCY) -> str:
    symbol = CURRENCY_SYMBOLS.get(currency.upper(), f"{currency.upper()} ")
    return f"{symbol}{amount:,.2f}"


# --------------------------------------------------------------------------
# Terminal rendering
# --------------------------------------------------------------------------
class Ansi:
    """Tiny colour helper that disables itself when the output is piped."""

    enabled = True

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"

    @classmethod
    def configure(cls, stream=sys.stdout, *, force: bool | None = None) -> None:
        if force is not None:
            cls.enabled = force
            return
        cls.enabled = bool(getattr(stream, "isatty", lambda: False)()) and "NO_COLOR" not in os.environ

    @classmethod
    def paint(cls, text: str, *codes: str) -> str:
        if not cls.enabled or not codes:
            return text
        return "".join(codes) + text + cls.RESET


def render_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    aligns: Sequence[str] | None = None,
    empty: str = "(nothing to show)",
) -> str:
    """Render a fixed width ASCII table."""
    if not rows:
        return Ansi.paint(empty, Ansi.DIM)

    cells = [[("" if value is None else str(value)) for value in row] for row in rows]
    aligns = list(aligns or ["left"] * len(headers))
    aligns += ["left"] * (len(headers) - len(aligns))
    widths = [len(str(header)) for header in headers]
    for row in cells:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def justify(value: str, index: int) -> str:
        if aligns[index] == "right":
            return value.rjust(widths[index])
        if aligns[index] == "center":
            return value.center(widths[index])
        return value.ljust(widths[index])

    lines = [
        "  ".join(Ansi.paint(justify(str(header), index), Ansi.BOLD) for index, header in enumerate(headers)),
        "  ".join("-" * width for width in widths),
    ]
    lines.extend("  ".join(justify(value, index) for index, value in enumerate(row)) for row in cells)
    return "\n".join(lines)


def render_bars(
    pairs: Sequence[tuple[str, float]],
    *,
    width: int = 32,
    formatter: Callable[[float], str] = lambda value: f"{value:.2f}",
) -> str:
    """Render a horizontal bar chart made of block characters."""
    if not pairs:
        return Ansi.paint("(no data)", Ansi.DIM)
    peak = max((abs(value) for _, value in pairs), default=0.0) or 1.0
    label_width = max(len(label) for label, _ in pairs)
    lines = []
    for label, value in pairs:
        filled = int(round(width * abs(value) / peak))
        bar = "█" * filled if filled else "▏"
        lines.append(f"{label.ljust(label_width)}  {Ansi.paint(bar, Ansi.CYAN)} {formatter(value)}")
    return "\n".join(lines)


def echo(message: str = "") -> None:
    print(message)


# --------------------------------------------------------------------------
# Database access
# --------------------------------------------------------------------------
def default_db_path() -> str:
    """Best guess for the location the Flutter app uses on this platform."""
    override = os.environ.get("TIMETRACK_DB")
    if override:
        return os.path.expanduser(override)

    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        base = os.path.join(home, "Library", "Application Support", "com.example.timeTracker")
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA", home), "com.example", "time_tracker")
    else:
        base = os.path.join(
            os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local", "share")),
            "com.example.time_tracker",
        )
    return os.path.join(base, APP_DB_FILENAME)


class Database:
    """Thin wrapper around :mod:`sqlite3` with the app's conventions applied."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._connection: sqlite3.Connection | None = None

    # -- lifecycle ------------------------------------------------------
    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise AppError("database is not open")
        return self._connection

    def open(self, *, create: bool = False) -> "Database":
        if self.path != ":memory:" and not os.path.exists(self.path):
            if not create:
                raise AppError(
                    f"no database at {self.path}\n"
                    "Run 'timetrack.py init' or point --db at the app's app_tracker.sqlite."
                )
            parent = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(parent, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        return self

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- helpers --------------------------------------------------------
    def create_schema(self) -> None:
        with self.connection:
            for statement in SCHEMA_STATEMENTS:
                self.connection.execute(statement)

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return list(self.connection.execute(sql, tuple(params)))

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        rows = self.connection.execute(sql, tuple(params)).fetchone()
        return rows

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self.connection:
            return self.connection.execute(sql, tuple(params))

    def insert(self, sql: str, params: Sequence[Any] = ()) -> int:
        cursor = self.execute(sql, params)
        return int(cursor.lastrowid or 0)

    def tables(self) -> list[str]:
        rows = self.query("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
        return [row["name"] for row in rows if not row["name"].startswith("sqlite_")]


# --------------------------------------------------------------------------
# Domain models
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Client:
    id: int
    name: str
    email: str | None
    address: str | None
    currency: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Client":
        return cls(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            address=row["address"],
            currency=row["currency"] or DEFAULT_CURRENCY,
        )


@dataclass(frozen=True)
class Project:
    id: int
    client_id: int
    name: str
    hourly_rate: float
    monthly_time_limit: int | None
    status: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Project":
        return cls(
            id=row["id"],
            client_id=row["client_id"],
            name=row["name"],
            hourly_rate=float(row["hourly_rate"]),
            monthly_time_limit=row["monthly_time_limit"],
            status=row["status"] or "Active",
        )


@dataclass(frozen=True)
class TimeEntry:
    id: int
    project_id: int
    description: str
    start_time: datetime
    end_time: datetime | None
    category: str
    is_billable: bool
    is_billed: bool
    is_logged: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TimeEntry":
        start = from_db_timestamp(row["start_time"])
        assert start is not None  # start_time is NOT NULL in the schema
        return cls(
            id=row["id"],
            project_id=row["project_id"],
            description=row["description"],
            start_time=start,
            end_time=from_db_timestamp(row["end_time"]),
            category=row["category"],
            is_billable=bool(row["is_billable"]),
            is_billed=bool(row["is_billed"]),
            is_logged=bool(row["is_logged"]),
        )

    @property
    def running(self) -> bool:
        return self.end_time is None

    def duration(self, *, reference: datetime | None = None) -> timedelta:
        end = self.end_time or reference or now()
        return max(end - self.start_time, timedelta(0))


@dataclass(frozen=True)
class Expense:
    id: int
    description: str
    project_id: int | None
    client_id: int | None
    category: str
    amount: float
    date: datetime
    distance: float | None
    cost_per_unit: float | None
    is_billed: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Expense":
        moment = from_db_timestamp(row["date"])
        assert moment is not None
        return cls(
            id=row["id"],
            description=row["description"],
            project_id=row["project_id"],
            client_id=row["client_id"],
            category=row["category"],
            amount=float(row["amount"]),
            date=moment,
            distance=row["distance"],
            cost_per_unit=row["cost_per_unit"],
            is_billed=bool(row["is_billed"]),
        )


@dataclass(frozen=True)
class Invoice:
    id: int
    invoice_id_string: str
    client_id: int
    issue_date: datetime
    due_date: datetime
    total_amount: float
    status: str
    notes: str | None
    line_items: list[dict[str, Any]]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Invoice":
        issued = from_db_timestamp(row["issue_date"])
        due = from_db_timestamp(row["due_date"])
        assert issued is not None and due is not None
        raw_items = row["line_items_json"]
        try:
            items = json.loads(raw_items) if raw_items else []
        except json.JSONDecodeError:
            items = []
        return cls(
            id=row["id"],
            invoice_id_string=row["invoice_id_string"],
            client_id=row["client_id"],
            issue_date=issued,
            due_date=due,
            total_amount=float(row["total_amount"]),
            status=row["status"],
            notes=row["notes"],
            line_items=items,
        )


@dataclass(frozen=True)
class Todo:
    id: int
    title: str
    description: str | None
    project_id: int
    category: str
    deadline: datetime
    priority: str
    is_completed: bool
    start_time: datetime
    estimated_hours: float | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Todo":
        deadline = from_db_timestamp(row["deadline"])
        start = from_db_timestamp(row["start_time"])
        assert deadline is not None and start is not None
        return cls(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            project_id=row["project_id"],
            category=row["category"],
            deadline=deadline,
            priority=row["priority"],
            is_completed=bool(row["is_completed"]),
            start_time=start,
            estimated_hours=row["estimated_hours"],
        )


@dataclass(frozen=True)
class LineItem:
    """Matches ``lib/models/line_item.dart`` so the app can render it."""

    description: str
    quantity: float
    unit_price: float

    @property
    def total(self) -> float:
        return self.quantity * self.unit_price

    def to_json(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "quantity": round(self.quantity, 4),
            "unitPrice": round(self.unit_price, 4),
        }


# --------------------------------------------------------------------------
# Repositories
# --------------------------------------------------------------------------
class ClientRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, name: str, email: str | None, address: str | None, currency: str) -> int:
        return self.db.insert(
            "INSERT INTO clients (name, email, address, currency) VALUES (?, ?, ?, ?)",
            (name, email, address, currency.upper()),
        )

    def list(self) -> list[Client]:
        return [Client.from_row(row) for row in self.db.query("SELECT * FROM clients ORDER BY name")]

    def get(self, client_id: int) -> Client:
        row = self.db.query_one("SELECT * FROM clients WHERE id = ?", (client_id,))
        if row is None:
            raise NotFound(f"client {client_id} does not exist")
        return Client.from_row(row)

    def find_by_name(self, needle: str) -> list[Client]:
        rows = self.db.query("SELECT * FROM clients WHERE name LIKE ? ORDER BY name", (f"%{needle}%",))
        return [Client.from_row(row) for row in rows]

    def update(self, client_id: int, **fields: Any) -> None:
        self.get(client_id)
        assignments = {key: value for key, value in fields.items() if value is not None}
        if not assignments:
            return
        clause = ", ".join(f"{key} = ?" for key in assignments)
        self.db.execute(
            f"UPDATE clients SET {clause} WHERE id = ?", (*assignments.values(), client_id)
        )

    def delete(self, client_id: int) -> None:
        self.get(client_id)
        self.db.execute("DELETE FROM clients WHERE id = ?", (client_id,))


class ProjectRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(
        self,
        client_id: int,
        name: str,
        hourly_rate: float,
        monthly_time_limit: int | None = None,
        status: str = "Active",
    ) -> int:
        return self.db.insert(
            "INSERT INTO projects (client_id, name, hourly_rate, monthly_time_limit, status)"
            " VALUES (?, ?, ?, ?, ?)",
            (client_id, name, hourly_rate, monthly_time_limit, status),
        )

    def list(self, *, client_id: int | None = None, status: str | None = None) -> list[Project]:
        sql = "SELECT * FROM projects"
        clauses: list[str] = []
        params: list[Any] = []
        if client_id is not None:
            clauses.append("client_id = ?")
            params.append(client_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY name"
        return [Project.from_row(row) for row in self.db.query(sql, params)]

    def get(self, project_id: int) -> Project:
        row = self.db.query_one("SELECT * FROM projects WHERE id = ?", (project_id,))
        if row is None:
            raise NotFound(f"project {project_id} does not exist")
        return Project.from_row(row)

    def update(self, project_id: int, **fields: Any) -> None:
        self.get(project_id)
        assignments = {key: value for key, value in fields.items() if value is not None}
        if not assignments:
            return
        clause = ", ".join(f"{key} = ?" for key in assignments)
        self.db.execute(
            f"UPDATE projects SET {clause} WHERE id = ?", (*assignments.values(), project_id)
        )

    def delete(self, project_id: int) -> None:
        self.get(project_id)
        self.db.execute("DELETE FROM projects WHERE id = ?", (project_id,))


class TimeEntryRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(
        self,
        project_id: int,
        description: str,
        start: datetime,
        end: datetime | None,
        category: str = DEFAULT_CATEGORY,
        *,
        billable: bool = True,
    ) -> int:
        if end is not None and end < start:
            raise AppError("the end of an entry cannot be before its start")
        return self.db.insert(
            "INSERT INTO time_entries"
            " (project_id, description, start_time, end_time, category, is_billable, is_billed, is_logged)"
            " VALUES (?, ?, ?, ?, ?, ?, 0, 0)",
            (
                project_id,
                description,
                to_db_timestamp(start),
                to_db_timestamp(end) if end else None,
                category,
                1 if billable else 0,
            ),
        )

    def get(self, entry_id: int) -> TimeEntry:
        row = self.db.query_one("SELECT * FROM time_entries WHERE id = ?", (entry_id,))
        if row is None:
            raise NotFound(f"time entry {entry_id} does not exist")
        return TimeEntry.from_row(row)

    def running(self) -> TimeEntry | None:
        row = self.db.query_one(
            "SELECT * FROM time_entries WHERE end_time IS NULL ORDER BY start_time DESC LIMIT 1"
        )
        return TimeEntry.from_row(row) if row else None

    def stop(self, entry_id: int, end: datetime) -> None:
        entry = self.get(entry_id)
        if not entry.running:
            raise AppError(f"time entry {entry_id} is already stopped")
        if end < entry.start_time:
            raise AppError("cannot stop an entry before it started")
        self.db.execute(
            "UPDATE time_entries SET end_time = ? WHERE id = ?", (to_db_timestamp(end), entry_id)
        )

    def list(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        project_id: int | None = None,
        client_id: int | None = None,
        billable_only: bool = False,
        unbilled_only: bool = False,
        include_running: bool = True,
        limit: int | None = None,
    ) -> list[TimeEntry]:
        sql = (
            "SELECT time_entries.* FROM time_entries"
            " JOIN projects ON projects.id = time_entries.project_id"
        )
        clauses: list[str] = []
        params: list[Any] = []
        if start is not None:
            clauses.append("time_entries.start_time >= ?")
            params.append(to_db_timestamp(start))
        if end is not None:
            clauses.append("time_entries.start_time <= ?")
            params.append(to_db_timestamp(end))
        if project_id is not None:
            clauses.append("time_entries.project_id = ?")
            params.append(project_id)
        if client_id is not None:
            clauses.append("projects.client_id = ?")
            params.append(client_id)
        if billable_only:
            clauses.append("time_entries.is_billable = 1")
        if unbilled_only:
            clauses.append("time_entries.is_billed = 0")
        if not include_running:
            clauses.append("time_entries.end_time IS NOT NULL")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY time_entries.start_time DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [TimeEntry.from_row(row) for row in self.db.query(sql, params)]

    def mark_billed(self, entry_ids: Iterable[int]) -> int:
        ids = list(entry_ids)
        if not ids:
            return 0
        placeholders = ", ".join("?" for _ in ids)
        cursor = self.db.execute(
            f"UPDATE time_entries SET is_billed = 1 WHERE id IN ({placeholders})", ids
        )
        return cursor.rowcount

    def set_flags(self, entry_id: int, **flags: bool) -> None:
        self.get(entry_id)
        allowed = {"is_billable", "is_billed", "is_logged"}
        assignments = {key: value for key, value in flags.items() if key in allowed and value is not None}
        if not assignments:
            return
        clause = ", ".join(f"{key} = ?" for key in assignments)
        self.db.execute(
            f"UPDATE time_entries SET {clause} WHERE id = ?",
            (*[1 if value else 0 for value in assignments.values()], entry_id),
        )

    def delete(self, entry_id: int) -> None:
        self.get(entry_id)
        self.db.execute("DELETE FROM time_entries WHERE id = ?", (entry_id,))


class ExpenseRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(
        self,
        description: str,
        amount: float,
        moment: datetime,
        *,
        project_id: int | None = None,
        client_id: int | None = None,
        category: str = "General",
        distance: float | None = None,
        cost_per_unit: float | None = None,
    ) -> int:
        if distance is not None and cost_per_unit is not None:
            amount = distance * cost_per_unit
        return self.db.insert(
            "INSERT INTO expenses"
            " (description, project_id, client_id, category, amount, date, distance, cost_per_unit, is_billed)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (
                description,
                project_id,
                client_id,
                category,
                amount,
                to_db_timestamp(moment),
                distance,
                cost_per_unit,
            ),
        )

    def list(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        project_id: int | None = None,
        client_id: int | None = None,
        unbilled_only: bool = False,
    ) -> list[Expense]:
        sql = (
            "SELECT expenses.* FROM expenses"
            " LEFT JOIN projects ON projects.id = expenses.project_id"
        )
        clauses: list[str] = []
        params: list[Any] = []
        if start is not None:
            clauses.append("expenses.date >= ?")
            params.append(to_db_timestamp(start))
        if end is not None:
            clauses.append("expenses.date <= ?")
            params.append(to_db_timestamp(end))
        if project_id is not None:
            clauses.append("expenses.project_id = ?")
            params.append(project_id)
        if client_id is not None:
            clauses.append("(expenses.client_id = ? OR projects.client_id = ?)")
            params.extend([client_id, client_id])
        if unbilled_only:
            clauses.append("expenses.is_billed = 0")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY expenses.date DESC"
        return [Expense.from_row(row) for row in self.db.query(sql, params)]

    def mark_billed(self, expense_ids: Iterable[int]) -> int:
        ids = list(expense_ids)
        if not ids:
            return 0
        placeholders = ", ".join("?" for _ in ids)
        cursor = self.db.execute(
            f"UPDATE expenses SET is_billed = 1 WHERE id IN ({placeholders})", ids
        )
        return cursor.rowcount

    def delete(self, expense_id: int) -> None:
        self.db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))


class TodoRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(
        self,
        title: str,
        project_id: int,
        deadline: datetime,
        *,
        description: str | None = None,
        category: str = DEFAULT_CATEGORY,
        priority: str = "Medium",
        estimated_hours: float | None = None,
        start: datetime | None = None,
    ) -> int:
        return self.db.insert(
            "INSERT INTO todos"
            " (title, description, project_id, category, deadline, priority, is_completed, start_time, estimated_hours)"
            " VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (
                title,
                description,
                project_id,
                category,
                to_db_timestamp(deadline),
                priority,
                to_db_timestamp(start or now()),
                estimated_hours,
            ),
        )

    def list(self, *, project_id: int | None = None, open_only: bool = False) -> list[Todo]:
        sql = "SELECT * FROM todos"
        clauses: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        if open_only:
            clauses.append("is_completed = 0")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY is_completed, deadline"
        return [Todo.from_row(row) for row in self.db.query(sql, params)]

    def complete(self, todo_id: int, *, completed: bool = True) -> None:
        row = self.db.query_one("SELECT id FROM todos WHERE id = ?", (todo_id,))
        if row is None:
            raise NotFound(f"todo {todo_id} does not exist")
        self.db.execute("UPDATE todos SET is_completed = ? WHERE id = ?", (1 if completed else 0, todo_id))

    def delete(self, todo_id: int) -> None:
        self.db.execute("DELETE FROM todos WHERE id = ?", (todo_id,))


class InvoiceRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(
        self,
        invoice_id_string: str,
        client_id: int,
        issue_date: datetime,
        due_date: datetime,
        total_amount: float,
        status: str,
        notes: str | None,
        line_items: Sequence[LineItem],
    ) -> int:
        return self.db.insert(
            "INSERT INTO invoices"
            " (invoice_id_string, client_id, issue_date, due_date, total_amount, status, notes, line_items_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                invoice_id_string,
                client_id,
                to_db_timestamp(issue_date),
                to_db_timestamp(due_date),
                round(total_amount, 2),
                status,
                notes,
                json.dumps([item.to_json() for item in line_items]),
            ),
        )

    def list(self, *, client_id: int | None = None, status: str | None = None) -> list[Invoice]:
        sql = "SELECT * FROM invoices"
        clauses: list[str] = []
        params: list[Any] = []
        if client_id is not None:
            clauses.append("client_id = ?")
            params.append(client_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY issue_date DESC, id DESC"
        return [Invoice.from_row(row) for row in self.db.query(sql, params)]

    def get(self, invoice_id: int) -> Invoice:
        row = self.db.query_one("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
        if row is None:
            raise NotFound(f"invoice {invoice_id} does not exist")
        return Invoice.from_row(row)

    def set_status(self, invoice_id: int, status: str) -> None:
        if status not in INVOICE_STATUSES:
            raise AppError(f"unknown invoice status {status!r} (expected one of {', '.join(INVOICE_STATUSES)})")
        self.get(invoice_id)
        self.db.execute("UPDATE invoices SET status = ? WHERE id = ?", (status, invoice_id))

    def next_number(self, *, year: int) -> str:
        rows = self.db.query(
            "SELECT invoice_id_string FROM invoices WHERE invoice_id_string LIKE ?",
            (f"INV-{year}-%",),
        )
        highest = 0
        for row in rows:
            match = re.search(r"-(\d+)$", row["invoice_id_string"] or "")
            if match:
                highest = max(highest, int(match.group(1)))
        return f"INV-{year}-{highest + 1:04d}"


# --------------------------------------------------------------------------
# Services
# --------------------------------------------------------------------------
@dataclass
class Repositories:
    clients: ClientRepository
    projects: ProjectRepository
    entries: TimeEntryRepository
    expenses: ExpenseRepository
    todos: TodoRepository
    invoices: InvoiceRepository

    @classmethod
    def for_db(cls, db: Database) -> "Repositories":
        return cls(
            clients=ClientRepository(db),
            projects=ProjectRepository(db),
            entries=TimeEntryRepository(db),
            expenses=ExpenseRepository(db),
            todos=TodoRepository(db),
            invoices=InvoiceRepository(db),
        )


@dataclass
class ReportRow:
    key: str
    label: str
    seconds: float
    amount: float
    entry_count: int

    @property
    def hours(self) -> float:
        return self.seconds / 3600


class ReportService:
    """Aggregates time entries into the shapes the report command prints."""

    GROUPINGS = ("project", "client", "category", "day", "week", "month")

    def __init__(self, repos: Repositories) -> None:
        self.repos = repos

    def _bucket(self, entry: TimeEntry, project: Project, client: Client, grouping: str) -> tuple[str, str]:
        if grouping == "project":
            return f"project:{project.id}", f"{project.name} ({client.name})"
        if grouping == "client":
            return f"client:{client.id}", client.name
        if grouping == "category":
            return f"category:{entry.category}", entry.category
        if grouping == "day":
            key = entry.start_time.date().isoformat()
            return key, key
        if grouping == "week":
            iso = entry.start_time.isocalendar()
            key = f"{iso[0]}-W{iso[1]:02d}"
            return key, key
        if grouping == "month":
            key = entry.start_time.strftime("%Y-%m")
            return key, key
        raise AppError(f"unknown grouping {grouping!r}")

    def summarise(
        self,
        *,
        grouping: str = "project",
        start: datetime | None = None,
        end: datetime | None = None,
        client_id: int | None = None,
        project_id: int | None = None,
        billable_only: bool = False,
    ) -> list[ReportRow]:
        entries = self.repos.entries.list(
            start=start,
            end=end,
            client_id=client_id,
            project_id=project_id,
            billable_only=billable_only,
            include_running=False,
        )
        projects = {project.id: project for project in self.repos.projects.list()}
        clients = {client.id: client for client in self.repos.clients.list()}

        buckets: dict[str, ReportRow] = {}
        for entry in entries:
            project = projects.get(entry.project_id)
            if project is None:
                continue
            client = clients.get(project.client_id)
            if client is None:
                continue
            key, label = self._bucket(entry, project, client, grouping)
            seconds = entry.duration().total_seconds()
            amount = seconds / 3600 * project.hourly_rate if entry.is_billable else 0.0
            row = buckets.get(key)
            if row is None:
                buckets[key] = ReportRow(key, label, seconds, amount, 1)
            else:
                buckets[key] = ReportRow(
                    key, row.label, row.seconds + seconds, row.amount + amount, row.entry_count + 1
                )

        rows = list(buckets.values())
        if grouping in {"day", "week", "month"}:
            rows.sort(key=lambda row: row.key)
        else:
            rows.sort(key=lambda row: row.seconds, reverse=True)
        return rows

    def totals(self, rows: Sequence[ReportRow]) -> tuple[float, float]:
        return sum(row.seconds for row in rows), sum(row.amount for row in rows)

    def monthly_budget_status(self, *, anchor: date | None = None) -> list[dict[str, Any]]:
        """How much of each project's monthly time limit is already used."""
        anchor = anchor or now().date()
        first, last = month_bounds(anchor)
        start, end = start_of_day(first), end_of_day(last)
        report: list[dict[str, Any]] = []
        for project in self.repos.projects.list(status="Active"):
            if not project.monthly_time_limit:
                continue
            entries = self.repos.entries.list(
                start=start, end=end, project_id=project.id, include_running=False
            )
            used = sum(entry.duration().total_seconds() for entry in entries) / 3600
            limit = float(project.monthly_time_limit)
            report.append(
                {
                    "project": project,
                    "used_hours": used,
                    "limit_hours": limit,
                    "ratio": used / limit if limit else 0.0,
                }
            )
        report.sort(key=lambda item: item["ratio"], reverse=True)
        return report


@dataclass
class InvoiceDraft:
    client: Client
    line_items: list[LineItem]
    entry_ids: list[int]
    expense_ids: list[int]
    total: float
    number: str
    issue_date: datetime
    due_date: datetime
    notes: str | None


class InvoiceService:
    """Turns unbilled time entries and expenses into an invoice."""

    def __init__(self, repos: Repositories) -> None:
        self.repos = repos

    def build_draft(
        self,
        *,
        client_id: int,
        start: datetime | None,
        end: datetime | None,
        due_in_days: int = DEFAULT_PAYMENT_TERMS_DAYS,
        include_expenses: bool = True,
        notes: str | None = None,
        issue_date: datetime | None = None,
    ) -> InvoiceDraft:
        client = self.repos.clients.get(client_id)
        issued = issue_date or now()
        entries = self.repos.entries.list(
            start=start,
            end=end,
            client_id=client_id,
            billable_only=True,
            unbilled_only=True,
            include_running=False,
        )
        projects = {project.id: project for project in self.repos.projects.list(client_id=client_id)}

        grouped: dict[int, list[TimeEntry]] = {}
        for entry in entries:
            grouped.setdefault(entry.project_id, []).append(entry)

        line_items: list[LineItem] = []
        entry_ids: list[int] = []
        for project_id, project_entries in sorted(grouped.items()):
            project = projects.get(project_id)
            if project is None:
                continue
            hours = sum(entry.duration().total_seconds() for entry in project_entries) / 3600
            if hours <= 0:
                continue
            line_items.append(
                LineItem(
                    description=f"{project.name} – {plural(len(project_entries), 'entry', 'entries')}",
                    quantity=round(hours, 2),
                    unit_price=project.hourly_rate,
                )
            )
            entry_ids.extend(entry.id for entry in project_entries)

        expense_ids: list[int] = []
        if include_expenses:
            for expense in self.repos.expenses.list(
                start=start, end=end, client_id=client_id, unbilled_only=True
            ):
                line_items.append(
                    LineItem(
                        description=f"{expense.category}: {expense.description}",
                        quantity=1.0,
                        unit_price=round(expense.amount, 2),
                    )
                )
                expense_ids.append(expense.id)

        if not line_items:
            raise AppError("nothing to invoice: no unbilled billable work in that period")

        total = round(sum(item.total for item in line_items), 2)
        return InvoiceDraft(
            client=client,
            line_items=line_items,
            entry_ids=entry_ids,
            expense_ids=expense_ids,
            total=total,
            number=self.repos.invoices.next_number(year=issued.year),
            issue_date=issued,
            due_date=issued + timedelta(days=due_in_days),
            notes=notes,
        )

    def commit(self, draft: InvoiceDraft, *, status: str = "Draft") -> int:
        invoice_id = self.repos.invoices.add(
            draft.number,
            draft.client.id,
            draft.issue_date,
            draft.due_date,
            draft.total,
            status,
            draft.notes,
            draft.line_items,
        )
        self.repos.entries.mark_billed(draft.entry_ids)
        self.repos.expenses.mark_billed(draft.expense_ids)
        return invoice_id


class ExportService:
    """Writes entries, expenses or invoices as CSV or JSON."""

    def __init__(self, repos: Repositories) -> None:
        self.repos = repos

    def entries_rows(self, entries: Sequence[TimeEntry]) -> list[dict[str, Any]]:
        projects = {project.id: project for project in self.repos.projects.list()}
        clients = {client.id: client for client in self.repos.clients.list()}
        rows: list[dict[str, Any]] = []
        for entry in entries:
            project = projects.get(entry.project_id)
            client = clients.get(project.client_id) if project else None
            hours = entry.duration().total_seconds() / 3600
            rate = project.hourly_rate if project else 0.0
            rows.append(
                {
                    "id": entry.id,
                    "client": client.name if client else "",
                    "project": project.name if project else "",
                    "description": entry.description,
                    "category": entry.category,
                    "start": entry.start_time.isoformat(timespec="minutes"),
                    "end": entry.end_time.isoformat(timespec="minutes") if entry.end_time else "",
                    "hours": round(hours, 2),
                    "rate": rate,
                    "amount": round(hours * rate, 2) if entry.is_billable else 0.0,
                    "billable": entry.is_billable,
                    "billed": entry.is_billed,
                    "logged": entry.is_logged,
                }
            )
        return rows

    def expenses_rows(self, expenses: Sequence[Expense]) -> list[dict[str, Any]]:
        projects = {project.id: project for project in self.repos.projects.list()}
        return [
            {
                "id": expense.id,
                "date": expense.date.date().isoformat(),
                "project": projects[expense.project_id].name if expense.project_id in projects else "",
                "category": expense.category,
                "description": expense.description,
                "amount": round(expense.amount, 2),
                "distance": expense.distance or "",
                "cost_per_unit": expense.cost_per_unit or "",
                "billed": expense.is_billed,
            }
            for expense in expenses
        ]

    def invoices_rows(self, invoices: Sequence[Invoice]) -> list[dict[str, Any]]:
        clients = {client.id: client for client in self.repos.clients.list()}
        return [
            {
                "id": invoice.id,
                "number": invoice.invoice_id_string,
                "client": clients[invoice.client_id].name if invoice.client_id in clients else "",
                "issued": invoice.issue_date.date().isoformat(),
                "due": invoice.due_date.date().isoformat(),
                "total": round(invoice.total_amount, 2),
                "status": invoice.status,
                "items": len(invoice.line_items),
            }
            for invoice in invoices
        ]

    @staticmethod
    def write(rows: Sequence[dict[str, Any]], *, fmt: str, destination: str | None) -> str:
        if fmt == "json":
            payload = json.dumps(rows, indent=2, ensure_ascii=False)
        elif fmt == "csv":
            import io

            buffer = io.StringIO()
            fieldnames = list(rows[0].keys()) if rows else []
            writer = csv.DictWriter(buffer, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            payload = buffer.getvalue()
        else:
            raise AppError(f"unknown export format {fmt!r}")

        if destination:
            with open(destination, "w", encoding="utf-8", newline="") as handle:
                handle.write(payload)
        return payload


# --------------------------------------------------------------------------
# Command handlers
# --------------------------------------------------------------------------
@dataclass
class Context:
    db: Database
    repos: Repositories
    args: argparse.Namespace

    @property
    def reports(self) -> ReportService:
        return ReportService(self.repos)

    @property
    def invoicing(self) -> InvoiceService:
        return InvoiceService(self.repos)

    @property
    def exporting(self) -> ExportService:
        return ExportService(self.repos)

    def currency_for_project(self, project: Project) -> str:
        return self.repos.clients.get(project.client_id).currency

    def display_currency(self, *, client_id: int | None = None, project_id: int | None = None) -> str:
        """The currency to print totals in.

        A report can span several clients; only when they all agree does a
        single symbol mean anything, otherwise we fall back to the default.
        """
        if project_id is not None:
            return self.currency_for_project(self.repos.projects.get(project_id))
        if client_id is not None:
            return self.repos.clients.get(client_id).currency
        currencies = {client.currency for client in self.repos.clients.list()}
        return currencies.pop() if len(currencies) == 1 else DEFAULT_CURRENCY


def cmd_init(ctx: Context) -> int:
    ctx.db.create_schema()
    echo(Ansi.paint(f"Schema ready at {ctx.db.path}", Ansi.GREEN))
    echo("Tables: " + ", ".join(ctx.db.tables()))
    return 0


def cmd_client_add(ctx: Context) -> int:
    client_id = ctx.repos.clients.add(
        ctx.args.name, ctx.args.email, ctx.args.address, ctx.args.currency
    )
    echo(Ansi.paint(f"Client #{client_id} – {ctx.args.name}", Ansi.GREEN))
    return 0


def cmd_client_list(ctx: Context) -> int:
    clients = ctx.repos.clients.list()
    rows = []
    for client in clients:
        projects = ctx.repos.projects.list(client_id=client.id)
        rows.append([client.id, client.name, client.email or "-", client.currency, len(projects)])
    echo(
        render_table(
            ["ID", "Name", "Email", "Currency", "Projects"],
            rows,
            aligns=["right", "left", "left", "left", "right"],
            empty="No clients yet - add one with 'client add'.",
        )
    )
    return 0


def cmd_client_rm(ctx: Context) -> int:
    client = ctx.repos.clients.get(ctx.args.client_id)
    ctx.repos.clients.delete(client.id)
    echo(Ansi.paint(f"Deleted client #{client.id} ({client.name}) and its projects", Ansi.YELLOW))
    return 0


def cmd_project_add(ctx: Context) -> int:
    ctx.repos.clients.get(ctx.args.client)
    project_id = ctx.repos.projects.add(
        ctx.args.client, ctx.args.name, ctx.args.rate, ctx.args.limit, ctx.args.status
    )
    echo(Ansi.paint(f"Project #{project_id} – {ctx.args.name}", Ansi.GREEN))
    return 0


def cmd_project_list(ctx: Context) -> int:
    clients = {client.id: client for client in ctx.repos.clients.list()}
    rows = []
    for project in ctx.repos.projects.list(client_id=ctx.args.client, status=ctx.args.status):
        client = clients.get(project.client_id)
        currency = client.currency if client else DEFAULT_CURRENCY
        rows.append(
            [
                project.id,
                project.name,
                client.name if client else "?",
                format_money(project.hourly_rate, currency) + "/h",
                project.monthly_time_limit or "-",
                project.status,
            ]
        )
    echo(
        render_table(
            ["ID", "Project", "Client", "Rate", "Limit", "Status"],
            rows,
            aligns=["right", "left", "left", "right", "right", "left"],
            empty="No projects yet - add one with 'project add'.",
        )
    )
    return 0


def cmd_start(ctx: Context) -> int:
    running = ctx.repos.entries.running()
    if running is not None:
        if not ctx.args.force:
            raise AppError(
                f"timer #{running.id} is already running ({running.description}). "
                "Stop it first or pass --force to switch."
            )
        ctx.repos.entries.stop(running.id, now())
        echo(Ansi.paint(f"Stopped #{running.id} after {format_duration(running.duration())}", Ansi.YELLOW))

    project = ctx.repos.projects.get(ctx.args.project)
    start = parse_datetime(ctx.args.at) if ctx.args.at else now()
    entry_id = ctx.repos.entries.add(
        project.id,
        ctx.args.description,
        start,
        None,
        ctx.args.category,
        billable=not ctx.args.non_billable,
    )
    echo(
        Ansi.paint(
            f"▶ #{entry_id} {project.name}: {ctx.args.description} "
            f"(since {start.strftime('%H:%M')})",
            Ansi.GREEN,
        )
    )
    return 0


def cmd_stop(ctx: Context) -> int:
    running = ctx.repos.entries.running()
    if running is None:
        raise AppError("no timer is running")
    end = parse_datetime(ctx.args.at) if ctx.args.at else now()
    ctx.repos.entries.stop(running.id, end)
    entry = ctx.repos.entries.get(running.id)
    project = ctx.repos.projects.get(entry.project_id)
    amount = entry.duration().total_seconds() / 3600 * project.hourly_rate
    currency = ctx.currency_for_project(project)
    echo(
        Ansi.paint(
            f"■ #{entry.id} {project.name}: {format_duration(entry.duration())}"
            + (f" – {format_money(amount, currency)}" if entry.is_billable else " (non billable)"),
            Ansi.GREEN,
        )
    )
    return 0


def cmd_status(ctx: Context) -> int:
    running = ctx.repos.entries.running()
    if running is None:
        echo(Ansi.paint("No timer running.", Ansi.DIM))
    else:
        project = ctx.repos.projects.get(running.project_id)
        client = ctx.repos.clients.get(project.client_id)
        elapsed = running.duration()
        echo(
            Ansi.paint("▶ running  ", Ansi.GREEN)
            + f"#{running.id} {project.name} ({client.name}) – {running.description}"
        )
        echo(
            f"  started {running.start_time.strftime('%Y-%m-%d %H:%M')}"
            f"   elapsed {Ansi.paint(format_duration(elapsed), Ansi.BOLD)}"
            f"   value {format_money(elapsed.total_seconds() / 3600 * project.hourly_rate, client.currency)}"
        )

    start, end, _ = resolve_period("today", None, None)
    today_entries = ctx.repos.entries.list(start=start, end=end, include_running=True)
    total = sum(entry.duration().total_seconds() for entry in today_entries)
    echo()
    echo(f"Today: {Ansi.paint(format_duration(total), Ansi.BOLD)} across {plural(len(today_entries), 'entry', 'entries')}")
    return 0


def cmd_log(ctx: Context) -> int:
    project = ctx.repos.projects.get(ctx.args.project)
    duration = parse_duration(ctx.args.duration)
    if ctx.args.at:
        start = parse_datetime(ctx.args.at)
    else:
        start = now() - duration
    entry_id = ctx.repos.entries.add(
        project.id,
        ctx.args.description,
        start,
        start + duration,
        ctx.args.category,
        billable=not ctx.args.non_billable,
    )
    echo(
        Ansi.paint(
            f"Logged #{entry_id} – {format_duration(duration)} on {project.name} "
            f"({start.strftime('%Y-%m-%d %H:%M')})",
            Ansi.GREEN,
        )
    )
    return 0


def cmd_entry_list(ctx: Context) -> int:
    start, end, label = resolve_period(ctx.args.period, ctx.args.since, ctx.args.until)
    entries = ctx.repos.entries.list(
        start=start,
        end=end,
        project_id=ctx.args.project,
        client_id=ctx.args.client,
        unbilled_only=ctx.args.unbilled,
        limit=ctx.args.limit,
    )
    projects = {project.id: project for project in ctx.repos.projects.list()}
    rows = []
    for entry in entries:
        project = projects.get(entry.project_id)
        flags = "".join(
            [
                "B" if entry.is_billable else "-",
                "$" if entry.is_billed else "-",
                "L" if entry.is_logged else "-",
                "▶" if entry.running else " ",
            ]
        )
        rows.append(
            [
                entry.id,
                entry.start_time.strftime("%Y-%m-%d %H:%M"),
                format_duration(entry.duration()),
                project.name if project else "?",
                entry.category,
                entry.description[:48],
                flags,
            ]
        )
    echo(Ansi.paint(f"Time entries – {label}", Ansi.BOLD))
    echo(
        render_table(
            ["ID", "Start", "Duration", "Project", "Category", "Description", "Flags"],
            rows,
            aligns=["right", "left", "right", "left", "left", "left", "left"],
            empty="No entries in that period.",
        )
    )
    total = sum(entry.duration().total_seconds() for entry in entries)
    echo()
    echo(f"{plural(len(entries), 'entry', 'entries')}, {Ansi.paint(format_duration(total), Ansi.BOLD)} total")
    return 0


def cmd_entry_rm(ctx: Context) -> int:
    ctx.repos.entries.delete(ctx.args.entry_id)
    echo(Ansi.paint(f"Deleted time entry #{ctx.args.entry_id}", Ansi.YELLOW))
    return 0


def cmd_entry_flag(ctx: Context) -> int:
    flags: dict[str, bool] = {}
    if ctx.args.billed is not None:
        flags["is_billed"] = ctx.args.billed
    if ctx.args.billable is not None:
        flags["is_billable"] = ctx.args.billable
    if ctx.args.logged is not None:
        flags["is_logged"] = ctx.args.logged
    if not flags:
        raise AppError("nothing to change: pass --billed/--billable/--logged")
    ctx.repos.entries.set_flags(ctx.args.entry_id, **flags)
    echo(Ansi.paint(f"Updated time entry #{ctx.args.entry_id}", Ansi.GREEN))
    return 0


def cmd_expense_add(ctx: Context) -> int:
    moment = parse_datetime(ctx.args.at) if ctx.args.at else now()
    expense_id = ctx.repos.expenses.add(
        ctx.args.description,
        ctx.args.amount or 0.0,
        moment,
        project_id=ctx.args.project,
        client_id=ctx.args.client,
        category=ctx.args.category,
        distance=ctx.args.distance,
        cost_per_unit=ctx.args.cost_per_unit,
    )
    echo(Ansi.paint(f"Expense #{expense_id} recorded", Ansi.GREEN))
    return 0


def cmd_expense_list(ctx: Context) -> int:
    start, end, label = resolve_period(ctx.args.period, ctx.args.since, ctx.args.until)
    expenses = ctx.repos.expenses.list(
        start=start,
        end=end,
        project_id=ctx.args.project,
        client_id=ctx.args.client,
        unbilled_only=ctx.args.unbilled,
    )
    projects = {project.id: project for project in ctx.repos.projects.list()}
    rows = [
        [
            expense.id,
            expense.date.date().isoformat(),
            projects[expense.project_id].name if expense.project_id in projects else "-",
            expense.category,
            expense.description[:40],
            f"{expense.amount:,.2f}",
            "billed" if expense.is_billed else "open",
        ]
        for expense in expenses
    ]
    echo(Ansi.paint(f"Expenses – {label}", Ansi.BOLD))
    echo(
        render_table(
            ["ID", "Date", "Project", "Category", "Description", "Amount", "State"],
            rows,
            aligns=["right", "left", "left", "left", "left", "right", "left"],
            empty="No expenses in that period.",
        )
    )
    echo()
    echo(f"Total: {Ansi.paint(f'{sum(e.amount for e in expenses):,.2f}', Ansi.BOLD)}")
    return 0


def cmd_todo_add(ctx: Context) -> int:
    ctx.repos.projects.get(ctx.args.project)
    deadline = parse_datetime(ctx.args.deadline) if ctx.args.deadline else now() + timedelta(days=7)
    todo_id = ctx.repos.todos.add(
        ctx.args.title,
        ctx.args.project,
        deadline,
        description=ctx.args.description,
        category=ctx.args.category,
        priority=ctx.args.priority,
        estimated_hours=ctx.args.estimate,
    )
    echo(Ansi.paint(f"Todo #{todo_id} due {deadline.date()}", Ansi.GREEN))
    return 0


def cmd_todo_list(ctx: Context) -> int:
    todos = ctx.repos.todos.list(project_id=ctx.args.project, open_only=not ctx.args.all)
    projects = {project.id: project for project in ctx.repos.projects.list()}
    today = now().date()
    rows = []
    for todo in todos:
        overdue = not todo.is_completed and todo.deadline.date() < today
        deadline = todo.deadline.date().isoformat()
        rows.append(
            [
                todo.id,
                "✓" if todo.is_completed else " ",
                todo.title[:44],
                projects[todo.project_id].name if todo.project_id in projects else "?",
                todo.priority,
                Ansi.paint(deadline, Ansi.RED) if overdue else deadline,
                f"{todo.estimated_hours:.1f}h" if todo.estimated_hours else "-",
            ]
        )
    echo(
        render_table(
            ["ID", "✓", "Title", "Project", "Priority", "Deadline", "Est."],
            rows,
            aligns=["right", "center", "left", "left", "left", "left", "right"],
            empty="Nothing on the list.",
        )
    )
    return 0


def cmd_todo_done(ctx: Context) -> int:
    ctx.repos.todos.complete(ctx.args.todo_id, completed=not ctx.args.undo)
    echo(Ansi.paint(f"Todo #{ctx.args.todo_id} marked {'open' if ctx.args.undo else 'done'}", Ansi.GREEN))
    return 0


def cmd_report_summary(ctx: Context) -> int:
    start, end, label = resolve_period(ctx.args.period, ctx.args.since, ctx.args.until)
    rows = ctx.reports.summarise(
        grouping=ctx.args.group,
        start=start,
        end=end,
        client_id=ctx.args.client,
        project_id=ctx.args.project,
        billable_only=ctx.args.billable_only,
    )
    seconds, amount = ctx.reports.totals(rows)
    currency = ctx.display_currency(client_id=ctx.args.client, project_id=ctx.args.project)

    echo(Ansi.paint(f"Report by {ctx.args.group} – {label}", Ansi.BOLD))
    echo(
        render_table(
            [ctx.args.group.title(), "Entries", "Hours", "Duration", "Amount"],
            [
                [row.label, row.entry_count, format_hours(row.seconds), format_duration(row.seconds), format_money(row.amount, currency)]
                for row in rows
            ],
            aligns=["left", "right", "right", "right", "right"],
            empty="Nothing tracked in that period.",
        )
    )
    if rows:
        echo()
        echo(render_bars([(row.label, row.hours) for row in rows], formatter=lambda value: f"{value:.2f}h"))
        echo()
        echo(
            f"TOTAL  {Ansi.paint(format_duration(seconds), Ansi.BOLD)}"
            f"  ({format_hours(seconds)} h)  {Ansi.paint(format_money(amount, currency), Ansi.BOLD)}"
        )
    return 0


def cmd_report_budget(ctx: Context) -> int:
    status = ctx.reports.monthly_budget_status()
    clients = {client.id: client for client in ctx.repos.clients.list()}
    rows = []
    for item in status:
        project: Project = item["project"]
        ratio = item["ratio"]
        marker = "!" if ratio >= 1 else ("~" if ratio >= 0.8 else " ")
        rows.append(
            [
                marker,
                project.name,
                clients[project.client_id].name if project.client_id in clients else "?",
                f"{item['used_hours']:.2f}",
                f"{item['limit_hours']:.0f}",
                f"{ratio * 100:.0f}%",
            ]
        )
    echo(Ansi.paint(f"Monthly limits – {now().strftime('%B %Y')}", Ansi.BOLD))
    echo(
        render_table(
            ["", "Project", "Client", "Used", "Limit", "Usage"],
            rows,
            aligns=["center", "left", "left", "right", "right", "right"],
            empty="No project has a monthly time limit configured.",
        )
    )
    return 0


def cmd_invoice_create(ctx: Context) -> int:
    start, end, label = resolve_period(ctx.args.period, ctx.args.since, ctx.args.until)
    draft = ctx.invoicing.build_draft(
        client_id=ctx.args.client,
        start=start,
        end=end,
        due_in_days=ctx.args.due,
        include_expenses=not ctx.args.no_expenses,
        notes=ctx.args.notes,
    )
    currency = draft.client.currency

    echo(Ansi.paint(f"{draft.number} – {draft.client.name} ({label})", Ansi.BOLD))
    echo(
        render_table(
            ["Description", "Qty", "Unit price", "Total"],
            [
                [
                    item.description,
                    f"{item.quantity:,.2f}",
                    format_money(item.unit_price, currency),
                    format_money(item.total, currency),
                ]
                for item in draft.line_items
            ],
            aligns=["left", "right", "right", "right"],
        )
    )
    echo()
    echo(f"Issue date {draft.issue_date.date()}   due {draft.due_date.date()}")
    echo(f"TOTAL {Ansi.paint(format_money(draft.total, currency), Ansi.BOLD)}")

    if ctx.args.dry_run:
        echo(Ansi.paint("\nDry run: nothing was written to the database.", Ansi.YELLOW))
        return 0

    invoice_id = ctx.invoicing.commit(draft, status=ctx.args.status)
    echo(
        Ansi.paint(
            f"\nSaved invoice #{invoice_id} ({draft.number}); "
            f"{plural(len(draft.entry_ids), 'entry', 'entries')} and "
            f"{plural(len(draft.expense_ids), 'expense')} marked billed.",
            Ansi.GREEN,
        )
    )
    return 0


def cmd_invoice_list(ctx: Context) -> int:
    invoices = ctx.repos.invoices.list(client_id=ctx.args.client, status=ctx.args.status)
    clients = {client.id: client for client in ctx.repos.clients.list()}
    today = now().date()
    rows = []
    for invoice in invoices:
        client = clients.get(invoice.client_id)
        overdue = invoice.status != "Paid" and invoice.due_date.date() < today
        status = Ansi.paint(invoice.status, Ansi.RED) if overdue else invoice.status
        rows.append(
            [
                invoice.id,
                invoice.invoice_id_string,
                client.name if client else "?",
                invoice.issue_date.date().isoformat(),
                invoice.due_date.date().isoformat(),
                format_money(invoice.total_amount, client.currency if client else DEFAULT_CURRENCY),
                status,
            ]
        )
    echo(
        render_table(
            ["ID", "Number", "Client", "Issued", "Due", "Total", "Status"],
            rows,
            aligns=["right", "left", "left", "left", "left", "right", "left"],
            empty="No invoices yet.",
        )
    )
    return 0


def cmd_invoice_show(ctx: Context) -> int:
    invoice = ctx.repos.invoices.get(ctx.args.invoice_id)
    client = ctx.repos.clients.get(invoice.client_id)
    echo(Ansi.paint(f"{invoice.invoice_id_string} – {client.name}", Ansi.BOLD))
    echo(f"Issued {invoice.issue_date.date()}   due {invoice.due_date.date()}   status {invoice.status}")
    if invoice.notes:
        echo(f"Notes: {invoice.notes}")
    echo()
    echo(
        render_table(
            ["Description", "Qty", "Unit price", "Total"],
            [
                [
                    item.get("description", ""),
                    f"{float(item.get('quantity', 0)):,.2f}",
                    format_money(float(item.get("unitPrice", 0)), client.currency),
                    format_money(float(item.get("quantity", 0)) * float(item.get("unitPrice", 0)), client.currency),
                ]
                for item in invoice.line_items
            ],
            aligns=["left", "right", "right", "right"],
        )
    )
    echo()
    echo(f"TOTAL {Ansi.paint(format_money(invoice.total_amount, client.currency), Ansi.BOLD)}")
    return 0


def cmd_invoice_status(ctx: Context) -> int:
    ctx.repos.invoices.set_status(ctx.args.invoice_id, ctx.args.status)
    echo(Ansi.paint(f"Invoice #{ctx.args.invoice_id} is now {ctx.args.status}", Ansi.GREEN))
    return 0


def cmd_export(ctx: Context) -> int:
    start, end, _ = resolve_period(ctx.args.period, ctx.args.since, ctx.args.until)
    if ctx.args.what == "entries":
        rows = ctx.exporting.entries_rows(
            ctx.repos.entries.list(
                start=start, end=end, project_id=ctx.args.project, client_id=ctx.args.client
            )
        )
    elif ctx.args.what == "expenses":
        rows = ctx.exporting.expenses_rows(
            ctx.repos.expenses.list(
                start=start, end=end, project_id=ctx.args.project, client_id=ctx.args.client
            )
        )
    else:
        rows = ctx.exporting.invoices_rows(ctx.repos.invoices.list(client_id=ctx.args.client))

    payload = ExportService.write(rows, fmt=ctx.args.format, destination=ctx.args.out)
    if ctx.args.out:
        echo(Ansi.paint(f"Wrote {len(rows)} rows to {ctx.args.out}", Ansi.GREEN))
    else:
        sys.stdout.write(payload)
    return 0


def cmd_db_info(ctx: Context) -> int:
    echo(f"Database: {ctx.db.path}")
    if os.path.exists(ctx.db.path):
        echo(f"Size:     {os.path.getsize(ctx.db.path) / 1024:.1f} KiB")
    counts = []
    for table in ctx.db.tables():
        row = ctx.db.query_one(f"SELECT COUNT(*) AS total FROM {table}")
        counts.append([table, row["total"] if row else 0])
    echo()
    echo(render_table(["Table", "Rows"], counts, aligns=["left", "right"]))
    return 0


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------
def add_period_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--period",
        default="all",
        help="today, yesterday, week, last-week, month, last-month, year, 30d or all",
    )
    parser.add_argument("--from", dest="since", help="start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="until", help="end date (YYYY-MM-DD)")


def add_scope_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--client", type=int, help="restrict to a client id")
    parser.add_argument("--project", type=int, help="restrict to a project id")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="timetrack",
        description="Command line companion for the Time Tracker app.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", help=f"path to the SQLite file (default: {default_db_path()})")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    parser.add_argument("--version", action="version", version=f"timetrack {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="create the database and its tables")
    init.set_defaults(handler=cmd_init, creates_db=True)

    # -- clients --------------------------------------------------------
    client = subparsers.add_parser("client", help="manage clients").add_subparsers(
        dest="client_command", required=True
    )
    client_add = client.add_parser("add", help="add a client")
    client_add.add_argument("name")
    client_add.add_argument("--email")
    client_add.add_argument("--address")
    client_add.add_argument("--currency", default=DEFAULT_CURRENCY)
    client_add.set_defaults(handler=cmd_client_add)

    client_list = client.add_parser("list", help="list clients")
    client_list.set_defaults(handler=cmd_client_list)

    client_rm = client.add_parser("rm", help="delete a client and everything below it")
    client_rm.add_argument("client_id", type=int)
    client_rm.set_defaults(handler=cmd_client_rm)

    # -- projects -------------------------------------------------------
    project = subparsers.add_parser("project", help="manage projects").add_subparsers(
        dest="project_command", required=True
    )
    project_add = project.add_parser("add", help="add a project")
    project_add.add_argument("name")
    project_add.add_argument("--client", type=int, required=True)
    project_add.add_argument("--rate", type=float, required=True, help="hourly rate")
    project_add.add_argument("--limit", type=int, help="monthly time limit in hours")
    project_add.add_argument("--status", choices=PROJECT_STATUSES, default="Active")
    project_add.set_defaults(handler=cmd_project_add)

    project_list = project.add_parser("list", help="list projects")
    project_list.add_argument("--client", type=int)
    project_list.add_argument("--status", choices=PROJECT_STATUSES)
    project_list.set_defaults(handler=cmd_project_list)

    # -- timer ----------------------------------------------------------
    start = subparsers.add_parser("start", help="start a timer")
    start.add_argument("project", type=int)
    start.add_argument("description")
    start.add_argument("--category", default=DEFAULT_CATEGORY)
    start.add_argument("--at", help="start time (e.g. 09:15 or 'yesterday 16:00')")
    start.add_argument("--non-billable", action="store_true")
    start.add_argument("--force", action="store_true", help="stop a running timer first")
    start.set_defaults(handler=cmd_start)

    stop = subparsers.add_parser("stop", help="stop the running timer")
    stop.add_argument("--at", help="end time (defaults to now)")
    stop.set_defaults(handler=cmd_stop)

    status = subparsers.add_parser("status", help="show the running timer and today's total")
    status.set_defaults(handler=cmd_status)

    log = subparsers.add_parser("log", help="add a finished entry by duration")
    log.add_argument("project", type=int)
    log.add_argument("description")
    log.add_argument("--duration", required=True, help="90m, 1h30m, 1:30 ...")
    log.add_argument("--at", help="start time (defaults to now minus duration)")
    log.add_argument("--category", default=DEFAULT_CATEGORY)
    log.add_argument("--non-billable", action="store_true")
    log.set_defaults(handler=cmd_log)

    # -- entries --------------------------------------------------------
    entry = subparsers.add_parser("entry", help="inspect time entries").add_subparsers(
        dest="entry_command", required=True
    )
    entry_list = entry.add_parser("list", help="list time entries")
    add_period_options(entry_list)
    add_scope_options(entry_list)
    entry_list.add_argument("--unbilled", action="store_true")
    entry_list.add_argument("--limit", type=int, default=50)
    entry_list.set_defaults(handler=cmd_entry_list)

    entry_rm = entry.add_parser("rm", help="delete a time entry")
    entry_rm.add_argument("entry_id", type=int)
    entry_rm.set_defaults(handler=cmd_entry_rm)

    entry_flag = entry.add_parser("flag", help="toggle billable/billed/logged")
    entry_flag.add_argument("entry_id", type=int)
    entry_flag.add_argument("--billed", type=parse_bool)
    entry_flag.add_argument("--billable", type=parse_bool)
    entry_flag.add_argument("--logged", type=parse_bool)
    entry_flag.set_defaults(handler=cmd_entry_flag)

    # -- expenses -------------------------------------------------------
    expense = subparsers.add_parser("expense", help="manage expenses").add_subparsers(
        dest="expense_command", required=True
    )
    expense_add = expense.add_parser("add", help="record an expense")
    expense_add.add_argument("description")
    expense_add.add_argument("--amount", type=float)
    expense_add.add_argument("--project", type=int)
    expense_add.add_argument("--client", type=int)
    expense_add.add_argument("--category", default="General")
    expense_add.add_argument("--distance", type=float, help="mileage distance")
    expense_add.add_argument("--cost-per-unit", type=float, dest="cost_per_unit")
    expense_add.add_argument("--at", help="date of the expense")
    expense_add.set_defaults(handler=cmd_expense_add)

    expense_list = expense.add_parser("list", help="list expenses")
    add_period_options(expense_list)
    add_scope_options(expense_list)
    expense_list.add_argument("--unbilled", action="store_true")
    expense_list.set_defaults(handler=cmd_expense_list)

    # -- todos ----------------------------------------------------------
    todo = subparsers.add_parser("todo", help="manage the to-do list").add_subparsers(
        dest="todo_command", required=True
    )
    todo_add = todo.add_parser("add", help="add a task")
    todo_add.add_argument("title")
    todo_add.add_argument("--project", type=int, required=True)
    todo_add.add_argument("--description")
    todo_add.add_argument("--deadline", help="date or 'today'/'+3d'")
    todo_add.add_argument("--category", default=DEFAULT_CATEGORY)
    todo_add.add_argument("--priority", choices=TODO_PRIORITIES, default="Medium")
    todo_add.add_argument("--estimate", type=float, help="estimated hours")
    todo_add.set_defaults(handler=cmd_todo_add)

    todo_list = todo.add_parser("list", help="list tasks")
    todo_list.add_argument("--project", type=int)
    todo_list.add_argument("--all", action="store_true", help="include completed tasks")
    todo_list.set_defaults(handler=cmd_todo_list)

    todo_done = todo.add_parser("done", help="mark a task as completed")
    todo_done.add_argument("todo_id", type=int)
    todo_done.add_argument("--undo", action="store_true")
    todo_done.set_defaults(handler=cmd_todo_done)

    # -- reports --------------------------------------------------------
    report = subparsers.add_parser("report", help="reporting").add_subparsers(
        dest="report_command", required=True
    )
    report_summary = report.add_parser("summary", help="aggregate tracked time")
    report_summary.add_argument("--group", choices=ReportService.GROUPINGS, default="project")
    add_period_options(report_summary)
    add_scope_options(report_summary)
    report_summary.add_argument("--billable-only", action="store_true")
    report_summary.set_defaults(handler=cmd_report_summary)

    report_budget = report.add_parser("budget", help="monthly time limit usage")
    report_budget.set_defaults(handler=cmd_report_budget)

    # -- invoices -------------------------------------------------------
    invoice = subparsers.add_parser("invoice", help="manage invoices").add_subparsers(
        dest="invoice_command", required=True
    )
    invoice_create = invoice.add_parser("create", help="invoice the unbilled work of a client")
    invoice_create.add_argument("--client", type=int, required=True)
    add_period_options(invoice_create)
    invoice_create.add_argument("--due", type=int, default=DEFAULT_PAYMENT_TERMS_DAYS)
    invoice_create.add_argument("--status", choices=INVOICE_STATUSES, default="Draft")
    invoice_create.add_argument("--notes")
    invoice_create.add_argument("--no-expenses", action="store_true")
    invoice_create.add_argument("--dry-run", action="store_true")
    invoice_create.set_defaults(handler=cmd_invoice_create)

    invoice_list = invoice.add_parser("list", help="list invoices")
    invoice_list.add_argument("--client", type=int)
    invoice_list.add_argument("--status", choices=INVOICE_STATUSES)
    invoice_list.set_defaults(handler=cmd_invoice_list)

    invoice_show = invoice.add_parser("show", help="show one invoice with its line items")
    invoice_show.add_argument("invoice_id", type=int)
    invoice_show.set_defaults(handler=cmd_invoice_show)

    invoice_status = invoice.add_parser("status", help="change an invoice status")
    invoice_status.add_argument("invoice_id", type=int)
    invoice_status.add_argument("status", choices=INVOICE_STATUSES)
    invoice_status.set_defaults(handler=cmd_invoice_status)

    # -- export / db ----------------------------------------------------
    export = subparsers.add_parser("export", help="export data as CSV or JSON")
    export.add_argument("what", choices=("entries", "expenses", "invoices"))
    export.add_argument("--format", choices=("csv", "json"), default="csv")
    export.add_argument("--out", help="write to this file instead of stdout")
    add_period_options(export)
    add_scope_options(export)
    export.set_defaults(handler=cmd_export)

    db_info = subparsers.add_parser("info", help="show database statistics")
    db_info.set_defaults(handler=cmd_db_info)

    return parser


def parse_bool(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected a boolean, got {text!r}")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    Ansi.configure(force={"always": True, "never": False}.get(args.color))

    db_path = args.db or default_db_path()
    with Database(db_path) as db:
        db.open(create=getattr(args, "creates_db", False))
        if getattr(args, "creates_db", False):
            db.create_schema()
        ctx = Context(db=db, repos=Repositories.for_db(db), args=args)
        handler: Callable[[Context], int] = args.handler
        return handler(ctx)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(argv)
    except AppError as error:
        print(Ansi.paint(f"error: {error}", Ansi.RED), file=sys.stderr)
        return 2
    except sqlite3.Error as error:
        print(Ansi.paint(f"database error: {error}", Ansi.RED), file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("\naborted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
