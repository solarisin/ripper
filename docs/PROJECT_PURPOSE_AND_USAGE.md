# Ripper Project Purpose And Usage

## Overview

Ripper is a Python and Qt desktop application for browsing Google Sheets data, caching spreadsheet metadata and cell data locally, and experimenting with financial dashboard views over Tiller-style spreadsheet data.

The primary application flow is:

1. Start the Ripper desktop application.
2. Register a Google OAuth client.
3. Authenticate with Google.
4. Select a Google Sheet from Drive.
5. Choose a worksheet and A1 range.
6. Load the selected data into a sortable, filterable table view.

The repository also contains an embedded dashboard subsystem. It stores dashboard definitions as JSON files, lets users create/edit dashboards, and includes financial widgets for spending trends, category breakdowns, budget comparison, and top expenses.

## Project Layout

- `ripper/main.py`: Click command line entry point, logging setup, database commands, and main GUI startup.
- `ripper/ripperlib/`: Core non-UI logic for Google OAuth, Google Sheets/Drive access, SQLite persistence, range parsing, and sheet-data caching.
- `ripper/rippergui/`: Main Qt GUI, OAuth configuration view, Google Sheet selection dialog, table view, thumbnail widget, reusable widgets, and font utilities.
- `ripper/rippergui/dashboard/`: Dashboard models, dashboard editor/view widgets, financial widgets, and dashboard data refresh services.
- `test/`: Pytest test suite mirroring the package layout.
- `scripts/`: Developer helper scripts, including pre-commit checks and Qt test discovery.
- `res/`: Application image/resource helpers. This directory is excluded from ruff.

## Runtime Dependencies

