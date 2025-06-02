"""
Test utilities and helpers for the ripper test suite.

This module provides common test utilities, factories, and assertions
that can be used across test modules.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials


def create_test_credentials(
    token: str = "test-token",
    refresh_token: str = "test-refresh-token",
    scopes: Optional[List[str]] = None,
) -> Credentials:
    """Create test OAuth2 credentials.

    Args:
        token: Access token
        refresh_token: Refresh token
        scopes: List of OAuth scopes

    Returns:
        Credentials: Configured credentials object
    """
    if scopes is None:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]

    return Credentials(
        token=token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id="test-client-id",
        client_secret="test-client-secret",
        scopes=scopes,
    )


def create_spreadsheet_data(
    spreadsheet_id: str = "test_spreadsheet_id",
    title: str = "Test Spreadsheet",
    sheet_title: str = "Sheet1",
    row_count: int = 1000,
    column_count: int = 26,
) -> Dict[str, Any]:
    """Create test spreadsheet data.

    Args:
        spreadsheet_id: ID for the test spreadsheet
        title: Title for the spreadsheet
        sheet_title: Title for the default sheet
        row_count: Number of rows in the sheet
        column_count: Number of columns in the sheet

    Returns:
        Dict: Spreadsheet data in Google Sheets API format
    """
    return {
        "spreadsheetId": spreadsheet_id,
        "properties": {
            "title": title,
            "locale": "en_US",
            "timeZone": "America/New_York",
        },
        "sheets": [
            {
                "properties": {
                    "sheetId": 123456,
                    "title": sheet_title,
                    "index": 0,
                    "sheetType": "GRID",
                    "gridProperties": {
                        "rowCount": row_count,
                        "columnCount": column_count,
                    },
                }
            }
        ],
    }


def create_sheet_data(headers: Optional[List[str]] = None, rows: Optional[List[List[Any]]] = None) -> List[List[Any]]:
    """Create test sheet data.

    Args:
        headers: Optional list of header strings
        rows: Optional list of row data

    Returns:
        List of lists representing sheet data
    """
    if headers is None:
        headers = ["Header 1", "Header 2", "Header 3"]
    if rows is None:
        rows = [
            ["Data 1", 123, True],
            ["Data 2", 456, False],
            ["Data 3", 789, True],
        ]
    return [headers] + rows


def assert_dict_contains(actual: Dict[Any, Any], expected: Dict[Any, Any]) -> None:
    """Assert that actual dict contains all key-value pairs from expected.

    Args:
        actual: The dictionary to check
        expected: The dictionary of expected key-value pairs
    """
    for key, value in expected.items():
        assert key in actual, f"Key '{key}' not found in actual dict"
        assert actual[key] == value, f"Value for key '{key}' does not match"


def assert_lists_equal(actual: List[Any], expected: List[Any]) -> None:
    """Assert that two lists are equal, with helpful error messages.

    Args:
        actual: The actual list
        expected: The expected list
    """
    assert len(actual) == len(expected), f"Length mismatch: {len(actual)} != {len(expected)}"
    for i, (a, e) in enumerate(zip(actual, expected)):
        assert a == e, f"Mismatch at index {i}: {a} != {e}"


def save_test_data(data: Any, filename: str, test_data_dir: Path) -> Path:
    """Save test data to a file in the test data directory.

    Args:
        data: Data to save (will be JSON-serialized)
        filename: Name of the file to save
        test_data_dir: Path to the test data directory

    Returns:
        Path to the saved file
    """
    path = test_data_dir / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path
