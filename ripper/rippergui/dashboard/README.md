# Dashboard System

Ripper dashboards are embedded in the main Ripper GUI. They are JSON-backed configurations for financial widgets over Tiller-style Google Sheets data.

## Current Capabilities

- Create, load, save, and delete dashboard JSON files.
- Persist dashboard data sources and widget configurations.
- Add widgets from a palette to a dashboard canvas.
- Create a Tiller transaction data source with the Google Sheet picker.
- Store exact spreadsheet ID, sheet name, and A1 range for each data source.
- Validate transaction sources for required columns before saving.
- Refresh transaction data through `DashboardDataService`.
- Render spending trend, category breakdown, and top expenses from refreshed transaction data.

## Current Limits

- The standalone dashboard application has been removed; use the main Ripper GUI.
- Existing dashboard JSON compatibility is not guaranteed.
- Budget/category source refresh is not implemented yet.
- Budget vs actual shows an unsupported state.
- Several basic widget types are placeholders.
- Existing widgets cannot yet be moved or resized after drop.
- Widget properties are limited to title and data-source assignment.

## Storage

Dashboard files are stored under:

```text
~/.ripper/dashboards
```

Fetched sheet data is runtime-only in the dashboard layer. It is not written to dashboard JSON.
