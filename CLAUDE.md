# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

`time_tracker` — a cross-platform Flutter app for freelancers/consultants: clients,
projects, time tracking, to-dos, expenses, PDF invoices, and reports.

All data is **local only** (SQLite via Drift). There is no backend, no auth, no
network layer. Targets Android, iOS, Windows, macOS, Linux, and web (the `web/`
target is unverified — the app depends on `dart:io` and `path_provider`).

## Commands

```sh
flutter pub get                                        # install deps
dart run build_runner build --delete-conflicting-outputs  # regenerate database.g.dart
dart run build_runner watch --delete-conflicting-outputs  # regenerate on save
flutter analyze                                        # lints (flutter_lints)
flutter test                                           # see "Tests" caveat below
flutter run                                            # run on the default device
flutter run -d macos|windows|linux|chrome              # pick a platform
```

Run `build_runner` after **any** change to `lib/database/database.dart`, otherwise
the generated row/companion classes go stale and the app won't compile.

## Layout

```
lib/
  main.dart                  # entry point: Provider<AppDatabase> + dark ThemeData
  database/
    database.dart            # Drift table definitions + AppDatabase + migrations
    database.g.dart          # GENERATED — never edit by hand
  models/line_item.dart      # plain Dart model + JSON helpers (not a Drift table)
  screens/
    main_screen.dart         # BottomNavigationBar shell holding all 8 screens
    home_screen.dart         # to-do list; can start a timer from a task
    time_tracker/            # active timer, entry list, add dialog, edit screen
    clients/ projects/ expenses/ invoices/ reports/ settings/
  utils/pdf_generator.dart   # builds and shows the invoice PDF
```

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
- **Navigation** is `Navigator.push` with `MaterialPageRoute` for edit screens;
  the top-level screens live in `MainScreen`.

### Adding a top-level screen

`MainScreen` keeps three parallel, index-aligned lists: `_screens`, `_titles`, and
the `BottomNavigationBarItem`s. Update all three together or the tabs desync.

## Drift conventions

Drift's `Column` and `Table` collide with Flutter's widgets, so screens import it
under a prefix:

```dart
import 'package:drift/drift.dart' as drift;   // most screens
import 'package:drift/drift.dart' hide Column; // where unprefixed query DSL is wanted
```

Generated names follow Drift's singularization — table `Clients` produces row class
`Client` and `ClientsCompanion`; `CompanySettings` produces `CompanySetting`.
Writes use companions with wrapped values:

```dart
(db.update(db.timeEntries)..where((t) => t.id.equals(entry.id)))
    .write(TimeEntriesCompanion(isLogged: drift.Value(newValue)));
```

### Schema changes

`AppDatabase.schemaVersion` is currently **3**, with an `onUpgrade` in
`MigrationStrategy`. Any table change means bumping `schemaVersion` *and* adding
the matching branch in `onUpgrade` — the existing `if (from < 2)` block is the
pattern. All foreign keys use `onDelete: KeyAction.cascade`.

## Domain rules worth knowing

- **Active timer** = a `TimeEntries` row with `endTime == null`. The app assumes at
  most one exists; `home_screen.dart` checks for a running timer before starting a
  new one. Preserve that guard in new entry points.
- **Three independent booleans on a time entry:** `isBillable` (should it be
  charged), `isBilled` (already on an invoice), `isLogged` (recorded in an external
  system). They are not redundant — don't collapse them.
- **`CompanySettings` is a singleton row** keyed on `id == 1`; reads use
  `getSingleOrNull()` and writes use `insertOnConflictUpdate` with
  `id: drift.Value(1)`.
- **Invoice line items are denormalized JSON** in `Invoices.lineItemsJson`, encoded
  and decoded with `lineItemsToJson` / `lineItemsFromJson` from
  `lib/models/line_item.dart`. There is no line-items table.
- **Expenses** may attach to a project *or* a client (both nullable), and mileage
  expenses derive `amount` from `distance * costPerUnit`.
- **Currency** is per client (`Clients.currency`, default `USD`) and formatted with
  `NumberFormat.simpleCurrency(name: client.currency)`. Note `reports_screen.dart`
  hardcodes `en_US`/`USD` instead — a known inconsistency, not a convention to copy.
- **Logos** are stored as filesystem paths in `CompanySettings.logoPath` and read
  with `dart:io` `File`, so they are desktop/mobile only.

## Theming

The app is dark-only: a single `ThemeData.dark().copyWith(...)` in `main.dart`
(deep purple seed, `Color.fromARGB(255, 28, 25, 38)` background). Several screens
still hardcode colors inline (e.g. the nav bar's `Color(0xFF1E1E1E)`, teal accents,
green/red `withAlpha` row tints). Prefer `Theme.of(context).colorScheme` in new
code.

## Tests

`test/widget_test.dart` is still the **unmodified Flutter counter template** — it
looks for a counter UI this app doesn't have, and pumps `MyApp` without the
`Provider<AppDatabase>` its screens require, so `flutter test` fails out of the box.
Replace or delete it rather than treating a red run as a real regression. New widget
tests must wrap the tree in a `Provider<AppDatabase>` (use an in-memory
`NativeDatabase.memory()` connection).
