import sys
import unittest
from unittest.mock import MagicMock, patch

import PySide6QtAds as ads  # type: ignore[import-untyped]
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from ripper.rippergui.mainview import MainView


@pytest.mark.qt
class TestMainView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure a QApplication exists
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        self.main_view = MainView()

    def test_initial_state(self):
        self.assertEqual(self.main_view.windowTitle(), "ripper")
        self.assertIsNotNone(self.main_view._file_menu)
        self.assertIsNotNone(self.main_view._edit_menu)
        self.assertIsNotNone(self.main_view._view_menu)
        self.assertIsNotNone(self.main_view._oauth_menu)
        self.assertIsNotNone(self.main_view._help_menu)

    @patch("ripper.rippergui.mainview.QMessageBox.information")
    @patch("ripper.rippergui.mainview.AuthManager")
    def test_authenticate_oauth_success(self, mock_auth_manager_class, mock_information):
        mock_auth_manager = mock_auth_manager_class.return_value
        mock_auth_manager.authorize.return_value = True
        self.main_view._authenticate_oauth_act.setEnabled(True)
        self.main_view.authenticate_oauth()
        mock_information.assert_called()

    @patch("ripper.rippergui.mainview.QMessageBox.warning")
    @patch("ripper.rippergui.mainview.AuthManager")
    def test_authenticate_oauth_failure(self, mock_auth_manager_class, mock_warning):
        mock_auth_manager = mock_auth_manager_class.return_value
        mock_auth_manager.authorize.return_value = False
        self.main_view._authenticate_oauth_act.setEnabled(True)
        self.main_view.authenticate_oauth()
        mock_warning.assert_called()

    @patch("ripper.rippergui.mainview.QMessageBox.warning")
    @patch("ripper.rippergui.mainview.AuthManager")
    def test_new_source_not_logged_in(self, mock_auth_manager_class, mock_warning):
        mock_auth_manager = mock_auth_manager_class.return_value
        mock_auth_info = MagicMock()
        mock_auth_info.auth_state.return_value = 1  # NOT_LOGGED_IN
        mock_auth_manager.auth_info.return_value = mock_auth_info
        self.main_view.new_source()
        mock_warning.assert_called()


@pytest.mark.qt
def test_central_widget_is_dock_manager(qtbot):
    """Central widget must be a CDockManager after Phase 1 migration."""
    view = MainView()
    qtbot.addWidget(view)
    assert isinstance(view.centralWidget(), ads.CDockManager)


@pytest.mark.qt
def test_show_data_source_creates_table_dock(qtbot):
    """Calling _show_data_source_in_dock() must create a CDockWidget, not QDockWidget."""
    view = MainView()
    qtbot.addWidget(view)
    assert view._table_dock is None

    with patch("ripper.rippergui.mainview.Db") as mock_db:
        mock_db.get_data_source.return_value = {"last_fetched_at": "2024-01-01"}
        sheet_data = [["ID", "Date", "Description"], ["1", "2024-01-01", "Test"]]
        view._show_data_source_in_dock(1, "Test Source", sheet_data, {"spreadsheet_id": "s1", "sheet_name": "Sheet1"})

    assert view._table_dock is not None
    assert isinstance(view._table_dock, ads.CDockWidget)


@pytest.mark.qt
def test_dashboard_dock_initialized(qtbot):
    """Dashboard CDockWidget must be initialized after create_main_layout."""
    view = MainView()
    qtbot.addWidget(view)
    if view._dashboard_dock is None:
        pytest.skip("dashboard not importable in this environment")
    assert view._dashboard_dock is not None
    assert isinstance(view._dashboard_dock, ads.CDockWidget)


@pytest.mark.qt
def test_close_saves_layout(qtbot, monkeypatch, tmp_path):
    """Closing MainView must persist dock layout to QSettings."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    view = MainView()
    qtbot.addWidget(view)
    QSettings("solarisin", "ripper").remove("dock_layout/state")  # start clean
    view.close()
    state = QSettings("solarisin", "ripper").value("dock_layout/state")
    assert state is not None


@pytest.mark.qt
def test_reset_layout_clears_settings(qtbot, monkeypatch, tmp_path):
    """_reset_layout must remove the saved layout key from QSettings."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    view = MainView()
    qtbot.addWidget(view)
    QSettings("solarisin", "ripper").setValue("dock_layout/state", b"dummy")
    with patch("ripper.rippergui.mainview.QMessageBox.information"):
        view._reset_layout()
    assert QSettings("solarisin", "ripper").value("dock_layout/state") is None


@pytest.mark.qt
def test_restore_layout_invalid_state_no_crash(qtbot, monkeypatch, tmp_path):
    """_restore_layout must not crash when QSettings contains garbage."""
    from PySide6.QtCore import QByteArray

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    view = MainView()
    qtbot.addWidget(view)
    QSettings("solarisin", "ripper").setValue("dock_layout/state", QByteArray(b"not-valid-state"))
    view._restore_layout()  # must not raise


