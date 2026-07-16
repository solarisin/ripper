# Dashboard System Status And Path Forward

## Purpose

The dashboard system provides an embedded financial dashboard experience inside the main Ripper GUI. It is focused on Tiller-style Google Sheets data and is built around persisted dashboard configuration, runtime-only data refresh, and widget renderers created from widget configs.

## Implemented

- Dashboards run through the main Ripper `Dashboard` tab. The separate standalone dashboard shell has been removed.
- Dashboard JSON persists data sources and `WidgetConfig` objects only. Runtime widget classes are created from config through the widget registry.
- Data sources store exact spreadsheet selection: spreadsheet ID, sheet name, and A1 range.
- The dashboard editor can add/remove widget configs, edit widget title, assign a data source, and create a transaction data source through the Google Sheet picker.
- Transaction data-source creation validates required normalized columns before saving: `date`, `description`, `category`, `amount`, and `account`.
- `DashboardDataService` refreshes transaction data sources through `AuthManager`, uses the existing cached Sheets retrieval path, applies date/account/category filters, and returns structured refresh status.
- Dashboard view refresh stores fetched rows in runtime memory only and re-renders widgets from config plus refreshed data.
- Spending trend, category breakdown, and top expenses widgets consume refreshed transaction data.
- Budget vs actual remains visible but reports that budget sources are not supported yet.

## Still Not Implemented

- Tiller categories and budget data-source refresh.
- The non-functional placeholder and unimplemented widget types (line chart, bar chart, pie chart, table, KPI, gauge, net worth, savings goal, income-vs-expense) were removed in #41 rather than left pending. Only the four functional financial widgets (spending trend, category breakdown, budget vs actual, top expenses) remain. Re-adding any of these would require a real implementation plus registry entry.
- Full widget-specific properties such as colors, limits, category options, and chart style.
- Moving/resizing existing widgets after they are dropped.
- Dashboard rename, duplicate, import/export, and multi-dashboard selector UI.
- Account/category list population from a selected spreadsheet in the editor.
- Persisted migration for old dashboard JSON. Existing files may need to be recreated.

## Remaining Design Work

- Decide whether `DataSource.fetch_data()` should remain as a legacy convenience or be removed so all dashboard reads flow through `DashboardDataService`.
- Add a clearer dashboard-level status surface instead of modal warnings for refresh failures.
- Add a formal runtime data cache type if more source types are added.
- Decide how budget data should be modeled before implementing budget-vs-actual for real.

## Recommended Next Steps

1. Add categories and budget refresh support to `DashboardDataService`.
2. Replace budget-vs-actual's unsupported state with a real budget-backed implementation.
3. Populate account/category filter choices from refreshed transaction data.
4. Add widget-specific property editors for the currently implemented financial widgets.
5. Add move/resize behavior to `DashboardCanvas`.
6. Add a multi-dashboard selector and dashboard rename flow.

## Test Coverage Added

- Dashboard JSON round trip with config-only widgets.
- Data source exact range serialization.
- Referenced data source removal guard.
- Required transaction column validation.
- Missing-auth and unsupported-source refresh statuses.
- Transaction refresh with exact sheet/range and date filtering.
- Dashboard view rendering from `WidgetConfig`.
