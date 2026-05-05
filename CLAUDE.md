# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
poetry install          # install dependencies
poetry sync             # sync exactly to lock file
poetry run python -m ripper.main                      # run the app
poetry run python -m ripper.main --log-level INFO     # with verbose logging
poetry run python -m ripper.main --clear-credential-cache
poetry run python -m ripper.main db create            # create SQLite DB and schema
poetry run python -m ripper.main db clean             # delete the DB file
```

**Validation (run narrowest first, then broaden before finishing):**

```bash
poetry run pytest test/ripper/ripperlib/test_database.py     # focused lib test
poetry run pytest test/ripper/rippergui/test_mainview.py -m qt  # focused Qt test
poetry run pytest                                              # all tests
poetry run flake8
poetry run ruff check
poetry run mypy
poetry run python scripts/pre-commit.py   # runs flake8 → mypy → pytest in order
```

Run `poetry run black .` and `poetry run isort .` only when formatting/import order changes are needed — avoid unrelated churn.

## Architecture

**Entry point:** `ripper/main.py` — Click CLI, loguru logging setup, `db` subcommands, and default GUI startup.

**`ripper/ripperlib/`** — backend logic, no Qt dependencies:
- `auth.py` — Google OAuth client registration, token storage, and service construction. All OAuth/credential work lives here; tests must mock keyring and Google APIs.
- `sheets_backend.py` — Google Sheets/Drive API calls and cache population.
- `database.py` — SQLite persistence via the `Db` application-wide singleton. Uses a context-manager transaction pattern for thread-safe access. Tests that change DB state must isolate paths/connections and clean up.
- `range_manager.py` — `CellRange` dataclass with full A1 range algebra: parsing, intersection, union, subtraction, and containment.
- `sheet_data_cache.py` — Smart cache that reuses stored ranges and fetches only missing sub-ranges.
- `defs.py` — API data models (`SpreadsheetProperties`, `SheetProperties`), Protocol classes for Google API services, `get_app_data_dir()`, constants (`LOG_FILE_PATH`, `DRIVE_FILE_FIELDS`), and `LoadSource` enum.

**`ripper/rippergui/`** — PySide6/Qt6 UI:
- `mainview.py` — Main window; dockable table, OAuth and File menus. Save, Print, and Undo are placeholder stubs; New Source is fully implemented.
- `sheets_selection_view.py` — Spreadsheet/worksheet/range selection dialog.
- `table_view.py` — Sortable, filterable transaction table. Expects columns: `ID`, `Date`, `Description`, `Category`, `Amount`, `Account`.
- `oauth_client_config_view.py` — OAuth client credential entry dialog.
- `fonts.py` — `FontManager` singleton for application fonts.
- `widgets/` — Reusable Qt widgets (e.g., `accordion_widget.py`).
- `dashboard/` — Prototype dashboard subsystem:
  - `models/` — `Dashboard`, widget, data source, and Tiller data models; `registry.py` for widget type registration.
  - `views/` — Dashboard editor/viewer and data source dialog.
  - `services.py` — Synchronous data refresh service (`DashboardDataService`).

**Test layout:** `test/ripper/ripperlib/` and `test/ripper/rippergui/` mirror the source tree. The `qt` pytest marker is declared for Qt-specific tests; these may need skipping in headless CI.

## Key Constraints

- **Singletons** (`Db`, `AuthManager`, `FontManager`) are established patterns — do not introduce new singleton-style global state.
- **mypy** is currently scoped to `ripper/main.py` only (`[tool.mypy].files = ["ripper/main.py"]`); do not widen this scope unintentionally.
- **beartype** runtime checking is present in dev dependencies and available but currently commented out in `pytest addopts`.
- **No live API calls in tests** — mock Google API clients, keyring, filesystem paths, and network downloads.
- **Long-running/networked work** must not run in direct Qt UI event handlers; use background threads (existing code uses `QThread`-based workers).
- Use **Qt signals/slots** for cross-widget state changes rather than direct coupling.

## Coding Style

- `loguru.logger` for diagnostics, never `print`.
- f-strings for string formatting.
- `beartype.typing` for imported typing constructs in files that already use it; `list[...]`/`tuple[...]` built-in generics elsewhere.
- `X | None` over `Optional[X]` in files already using modern union syntax — do not churn unrelated annotations.
- No mutable default arguments.

## Local Data Paths (runtime)

- SQLite DB: `platformdirs.user_data_dir("ripper") / "ripper.db"`
- Log file: `<user-data-dir>/ripper.log` (rotates at 10 MB, retains 10 days)
- OAuth credentials/tokens: system keyring
