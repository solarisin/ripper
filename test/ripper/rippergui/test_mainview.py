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
