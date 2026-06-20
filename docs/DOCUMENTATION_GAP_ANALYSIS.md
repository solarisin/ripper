# Documentation Gap Analysis

**Date:** 2026-06-20
**Branch:** `doc-review-and-goal-definition`
**Scope:** All in-repo documentation (`README.md`, `CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`, `.junie/guidelines.md`, `docs/`, `scripts/README.md`, `test/README.md`, `ripper/rippergui/dashboard/README.md`) compared against the current code on `main` (HEAD `f67b532`, post `feature/dockable-windows` merge).

This document records what is **accurate**, what is **outdated/contradictory**, and what is **missing** so the docs can be brought back in line with the architecture.

---

## 1. Executive Summary

The codebase has moved on significantly from much of its prose documentation. The single largest driver is the **`feature/dockable-windows`** merge (PR #26) plus the introduction of **persisted, named data sources**. Two user-facing concepts changed that ripple through almost every doc:

1. **`File → Select Google Sheet` no longer exists.** The primary workflow is now `File → New Source`, which creates a *persisted named data source* that appears in a **Data Sources** sidebar.
2. **The UI is now a dockable-panel layout (PySide6QtAds / ADS)**, not a tabbed window. There is no "Data tab" / "Dashboard tab".

Fidelity ranking of the docs (best → worst):

| Document | Fidelity | One-line verdict |
|---|---|---|
| `docs/DASHBOARD_SYSTEM_STATUS.md` | **High** | Matches dashboard code well; best-maintained doc. |
| `ripper/rippergui/dashboard/README.md` | **High** | Consistent with dashboard code. |
| `CLAUDE.md` | **Medium-High** | Mostly correct; file list incomplete; misses sidebar/docks. |
| `AGENTS.md` | **Medium-High** | Commands/constraints correct; references a non-existent `.windsurf/rules/`. |
| `.github/copilot-instructions.md` | **Medium** | Generic rules still valid; no architecture claims to rot. |
| `README.md` | **Medium-Low** | Self-contradictory on New Source; wrong primary workflow; missing deps. |
| `docs/PROJECT_PURPOSE_AND_USAGE.md` | **Low-Medium** | Several stale claims, wrong menu/tab model, contradicts itself. |
| `.junie/guidelines.md` | **Low** | Wrong package layout, wrong test paths, deprecated commands. |
| `test/README.md` | **Low** | Wrong test tree, references deleted functions, stale "known issues". |

---

## 2. Cross-Cutting Architectural Drift

These items affect multiple documents. They are the root causes behind most individual gaps in §3.

### 2.1 `Select Google Sheet` → `New Source` (CRITICAL)
- **Code reality** (`ripper/rippergui/mainview.py`): The File menu contains `New Source`, `Save`, `Print`, `Quit`. There is **no** `Select Google Sheet` action. `New Source` (`new_source()`, `mainview.py:548`) opens `SheetsSelectionDialog`, and on confirmation **persists a named data source** to the `data_sources` table, then refreshes the sidebar.
- **`New Source` is fully implemented**, not a placeholder. `CLAUDE.md` states this correctly; `README.md` and `PROJECT_PURPOSE_AND_USAGE.md` both still call it a placeholder (and `README` even lists it in its placeholder list while the workflow depends on it).
- **Affected docs:** `README.md` (lines 79–81 workflow, line 165 placeholder list), `PROJECT_PURPOSE_AND_USAGE.md` (lines 79–80, 176–209).

### 2.2 Dockable-panel UI via PySide6QtAds (CRITICAL)
- **Code reality:** `MainView` builds the UI on `PySide6QtAds.CDockManager` (`mainview.py:383`). Docks:
  - **Data Sources** dock (left) — `DataSourceListWidget` (`mainview.py:392`).
  - **Table** dock (center) — created on demand to show the active source (`_show_data_source_in_dock`, `mainview.py:749`).
  - **Dashboard** dock (right) — `DashboardManagerWidget` (`mainview.py:308`).
- Dock layout is **persisted to `QSettings("solarisin","ripper")`** with `View → Save Layout` / `Reset Layout` and per-dock toggle actions (`mainview.py:357–410`).
- **Dependency:** `pyside6-qtads = ">=4.5.0"` (`pyproject.toml:28`) is central but is **not listed** in any dependency summary.
- **Affected docs:** `PROJECT_PURPOSE_AND_USAGE.md` (the "Data tab / Dashboard tab" description, lines 73–80, is wrong — these are docks, and a "Data Sources" dock exists), `README.md` and `PROJECT_PURPOSE_AND_USAGE.md` dependency lists.

### 2.3 Persisted named data sources (UNDOCUMENTED)
- **Code reality:** New `data_sources` SQLite table (`database.py:229`) with full CRUD: `create_data_source`, `list_data_sources`, `get_data_source`, `update_data_source`, `delete_data_source`, `update_data_source_fetched_at` (`database.py:972–1150`). Driven by the `DataSourceListWidget` sidebar with select/refresh and `last_fetched_at` tracking.
- **Note — naming collision:** there are now **two** "data source" concepts: (a) the DB-backed named source above (main window), and (b) the dashboard model `DataSource` dataclass (`dashboard/models/data_source.py:61`). Docs should disambiguate.
- **Affected docs:** none currently describe (a). `README.md`, `PROJECT_PURPOSE_AND_USAGE.md`, and `CLAUDE.md` should add it.

### 2.4 Menu structure (drift)
- **Code reality** (`create_menus`, `mainview.py:239`): `File` (New Source, Save, Print, Quit), `Edit` (Undo), `View` (Save/Reset Layout + dock toggles), `Dashboard` (Show Dashboard), `OAuth` (Register/Update, Authenticate), `Help` (About, About Qt).
- Docs variously describe only "OAuth and File menus" (`CLAUDE.md`) or "file/OAuth/dashboard/help" tabs+menus (`PROJECT_PURPOSE`). None list the `Edit`/`View` menus or layout actions.

---

## 3. Per-Document Findings

### 3.1 `README.md` — Medium-Low
**Accurate:** Project description; install/run/`db` commands; OAuth scopes (openid, email, Sheets, Drive read-only); keyring storage; local data paths; log rotation (10 MB / 10 days); lint/type/test commands; "dockable transaction-style table view" feature bullet.

**Outdated / contradictory:**
- Workflow step "Open `File -> Select Google Sheet`" (lines 79–81) — action removed; should be `File → New Source`.
- "New Source" listed as a placeholder (line 165) while it is the implemented primary path — directly contradicts `CLAUDE.md` and the code.
- Dependency list (line 42) omits `pyside6-qtads`, `requests`, and `toml`.

**Missing:**
- Data Sources sidebar and persisted named sources (§2.3).
- Dock layout persistence and the `View`/`Edit`/`Dashboard` menus (§2.2, §2.4).

### 3.2 `docs/PROJECT_PURPOSE_AND_USAGE.md` — Low-Medium
**Accurate:** Install/run/CLI options (`--log-level`, `--clear-credential-cache`, `--debug-cli`); `db` commands and `--file-path`; schema description; keyring key names (`ripper-oauth-client`, `ripper-app-auth-token`, `ripper-app-auth-userinfo`); legacy token-file note (still true — see `auth.py:323`, `auth.py:332`, `auth.py:274`); dashboard subsystem description; Tiller helpers; sheet-data cache behavior; test-coverage overview.

**Outdated / contradictory:**
- "A `Data` tab … A `Dashboard` tab" (lines 75–80) — the UI is dockable panels, not tabs; a **Data Sources** dock is unmentioned.
- "File menu and toolbar … New Source, Select Google Sheet, Save, Print, and Undo … implemented sheet-loading path is `Select Google Sheet`; Save, Print, Undo, and **New Source** are placeholders" (lines 79–80) — `Select Google Sheet` is gone; `New Source` is implemented; `Undo` lives in the `Edit` menu.
- "The top-level `README.md` contains only the project name." (line 352) — **false**; README is now comprehensive (and this very doc is linked from it).
- "Some error paths print directly instead of using Loguru." (line 358) — **false**; there are no `print(` calls in `ripper/` (verified). This is resolved.

**Missing:** Data Sources sidebar/persistence; dock layout persistence; `View`/`Edit` menus.

### 3.3 `CLAUDE.md` — Medium-High
**Accurate:** Commands block; architecture boundaries (`ripperlib` no-Qt, `auth.py`/`sheets_backend.py`/`database.py`/`range_manager.py`/`sheet_data_cache.py` roles); `defs.py` contents (verified: Protocols, `SpreadsheetProperties`, `SheetProperties`, `get_app_data_dir`, `LOG_FILE_PATH`, `DRIVE_FILE_FIELDS`, `LoadSource`); singletons; mypy scoped to `ripper/main.py` (`pyproject.toml:88`); `qt` marker; table-view expected columns; "New Source is fully implemented" (correct, unlike README/PROJECT_PURPOSE).

**Outdated / incomplete:**
- `rippergui/` file list omits three present modules: `datasource_list_widget.py`, `sheet_utils.py`, `spreadsheet_thumbnail_widget.py`.
- `mainview.py` summary ("dockable table, OAuth and File menus") understates current scope: it omits the Data Sources sidebar, Dashboard dock, and `Edit`/`View`/`Dashboard` menus.
- `oauth_client_config_view.py` is described as the OAuth dialog; note its primary class is `AuthView` (minor, for grep-ability).

**Missing:** the `data_sources` DB table + CRUD; dock layout persistence.

### 3.4 `AGENTS.md` — Medium-High
**Accurate:** Project shape; Poetry commands incl. modern `$(poetry env activate)`; Python `>=3.11,<3.14`, mypy `python_version 3.12`; pytest config (testpaths/pythonpath/coverage/strict markers); flake8 via `flake8-pyproject`; mypy scoped to `ripper/main.py`; pre-commit runs flake8→mypy→pytest with **no** black/isort; the corrections list (tests under `test/ripper/...`, etc.).

**Outdated:**
- Line 98 references "`.windsurf/rules/` files" as background — **`.windsurf/` does not exist** in the repo. Either drop the reference or note it as historical.

### 3.5 `.github/copilot-instructions.md` — Medium
**Accurate:** Tooling rules (pytest/mypy/flake8/ruff incl. `ruff format`), tests in `test/`, no network in tests, type hints, loguru-not-print, f-strings, no mutable defaults, imports at top, PySide6/Qt6, no disabling lint without consent.

**Minor:** Rule 9 ("prefer `beartype.typing`") is stricter than `CLAUDE.md`/`AGENTS.md`, which say *follow the local file's style* (the codebase is mixed — `defs.py` uses `beartype.typing`, many files use built-in generics). Harmonize the guidance.

### 3.6 `.junie/guidelines.md` — Low
**Accurate:** Target use case (Tiller bank transactions → local DB → visualize); Google Cloud OAuth setup steps; general intent.

**Outdated (significant):**
- Project Structure (lines 145–155): claims `ripperlib/` and `rippergui/` at the repo root with `main.py` **inside** `ripperlib/`. Reality: everything is under `ripper/`, and the entry point is `ripper/main.py`.
- Test Structure (line 56, 72–79): `test/ripperlib/...`. Reality: `test/ripper/ripperlib/...`.
- The cited test `test_list_sheets_success` and function `list_sheets` **no longer exist** (verified — no `list_sheets` in `ripper/`).
- "Activate … `poetry shell`" (line 35) is deprecated in Poetry 2.x; `AGENTS.md` uses the current `$(poetry env activate)`.
- "Black for code formatting (line length 120)" / `poetry run black .` as *the* style tool (lines 159–166): there is no black config in `pyproject.toml`; ruff (`ruff format`, line-length 120) is the active formatter. black/isort remain in dev deps but are not the documented path, and pre-commit does not run them.

`AGENTS.md` already warns this file needs verification — but the file itself is uncorrected.

### 3.7 `test/README.md` — Low
**Accurate:** Mocking philosophy (no live API calls); pytest-qt usage; high-level approach.

**Outdated (significant):**
- Test tree (lines 17–28) shows `test/ripperlib/` and `test/rippergui/` with ~5 files. Reality: `test/ripper/ripperlib/` (incl. `test_database_caching.py`, `test_defs.py`, `test_range_manager.py`, `test_sheet_data_cache.py`), `test/ripper/rippergui/` (incl. `test_mainview.py`, `test_oauth_client_config_view.py`, `test_sheet_utils.py`, `test_sheets_selection_view.py`, `widgets/test_accordion_widget.py`), and `test/ripper/rippergui/dashboard/` (4 files). ~16 test files total.
- Examples reference `ripperlib.database.create_connection`, `retrieve_transactions`, and `list_sheets` — wrong import root (`ripper.ripperlib`) and/or **deleted functions**.
- "Known Issues" (lines 158–166) are stale history: the `@pytest.mark.qt` marker is now registered (`pyproject.toml:64`), and the listed failing-test issues read as obsolete.

### 3.8 `scripts/README.md` — Medium-High
**Accurate:** Describes `pre-commit.py` + wrappers (`.ps1`/`.sh`/`.bat`), check order flake8→mypy→pytest, exit codes, git-hook setup. Matches `scripts/`.

**Minor (cosmetic):** The heading and intro paragraph are **duplicated** (lines 1–7 repeat "# Pre-commit Scripts" / "This directory contains…"). Remove the duplicate.

### 3.9 `docs/DASHBOARD_SYSTEM_STATUS.md` & `ripper/rippergui/dashboard/README.md` — High
**Accurate and well-maintained.** Verified against code:
- `DashboardManager` (`dashboard/models/dashboard.py:144`), `Dashboard`, `WidgetConfig` (`widgets.py:18`), `DataSource` (`data_source.py:61`), `DashboardView`, `DashboardDataService`/`DataSourceRefreshStatus` (`services.py`).
- `WidgetType` enum (`widget_types.py`) has all 13 values; spending trend / category breakdown / top expenses implemented (`financial_widgets.py`), budget-vs-actual shows "unsupported", and net worth / savings goal / income-vs-expense are enum-only — exactly as documented.
- Standalone dashboard shell removed; dashboard runs as a dock — matches code.

**Minor:** could note the `__init__` export `DashboardManagerWidget` (the Qt wrapper around `DashboardView`) alongside `DashboardManager`.

---

## 4. Missing / Referenced-But-Absent

- **`.windsurf/rules/`** — referenced by `AGENTS.md` (line 98) and the documentation-review brief, but the directory does not exist. No Windsurf rules are present in the repo.
- **No `data_sources` table / named-source workflow documentation** anywhere outside this analysis (§2.3).
- **No documentation of dock layout persistence** (`QSettings` keys, Save/Reset Layout) (§2.2).
- **`pyside6-qtads` dependency** is undocumented in every dependency summary despite being foundational to the UI.

---

## 5. Prioritized Remediation Plan

**P0 — correctness (users/agents will be actively misled):**
1. Replace every `Select Google Sheet` reference with the `New Source` workflow; stop calling `New Source` a placeholder (`README.md`, `PROJECT_PURPOSE_AND_USAGE.md`).
2. Rewrite the "tabs" description as the dockable-panel layout and document the **Data Sources** sidebar + persisted named sources (`README.md`, `PROJECT_PURPOSE_AND_USAGE.md`).
3. Fix `.junie/guidelines.md` package/test paths and the deleted-function examples, or mark the file as deprecated in favor of `AGENTS.md`/`CLAUDE.md`.
4. Fix `test/README.md` test tree and deleted-function examples; remove or date the stale "Known Issues".

**P1 — completeness:**
5. Add `pyside6-qtads` (and `requests`/`toml`) to dependency summaries.
6. Add the three missing `rippergui/` modules to `CLAUDE.md`; expand the `mainview.py` summary (sidebar, docks, `Edit`/`View`/`Dashboard` menus).
7. Document the `data_sources` table + CRUD and disambiguate it from the dashboard `DataSource` model.
8. Document dock layout persistence (`View → Save/Reset Layout`, `QSettings`).

**P2 — hygiene:**
9. Remove the stale "README contains only the project name" and "print instead of Loguru" claims from `PROJECT_PURPOSE_AND_USAGE.md`.
10. Resolve the `.windsurf/rules/` reference in `AGENTS.md`.
11. De-duplicate the `scripts/README.md` heading block.
12. Harmonize the `beartype.typing` guidance across `copilot-instructions.md`, `CLAUDE.md`, and `AGENTS.md`.

---

## 6. Verification Notes

Claims in this document were checked against source at HEAD `f67b532`:
- Menu/dock/workflow facts: `ripper/rippergui/mainview.py`.
- Data-source persistence: `ripper/ripperlib/database.py` (`create_tables`, `*_data_source*`).
- `defs.py` contents and `LoadSource`: `ripper/ripperlib/defs.py`.
- Dashboard model/enum/widget status: `ripper/rippergui/dashboard/**`.
- Tooling/scoping: `pyproject.toml`.
- "No `print()`" and "no `list_sheets`/`retrieve_transactions`": repo-wide grep over `ripper/`.
- `.windsurf/` absence: directory listing.
