# Tests

The test suite mirrors the package layout under `test/ripper/`:

```
test/
├── conftest.py                     # shared fixtures (offscreen Qt, isolated Db singleton)
├── ripper/
│   ├── ripperlib/                  # backend tests (auth, database, sheets_backend, range_manager, ...)
│   └── rippergui/                  # Qt UI tests (mainview, table_view, dashboard/, ...)
```

## Conventions

- **No live external calls.** Google Sheets/Drive clients, `keyring`, the filesystem, and network
  downloads are always mocked. Test doubles must satisfy the declared types/Protocols that beartype
  enforces at runtime — use `MagicMock(spec=...)`, not a bare `object()`.
- **Qt tests carry the `qt` marker** (`@pytest.mark.qt`, or a module-level `pytestmark`). CI runs
  `-m "not qt"` so the GUI-only tests are skipped headlessly; everything else, including the
  non-Qt dashboard model/service tests, runs in CI. `conftest.py` forces `QT_QPA_PLATFORM=offscreen`
  so `qt` tests still run locally without a display.
- **DB tests isolate state.** The autouse `_isolate_global_db` fixture swaps a per-test temporary
  `RipperDb` in and out; tests that construct `RipperDb` directly use temp files and clean up.

## Running

The canonical commands live in the repo `CLAUDE.md` ("Validation"). In short:

```bash
uv run pytest                        # whole suite (includes qt tests locally)
uv run pytest test/ripper/ripperlib/test_database.py     # one file
uv run pytest -m qt                  # only Qt tests
uv run pytest -m "not qt"            # what CI runs
```

Lint/format/type checks: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`.
