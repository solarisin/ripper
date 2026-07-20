"""Tests for dashboard model persistence."""

from unittest.mock import patch

import pytest

from ripper.rippergui.dashboard.models import (
    Dashboard,
    DashboardManager,
    DataSource,
    DataSourceType,
    DateRange,
    DateRangePreset,
    WidgetConfig,
    WidgetType,
)


def test_dashboard_round_trip_with_widget_configs_and_exact_ranges(tmp_path):
    dashboard = Dashboard.create_new("Finance")
    source = DataSource(
        id="source-1",
        type=DataSourceType.TILLER_TRANSACTIONS,
        name="Transactions",
        spreadsheet_id="spreadsheet-1",
        sheet_name="Transactions",
        range_a1="A1:F100",
        date_range=DateRange(DateRangePreset.YEAR_TO_DATE),
    )
    widget = WidgetConfig(
        id="widget-1",
        type=WidgetType.SPENDING_TREND,
        title="Spending",
        position=(0, 0),
        size=(4, 3),
        data_source_id=source.id,
    )
    dashboard.add_data_source(source)
    dashboard.add_widget(widget)

    file_path = tmp_path / "dashboard.json"
    dashboard.save_to_file(file_path)

    loaded = Dashboard.load_from_file(file_path)

    assert loaded.name == "Finance"
    assert loaded.data_sources["source-1"].sheet_name == "Transactions"
    assert loaded.data_sources["source-1"].range_a1 == "A1:F100"
    assert loaded.widgets["widget-1"] == widget


def test_remove_referenced_data_source_fails():
    dashboard = Dashboard.create_new("Finance")
    source = DataSource(
        id="source-1",
        type=DataSourceType.TILLER_TRANSACTIONS,
        name="Transactions",
        spreadsheet_id="spreadsheet-1",
        sheet_name="Transactions",
        range_a1="A1:F100",
        date_range=DateRange(DateRangePreset.YEAR_TO_DATE),
    )
    dashboard.add_data_source(source)
    dashboard.add_widget(
        WidgetConfig(
            id="widget-1",
            type=WidgetType.TOP_EXPENSES,
            title="Top Expenses",
            position=(0, 0),
            size=(4, 3),
            data_source_id=source.id,
        )
    )

    try:
        dashboard.remove_data_source(source.id)
    except ValueError as exc:
        assert "Top Expenses" in str(exc)
    else:
        raise AssertionError("Expected referenced data source removal to fail")


def test_save_dashboard_failed_write_does_not_register_edited_copy(tmp_path):
    """A failed disk write must leave the manager's in-memory store untouched (#95 review).

    If the edited copy were registered before the write, a failed save would leave
    memory and disk inconsistent: later lookups would return (and a later save would
    silently persist) an edit the user was told failed.
    """
    manager = DashboardManager(tmp_path)
    original = manager.create_dashboard("Finance")
    manager.save_dashboard(original)

    edited = Dashboard.from_dict(original.to_dict())
    edited.name = "Edited"

    with patch.object(Dashboard, "save_to_file", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            manager.save_dashboard(edited)

    # The manager still holds the original instance, not the unpersisted edit.
    assert manager.get_dashboard(original.id) is original

    # A subsequent successful save of the original must not leak the failed edit.
    manager.save_dashboard(original)
    reloaded = Dashboard.load_from_file(tmp_path / f"{original.id}.json")
    assert reloaded.name == "Finance"
