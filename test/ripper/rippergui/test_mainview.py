import sys
import unittest
from unittest.mock import MagicMock, patch

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
    def test_select_google_sheet_not_logged_in(self, mock_auth_manager_class, mock_warning):
        mock_auth_manager = mock_auth_manager_class.return_value
        mock_auth_info = MagicMock()
        mock_auth_info.auth_state.return_value = 1  # NOT_LOGGED_IN
        mock_auth_manager.auth_info.return_value = mock_auth_info
        self.main_view.select_google_sheet()
        mock_warning.assert_called()


if __name__ == "__main__":
    unittest.main()
