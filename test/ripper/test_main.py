import importlib.metadata
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from ripper.main import cli, get_version


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


class TestDbCreateFilePath:
    """Regression tests for `db --file-path ... create` (issue #71)."""

    def test_create_applies_custom_path_to_ripperdb(self, tmp_path: Path) -> None:
        """`db --file-path X create` must construct a RipperDb targeting X, not the default."""
        custom_path = tmp_path / "custom.db"
        runner = CliRunner()

        with patch("ripper.ripperlib.database.RipperDb") as mock_ripper_db:
            result = runner.invoke(cli, ["db", "--file-path", str(custom_path), "create"], obj={})

        assert result.exit_code == 0, result.output
        # The path must actually be applied to the DB that gets opened.
        mock_ripper_db.assert_called_once_with(str(custom_path))
        # The scoped connection is closed after creation.
        mock_ripper_db.return_value.close.assert_called_once_with()

    def test_create_initializes_requested_file_and_leaves_default_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end: exactly the requested file is created; the default DB is never touched."""
        default_path = tmp_path / "default.db"
        custom_path = tmp_path / "subdir" / "custom.db"
        monkeypatch.setattr("ripper.ripperlib.database.default_db_path", lambda: default_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["db", "--file-path", str(custom_path), "create"], obj={})

        assert result.exit_code == 0, result.output
        assert custom_path.exists(), "requested database file was not created"
        assert not default_path.exists(), "default database must not be created for a custom path"
