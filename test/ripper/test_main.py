import importlib.metadata
import unittest
from unittest.mock import patch

from ripper.main import get_version


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