if __name__ == "__main__":
    unittest.main()


def test_refresh_data_source_invalidates_cache_on_instance() -> None:
    """`_refresh_data_source` must call `invalidate_cache` on a SheetDataCache *instance*.

    `invalidate_cache` is an instance method; calling it on the class (the original bug, #67)
    binds `spreadsheet_id` to `self` and raises AttributeError at runtime. Exercised without a
    real MainView via the unbound method + a mock `self` (no Qt needed).
    """
    mock_self = MagicMock()
    record = {"spreadsheet_id": "book-1", "sheet_name": "Transactions"}

    with patch("ripper.rippergui.mainview.Db") as mock_db:
        mock_db.get_data_source.return_value = record
        with patch("ripper.ripperlib.sheet_data_cache.SheetDataCache") as mock_cache_cls:
            MainView._refresh_data_source(mock_self, 7)

            # The fix calls SheetDataCache().invalidate_cache(...), i.e. on the instance.
            mock_cache_cls.return_value.invalidate_cache.assert_called_once_with("book-1", "Transactions")
            mock_self._load_data_source_by_id.assert_called_once_with(7, stamp_on_success=True)


def test_data_fetch_worker_passes_sheet_and_range_separately() -> None:
    """The worker must call retrieve_sheet_data_for with separate sheet_name/range_a1 (#72 review).

    A whole-sheet load of a '!'-containing title must not be collapsed into a combined
    'Sheet!Range' string (which would misparse 'Q1!Actuals' as sheet 'Q1'). Exercised via the
    unbound run() with a mock self, so no QThread/QApplication is needed.
    """
    from unittest.mock import MagicMock, patch

    from ripper.rippergui.mainview import _DataFetchWorker

    mock_self = MagicMock()
    mock_self._spreadsheet_id = "book"
    mock_self._sheet_name = "Q1!Actuals"
    mock_self._range_a1 = ""  # whole-sheet load

    with patch("ripper.rippergui.mainview.AuthManager") as mock_auth_cls:
        mock_auth_cls.return_value.create_sheets_service.return_value = MagicMock()
        with patch("ripper.ripperlib.sheets_backend.retrieve_sheet_data_for") as mock_retrieve:
            mock_retrieve.return_value = ([], [])
            _DataFetchWorker.run(mock_self)

            service = mock_auth_cls.return_value.create_sheets_service.return_value
            mock_retrieve.assert_called_once_with(service, "book", "Q1!Actuals", "")


def test_get_records_for_dashboard_keys_on_range() -> None:
    """Two sources on the same tab but different ranges must resolve to their own widget (#73)."""
    from unittest.mock import MagicMock

    mock_self = MagicMock()
    widget_a = MagicMock()
    widget_a.get_filtered_records.return_value = [{"row": "a"}]
    widget_b = MagicMock()
    widget_b.get_filtered_records.return_value = [{"row": "b"}]
    mock_self._table_widgets = {
        ("book", "Transactions", "A1:E10"): widget_a,
        ("book", "Transactions", "G1:K10"): widget_b,
    }

    assert MainView._get_records_for_dashboard(mock_self, "book", "Transactions", "A1:E10") == [{"row": "a"}]
    assert MainView._get_records_for_dashboard(mock_self, "book", "Transactions", "G1:K10") == [{"row": "b"}]
    # A range with no loaded widget falls back to the API path (None).
    assert MainView._get_records_for_dashboard(mock_self, "book", "Transactions", "Z1:Z9") is None


def test_load_data_source_passes_range_to_dock_for_dashboard_keying() -> None:
    """A loaded existing source must carry its range so the dashboard provider key matches (#73 review).

    Without it, `_show_data_source_in_dock` stores the widget under (spreadsheet_id, sheet_name, "")
    while the dashboard queries with the real range_a1, so the provider always misses. Exercised
    via the unbound method with Qt (QProgressDialog/worker) patched out.
    """
    from unittest.mock import MagicMock, patch

    mock_self = MagicMock()
    record = {
        "spreadsheet_id": "book",
        "sheet_name": "Transactions",
        "range_a1": "G1:K10",
        "name": "My Source",
        "spreadsheet_name": "Book",
    }

    with patch("ripper.rippergui.mainview.Db") as mock_db:
        mock_db.get_data_source.return_value = record
        with patch("ripper.rippergui.mainview.QProgressDialog"):
            with patch("ripper.rippergui.mainview._DataFetchWorker") as mock_worker_cls:
                worker = mock_worker_cls.return_value
                MainView._load_data_source_by_id(mock_self, 5)

                # Capture the on_finished slot and drive it with sample data.
                on_finished = worker.finished.connect.call_args_list[0].args[0]
                on_finished([["Date", "Amount"], ["2024-01-01", "5"]], [("api", "'Transactions'!G1:K10")])

    source_info = mock_self._show_data_source_in_dock.call_args.args[3]
    assert source_info["sheet_range"] == "G1:K10"
