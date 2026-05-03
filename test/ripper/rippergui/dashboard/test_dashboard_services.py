"""Tests for dashboard data refresh services."""

from datetime import datetime

from ripper.rippergui.dashboard.models import Dashboard, DataSource, DataSourceType, DateRange, DateRangePreset
from ripper.rippergui.dashboard.services import DashboardDataService, validate_transaction_sheet_data


class FakeAuthManager:
    def __init__(self, service=None):
        self.service = service

    def create_sheets_service(self):
        return self.service


def make_transaction_source(source_id="source-1"):
    return DataSource(
        id=source_id,
        type=DataSourceType.TILLER_TRANSACTIONS,
        name="Transactions",
        spreadsheet_id="spreadsheet-1",
        sheet_name="Transactions",
        range_a1="A1:E10",
        date_range=DateRange(
            DateRangePreset.CUSTOM,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31, 23, 59, 59),
        ),
    )


def test_validate_transaction_sheet_data_accepts_required_columns():
    valid, missing = validate_transaction_sheet_data(
        [["Date", "Description", "Category", "Amount", "Account"], ["2024-01-01", "Coffee", "Food", "-5", "Visa"]]
    )

    assert valid
    assert missing == set()


def test_validate_transaction_sheet_data_rejects_missing_columns():
    valid, missing = validate_transaction_sheet_data([["Date", "Description"], ["2024-01-01", "Coffee"]])

    assert not valid
    assert missing == {"account", "amount", "category"}


def test_refresh_dashboard_reports_missing_auth():
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(make_transaction_source())

    result = DashboardDataService(FakeAuthManager()).refresh_dashboard(dashboard)

    assert result.has_errors()
    assert result.statuses["source-1"].message == "Could not authenticate with Google Sheets API."


def test_refresh_dashboard_fetches_transaction_source_once():
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(make_transaction_source())
    calls = []

    def fake_retrieve_sheet_data(service, spreadsheet_id, range_name):
        calls.append((spreadsheet_id, range_name))
        return (
            [
                ["Date", "Description", "Category", "Amount", "Account"],
                ["2024-01-01", "Coffee", "Food", "-5", "Visa"],
                ["2025-01-01", "Old", "Food", "-10", "Visa"],
            ],
            [],
        )

    result = DashboardDataService(
        FakeAuthManager(service=object()), retrieve_sheet_data_fn=fake_retrieve_sheet_data
    ).refresh_dashboard(dashboard)

    assert calls == [("spreadsheet-1", "Transactions!A1:E10")]
    assert result.statuses["source-1"].ok
    assert result.statuses["source-1"].row_count == 1
    assert result.data["source-1"][0]["description"] == "Coffee"


def test_refresh_dashboard_reports_unsupported_source():
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(
        DataSource(
            id="budget-1",
            type=DataSourceType.TILLER_BUDGET,
            name="Budget",
            spreadsheet_id="spreadsheet-1",
            sheet_name="Budget",
            range_a1="A1:E10",
            date_range=DateRange(DateRangePreset.YEAR_TO_DATE),
        )
    )

    result = DashboardDataService(FakeAuthManager(service=object())).refresh_dashboard(dashboard)

    assert result.statuses["budget-1"].unsupported
    assert not result.statuses["budget-1"].ok
