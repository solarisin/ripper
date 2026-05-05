import sys
import unittest
from unittest.mock import MagicMock, patch

import PySide6QtAds as ads  # type: ignore[import-untyped]
import pytest
from PySide6.QtWidgets import QApplication

from ripper.rippergui.mainview import MainView


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
    from unittest.mock import patch, MagicMock
    view = MainView()
    qtbot.addWidget(view)
    assert view._table_dock is None

    with patch("ripper.rippergui.mainview.Db") as mock_db:
        mock_db.get_data_source.return_value = {"last_fetched_at": "2024-01-01"}
        sheet_data = [["ID", "Date", "Description"], ["1", "2024-01-01", "Test"]]
        view._show_data_source_in_dock(1, "Test Source", sheet_data, {"spreadsheet_id": "s1", "sheet_name": "Sheet1"})

    assert view._table_dock is not None
    assert isinstance(view._table_dock, ads.CDockWidget)


if __name__ == "__main__":
    unittest.main()
