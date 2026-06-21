# Codex Project Instructions

## Project Shape

Ripper is a Python GUI application for browsing Google Sheets data and caching spreadsheet metadata/data locally.

- Application code lives under `ripper/`.
- Core data, auth, Google API, and SQLite logic lives under `ripper/ripperlib/`.
- Qt UI code lives under `ripper/rippergui/`.
- Tests live under `test/` and mirror the package path, for example `test/ripper/ripperlib/test_database.py`.
- Developer helper scripts live under `scripts/`.
- Resource helpers live under `res/`; `res/` is excluded from ruff.

The main entry point is `ripper/main.py`. It defines the Click CLI, logging setup, database subcommands, and the default GUI startup path.

## Environment And Commands

Use Poetry for project commands.

```bash
poetry install
poetry sync
$(poetry env activate)
poetry run python -m ripper.main
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
poetry run python scripts/pre-commit.py
```

Notes:

- `pyproject.toml` supports Python `>=3.11,<3.14`; mypy is configured with `python_version = "3.12"`.
- Pytest is configured with `testpaths = ["test"]`, `pythonpath = ["."]`, `--import-mode=importlib`, beartype runtime checking (`--beartype-packages=ripper`), and strict markers. Coverage is invoked explicitly in CI rather than in default `addopts`.
- The `qt` pytest marker is declared for Qt-specific tests; CI runs `-m "not qt" -p no:pytest_qt`.
- ruff is the single tool for linting, import sorting, and formatting (it replaces flake8, isort, and black).
- Mypy checks the whole `ripper` package because `[tool.mypy].files = ["ripper"]`, and runs in CI.
- The pre-commit script runs ruff (lint + format check), mypy, and pytest in that order.

For targeted validation during edits, prefer the narrowest relevant command first, then run broader checks before finishing if the change is not trivial.

## Coding Style

- Keep imports at module scope unless there is a concrete dependency or startup-time reason to defer them.
- Avoid global mutable state when adding new code. Existing singletons such as `Db`, `AuthManager`, and `FontManager` are established project patterns; do not introduce new singleton-style state casually.
- Use f-strings for formatting.
- Use `loguru.logger` for application diagnostics instead of `print`.
- Avoid mutable default arguments.
- Keep trailing whitespace and whitespace-only blank lines out of edits.
- Use modern Python type hints. Existing code commonly uses `beartype.typing` for imported typing constructs and built-in generics such as `list[...]` and `tuple[...]`; follow the local file's style.
- Prefer `X | None` over `Optional[X]` when touching code that already uses modern union syntax. Do not churn unrelated annotations just for style.
- Add docstrings for new public functions, classes, commands, fixtures, and non-obvious helpers. Keep comments focused on why the code exists or why a constraint matters.

## Qt And GUI Guidance

- Use PySide6/Qt6 only.
- Keep widgets modular and testable with `pytest-qt`.
- Register widgets with `qtbot.addWidget(...)` in tests.
- Be careful with Qt ownership and parent-child relationships. Pass parents where appropriate and make sure widgets are inserted into layouts or containers before assuming they are visible.
- Use Qt signals/slots for UI state changes instead of direct cross-widget coupling where practical.
- For images/icons, prefer existing Qt resource or `QIcon.fromTheme(...)` patterns already present in the UI.
- Keep long-running or networked work out of direct UI event handlers unless the existing code path already does it and the change is deliberately scoped.

## Auth, Google API, And Database Boundaries

- Google OAuth and service construction are centered in `ripper/ripperlib/auth.py`.
- OAuth tokens, user info, and OAuth client credentials are stored through `keyring`; tests should mock keyring and Google API calls rather than touching real user credentials or network services.
- Google Sheets/Drive retrieval and cache population are centered in `ripper/ripperlib/sheets_backend.py`.
- SQLite persistence is centered in `ripper/ripperlib/database.py`.
- `Db` is the application-wide database singleton instance. Tests that change database state should isolate paths/connections and clean up after themselves.
- Do not make live Google API calls from unit tests.

## Testing Guidance

- Add or update tests with production changes.
- For backend logic, mock Google API clients, keyring, filesystem paths, and network downloads as needed.
- For GUI logic, use `pytest-qt`; keep assertions around visible state, enabled/disabled actions, emitted signals, and model/view data.
- Prefer focused test runs while iterating, for example:

```bash
poetry run pytest test/ripper/ripperlib/test_database.py
poetry run pytest test/ripper/rippergui/test_mainview.py -m qt
```

Before handing off broad changes, run:

```bash
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
```

Run `poetry run ruff format .` and `poetry run ruff check --fix .` when formatting/import order changes are needed, but avoid unrelated formatting churn.

## When Updating Existing Guidance

The older `.junie/guidelines.md` and `.windsurf/rules/` files are useful background, but verify their file paths and commands against the live repository before relying on them. Known corrections reflected here:

- Tests are under `test/ripper/...`, not `test/ripperlib/...`.
- `ripper/main.py` is the entry point; `ripperlib` and `rippergui` are subpackages under `ripper/`.
- ruff (lint + format) replaces flake8, isort, and black; the pre-commit helper runs ruff, mypy, then pytest.
- Mypy checks the full `ripper` package (`[tool.mypy].files = ["ripper"]`).
