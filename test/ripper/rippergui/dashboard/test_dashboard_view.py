"""Tests for dashboard view rendering from widget configs."""

import threading
from unittest.mock import MagicMock

import pytest
from PySide6.QtCharts import QChartView
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QScrollArea, QSplitter

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


def test_edit_and_delete_disabled_during_refresh_and_reenabled(tmp_path, qtbot):
    """Edit/Delete must be disabled while a refresh is in flight, then re-enabled (#96).

    Leaving Edit/Delete enabled lets the user reassign/re-render the current dashboard while the
    worker thread is refreshing it. We block the worker mid-refresh to observe the disabled state,
    then release it and assert everything is re-enabled once the result lands.
    """
    dashboard = Dashboard.create_new("Finance")
    dashboard.save_to_file(tmp_path / f"{dashboard.id}.json")

    release = threading.Event()

    def blocking_refresh(_dashboard):
        release.wait(timeout=5)
        return DashboardRefreshResult()

    service = MagicMock(spec=DashboardDataService)
    service.refresh_dashboard.side_effect = blocking_refresh

    view = DashboardView(tmp_path, data_service=service)
    qtbot.addWidget(view)
    view.current_dashboard = dashboard

    view.refresh()
    # Disabling happens synchronously on the GUI thread before the worker starts.
    assert not view.refresh_dashboard_btn.isEnabled()
    assert not view.edit_dashboard_btn.isEnabled()
    assert not view.delete_dashboard_btn.isEnabled()

    release.set()
    qtbot.waitUntil(lambda: view.refresh_dashboard_btn.isEnabled(), timeout=3000)
    assert view.edit_dashboard_btn.isEnabled()
    assert view.delete_dashboard_btn.isEnabled()


def test_edit_and_delete_reenabled_after_refresh_error(tmp_path, qtbot):
    """A failing refresh must still restore Edit/Delete so they don't get stuck disabled (#96)."""
    dashboard = Dashboard.create_new("Finance")
    dashboard.save_to_file(tmp_path / f"{dashboard.id}.json")

    service = MagicMock(spec=DashboardDataService)
    service.refresh_dashboard.side_effect = RuntimeError("boom")

    view = DashboardView(tmp_path, data_service=service)
    qtbot.addWidget(view)
    view.current_dashboard = dashboard

    view.refresh()
    # Disabled synchronously before the worker starts; the error slot must restore them.
    assert not view.edit_dashboard_btn.isEnabled()
    assert not view.delete_dashboard_btn.isEnabled()

    qtbot.waitUntil(lambda: view.refresh_dashboard_btn.isEnabled(), timeout=3000)

    assert "boom" in view.status_label.text()
    assert view.edit_dashboard_btn.isEnabled()
    assert view.delete_dashboard_btn.isEnabled()


def _blocking_data_service():
    """A data service whose refresh_dashboard blocks until released.

    Returns ``(service, started, release)``: ``started`` is set once the worker thread has
    entered ``refresh_dashboard`` (the refresh is now in flight), and setting ``release`` lets
    it complete. Lets a test hold a refresh mid-flight and inspect control-enablement state.
    """
    started = threading.Event()
    release = threading.Event()
    service = MagicMock(spec=DashboardDataService)

    def _blocking_refresh(dashboard):
        started.set()
        release.wait(timeout=5)
        return DashboardRefreshResult()

    service.refresh_dashboard.side_effect = _blocking_refresh
    return service, started, release


def _two_dashboard_view(tmp_path, qtbot, service):
    """Build a DashboardView backed by two stored dashboards, using *service*."""
    first = Dashboard.create_new("One")
    first.save_to_file(tmp_path / f"{first.id}.json")
    second = Dashboard.create_new("Two")
    second.save_to_file(tmp_path / f"{second.id}.json")

    view = DashboardView(tmp_path, data_service=service)
    qtbot.addWidget(view)
    return view, first, second


def test_switching_combo_during_in_flight_refresh_does_not_re_enable_controls(tmp_path, qtbot):
    """A refresh in flight must not be bypassable by changing the dashboard combo (#96 review).

    While the worker runs, every control that can switch/mutate the current dashboard is
    disabled. Forcing a combo selection change (as the reviewer asked) must NOT re-enable
    Edit/Delete/Refresh, nor reassign the current dashboard. After the worker finishes, the
    controls are restored.
    """
    service, started, release = _blocking_data_service()
    view, _first, _second = _two_dashboard_view(tmp_path, qtbot, service)
    original = view.current_dashboard
    assert original is not None

    try:
        view.refresh()
        qtbot.waitUntil(started.is_set, timeout=3000)  # worker is now blocked mid-refresh

        # In flight: everything that could switch or mutate the current dashboard is disabled.
        assert view._refresh_in_flight
        assert not view.refresh_dashboard_btn.isEnabled()
        assert not view.edit_dashboard_btn.isEnabled()
        assert not view.delete_dashboard_btn.isEnabled()
        assert not view.dashboard_combo.isEnabled()
        assert not view.add_dashboard_btn.isEnabled()

        # Force a selection change to the *other* dashboard. In the pre-fix code this routed
        # through _set_current_dashboard() and re-enabled the guarded buttons.
        other_index = 1 - view.dashboard_combo.currentIndex()
        view.dashboard_combo.setCurrentIndex(other_index)

        # The guard must hold: buttons stay disabled and the current dashboard is unchanged.
        assert not view.edit_dashboard_btn.isEnabled()
        assert not view.delete_dashboard_btn.isEnabled()
        assert not view.refresh_dashboard_btn.isEnabled()
        assert view.current_dashboard is original
    finally:
        release.set()

    # After the worker completes, the controls are restored.
    qtbot.waitUntil(lambda: view.refresh_dashboard_btn.isEnabled(), timeout=3000)
    assert not view._refresh_in_flight
    assert view.edit_dashboard_btn.isEnabled()
    assert view.delete_dashboard_btn.isEnabled()
    assert view.dashboard_combo.isEnabled()
    assert view.add_dashboard_btn.isEnabled()
    assert view.current_dashboard is original


