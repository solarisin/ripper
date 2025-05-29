import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QGroupBox, QLineEdit, QRadioButton

from ripper.rippergui.oauth_client_config_view import AuthView


class TestAuthView(unittest.TestCase):
    @patch("ripper.rippergui.oauth_client_config_view.QMessageBox.warning")
    @patch("ripper.rippergui.oauth_client_config_view.AuthManager")
    @patch.object(AuthView, "__init__", return_value=None)
    def test_store_credentials_handles_exception(self, mock_auth_view_init, mock_auth_manager_class, mock_warning):
        """
        Test that store_credentials handles exceptions from AuthManager and shows a warning.
        """
        mock_auth_manager_instance = mock_auth_manager_class.return_value
        mock_auth_manager_instance.store_oauth_client_credentials.side_effect = Exception("fail")
        auth_view = AuthView()
        mock_auth_view_init.assert_called_once()
        auth_view.client_id_edit = self.mock_client_id_edit
        auth_view.client_secret_edit = self.mock_client_secret_edit
        self.mock_client_id_edit.text.return_value = "id"
        self.mock_client_secret_edit.text.return_value = "secret"

        # Patch QMessageBox.warning to check for error
        auth_view.store_credentials()
        mock_warning.assert_called()

    def _setup_auth_view_for_manual(self, auth_view, client_id, client_secret):
        auth_view.file_radio = self.mock_file_radio
        auth_view.file_radio.isChecked.return_value = False
        auth_view.manual_radio = self.mock_manual_radio
        auth_view.manual_radio.isChecked.return_value = True
        auth_view.client_id_edit = self.mock_client_id_edit
        auth_view.client_id_edit.text.return_value = client_id
        auth_view.client_secret_edit = self.mock_client_secret_edit
        auth_view.client_secret_edit.text.return_value = client_secret

    def setUp(self):
        # Common mocks for AuthView attributes
        self.mock_client_id_edit = MagicMock(spec=QLineEdit)
        self.mock_client_secret_edit = MagicMock(spec=QLineEdit)
        self.mock_file_radio = MagicMock(spec=QRadioButton)
        self.mock_manual_radio = MagicMock(spec=QRadioButton)
        self.mock_file_group = MagicMock(spec=QGroupBox)
        self.mock_manual_group = MagicMock(spec=QGroupBox)
        self.mock_file_path_edit = MagicMock(spec=QLineEdit)

    """Test cases for the AuthView class."""

    @patch("ripper.rippergui.oauth_client_config_view.AuthManager")
    @patch.object(AuthView, "__init__", return_value=None)
    def test_store_credentials_manual(self, mock_auth_view_init, mock_auth_manager_class):
        """Test that store_credentials stores manual credentials."""
        mock_auth_manager_instance = mock_auth_manager_class.return_value
        auth_view = AuthView()
        mock_auth_view_init.assert_called_once()

        auth_view.client_id_edit = MagicMock(spec=QLineEdit)
        auth_view.client_secret_edit = MagicMock(spec=QLineEdit)
        auth_view.client_id_edit.text.return_value = "test_client_id"
        auth_view.client_secret_edit.text.return_value = "test_client_secret"

        auth_view.store_credentials()

        mock_auth_manager_instance.store_oauth_client_credentials.assert_called_once_with(
            "test_client_id", "test_client_secret"
        )

    @patch("ripper.rippergui.oauth_client_config_view.AuthManager")
    @patch.object(AuthView, "__init__", return_value=None)
    def test_store_credentials_with_args(self, mock_auth_view_init, mock_auth_manager_class):
        """Test that store_credentials stores credentials passed as arguments."""
        mock_auth_manager_instance = mock_auth_manager_class.return_value
        auth_view = AuthView()
        mock_auth_view_init.assert_called_once()

        auth_view.store_credentials("arg_client_id", "arg_client_secret")

        mock_auth_manager_instance.store_oauth_client_credentials.assert_called_once_with(
            "arg_client_id", "arg_client_secret"
        )

    @patch("ripper.rippergui.oauth_client_config_view.AuthManager")
    @patch.object(AuthView, "__init__", return_value=None)
    def test_load_credentials_found(self, mock_auth_view_init, mock_auth_manager_class):
        """
        Test that load_credentials sets the correct values when credentials are found.
        """
        mock_auth_manager_instance = mock_auth_manager_class.return_value
        mock_auth_manager_instance.load_oauth_client_credentials.return_value = ("loaded_id", "loaded_secret")

        auth_view = AuthView()
        mock_auth_view_init.assert_called_once()
        auth_view.client_id_edit = self.mock_client_id_edit
        auth_view.client_secret_edit = self.mock_client_secret_edit
        auth_view.manual_radio = self.mock_manual_radio

        auth_view.load_credentials()

        self.mock_client_id_edit.setText.assert_called_once_with("loaded_id")
        self.mock_client_secret_edit.setText.assert_called_once_with("loaded_secret")
        self.mock_manual_radio.setChecked.assert_called_once_with(True)

    @patch("ripper.rippergui.oauth_client_config_view.AuthManager")
    @patch.object(AuthView, "__init__", return_value=None)
    def test_load_credentials_not_found(self, mock_auth_view_init, mock_auth_manager_class):
        """
        Test that load_credentials clears fields when no credentials are found.
        """
        mock_auth_manager_instance = mock_auth_manager_class.return_value
        mock_auth_manager_instance.load_oauth_client_credentials.return_value = (None, None)

        auth_view = AuthView()
        mock_auth_view_init.assert_called_once()
        auth_view.client_id_edit = self.mock_client_id_edit
        auth_view.client_secret_edit = self.mock_client_secret_edit
        auth_view.manual_radio = self.mock_manual_radio

        auth_view.load_credentials()

        self.mock_client_id_edit.setText.assert_called_once_with("")
        self.mock_client_secret_edit.setText.assert_called_once_with("")
        self.mock_manual_radio.setChecked.assert_not_called()

    @patch.object(AuthView, "__init__", return_value=None)
    def test_update_ui(self, mock_auth_view_init):
        """
        Test that update_ui enables/disables the correct groups based on radio button selection.
        """
        auth_view = AuthView()
        mock_auth_view_init.assert_called_once()
        auth_view.file_group = self.mock_file_group
        auth_view.manual_group = self.mock_manual_group
        auth_view.file_radio = self.mock_file_radio
        auth_view.manual_radio = self.mock_manual_radio

        self.mock_file_radio.isChecked.return_value = True
        self.mock_manual_radio.isChecked.return_value = False
        auth_view.update_ui()
        self.mock_file_group.setEnabled.assert_called_once_with(True)
        self.mock_manual_group.setEnabled.assert_called_once_with(False)

        self.mock_file_group.setEnabled.reset_mock()
        self.mock_manual_group.setEnabled.reset_mock()

        self.mock_file_radio.isChecked.return_value = False
        self.mock_manual_radio.isChecked.return_value = True
        auth_view.update_ui()
        self.mock_file_group.setEnabled.assert_called_once_with(False)
        self.mock_manual_group.setEnabled.assert_called_once_with(True)

    @patch(
        "ripper.rippergui.oauth_client_config_view.QFileDialog.getOpenFileName",
        return_value=("/fake/path/client_secret.json", ""),
    )
    @patch.object(AuthView, "__init__", return_value=None)
    def test_browse_file_selected(self, mock_auth_view_init, mock_get_open_file_name):
        """
        Test that browse_file sets the file path when a file is selected.
        """
        auth_view = AuthView()
        mock_auth_view_init.assert_called_once()
        auth_view.file_path_edit = self.mock_file_path_edit

        auth_view.browse_file()

        mock_get_open_file_name.assert_called_once()
        self.mock_file_path_edit.setText.assert_called_once_with("/fake/path/client_secret.json")

    @patch("ripper.rippergui.oauth_client_config_view.QFileDialog.getOpenFileName", return_value=("", ""))
    @patch.object(AuthView, "__init__", return_value=None)
    def test_browse_file_canceled(self, mock_auth_view_init, mock_get_open_file_name):
        """
        Test that browse_file does nothing when file selection is canceled.
        """
        auth_view = AuthView()
        mock_auth_view_init.assert_called_once()
        auth_view.file_path_edit = self.mock_file_path_edit

        auth_view.browse_file()

        mock_get_open_file_name.assert_called_once()
        self.mock_file_path_edit.setText.assert_not_called()

    @patch("ripper.rippergui.oauth_client_config_view.QMessageBox.warning")
    @patch("ripper.rippergui.oauth_client_config_view.AuthView.setup_ui")
    @patch("ripper.rippergui.oauth_client_config_view.AuthView.load_credentials")
    @patch.object(AuthView, "__init__", return_value=None)
    def test_register_client_file_no_file(
        self, mock_auth_view_init, mock_load_credentials, mock_setup_ui, mock_warning
    ):
        """Test register_client with file method and no file selected."""
        auth_view = AuthView()
        mock_auth_view_init.assert_called_once()
        auth_view.setup_ui = MagicMock()
        auth_view.load_credentials = MagicMock()
        auth_view.setup_ui()
        auth_view.load_credentials()

        auth_view.file_radio = MagicMock(spec=QRadioButton)
        auth_view.file_radio.isChecked.return_value = True
        auth_view.file_path_edit = MagicMock(spec=QLineEdit)
        auth_view.file_path_edit.text.return_value = ""

        auth_view.register_client()

        mock_warning.assert_called_once_with(
            auth_view, "OAuth Client Error", "Please select a client_secret.json file."
        )

    @patch("ripper.rippergui.oauth_client_config_view.QMessageBox.warning")
    @patch("ripper.rippergui.oauth_client_config_view.AuthView.setup_ui")
    @patch("ripper.rippergui.oauth_client_config_view.AuthView.load_credentials")
    @patch("os.path.exists", return_value=False)
    @patch.object(AuthView, "__init__", return_value=None)
    def test_register_client_file_file_not_exists(
        self, mock_auth_view_init, mock_exists, mock_load_credentials, mock_setup_ui, mock_warning
    ):
        """Test register_client with file method and selected file does not exist."""
        auth_view = AuthView()
        mock_auth_view_init.assert_called_once()
        # Manually mock and call setup_ui and load_credentials
        auth_view.setup_ui = MagicMock()
        auth_view.load_credentials = MagicMock()
        auth_view.setup_ui()
        auth_view.load_credentials()

        auth_view.file_radio = self.mock_file_radio
        self.mock_file_radio.isChecked.return_value = True
        auth_view.file_path_edit = self.mock_file_path_edit
        self.mock_file_path_edit.text.return_value = "/fake/path/non_existent_file.json"

        auth_view.register_client()

        mock_exists.assert_called_once_with("/fake/path/non_existent_file.json")
        mock_warning.assert_called_once_with(auth_view, "OAuth Client Error", "The selected file does not exist.")

    @patch("ripper.rippergui.oauth_client_config_view.QMessageBox.warning")
    @patch("ripper.rippergui.oauth_client_config_view.AuthView.setup_ui")
    @patch("ripper.rippergui.oauth_client_config_view.AuthView.load_credentials")
    @patch("os.path.exists", return_value=True)
    @patch("ripper.ripperlib.auth.AuthManager.oauth_client_credentials_from_json", return_value=(None, None))
    @patch.object(AuthView, "__init__", return_value=None)
    def test_register_client_file_invalid_json(
        self, mock_auth_view_init, mock_from_json, mock_exists, mock_load_credentials, mock_setup_ui, mock_warning
    ):
        """Test register_client with file method and invalid JSON content."""
        auth_view = AuthView()
        mock_auth_view_init.assert_called_once()
        auth_view.setup_ui = MagicMock()
        auth_view.load_credentials = MagicMock()
        auth_view.setup_ui()
        auth_view.load_credentials()

        auth_view.file_radio = self.mock_file_radio
        self.mock_file_radio.isChecked.return_value = True
        auth_view.file_path_edit = self.mock_file_path_edit
        self.mock_file_path_edit.text.return_value = "/fake/path/invalid_client_secret.json"

        auth_view.register_client()

        mock_from_json.assert_called_once_with("/fake/path/invalid_client_secret.json")
        mock_warning.assert_called_once_with(
            auth_view, "OAuth Client Error", "Invalid client_secret.json file: /fake/path/invalid_client_secret.json"
        )

    @patch("ripper.rippergui.oauth_client_config_view.QMessageBox.warning")
    @patch.object(AuthView, "__init__", return_value=None)
    def test_register_client_file_success(self, mock_init, mock_warning):
        """Test register_client with file method and valid JSON."""
        auth_view = AuthView()
        auth_view.setup_ui = MagicMock()
        auth_view.load_credentials = MagicMock()
        auth_view.setup_ui()
        auth_view.load_credentials()
        # Patch the signal emit and store_credentials
        auth_view.oauth_client_registered = MagicMock()
        auth_view.oauth_client_registered.emit = MagicMock()
        auth_view.store_credentials = MagicMock()

        # Patch the static method and os.path.exists
        import os

        import ripper.ripperlib.auth as auth_mod

        original_from_json = auth_mod.AuthManager.oauth_client_credentials_from_json
        original_exists = os.path.exists
        auth_mod.AuthManager.oauth_client_credentials_from_json = MagicMock(return_value=("client_id", "client_secret"))
        os.path.exists = MagicMock(return_value=True)

        auth_view.file_radio = self.mock_file_radio
        self.mock_file_radio.isChecked.return_value = True
        auth_view.file_path_edit = self.mock_file_path_edit
        self.mock_file_path_edit.text.return_value = "/fake/path/client_secret.json"

        auth_view.register_client()

        auth_mod.AuthManager.oauth_client_credentials_from_json.assert_called_once_with("/fake/path/client_secret.json")
        auth_view.store_credentials.assert_called_once_with("client_id", "client_secret")
        auth_view.oauth_client_registered.emit.assert_called_once()

        # Restore patched methods
        auth_mod.AuthManager.oauth_client_credentials_from_json = original_from_json
        os.path.exists = original_exists

    @patch("ripper.rippergui.oauth_client_config_view.QMessageBox.warning")
    @patch.object(AuthView, "__init__", return_value=None)
    def test_register_client_manual_missing_fields(self, mock_auth_view_init, mock_warning):
        """
        Test register_client with manual method and missing client ID or secret.
        Should warn if either is missing.
        """
        test_cases = [
            ("", "test_secret", "Please enter both Client ID and Client Secret."),
            ("test_id", "", "Please enter both Client ID and Client Secret."),
        ]
        for client_id, client_secret, expected_msg in test_cases:
            auth_view = AuthView()
            mock_auth_view_init.assert_called()
            auth_view.setup_ui = MagicMock()
            auth_view.load_credentials = MagicMock()
            auth_view.setup_ui()
            auth_view.load_credentials()
            self._setup_auth_view_for_manual(auth_view, client_id, client_secret)
            auth_view.register_client()
            mock_warning.assert_called_with(auth_view, "OAuth Client Error", expected_msg)
            mock_warning.reset_mock()

    @patch("ripper.rippergui.oauth_client_config_view.QMessageBox.warning")
    @patch("ripper.rippergui.oauth_client_config_view.AuthView.setup_ui")
    @patch("ripper.rippergui.oauth_client_config_view.AuthView.load_credentials")
    @patch.object(AuthView, "__init__", return_value=None)
    def test_register_client_manual_no_secret(
        self, mock_auth_view_init, mock_load_credentials, mock_setup_ui, mock_warning
    ):
        """Test register_client with manual method and no client secret."""
        auth_view = AuthView()
        mock_auth_view_init.assert_called_once()
        auth_view.setup_ui = MagicMock()
        auth_view.load_credentials = MagicMock()
        auth_view.setup_ui()
        auth_view.load_credentials()

        auth_view.file_radio = MagicMock(spec=QRadioButton)
        auth_view.file_radio.isChecked.return_value = False
        auth_view.manual_radio = MagicMock(spec=QRadioButton)
        auth_view.manual_radio.isChecked.return_value = True
        auth_view.client_id_edit = MagicMock(spec=QLineEdit)
        auth_view.client_id_edit.text.return_value = "test_id"
        auth_view.client_secret_edit = MagicMock(spec=QLineEdit)
        auth_view.client_secret_edit.text.return_value = ""

        auth_view.register_client()

        mock_warning.assert_called_once_with(
            auth_view, "OAuth Client Error", "Please enter both Client ID and Client Secret."
        )

    @patch("ripper.rippergui.oauth_client_config_view.QMessageBox.warning")
    @patch.object(AuthView, "__init__", return_value=None)
    def test_register_client_manual_success(self, mock_init, mock_warning):
        """Test register_client with manual method and valid credentials."""
        auth_view = AuthView()
        auth_view.setup_ui = MagicMock()
        auth_view.load_credentials = MagicMock()
        auth_view.setup_ui()
        auth_view.load_credentials()
        # Patch the signal emit and store_credentials
        auth_view.oauth_client_registered = MagicMock()
        auth_view.oauth_client_registered.emit = MagicMock()
        auth_view.store_credentials = MagicMock()

        # Patch the static method and os.path.exists
        import os

        import ripper.ripperlib.auth as auth_mod

        original_from_json = auth_mod.AuthManager.oauth_client_credentials_from_json
        original_exists = os.path.exists
        auth_mod.AuthManager.oauth_client_credentials_from_json = MagicMock(return_value=("client_id", "client_secret"))
        os.path.exists = MagicMock(return_value=True)

        auth_view.file_radio = self.mock_file_radio
        self.mock_file_radio.isChecked.return_value = False
        auth_view.manual_radio = self.mock_manual_radio
        self.mock_manual_radio.isChecked.return_value = True
        auth_view.client_id_edit = self.mock_client_id_edit
        self.mock_client_id_edit.text.return_value = "test_id"
        auth_view.client_secret_edit = self.mock_client_secret_edit
        self.mock_client_secret_edit.text.return_value = "test_secret"

        auth_view.register_client()

        auth_view.store_credentials.assert_called_once_with("test_id", "test_secret")
        auth_view.oauth_client_registered.emit.assert_called_once()

        # Restore patched methods
        auth_mod.AuthManager.oauth_client_credentials_from_json = original_from_json
        os.path.exists = original_exists

    @patch("os.environ.get", return_value="/fake/appdata")
    @patch("ripper.rippergui.oauth_client_config_view.AuthView.setup_ui")
    @patch("ripper.rippergui.oauth_client_config_view.AuthView.load_credentials")
    @patch.object(AuthView, "__init__", return_value=None)
    def test_get_client_secret_path(self, mock_auth_view_init, mock_load_credentials, mock_setup_ui, mock_environ_get):
        """Test that get_client_secret_path returns the correct path."""
        auth_view = AuthView()
        mock_auth_view_init.assert_called_once()
        auth_view.setup_ui = MagicMock()
        auth_view.load_credentials = MagicMock()
        auth_view.setup_ui()
        auth_view.load_credentials()

        import os

        expected_path = os.path.join("/fake/appdata", "ripper", "client_secret.json")
        self.assertEqual(auth_view._get_client_secret_path(), expected_path)

        mock_environ_get.assert_called_once_with("APPDATA", "")