Ripper targets Python `>=3.11,<3.14` and uses [uv](https://docs.astral.sh/uv/) for dependency management.

The main runtime stack is:

- PySide6 for the desktop GUI.
- Click for the command line interface.
- Loguru for diagnostics.
- Google API client libraries for Drive, Sheets, OAuth, and OAuth user info.
- Keyring for secure storage of OAuth client credentials and OAuth tokens.
- SQLite for local cache storage.
- Platformdirs for locating the per-user application data directory.
- Pandas and Qt Charts for financial dashboard processing and visualization.

## Installation

From the repository root, create the virtual environment and install dependencies exactly to the lock file:

```bash
uv sync
```

To activate the environment in the current shell:

```bash
source .venv/bin/activate   # on Windows: .venv\Scripts\activate
```

Commands can also be run without activating the environment by prefixing them with `uv run`.

## Running The Main Application

Start the main Ripper GUI with:

```bash
uv run python -m ripper.main
```

The application opens a Qt main window with:

- A `Data` tab for sheet loading and table display.
- A `Dashboard` tab backed by the dashboard subsystem.
- Menus for file actions, OAuth setup/authentication, dashboard access, and help.
- A status bar showing the current authentication state.

The File menu and toolbar currently include actions such as New Source, Select Google Sheet, Save, Print, and Undo. The implemented sheet-loading path is `Select Google Sheet`; Save, Print, Undo, and New Source are placeholders in the current code.

## Command Line Options

The root command accepts:

```bash
uv run python -m ripper.main --log-level INFO
uv run python -m ripper.main --clear-credential-cache
uv run python -m ripper.main --debug-cli
```

Options:

- `--log-level`, `-l`: Sets stdout and file log verbosity. Valid values are `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`. The default is `DEBUG`.
- `--clear-credential-cache`, `-c`: Clears stored OAuth tokens before launching the GUI.
- `--debug-cli`: Logs Click context and parameter details for debugging command invocation.

## Database Commands

Ripper stores cache data in a SQLite database under the user application data directory. The default path is `platformdirs.user_data_dir(appname="ripper") / "ripper.db"`.

Create the database and schema:

```bash
uv run python -m ripper.main db create
```

Delete the database file:

```bash
uv run python -m ripper.main db clean
```

Operate on a specific database file:

```bash
uv run python -m ripper.main db --file-path /path/to/ripper.db create
uv run python -m ripper.main db --file-path /path/to/ripper.db clean
```

The schema stores:

- Spreadsheet metadata from Google Drive.
- Sheet metadata and grid dimensions from Google Sheets.
- Spreadsheet thumbnails.
- Cached cell ranges and individual cell values.

When spreadsheet metadata changes, related sheet metadata, thumbnail data, and cached cell ranges are invalidated.

## Logging And Local Data

Logs are written to stdout/stderr and to:

```text
<user-data-dir>/ripper.log
```

The log file rotates at 10 MB and retains 10 days of logs.

Local persistent state includes:

- SQLite cache database in the platform-specific Ripper data directory.
- OAuth client credentials in the system keyring under `ripper-oauth-client`.
- OAuth token and user info in the system keyring under `ripper-app-auth-token` and `ripper-app-auth-userinfo`.
- Some legacy token-file helper methods still point at `%APPDATA%/ripper/token.json`, but the active token storage path in the current authorization flow is keyring-based.
- Dashboard JSON files under `platformdirs.user_data_dir(appname="ripper") / "dashboards"` (location varies by platform).

## Google OAuth Setup

Before selecting sheets, the app needs Google OAuth client credentials. Use:

```text
OAuth -> Register/Update OAuth Client
```

The dialog supports two registration methods:

- Select a Google `client_secret.json` file.
- Enter a client ID and client secret manually.

The OAuth scopes requested by the app are:

- `openid`
- Google user email
- Google Sheets access
- Google Drive read-only access

After registering the client, use:

```text
OAuth -> Authenticate
```

Authentication starts a local-server OAuth flow in the browser. On success, the app stores the token in keyring, fetches user info, and updates the status bar to show the logged-in email address.

## Selecting And Loading A Google Sheet

After authentication, use:

```text
File -> Select Google Sheet
```

The selection dialog:

- Lists Google spreadsheets found in the user's Drive.
- Shows spreadsheet thumbnails, loaded from cache when available.
- Displays spreadsheet metadata such as name, ID, created/modified timestamps, owner, sharing state, and web link.
- Loads worksheet names and dimensions for the selected spreadsheet.
- Pre-fills a range covering the selected worksheet, for example `A1:Z1000`.
- Validates range syntax and bounds before allowing selection.

When the user confirms a sheet:

1. The selected range is retrieved through `retrieve_sheet_data`.
2. The sheet-data cache checks whether the requested range can be served from SQLite.
3. Missing ranges are fetched from Google Sheets and cached.
4. Data is converted from rows into records using the first row as headers.
5. A dockable table view is added to the main window.

The table view supports:

- Sorting by column.
- Type-aware sorting for numbers and dates.
- Filtering by description, category, account, and amount range.
- Clearing all active filters.

The table model currently has a fixed transaction-oriented column list: `ID`, `Date`, `Description`, `Category`, `Amount`, and `Account`. It is best suited for sheets whose headers match those names, especially Tiller transaction sheets.

## Sheet Data Cache

The cache system is designed to avoid refetching data unnecessarily from Google Sheets.

Core behavior:

- A1 ranges are parsed into 1-based `CellRange` objects.
- Cached ranges are compared with requested ranges.
- Exact or covering cached ranges are served from SQLite.
- Missing sub-ranges are fetched from the API.
- Cached and newly fetched data are combined into one result matrix.
- Incomplete or orphaned cached ranges are detected and cleaned up before reuse.

The cache records both range metadata and cell values. Range sources are returned with each request, allowing callers to log whether data came from the database, the API, or a combination.

## Dashboard Subsystem

The dashboard subsystem is available inside the main GUI as the `Dashboard` tab.

Dashboard definitions are stored as JSON files in the platform-specific user data directory:

```text
platformdirs.user_data_dir(appname="ripper") / "dashboards"
```

The exact path depends on the operating system (e.g. `~/.local/share/ripper/dashboards` on Linux, `~/Library/Application Support/ripper/dashboards` on macOS). See `ripper.ripperlib.defs.get_app_data_dir()`.

Dashboard concepts:

- `Dashboard`: A named collection of data sources and widget configurations.
- `DataSource`: A configured Tiller data source, including spreadsheet ID, sheet name, exact A1 range, source type, date range, and filters.
- `WidgetConfig`: Widget identity, type, title, grid position, size, optional data source, and widget properties.
- `DashboardManager`: Loads, saves, creates, and deletes dashboard JSON files.
- Widget registry: Maps widget types to widget classes for dynamic loading.

Available widget types (the four functional financial widgets; non-functional placeholder and unimplemented types were removed in #41):

- Spending trend
- Category breakdown
- Budget vs actual
- Top expenses

The dashboard editor has a widget palette, drag-and-drop canvas, save button, delete-widget action, a transaction data-source picker, and minimal widget title/data-source properties. Financial widgets can render Qt Charts or tables when backed by refreshed Tiller transaction data.

## Tiller Data Support

The code includes helper functions for Tiller-style spreadsheets:

- `get_tiller_transactions`
- `get_tiller_categories`
- `get_tiller_budget`

These helpers read `A:Z` from the configured sheet, use the first row as headers, normalize header names to lowercase with underscores, and return a list of dictionaries.

Dashboard processing uses `TillerDataProcessor`, which converts transactions into a pandas DataFrame and supports:

- Date range filtering.
- Category filtering.
- Monthly spending aggregation.
- Spending by category.
- Top expenses.
- Budget vs actual comparison.
- Simplified net-worth-over-time calculation.

The current dashboard data-source fetch path accepts date ranges and filter options, but the lower-level Tiller retrieval helpers do not yet apply all of those filters internally.

## Developer Commands

Run all tests:

```bash
uv run pytest
```

Run a focused test file:

```bash
uv run pytest test/ripper/ripperlib/test_database.py
uv run pytest test/ripper/rippergui/test_mainview.py -m qt
```

Run linting and formatting checks:

```bash
uv run ruff check .
uv run ruff format --check .
```

Run type checking:

```bash
uv run mypy
```

Run the project pre-commit helper:

```bash
uv run python scripts/pre-commit.py
```

The pre-commit helper runs ruff (lint + format check), mypy, and pytest in that order.

Find Qt GUI tests that may need to be excluded in headless CI:

```bash
uv run python scripts/find_qt_tests.py
```

## Test Coverage

The test suite covers:

- OAuth state, token storage, credential loading, and AuthManager behavior.
- Spreadsheet and sheet property models.
- SQLite schema and CRUD/cache behavior.
- A1 range parsing, range overlap, containment, subtraction, and missing-range optimization.
- Sheet data cache behavior and fallbacks.
- Google Sheets/Drive backend functions with mocked API services.
- Main GUI authentication-state behavior.
- OAuth client configuration UI.
- Sheet selection and range validation UI.
- Spreadsheet thumbnail UI.
- Transaction table sorting/filtering.
- Accordion widget behavior.
- Financial dashboard widget models.

Unit tests mock Google APIs, keyring, and filesystem/database paths where appropriate. The project should not make live Google API calls during tests.

## Current Implementation Notes

The codebase is functional but still has prototype areas:

- The top-level `README.md` contains only the project name.
- Some GUI actions are placeholders.
- The table view is transaction-oriented even though the sheet selector can load any range.
- The dashboard subsystem is partially implemented; several controls and widget types are scaffolding.
- Some dashboard financial widgets expect data to already be attached to a `DataSource`.
- Some error paths print directly instead of using Loguru.
- The OAuth/token code contains both keyring-based storage and older token-file helper methods.

These notes are important when using the app: the main Google Sheets selection and table viewing path is the most complete user workflow, while dashboard editing and data-source configuration are still evolving.
