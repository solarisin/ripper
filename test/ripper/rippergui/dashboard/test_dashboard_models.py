"""Tests for dashboard model persistence."""

from ripper.rippergui.dashboard.models import (
    Dashboard,
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
