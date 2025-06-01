"""
Pytest configuration file.

This file contains fixtures and configuration for pytest.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

import pytest
from beartype.typing import Dict, List
from google.oauth2.credentials import Credentials
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

# Fixed timestamp for testing
TEST_TIMESTAMP = datetime.now(timezone.utc)


@pytest.fixture
def test_timestamp() -> datetime:
    """Return a fixed timestamp for testing."""
    return TEST_TIMESTAMP


# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Test data paths
TEST_DATA_DIR = Path(__file__).parent / "test_data"


@pytest.fixture(scope="session")
def qapp() -> Generator[QCoreApplication | QApplication, None, None]:
    """Fixture to provide a QApplication instance for Qt tests."""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app
    app.quit()


@pytest.fixture
def mock_credentials() -> Credentials:
    """Fixture providing a mock Google OAuth2 credentials object."""
    return Credentials(
        token="test-token",
        refresh_token="test-refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="test-client-id",
        client_secret="test-client-secret",
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )


@pytest.fixture
def spreadsheet_data() -> Dict[str, Any]:
    """Fixture providing sample spreadsheet data."""
    return {
        "spreadsheetId": "test_spreadsheet_id",
        "properties": {
            "title": "Test Spreadsheet",
            "locale": "en_US",
            "timeZone": "America/New_York",
        },
        "sheets": [
            {
                "properties": {
                    "sheetId": 123456,
                    "title": "Sheet1",
                    "index": 0,
                    "sheetType": "GRID",
                    "gridProperties": {
                        "rowCount": 1000,
                        "columnCount": 26,
                    },
                }
            }
        ],
    }


@pytest.fixture
def sheet_data() -> List[List[Any]]:
    """Fixture providing sample sheet data."""
    return [
        ["Header 1", "Header 2", "Header 3"],
        ["Data 1", 123, True],
        ["Data 2", 456, False],
        ["Data 3", 789, True],
    ]


@pytest.fixture
def test_data_dir() -> Path:
    """Fixture providing the test data directory path."""
    return TEST_DATA_DIR


def pytest_configure(config):
    """Pytest configuration hook."""
    # Ensure test data directory exists
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
