# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

`time_tracker` — a cross-platform Flutter app for freelancers/consultants: clients,
projects, time tracking, to-dos, expenses, PDF invoices, and reports.

All data is **local only** (SQLite via Drift). There is no backend, no auth, no
network layer. Targets Android, iOS, Windows, macOS, Linux, and web (the `web/`
target is unverified — the app depends on `dart:io` and `path_provider`).

## Commands

Requires the Dart SDK constraint in `pubspec.yaml`: `sdk: ^3.8.1`.

```sh
flutter pub get                                           # install deps
dart run build_runner build --delete-conflicting-outputs  # regenerate database.g.dart
dart run build_runner watch --delete-conflicting-outputs  # regenerate on save
flutter analyze                                           # lints (flutter_lints ^6.0.0)
flutter test                                              # see "Tests" caveat below
flutter run                                               # run on the default device
flutter run -d macos                                      # or: windows, linux, chrome
```

Run `build_runner` after **any** change to `lib/database/database.dart`, otherwise
the generated row/companion classes go stale and the app won't compile.

There is no CI: `.github/` contains only `FUNDING.yml`, so nothing runs these
commands for you.

## Layout

```
lib/
  main.dart                  # entry point: Provider<AppDatabase> + dark ThemeData
  database/
    database.dart            # Drift table definitions + AppDatabase + migrations
    database.g.dart          # GENERATED — never edit by hand
  models/line_item.dart      # plain Dart model + JSON helpers (not a Drift table)
  screens/
    main_screen.dart         # BottomNavigationBar shell holding all 8 tab screens
    home_screen.dart         # the to-do list itself; can start a timer from a task
    todos/                   # todo_edit_screen.dart — the to-do add/edit form
    time_tracker/            # active timer, entry list, add dialog, edit screen
    clients/ projects/ expenses/ invoices/ reports/ settings/
  utils/pdf_generator.dart   # builds the invoice PDF and hands it to Printing.layoutPdf
```

Note the to-do feature is split: the list is `home_screen.dart` (a tab), while its
editor is `screens/todos/todo_edit_screen.dart` (pushed from that screen). There is
no `todos/todos_screen.dart`.

## Architecture

**There is no repository, service, or view-model layer.** Screens talk to Drift
directly. `AppDatabase` is provided once in `main.dart` and read in screens with
`Provider.of<AppDatabase>(context)` (`listen: false` inside callbacks). Keep new
code in this style rather than introducing an abstraction layer for one screen.

- **Lists are reactive:** build a query and pass `query.watch()` to a
  `StreamBuilder`. Writes elsewhere refresh the list automatically — do not call
  `setState` to reload data.
- **Edit/detail screens** use `FutureBuilder` or plain `await`ed queries, since
  they load a fixed record once.
- **Navigation** is `Navigator.of(context).push` with `MaterialPageRoute` for edit
  screens; the top-level screens live in `MainScreen`.

### Adding a top-level screen

`MainScreen` keeps three parallel, index-aligned lists: `_screens`, `_titles`, and
the `BottomNavigationBarItem`s. Update all three together or the tabs desync.

## Drift conventions

Drift's `Column` and `Table` collide with Flutter's widgets, so screens import it
under a prefix:

```dart
import 'package:drift/drift.dart' as drift;   // most screens
import 'package:drift/drift.dart' hide Column; // time_tracker_screen.dart, where the unprefixed query DSL is wanted
```

`projects_screen.dart`, `invoices_screen.dart` and `expenses_screen.dart` still
carry a bare `import 'package:drift/drift.dart';`, but none of them reference
anything from it — those imports are unused leftovers, not a third convention.
Use one of the two forms above in new code.

Generated names follow Drift's singularization — table `Clients` produces row class
`Client` and `ClientsCompanion`; `CompanySettings` produces `CompanySetting`.

Two write shapes are in use. Edit screens build a full companion (including
`id: drift.Value(...)`) and replace the row:

```dart
await db.update(db.todos).replace(companion);
```

Partial updates filter first and `write` only the changed columns:

