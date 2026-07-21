"""Tests for dashboard model persistence."""

from typing import Any
from unittest.mock import MagicMock, patch

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
from ripper.rippergui.dashboard.models.widgets import BaseWidget


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


def _make_source(source_id: str) -> DataSource:
    return DataSource(
        id=source_id,
        type=DataSourceType.TILLER_TRANSACTIONS,
        name="Transactions",
        spreadsheet_id="spreadsheet-1",
        sheet_name="Transactions",
        range_a1="A1:F100",
        date_range=DateRange(DateRangePreset.YEAR_TO_DATE),
    )


def _make_widget(widget_id: str, data_source_id: str | None) -> WidgetConfig:
    return WidgetConfig(
        id=widget_id,
        type=WidgetType.SPENDING_TREND,
        title="Spending",
        position=(0, 0),
        size=(4, 3),
        data_source_id=data_source_id,
    )


def test_from_dict_skips_data_source_missing_required_field():
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(_make_source("source-good"))
    dashboard.add_widget(_make_widget("widget-1", "source-good"))
    data = dashboard.to_dict()

    bad_source = _make_source("source-bad").to_dict()
    del bad_source["spreadsheet_id"]
    data["data_sources"]["source-bad"] = bad_source

    loaded = Dashboard.from_dict(data)

    assert "source-good" in loaded.data_sources
    assert "source-bad" not in loaded.data_sources
    assert "widget-1" in loaded.widgets


def test_from_dict_skips_data_source_with_invalid_type():
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(_make_source("source-good"))
    dashboard.add_widget(_make_widget("widget-1", "source-good"))
    data = dashboard.to_dict()

    bad_source = _make_source("source-bad").to_dict()
    bad_source["type"] = "not_a_real_type"
    data["data_sources"]["source-bad"] = bad_source

    loaded = Dashboard.from_dict(data)

    assert "source-good" in loaded.data_sources
    assert "source-bad" not in loaded.data_sources
    assert "widget-1" in loaded.widgets


def test_from_dict_skips_data_source_with_null_date_range():
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(_make_source("source-good"))
    dashboard.add_widget(_make_widget("widget-1", "source-good"))
    data = dashboard.to_dict()

    bad_source = _make_source("source-bad").to_dict()
    bad_source["date_range"] = None
    data["data_sources"]["source-bad"] = bad_source

    loaded = Dashboard.from_dict(data)

    assert "source-good" in loaded.data_sources
    assert "source-bad" not in loaded.data_sources
    assert "widget-1" in loaded.widgets


def test_from_dict_skips_data_source_with_non_string_dates():
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(_make_source("source-good"))
    dashboard.add_widget(_make_widget("widget-1", "source-good"))
    data = dashboard.to_dict()

    bad_source = _make_source("source-bad").to_dict()
    bad_source["date_range"] = {
        "preset": DateRangePreset.CUSTOM.value,
        "start_date": 12345,
        "end_date": 67890,
    }
    data["data_sources"]["source-bad"] = bad_source

    loaded = Dashboard.from_dict(data)

    assert "source-good" in loaded.data_sources
    assert "source-bad" not in loaded.data_sources
    assert "widget-1" in loaded.widgets


def test_from_dict_skips_widget_with_null_position():
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(_make_source("source-good"))
    dashboard.add_widget(_make_widget("widget-good", "source-good"))
    data = dashboard.to_dict()

    bad_widget = _make_widget("widget-bad", "source-good").to_dict()
    bad_widget["position"] = None
    data["widgets"]["widget-bad"] = bad_widget

    loaded = Dashboard.from_dict(data)

    assert "widget-good" in loaded.widgets
    assert "widget-bad" not in loaded.widgets
    assert "source-good" in loaded.data_sources


def test_data_source_has_no_legacy_fetch_data_method():
    """Item 4 (#62): the legacy synchronous fetch path is dead code and must be removed."""
    assert not hasattr(DataSource, "fetch_data")


def test_base_widget_update_data_reads_dict_cache_only():
    """Item 4 (#62): BaseWidget.update_data must consume only the runtime dict cache.

    The legacy branch that called ``data_source.fetch_data(service)`` for a non-dict
    "service" object is gone, so such an argument is simply ignored (no fetch, no crash).
    """
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(_make_source("s1"))

    processed: list[Any] = []

    class _ConcreteWidget(BaseWidget):
        def create_widget(self, parent):  # pragma: no cover - not exercised here
            raise NotImplementedError

        def _process_data(self, data):
            processed.append(data)

    widget = _ConcreteWidget(_make_widget("w1", "s1"), dashboard)

    # The dict cache is the one supported contract.
    widget.update_data({"s1": [{"amount": 1}]})
    assert processed == [[{"amount": 1}]]

    # A legacy non-dict "service" object is ignored now that the sync branch is gone.
    processed.clear()
    widget.update_data(MagicMock())
    assert processed == []


def test_from_dict_prunes_widgets_with_dangling_data_source_references():
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_data_source(_make_source("source-good"))
    dashboard.add_widget(_make_widget("widget-bound", "source-good"))
    dashboard.add_widget(_make_widget("widget-unbound", None))
    data = dashboard.to_dict()

    data["widgets"]["widget-dangling"] = _make_widget("widget-dangling", "source-missing").to_dict()

    loaded = Dashboard.from_dict(data)

    assert "widget-dangling" not in loaded.widgets
    assert "widget-bound" in loaded.widgets
    assert "widget-unbound" in loaded.widgets
    assert loaded.name == "Finance"
    assert "source-good" in loaded.data_sources
