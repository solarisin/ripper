"""Tests for dashboard view rendering from widget configs."""

from unittest.mock import MagicMock

import pytest
from PySide6.QtCharts import QChartView
from PySide6.QtWidgets import QLabel, QScrollArea, QSplitter

from ripper.rippergui.dashboard.models import Dashboard, WidgetConfig, WidgetType
from ripper.rippergui.dashboard.services import DashboardDataService, DashboardRefreshResult
from ripper.rippergui.dashboard.views.dashboard_editor import DashboardEditor
from ripper.rippergui.dashboard.views.dashboard_view import DashboardView

# These tests instantiate Qt widgets via qtbot.
pytestmark = pytest.mark.qt


def _fake_data_service():
    """A stand-in data service that satisfies the DashboardDataService type contract."""
    service = MagicMock(spec=DashboardDataService)
    service.refresh_dashboard.return_value = DashboardRefreshResult()
    return service


def test_dashboard_view_renders_widget_config(tmp_path, qtbot):
    dashboard = Dashboard.create_new("Finance")
    dashboard.add_widget(
        WidgetConfig(
            id="widget-1",
            type=WidgetType.SPENDING_TREND,
            title="Spending",
            position=(0, 0),
            size=(2, 2),
        )
    )
    dashboard.save_to_file(tmp_path / f"{dashboard.id}.json")

    view = DashboardView(tmp_path, data_service=_fake_data_service())
    qtbot.addWidget(view)

    # SpendingTrendWidget.create_widget builds a real chart, not a placeholder label.
    chart_views = view.findChildren(QChartView)
    assert chart_views, "expected the functional widget to render a QChartView"
    assert chart_views[0].chart().title() == "Monthly Spending Trend"

    # The widget rendered successfully, so no error-label fallback should be present.
    error_labels = [label for label in view.findChildren(QLabel) if label.text().startswith("Error loading widget")]
    assert not error_labels


def test_dashboard_editor_uses_injected_data_source_provider(qtbot):
    """DashboardEditor takes an injectable data-source provider instead of the Db singleton (#33)."""
    dashboard = Dashboard.create_new("Finance")
    sentinel = [{"id": "ds-1", "name": "Test", "spreadsheet_id": "s1", "sheet_name": "Sheet1", "range_a1": "A1:E10"}]
    editor = DashboardEditor(dashboard, data_source_provider=lambda: sentinel)
    qtbot.addWidget(editor)

    assert editor._data_source_provider() == sentinel


def test_dashboard_editor_keeps_canvas_scrollable_and_properties_visible(qtbot):
    dashboard = Dashboard.create_new("Finance")
    editor = DashboardEditor(dashboard)
    qtbot.addWidget(editor)

    splitter = editor.findChild(QSplitter)

    assert splitter is not None
    assert splitter.count() == 3
    assert isinstance(splitter.widget(1), QScrollArea)
    assert splitter.widget(2) is editor.properties_panel
    assert not splitter.childrenCollapsible()
    assert editor.properties_panel.minimumWidth() >= 300


def test_refresh_runs_off_gui_thread_and_applies_result(tmp_path, qtbot):
    """refresh() must run the service on a worker thread and apply the result in a slot (#36).

    The data service authenticates + fetches over the network; doing that on the GUI thread
    freezes the UI. Here we assert refresh() drives the (real) worker and the returned result
    lands back on the view.
    """
    dashboard = Dashboard.create_new("Finance")
    dashboard.save_to_file(tmp_path / f"{dashboard.id}.json")

    result = DashboardRefreshResult()
    service = MagicMock(spec=DashboardDataService)
    service.refresh_dashboard.return_value = result

    view = DashboardView(tmp_path, data_service=service)
    qtbot.addWidget(view)
    view.current_dashboard = dashboard

    view.refresh()
    # The button is disabled while the background worker runs, then re-enabled by the slot.
    qtbot.waitUntil(lambda: view.refresh_dashboard_btn.isEnabled(), timeout=3000)

    service.refresh_dashboard.assert_called_once_with(dashboard)
    assert view.refresh_result is result


def test_refresh_reports_error_without_crashing(tmp_path, qtbot):
    """A failure in the worker is surfaced via the error slot, not raised on the GUI thread (#36)."""
    dashboard = Dashboard.create_new("Finance")
    dashboard.save_to_file(tmp_path / f"{dashboard.id}.json")

    service = MagicMock(spec=DashboardDataService)
    service.refresh_dashboard.side_effect = RuntimeError("boom")

    view = DashboardView(tmp_path, data_service=service)
    qtbot.addWidget(view)
    view.current_dashboard = dashboard

    view.refresh()
    qtbot.waitUntil(lambda: view.refresh_dashboard_btn.isEnabled(), timeout=3000)

    assert "boom" in view.status_label.text()


def test_refresh_result_for_switched_away_dashboard_is_ignored():
    """A result for a dashboard the user has navigated away from must not be applied (#36 review).

    Exercises the slot with a mock self so no Qt/thread is needed: if the current dashboard changed
    while the refresh was in flight, the stale result must be dropped rather than rendered onto the
    now-current dashboard.
    """
    view = MagicMock()
    dash_a = MagicMock(spec=Dashboard)
    dash_b = MagicMock(spec=Dashboard)
    view.current_dashboard = dash_b  # user switched to B while A's refresh was running

    result = DashboardRefreshResult()
    DashboardView._on_refresh_finished(view, result, dash_a)  # A's result arrives late

    assert view.refresh_result is not result  # not applied
    view._show_refresh_summary.assert_not_called()
    view._set_current_dashboard.assert_not_called()