```dart
(db.update(db.timeEntries)..where((t) => t.id.equals(entry.id)))
    .write(TimeEntriesCompanion(isLogged: drift.Value(newValue)));
```

### Schema changes

`AppDatabase.schemaVersion` is currently **3**, with an `onUpgrade` in
`MigrationStrategy`. Be aware that `onUpgrade` only has a `from < 2` branch
(`addColumn(timeEntries, timeEntries.isLogged)`) — **there is no `from < 3`
branch.** The comment there claiming Drift recreates tables automatically on a
version bump is wrong: Drift does nothing you don't write. So the
`onDelete: KeyAction.cascade` rules that motivated version 3 apply only to
databases created fresh; a database that already existed at version 2 was bumped
to 3 without ever getting them.

All foreign keys in `database.dart` declare `onDelete: KeyAction.cascade`. Any
table change means bumping `schemaVersion` *and* adding the matching `if (from <
N)` branch in `onUpgrade` — the `from < 2` block is the pattern to copy, and the
missing v3 branch is the mistake not to repeat.

## Domain rules worth knowing

- **Active timer** = a `TimeEntries` row with `endTime == null`. The app assumes at
  most one exists; `home_screen.dart` checks for a running timer before starting a
  new one (`_startTimerFromTodo` bails with a SnackBar). Preserve that guard in new
  entry points.
- **Three independent booleans on a time entry:** `isBillable` (should it be
  charged), `isBilled` (already on an invoice), `isLogged` (recorded in an external
  system). They are not redundant — don't collapse them. `Expenses` has its own
  separate `isBilled`.
- **Todos require a project.** `Todos.projectId`, `startTime`, `deadline`,
  `category` and `priority` are all non-nullable, so a to-do cannot exist without a
  project — `todo_edit_screen.dart` force-unwraps the selected project id. Only
  `description` and `estimatedHours` are nullable.
- **`CompanySettings` is a singleton row** keyed on `id == 1`; reads use
  `getSingleOrNull()` and writes use `insertOnConflictUpdate` with
  `id: drift.Value(1)`. The column is still a plain `autoIncrement()` — nothing in
  the schema enforces the singleton, only the screen's convention.
- **Invoice line items are denormalized JSON** in `Invoices.lineItemsJson`, encoded
  and decoded with `lineItemsToJson` / `lineItemsFromJson` from
  `lib/models/line_item.dart`. There is no line-items table. The human-facing
  invoice number is a separate text column, `Invoices.invoiceIdString`.
- **Expenses** may attach to a project *or* a client (both nullable), and mileage
  expenses (`category == 'Mileage'`) derive `amount` from `distance * costPerUnit`.
- **Currency** is per client (`Clients.currency`, default `USD`) and formatted with
  `NumberFormat.simpleCurrency(name: client.currency)`. Note `reports_screen.dart`
  hardcodes `locale: 'en_US', name: 'USD'` instead — a known inconsistency, not a
  convention to copy.
- **Logos** are stored as filesystem paths in `CompanySettings.logoPath` and read
  with `dart:io` `File`, so they are desktop/mobile only.

## Theming

The app is dark-only: a single `ThemeData.dark().copyWith(...)` in `main.dart`
(deep purple seed, `Color.fromARGB(255, 28, 25, 38)` scaffold and app bar, pure
black `cardColor`). Several screens still hardcode colors inline (e.g. the nav
bar's `Color(0xFF1E1E1E)`, `Colors.tealAccent` for the selected tab, green/red
`withAlpha` row tints). Prefer `Theme.of(context).colorScheme` in new code.

## Tests

`test/widget_test.dart` is still the **unmodified Flutter counter template** — it
looks for a counter UI this app doesn't have, and pumps `MyApp` without the
`Provider<AppDatabase>` its screens require, so `flutter test` fails out of the box.
Replace or delete it rather than treating a red run as a real regression. New widget
tests must wrap the tree in a `Provider<AppDatabase>` (use an in-memory
`NativeDatabase.memory()` connection from `package:drift/native.dart`).
