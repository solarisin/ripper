# Ripper

Ripper is a Python/PySide6 desktop application for browsing Google Sheets data, caching spreadsheet metadata and cell ranges locally, and experimenting with dashboard views over Tiller-style financial spreadsheets.

The most complete workflow is the main Google Sheets browser:

1. Register a Google OAuth client.
2. Authenticate with Google.
3. Select a spreadsheet from Drive.
4. Choose a worksheet and A1 range.
5. Load the data into a sortable, filterable table view.

For a fuller architecture and usage walkthrough, see [Project Purpose And Usage](docs/PROJECT_PURPOSE_AND_USAGE.md). For dashboard design notes, see [Dashboard System Status And Path Forward](docs/DASHBOARD_SYSTEM_STATUS.md).

## Features

- Google OAuth client registration from `client_secret.json` or manual client ID/secret entry.
- Google OAuth login with Sheets and Drive access.
- Google Drive spreadsheet browsing with cached metadata and thumbnails.
- Google Sheets worksheet/range selection with A1 range validation.
- SQLite-backed cache for spreadsheet metadata, sheet metadata, thumbnails, and cell ranges.
- Smart sheet-data cache that can reuse cached ranges and fetch only missing sub-ranges.
- Dockable transaction-style table view with sorting and filters.
- Embedded dashboard subsystem for JSON-backed financial dashboards and Tiller-style data widgets.

## Project Layout

- `ripper/main.py`: Click CLI, logging setup, database subcommands, and main GUI startup.
- `ripper/ripperlib/`: Auth, Google API access, SQLite cache, data models, and range/cache logic.
- `ripper/rippergui/`: Main Qt window, OAuth setup UI, sheet selection UI, thumbnails, table view, and reusable widgets.
- `ripper/rippergui/dashboard/`: Dashboard models, editor/view widgets, financial widgets, and data refresh service.
- `test/`: Pytest suite.
- `scripts/`: Developer helper scripts.
- `res/`: Image/resource helpers.

## Requirements

- Python `>=3.11,<3.14`
- Poetry
- A Google Cloud OAuth client configured for an installed/local desktop app

Runtime dependencies are managed by Poetry and include PySide6, Google API client libraries, keyring, loguru, click, platformdirs, pandas, and SQLite from the Python standard library.

## Install

```bash
poetry install
```

To sync the environment exactly with the lock file:

```bash
poetry sync
```

## Run

Start the main application:

```bash
poetry run python -m ripper.main
```

Useful launch options:

```bash
poetry run python -m ripper.main --log-level INFO
poetry run python -m ripper.main --clear-credential-cache
poetry run python -m ripper.main --debug-cli
```

## OAuth And Sheet Loading

In the main GUI:

1. Open `OAuth -> Register/Update OAuth Client`.
2. Select a Google `client_secret.json` file or enter the client ID and client secret manually.
3. Open `OAuth -> Authenticate` and complete the browser-based OAuth flow.
4. Open `File -> Select Google Sheet`.
5. Pick a spreadsheet, worksheet, and range.
6. Confirm the selection to open the data in a dockable table.

The app requests OpenID, user email, Google Sheets, and Google Drive read-only scopes. OAuth client credentials and tokens are stored with the system keyring.

## Local Data

Ripper stores runtime data locally:

- SQLite cache database: `platformdirs.user_data_dir(appname="ripper") / "ripper.db"`
- Log file: `<user-data-dir>/ripper.log`
- OAuth client credentials and tokens: system keyring
- Dashboard JSON files: `platformdirs.user_data_dir(appname="ripper") / "dashboards"` (location varies by platform)

The log file rotates at 10 MB and retains 10 days of logs.

## Database Commands

Create the default database and schema:

```bash
poetry run python -m ripper.main db create
```

Delete the default database file:

```bash
poetry run python -m ripper.main db clean
```

Use a specific database file:

```bash
poetry run python -m ripper.main db --file-path /path/to/ripper.db create
poetry run python -m ripper.main db --file-path /path/to/ripper.db clean
```

## Dashboard Status

The dashboard subsystem can create, save, load, edit, and delete dashboard JSON files. It includes a widget palette, drag-and-drop canvas, and financial widget classes for spending trend, category breakdown, budget vs actual, and top expenses.

This area is still partly prototype-level. Several widget types are scaffolding, some configuration panels are placeholders, and financial widgets expect prepared Tiller-style data to already be attached to their data source.

## Development

Run tests:

```bash
poetry run pytest
```

Run focused tests:

```bash
poetry run pytest test/ripper/ripperlib/test_database.py
poetry run pytest test/ripper/rippergui/test_mainview.py -m qt
```

Run lint and type checks:

```bash
poetry run flake8
poetry run ruff check
poetry run mypy
```

Run the project pre-commit helper:

```bash
poetry run python scripts/pre-commit.py
```

The pre-commit helper runs flake8, mypy, and pytest in that order.

Find GUI tests that may need to be skipped in headless CI:

```bash
poetry run python scripts/find_qt_tests.py
```

## Current Notes

- The main sheet-selection and table-view workflow is the most complete user path.
- The table view is transaction-oriented and currently expects columns named `ID`, `Date`, `Description`, `Category`, `Amount`, and `Account`.
- Unit tests mock Google APIs, keyring, and local paths; they should not make live Google API calls.
- Some GUI actions, including Save, Print, Undo, and New Source, are placeholders in the current code.
