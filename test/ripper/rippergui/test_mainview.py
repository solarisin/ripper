import sys
import unittest
from unittest.mock import MagicMock, patch

import PySide6QtAds as ads  # type: ignore[import-untyped]
import pytest
import shiboken6
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
def test_show_data_source_deletes_replaced_container(qtbot):
    """Replacing the dock's widget must destroy the old container, not leak it (#107).

    ``CDockWidget.setWidget()`` detaches the previous widget instead of deleting it, so without an
    explicit ``takeWidget()`` + ``deleteLater()`` every sidebar click / Refresh leaves a full
    table widget + model alive for the life of the app.
    """
    view = MainView()
    qtbot.addWidget(view)

    sheet_data = [["ID", "Date", "Description"], ["1", "2024-01-01", "Test"]]
    source_info = {"spreadsheet_id": "s1", "sheet_name": "Sheet1", "sheet_range": "A1:C10"}

    with patch("ripper.rippergui.mainview.Db") as mock_db:
        mock_db.get_data_source.return_value = {"last_fetched_at": "2024-01-01"}
        view._show_data_source_in_dock(1, "Test Source", sheet_data, source_info)
        assert view._table_dock is not None
        old_container = view._table_dock.widget()
        assert old_container is not None

        with qtbot.waitSignal(old_container.destroyed, timeout=2000):
            view._show_data_source_in_dock(1, "Test Source", sheet_data, source_info)
            QApplication.processEvents()

    new_container = view._table_dock.widget()
    assert new_container is not None
    assert not shiboken6.isValid(old_container)
    assert shiboken6.isValid(new_container)


@pytest.mark.qt
def test_show_data_source_keeps_new_widget_registered_after_old_destroyed(qtbot):
    """The new table widget must remain in ``_table_widgets`` after the old one is destroyed (#107).

    The ``destroyed`` handler pops the key only when the stored widget is still the destroyed one;
    since the new widget is registered before the old container is deleted, the identity guard must
    keep the new entry intact.
    """
    view = MainView()
    qtbot.addWidget(view)

    sheet_data = [["ID", "Date", "Description"], ["1", "2024-01-01", "Test"]]
    source_info = {"spreadsheet_id": "s1", "sheet_name": "Sheet1", "sheet_range": "A1:C10"}
    key = ("s1", "Sheet1", "A1:C10")

    with patch("ripper.rippergui.mainview.Db") as mock_db:
        mock_db.get_data_source.return_value = {"last_fetched_at": "2024-01-01"}
        view._show_data_source_in_dock(1, "Test Source", sheet_data, source_info)
        old_table_widget = view._table_widgets[key]
        assert view._table_dock is not None
        old_container = view._table_dock.widget()

        with qtbot.waitSignal(old_container.destroyed, timeout=2000):
            view._show_data_source_in_dock(1, "Test Source", sheet_data, source_info)
            QApplication.processEvents()

    qtbot.wait(50)
    assert key in view._table_widgets
    new_table_widget = view._table_widgets[key]
    assert new_table_widget is not old_table_widget
    assert shiboken6.isValid(new_table_widget)


@pytest.mark.qt
def test_dashboard_dock_initialized(qtbot):
    """Dashboard CDockWidget must be initialized after create_main_layout."""
    view = MainView()
    qtbot.addWidget(view)
    if view._dashboard_dock is None:
        pytest.skip("dashboard not importable in this environment")
    assert view._dashboard_dock is not None
    assert isinstance(view._dashboard_dock, ads.CDockWidget)


@pytest.fixture
def layout_settings(monkeypatch, tmp_path):
    """Redirect mainview's dock-layout QSettings to a temp INI file.

    The production factory returns ``QSettings("solarisin", "ripper")`` with the default
    NativeFormat, which on Windows is the developer's REAL ``HKCU\\Software\\solarisin\\ripper``
    registry key — sandboxing via the ``XDG_CONFIG_HOME`` env var only works on Linux. Patching
    the factory to a tmp_path-backed INI file isolates these tests on every platform. Tests use
    the same factory for their own reads/writes; writes may be cached per instance, so ``sync()``
    is called after writing / before reading through a different instance.
    """
    ini_path = str(tmp_path / "settings.ini")

    def factory() -> QSettings:
        return QSettings(ini_path, QSettings.Format.IniFormat)

    monkeypatch.setattr("ripper.rippergui.mainview._layout_settings", factory)
    return factory


@pytest.mark.qt
def test_close_saves_layout(qtbot, layout_settings):
    """Closing MainView must persist dock layout to QSettings."""
    view = MainView()
    qtbot.addWidget(view)
    settings = layout_settings()
    settings.remove("dock_layout/state")  # start clean
    settings.sync()
    view.close()
    reader = layout_settings()
    reader.sync()  # pick up the write flushed by close()
    assert reader.value("dock_layout/state") is not None


@pytest.mark.qt
def test_reset_layout_clears_settings(qtbot, layout_settings):
    """_reset_layout must remove the saved layout key from QSettings."""
    view = MainView()
    qtbot.addWidget(view)
    settings = layout_settings()
    settings.setValue("dock_layout/state", b"dummy")
    settings.sync()
    with patch("ripper.rippergui.mainview.QMessageBox.information"):
        view._reset_layout()
    reader = layout_settings()
    reader.sync()
    assert reader.value("dock_layout/state") is None


@pytest.mark.qt
def test_restore_layout_invalid_state_no_crash(qtbot, layout_settings):
    """_restore_layout must not crash when QSettings contains garbage."""
    from PySide6.QtCore import QByteArray

    view = MainView()
    qtbot.addWidget(view)
    settings = layout_settings()
    settings.setValue("dock_layout/state", QByteArray(b"not-valid-state"))
    settings.sync()
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


def test_refresh_data_source_aborts_when_cache_invalidation_fails() -> None:
    """A failed cache invalidation must abort refresh, not serve stale data stamped as fresh (#67 review).

    `invalidate_cache` returns False on failure (DB locked/error) without raising. Refresh must then
    warn and skip the reload/stamp rather than reloading the still-cached rows and marking them
    freshly refreshed. Exercised via the unbound method with a mock `self` (no Qt needed).
    """
    mock_self = MagicMock()
    record = {"spreadsheet_id": "book-1", "sheet_name": "Transactions"}

    with patch("ripper.rippergui.mainview.Db") as mock_db:
        mock_db.get_data_source.return_value = record
        with patch("ripper.ripperlib.sheet_data_cache.SheetDataCache") as mock_cache_cls:
            mock_cache_cls.return_value.invalidate_cache.return_value = False
            with patch("ripper.rippergui.mainview.QMessageBox") as mock_msgbox:
                MainView._refresh_data_source(mock_self, 7)

            mock_cache_cls.return_value.invalidate_cache.assert_called_once_with("book-1", "Transactions")
            # User is warned, and the stale data is NOT reloaded/stamped as fresh.
            mock_msgbox.warning.assert_called_once()
            mock_self._load_data_source_by_id.assert_not_called()


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
