import unittest
from unittest.mock import MagicMock, patch
import importlib.metadata
import logging
import sys
import pytest
from ripperlib.main import get_version, configure_logging


class TestMain(unittest.TestCase):
    """Test cases for the main module."""

    @patch("importlib.metadata.version")
    @patch("toml.load")
    def test_get_version_from_metadata(self, mock_toml_load, mock_metadata_version):
        """Test that get_version returns the version from package metadata when available."""
        # Set up the mock to return a version
        mock_metadata_version.return_value = "1.0.0"

        # Call get_version
        result = get_version()

        # Check that the result is the version from metadata
        self.assertEqual(result, "1.0.0")

        # Check that metadata.version was called with the correct package name
        mock_metadata_version.assert_called_once_with("ripper")

        # Check that toml.load was not called
        mock_toml_load.assert_not_called()

    @patch("importlib.metadata.version")
    @patch("toml.load")
    def test_get_version_from_toml(self, mock_toml_load, mock_metadata_version):
        """Test that get_version returns the version from pyproject.toml when metadata is not available."""
        # Set up the mock to raise an exception
        mock_metadata_version.side_effect = importlib.metadata.PackageNotFoundError("Package not found")

        # Set up the mock to return a pyproject.toml with a version
        mock_toml_load.return_value = {"project": {"version": "1.0.0"}}

        # Call get_version
        result = get_version()

        # Check that the result is the version from pyproject.toml
        self.assertEqual(result, "1.0.0")

        # Check that metadata.version was called with the correct package name
        mock_metadata_version.assert_called_once_with("ripper")

        # Check that toml.load was called
        mock_toml_load.assert_called_once()

    @patch("logging.basicConfig")
    def test_configure_logging_with_default_level(self, mock_basicConfig):
        """Test that configure_logging sets up logging with the default level (DEBUG)."""
        # Call configure_logging with no level
        configure_logging()

        # Check that basicConfig was called with the correct arguments
        mock_basicConfig.assert_called_once()
        args, kwargs = mock_basicConfig.call_args
        self.assertEqual(kwargs["level"], logging.DEBUG)
        self.assertEqual(kwargs["format"], "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.assertEqual(kwargs["datefmt"], "%Y-%m-%d %H:%M:%S")

    @patch("logging.basicConfig")
    def test_configure_logging_with_custom_level(self, mock_basicConfig):
        """Test that configure_logging sets up logging with a custom level."""
        # Call configure_logging with a custom level
        configure_logging(logging.INFO)

        # Check that basicConfig was called with the correct arguments
        mock_basicConfig.assert_called_once()
        args, kwargs = mock_basicConfig.call_args
        self.assertEqual(kwargs["level"], logging.INFO)
        self.assertEqual(kwargs["format"], "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.assertEqual(kwargs["datefmt"], "%Y-%m-%d %H:%M:%S")

    @pytest.mark.qt
    @patch("ripperlib.main.QApplication")
    @patch("ripperlib.main.MainView")
    @patch("ripperlib.main.AuthManager")
    @patch("sys.exit")
    def test_main_gui(self, mock_sys_exit, mock_auth_manager, mock_main_view, mock_qapp):
        """Test that main_gui initializes the application correctly."""
        # Set up mocks
        mock_app_instance = MagicMock()
        mock_qapp.return_value = mock_app_instance

        mock_main_view_instance = MagicMock()
        mock_main_view.return_value = mock_main_view_instance

        mock_auth_manager_instance = MagicMock()
        mock_auth_manager.return_value = mock_auth_manager_instance

        # Import main_gui function (it's not imported at the top level to avoid circular imports)
        from ripperlib.main import main_gui

        # Call main_gui
        main_gui()

        # Check that QApplication was created
        mock_qapp.assert_called_once_with(sys.argv)

        # Check that MainView was created
        mock_main_view.assert_called_once()

        # Check that AuthManager.check_stored_credentials was called
        mock_auth_manager_instance.check_stored_credentials.assert_called_once()

        # Check that MainView.show was called
        mock_main_view_instance.show.assert_called_once()

        # Check that sys.exit was called with app.exec()
        mock_sys_exit.assert_called_once_with(mock_app_instance.exec())