def test_new_dashboard_is_inert_during_in_flight_refresh(tmp_path, qtbot, monkeypatch):
    """New Dashboard must be blocked while a refresh is in flight (#96 review)."""
    from PySide6.QtWidgets import QInputDialog

    service, started, release = _blocking_data_service()
    view, _first, _second = _two_dashboard_view(tmp_path, qtbot, service)
    dashboards_before = len(view.dashboards)

    get_text = MagicMock(return_value=("Should Not Appear", True))
    monkeypatch.setattr(QInputDialog, "getText", get_text)

    try:
        view.refresh()
        qtbot.waitUntil(started.is_set, timeout=3000)

        assert not view.add_dashboard_btn.isEnabled()

        # Even if invoked programmatically, the handler must be inert: no prompt, no creation.
        view._on_add_dashboard()
        get_text.assert_not_called()
        assert len(view.dashboards) == dashboards_before
    finally:
        release.set()

    qtbot.waitUntil(lambda: view.add_dashboard_btn.isEnabled(), timeout=3000)
    assert view.add_dashboard_btn.isEnabled()


def _view_with_one_widget(tmp_path, qtbot):
    """Build a DashboardView over a stored dashboard containing a single widget."""
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
    return view, dashboard


def _patch_edit_dialog_exec(monkeypatch, mutate, result_code):
    """Patch QDialog.exec so the edit dialog 'runs': mutate the editor's model, then close.

    Simulates the user making an edit inside the modal editor and then pressing
    Save (Accepted) or Cancel (Rejected), without spinning a real event loop.
    """

    def fake_exec(dialog_self):
        editor = dialog_self.findChild(DashboardEditor)
        assert editor is not None, "edit dialog should contain the DashboardEditor"
        mutate(editor)
        return result_code

    monkeypatch.setattr(QDialog, "exec", fake_exec)


def test_edit_dialog_cancel_reverts_changes(tmp_path, qtbot, monkeypatch):
    """Cancelling the edit dialog must leave the live dashboard untouched (#95)."""
    view, dashboard = _view_with_one_widget(tmp_path, qtbot)

    _patch_edit_dialog_exec(
        monkeypatch,
        mutate=lambda editor: editor.dashboard.remove_widget("widget-1"),
        result_code=QDialog.DialogCode.Rejected,
    )
    view._on_edit_dashboard()

    assert view.current_dashboard is not None
    assert "widget-1" in view.current_dashboard.widgets, "cancelled deletion leaked into the live dashboard"

    # A later, unrelated save must not silently persist the cancelled deletion.
    view.dashboard_manager.save_dashboard(view.current_dashboard)
    reloaded = Dashboard.load_from_file(tmp_path / f"{dashboard.id}.json")
    assert "widget-1" in reloaded.widgets


def test_edit_dialog_save_persists_changes(tmp_path, qtbot, monkeypatch):
    """Accepting the edit dialog persists the edits and updates the in-memory state (#95)."""
    view, dashboard = _view_with_one_widget(tmp_path, qtbot)

    def mutate(editor):
        editor.dashboard.remove_widget("widget-1")
        editor.dashboard.name = "Renamed"

    _patch_edit_dialog_exec(monkeypatch, mutate=mutate, result_code=QDialog.DialogCode.Accepted)
    view._on_edit_dashboard()

    assert view.current_dashboard is not None
    assert "widget-1" not in view.current_dashboard.widgets
    assert view.current_dashboard.name == "Renamed"

    # Persisted to disk.
    reloaded = Dashboard.load_from_file(tmp_path / f"{dashboard.id}.json")
    assert "widget-1" not in reloaded.widgets
    assert reloaded.name == "Renamed"

    # The manager and combo now reference the edited dashboard, keyed by the same id.
    assert view.dashboard_manager.get_dashboard(dashboard.id) is view.current_dashboard
    assert view.current_dashboard.id == dashboard.id
    assert view.dashboard_combo.currentText() == "Renamed"


def test_edit_dialog_save_failure_keeps_original_dashboard_everywhere(tmp_path, qtbot, monkeypatch):
    """A failed save on Accept must leave both the view and the manager on the original (#95 review).

    The view already keeps displaying the original; the manager must not have
    registered the unpersisted working copy either.
    """
    view, dashboard = _view_with_one_widget(tmp_path, qtbot)
    original = view.current_dashboard
    assert original is not None

    _patch_edit_dialog_exec(
        monkeypatch,
        mutate=lambda editor: editor.dashboard.remove_widget("widget-1"),
        result_code=QDialog.DialogCode.Accepted,
    )
    critical = MagicMock(return_value=QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", critical)
    monkeypatch.setattr(Dashboard, "save_to_file", MagicMock(side_effect=OSError("disk full")))

    view._on_edit_dashboard()

    critical.assert_called_once()
    assert view.current_dashboard is original
    assert "widget-1" in view.current_dashboard.widgets
    # The manager must still resolve the id to the original, not the failed working copy.
    assert view.dashboard_manager.get_dashboard(dashboard.id) is original

    # A later, unrelated save must not silently persist the failed edit.
    monkeypatch.undo()
    view.dashboard_manager.save_dashboard(view.current_dashboard)
    reloaded = Dashboard.load_from_file(tmp_path / f"{dashboard.id}.json")
    assert "widget-1" in reloaded.widgets


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
