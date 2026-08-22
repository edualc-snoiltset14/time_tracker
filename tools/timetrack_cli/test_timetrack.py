#!/usr/bin/env python3
"""Unit tests for timetrack.py — run with ``python3 -m unittest discover``."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta

import timetrack as tt


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------
class DurationTests(unittest.TestCase):
    def test_hour_and_minute_forms(self) -> None:
        self.assertEqual(tt.parse_duration("2h"), timedelta(hours=2))
        self.assertEqual(tt.parse_duration("90m"), timedelta(minutes=90))
        self.assertEqual(tt.parse_duration("1h30m"), timedelta(minutes=90))
        self.assertEqual(tt.parse_duration("1h 30m"), timedelta(minutes=90))
        self.assertEqual(tt.parse_duration("1.5h"), timedelta(minutes=90))

    def test_clock_and_bare_minutes(self) -> None:
        self.assertEqual(tt.parse_duration("1:30"), timedelta(minutes=90))
        self.assertEqual(tt.parse_duration("0:45:30"), timedelta(minutes=45, seconds=30))
        self.assertEqual(tt.parse_duration("45"), timedelta(minutes=45))

    def test_rejects_garbage(self) -> None:
        for bad in ("", "soon", "12x", "--"):
            with self.subTest(value=bad):
                with self.assertRaises(tt.AppError):
                    tt.parse_duration(bad)

    def test_formatting(self) -> None:
        self.assertEqual(tt.format_duration(timedelta(minutes=90)), "1h 30m")
        self.assertEqual(tt.format_duration(timedelta(minutes=5)), "5m")
        self.assertEqual(tt.format_duration(timedelta(hours=7, minutes=5)), "7h 05m")
        self.assertEqual(tt.format_duration(-3600), "-1h 00m")


class DateParsingTests(unittest.TestCase):
    REFERENCE = date(2026, 8, 22)

    def test_relative_keywords(self) -> None:
        self.assertEqual(tt.parse_date("today", reference=self.REFERENCE), self.REFERENCE)
        self.assertEqual(tt.parse_date("yesterday", reference=self.REFERENCE), date(2026, 8, 21))
        self.assertEqual(tt.parse_date("tomorrow", reference=self.REFERENCE), date(2026, 8, 23))
        self.assertEqual(tt.parse_date("-3d", reference=self.REFERENCE), date(2026, 8, 19))

    def test_absolute_formats(self) -> None:
        self.assertEqual(tt.parse_date("2026-01-05", reference=self.REFERENCE), date(2026, 1, 5))
        self.assertEqual(tt.parse_date("05.01.2026", reference=self.REFERENCE), date(2026, 1, 5))

    def test_datetime_forms(self) -> None:
        ref = tt.now().replace(year=2026, month=8, day=22, hour=10, minute=0)
        self.assertEqual(tt.parse_datetime("now", reference=ref), ref)
        self.assertEqual(tt.parse_datetime("14:30", reference=ref).hour, 14)
        moment = tt.parse_datetime("yesterday 16:00", reference=ref)
        self.assertEqual((moment.date(), moment.hour), (date(2026, 8, 21), 16))

    def test_month_bounds(self) -> None:
        self.assertEqual(tt.month_bounds(date(2026, 2, 10)), (date(2026, 2, 1), date(2026, 2, 28)))
        self.assertEqual(tt.month_bounds(date(2026, 12, 5)), (date(2026, 12, 1), date(2026, 12, 31)))

    def test_resolve_period(self) -> None:
        start, end, label = tt.resolve_period("month", None, None, reference=date(2026, 8, 22))
        self.assertEqual(start.date(), date(2026, 8, 1))
        self.assertEqual(end.date(), date(2026, 8, 31))
        self.assertIn("2026", label)

        start, end, _ = tt.resolve_period("last-month", None, None, reference=date(2026, 1, 15))
        self.assertEqual((start.date(), end.date()), (date(2025, 12, 1), date(2025, 12, 31)))

        start, end, _ = tt.resolve_period(None, "2026-01-01", "2026-01-31")
        self.assertEqual((start.date(), end.date()), (date(2026, 1, 1), date(2026, 1, 31)))

        self.assertEqual(tt.resolve_period("all", None, None)[:2], (None, None))
        with self.assertRaises(tt.AppError):
            tt.resolve_period("someday", None, None)

    def test_timestamp_round_trip(self) -> None:
        moment = tt.now().replace(microsecond=0)
        self.assertEqual(tt.from_db_timestamp(tt.to_db_timestamp(moment)), moment)
        self.assertIsNone(tt.from_db_timestamp(None))
        self.assertEqual(tt.from_db_timestamp("2026-08-22T10:00:00+00:00").year, 2026)


class RenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        tt.Ansi.configure(force=False)

    def test_table(self) -> None:
        output = tt.render_table(["ID", "Name"], [[1, "ACME"], [22, "Globex"]], aligns=["right", "left"])
        lines = output.splitlines()
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[2].startswith(" 1"))

    def test_empty_table(self) -> None:
        self.assertEqual(tt.render_table(["A"], [], empty="none"), "none")

    def test_bars(self) -> None:
        chart = tt.render_bars([("a", 10.0), ("b", 5.0)])
        self.assertIn("a", chart)
        self.assertGreater(chart.splitlines()[0].count("█"), chart.splitlines()[1].count("█"))

    def test_plural(self) -> None:
        self.assertEqual(tt.plural(1, "entry", "entries"), "1 entry")
        self.assertEqual(tt.plural(2, "entry", "entries"), "2 entries")
        self.assertEqual(tt.plural(0, "expense"), "0 expenses")

    def test_money(self) -> None:
        self.assertEqual(tt.format_money(1234.5, "USD"), "$1,234.50")
        self.assertEqual(tt.format_money(10, "XYZ"), "XYZ 10.00")


# --------------------------------------------------------------------------
# Database backed tests
# --------------------------------------------------------------------------
class DatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tt.Ansi.configure(force=False)
        self.db = tt.Database(":memory:").open(create=True)
        self.db.create_schema()
        self.repos = tt.Repositories.for_db(self.db)
        self.client_id = self.repos.clients.add("ACME Corp", "billing@acme.test", None, "EUR")
        self.project_id = self.repos.projects.add(self.client_id, "Website", 100.0, 40)

    def tearDown(self) -> None:
        self.db.close()

    def log_entry(self, *, hours: float, days_ago: int = 0, billable: bool = True) -> int:
        start = tt.now().replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
        return self.repos.entries.add(
            self.project_id,
            f"work {hours}h",
            start,
            start + timedelta(hours=hours),
            "Development",
            billable=billable,
        )


class SchemaTests(DatabaseTestCase):
    def test_tables_match_the_flutter_app(self) -> None:
        self.assertEqual(
            set(self.db.tables()),
            {"clients", "projects", "time_entries", "expenses", "invoices", "todos", "company_settings"},
        )

    def test_cascade_delete(self) -> None:
        self.log_entry(hours=1)
        self.repos.clients.delete(self.client_id)
        self.assertEqual(self.repos.projects.list(), [])
        self.assertEqual(self.repos.entries.list(), [])

    def test_missing_rows_raise(self) -> None:
        with self.assertRaises(tt.NotFound):
            self.repos.projects.get(999)
        with self.assertRaises(tt.NotFound):
            self.repos.clients.get(999)


class TimerTests(DatabaseTestCase):
    def test_start_and_stop(self) -> None:
        start = tt.now() - timedelta(minutes=30)
        entry_id = self.repos.entries.add(self.project_id, "Timer", start, None)
        running = self.repos.entries.running()
        self.assertIsNotNone(running)
        self.assertEqual(running.id, entry_id)
        self.assertTrue(running.running)
        self.assertGreaterEqual(running.duration().total_seconds(), 1800)

        self.repos.entries.stop(entry_id, start + timedelta(minutes=45))
        self.assertIsNone(self.repos.entries.running())
        self.assertEqual(self.repos.entries.get(entry_id).duration(), timedelta(minutes=45))

    def test_cannot_stop_twice(self) -> None:
        entry_id = self.log_entry(hours=1)
        with self.assertRaises(tt.AppError):
            self.repos.entries.stop(entry_id, tt.now())

    def test_rejects_negative_span(self) -> None:
        start = tt.now()
        with self.assertRaises(tt.AppError):
            self.repos.entries.add(self.project_id, "backwards", start, start - timedelta(hours=1))

    def test_flags(self) -> None:
        entry_id = self.log_entry(hours=1)
        self.repos.entries.set_flags(entry_id, is_logged=True, is_billable=False)
        entry = self.repos.entries.get(entry_id)
        self.assertTrue(entry.is_logged)
        self.assertFalse(entry.is_billable)


class ReportTests(DatabaseTestCase):
    def test_summary_by_project(self) -> None:
        self.log_entry(hours=2)
        self.log_entry(hours=1.5)
        rows = tt.ReportService(self.repos).summarise(grouping="project")
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0].hours, 3.5, places=4)
        self.assertAlmostEqual(rows[0].amount, 350.0, places=2)
        self.assertEqual(rows[0].entry_count, 2)

    def test_non_billable_time_has_no_value(self) -> None:
        self.log_entry(hours=2, billable=False)
        rows = tt.ReportService(self.repos).summarise(grouping="client")
        self.assertAlmostEqual(rows[0].hours, 2.0, places=4)
        self.assertEqual(rows[0].amount, 0.0)

    def test_period_filter(self) -> None:
        self.log_entry(hours=2, days_ago=0)
        self.log_entry(hours=3, days_ago=10)
        start, end, _ = tt.resolve_period("today", None, None)
        rows = tt.ReportService(self.repos).summarise(grouping="day", start=start, end=end)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0].hours, 2.0, places=4)

    def test_running_entries_are_excluded(self) -> None:
        self.repos.entries.add(self.project_id, "running", tt.now() - timedelta(hours=1), None)
        self.assertEqual(tt.ReportService(self.repos).summarise(), [])

    def test_budget_status(self) -> None:
        self.log_entry(hours=10)
        status = tt.ReportService(self.repos).monthly_budget_status()
        self.assertEqual(len(status), 1)
        self.assertAlmostEqual(status[0]["used_hours"], 10.0, places=4)
        self.assertAlmostEqual(status[0]["ratio"], 0.25, places=4)


class CurrencyTests(DatabaseTestCase):
    def test_single_client_currency_wins(self) -> None:
        ctx = tt.Context(db=self.db, repos=self.repos, args=None)
        self.assertEqual(ctx.display_currency(), "EUR")
        self.assertEqual(ctx.display_currency(project_id=self.project_id), "EUR")

    def test_mixed_currencies_fall_back_to_the_default(self) -> None:
        other = self.repos.clients.add("Globex", None, None, "USD")
        ctx = tt.Context(db=self.db, repos=self.repos, args=None)
        self.assertEqual(ctx.display_currency(), tt.DEFAULT_CURRENCY)
        self.assertEqual(ctx.display_currency(client_id=other), "USD")
        self.assertEqual(ctx.display_currency(client_id=self.client_id), "EUR")


class InvoiceTests(DatabaseTestCase):
    def test_draft_groups_entries_per_project(self) -> None:
        self.log_entry(hours=2)
        self.log_entry(hours=1)
        self.repos.expenses.add("Train ticket", 60.0, tt.now(), project_id=self.project_id, category="Travel")

        draft = tt.InvoiceService(self.repos).build_draft(client_id=self.client_id, start=None, end=None)
        self.assertEqual(len(draft.line_items), 2)
        self.assertIn("2 entries", draft.line_items[0].description)
        time_item = draft.line_items[0]
        self.assertAlmostEqual(time_item.quantity, 3.0, places=2)
        self.assertAlmostEqual(time_item.unit_price, 100.0, places=2)
        self.assertAlmostEqual(draft.total, 360.0, places=2)
        self.assertEqual(draft.number, f"INV-{tt.now().year}-0001")

    def test_commit_marks_everything_billed(self) -> None:
        entry_id = self.log_entry(hours=2)
        expense_id = self.repos.expenses.add("Hotel", 120.0, tt.now(), project_id=self.project_id)
        service = tt.InvoiceService(self.repos)
        draft = service.build_draft(client_id=self.client_id, start=None, end=None)
        invoice_id = service.commit(draft, status="Sent")

        self.assertTrue(self.repos.entries.get(entry_id).is_billed)
        self.assertTrue(self.repos.expenses.list()[0].is_billed)
        self.assertEqual(expense_id, self.repos.expenses.list()[0].id)

        invoice = self.repos.invoices.get(invoice_id)
        self.assertEqual(invoice.status, "Sent")
        self.assertAlmostEqual(invoice.total_amount, 320.0, places=2)
        self.assertEqual(
            set(invoice.line_items[0]), {"description", "quantity", "unitPrice"}
        )

    def test_second_invoice_only_takes_new_work(self) -> None:
        self.log_entry(hours=2)
        service = tt.InvoiceService(self.repos)
        service.commit(service.build_draft(client_id=self.client_id, start=None, end=None))

        with self.assertRaises(tt.AppError):
            service.build_draft(client_id=self.client_id, start=None, end=None)

        self.log_entry(hours=1)
        second = service.build_draft(client_id=self.client_id, start=None, end=None)
        self.assertAlmostEqual(second.total, 100.0, places=2)
        self.assertEqual(second.number, f"INV-{tt.now().year}-0002")

    def test_non_billable_work_is_not_invoiced(self) -> None:
        self.log_entry(hours=2, billable=False)
        with self.assertRaises(tt.AppError):
            tt.InvoiceService(self.repos).build_draft(client_id=self.client_id, start=None, end=None)

    def test_status_validation(self) -> None:
        self.log_entry(hours=1)
        service = tt.InvoiceService(self.repos)
        invoice_id = service.commit(service.build_draft(client_id=self.client_id, start=None, end=None))
        self.repos.invoices.set_status(invoice_id, "Paid")
        self.assertEqual(self.repos.invoices.get(invoice_id).status, "Paid")
        with self.assertRaises(tt.AppError):
            self.repos.invoices.set_status(invoice_id, "Whatever")


class ExpenseTests(DatabaseTestCase):
    def test_mileage_amount_is_derived(self) -> None:
        expense_id = self.repos.expenses.add(
            "Client visit", 0.0, tt.now(), project_id=self.project_id, distance=120, cost_per_unit=0.7
        )
        expense = [item for item in self.repos.expenses.list() if item.id == expense_id][0]
        self.assertAlmostEqual(expense.amount, 84.0, places=2)

    def test_unbilled_filter(self) -> None:
        first = self.repos.expenses.add("A", 10.0, tt.now(), project_id=self.project_id)
        self.repos.expenses.add("B", 20.0, tt.now(), project_id=self.project_id)
        self.repos.expenses.mark_billed([first])
        self.assertEqual([item.description for item in self.repos.expenses.list(unbilled_only=True)], ["B"])


class TodoTests(DatabaseTestCase):
    def test_add_and_complete(self) -> None:
        todo_id = self.repos.todos.add("Write docs", self.project_id, tt.now() + timedelta(days=3))
        self.assertEqual(len(self.repos.todos.list(open_only=True)), 1)
        self.repos.todos.complete(todo_id)
        self.assertEqual(self.repos.todos.list(open_only=True), [])
        self.assertEqual(len(self.repos.todos.list()), 1)

    def test_unknown_todo(self) -> None:
        with self.assertRaises(tt.NotFound):
            self.repos.todos.complete(4711)


class ExportTests(DatabaseTestCase):
    def test_csv_export(self) -> None:
        self.log_entry(hours=2)
        service = tt.ExportService(self.repos)
        rows = service.entries_rows(self.repos.entries.list())
        payload = tt.ExportService.write(rows, fmt="csv", destination=None)
        self.assertIn("client,project,description", payload)
        self.assertIn("ACME Corp", payload)
        self.assertIn("200.0", payload)

    def test_json_export_to_file(self) -> None:
        self.log_entry(hours=1)
        rows = tt.ExportService(self.repos).entries_rows(self.repos.entries.list())
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "entries.json")
            tt.ExportService.write(rows, fmt="json", destination=target)
            with open(target, encoding="utf-8") as handle:
                parsed = json.load(handle)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["hours"], 1.0)

    def test_unknown_format(self) -> None:
        with self.assertRaises(tt.AppError):
            tt.ExportService.write([], fmt="xml", destination=None)


# --------------------------------------------------------------------------
# End to end CLI tests
# --------------------------------------------------------------------------
class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        tt.Ansi.configure(force=False)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db_path = os.path.join(self.folder.name, "app_tracker.sqlite")

    def run_cli(self, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = tt.main(["--db", self.db_path, "--color", "never", *argv])
        return code, buffer.getvalue()

    def test_full_workflow(self) -> None:
        self.assertEqual(self.run_cli("init")[0], 0)
        self.assertEqual(self.run_cli("client", "add", "ACME", "--currency", "EUR")[0], 0)
        self.assertEqual(
            self.run_cli("project", "add", "Website", "--client", "1", "--rate", "80")[0], 0
        )

        code, output = self.run_cli("log", "1", "Refactoring", "--duration", "2h")
        self.assertEqual(code, 0)
        self.assertIn("2h 00m", output)

        code, output = self.run_cli("start", "1", "Pairing")
        self.assertEqual(code, 0)
        code, output = self.run_cli("status")
        self.assertIn("running", output)
        code, output = self.run_cli("stop")
        self.assertEqual(code, 0)

        code, output = self.run_cli("report", "summary", "--group", "project")
        self.assertEqual(code, 0)
        self.assertIn("Website", output)

        code, output = self.run_cli("invoice", "create", "--client", "1", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("INV-", output)
        self.assertEqual(self.run_cli("invoice", "list")[1].strip().count("INV-"), 0)

        code, output = self.run_cli("invoice", "create", "--client", "1")
        self.assertEqual(code, 0)
        code, output = self.run_cli("invoice", "list")
        self.assertIn("INV-", output)

        code, output = self.run_cli("export", "entries", "--format", "json")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(output)), 2)

    def test_missing_database_is_an_error(self) -> None:
        code, _ = self.run_cli("client", "list")
        self.assertEqual(code, 2)

    def test_second_timer_needs_force(self) -> None:
        self.run_cli("init")
        self.run_cli("client", "add", "ACME")
        self.run_cli("project", "add", "App", "--client", "1", "--rate", "50")
        self.assertEqual(self.run_cli("start", "1", "first")[0], 0)
        self.assertEqual(self.run_cli("start", "1", "second")[0], 2)
        self.assertEqual(self.run_cli("start", "1", "second", "--force")[0], 0)

    def test_stop_without_timer(self) -> None:
        self.run_cli("init")
        self.assertEqual(self.run_cli("stop")[0], 2)

    def test_info(self) -> None:
        self.run_cli("init")
        code, output = self.run_cli("info")
        self.assertEqual(code, 0)
        self.assertIn("clients", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
