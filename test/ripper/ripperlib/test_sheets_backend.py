import json
import unittest
from unittest.mock import MagicMock

from googleapiclient.errors import HttpError

from ripper.ripperlib.defs import SheetProperties
from ripper.ripperlib.sheets_backend import (
    DRIVE_FILE_FIELDS,
    fetch_and_store_spreadsheets,
    list_spreadsheets,
    read_data_from_spreadsheet,
    read_spreadsheet_metadata,
)


class TestSheetsBackend(unittest.TestCase):
    """Test cases for the sheets_backend module."""

    def test_list_sheets_success(self):
        """Test that list_sheets returns the expected list of sheets when successful."""
        # Create a mock service
        mock_service = MagicMock()

        # Set up the mock to return a response with files
        mock_files_list = mock_service.files.return_value.list
        mock_files_list.return_value.execute.return_value = {
            "files": [
                {"id": "sheet1", "name": "Test Sheet 1"},
                {"id": "sheet2", "name": "Test Sheet 2"},
            ],
            "nextPageToken": None,
        }

        # Call the function with our mock
        result = list_spreadsheets(mock_service)

        # Verify the result
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "sheet1")
        self.assertEqual(result[0]["name"], "Test Sheet 1")
        self.assertEqual(result[1]["id"], "sheet2")
        self.assertEqual(result[1]["name"], "Test Sheet 2")

        # Verify the mock was called with the expected arguments
        mock_files_list.assert_called_once_with(
            q="mimeType='application/vnd.google-apps.spreadsheet'",
            spaces="drive",
            fields=f"nextPageToken, files({', '.join(DRIVE_FILE_FIELDS)})",
            pageToken=None,
        )

    def test_list_sheets_error(self):
        """Test that list_sheets returns None when an HttpError occurs."""
        # Create a mock service
        mock_service = MagicMock()

        # Set up the mock to raise an HttpError
        mock_files_list = mock_service.files.return_value.list
        mock_files_list.return_value.execute.side_effect = HttpError(
            resp=MagicMock(status=403), content=b"Access Denied"
        )

        # Call the function with our mock
        result = list_spreadsheets(mock_service)

        # Verify the result is None
        self.assertIsNone(result)

    def test_read_data_from_spreadsheet_success(self):
        """Test that read_data_from_spreadsheet returns the expected data when successful."""
        # Create a mock service
        mock_service = MagicMock()

        # Set up the mock to return a response with values
        mock_sheets = mock_service.spreadsheets.return_value
        mock_values = mock_sheets.values.return_value.get
        mock_values.return_value.execute.return_value = {
            "values": [
                ["Header1", "Header2"],
                ["Value1", "Value2"],
            ]
        }

        # Call the function with our mock
        result = read_data_from_spreadsheet(mock_service, "test_id", "Sheet1!A1:B2")

        # Verify the result
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], "Header1")
        self.assertEqual(result[0][1], "Header2")
        self.assertEqual(result[1][0], "Value1")
        self.assertEqual(result[1][1], "Value2")

        # Verify the mock was called with the expected arguments
        mock_values.assert_called_once_with(spreadsheetId="test_id", range="Sheet1!A1:B2")

    def test_read_data_from_spreadsheet_empty(self):
        """Test that read_data_from_spreadsheet returns None when no data is found."""
        # Create a mock service
        mock_service = MagicMock()

        # Set up the mock to return a response with no values
        mock_sheets = mock_service.spreadsheets.return_value
        mock_values = mock_sheets.values.return_value.get
        mock_values.return_value.execute.return_value = {}

        # Call the function with our mock
        result = read_data_from_spreadsheet(mock_service, "test_id", "Sheet1!A1:B2")

        # Verify the result is None
        self.assertIsNone(result)

    def test_read_data_from_spreadsheet_error(self):
        """Test that read_data_from_spreadsheet returns None when an HttpError occurs."""
        # Create a mock service
        mock_service = MagicMock()

        # Set up the mock to raise an HttpError
        mock_sheets = mock_service.spreadsheets.return_value
        mock_values = mock_sheets.values.return_value.get
        mock_values.return_value.execute.side_effect = HttpError(resp=MagicMock(status=404), content=b"Not Found")

        # Call the function with our mock
        result = read_data_from_spreadsheet(mock_service, "test_id", "Sheet1!A1:B2")

        # Verify the result is None
        self.assertIsNone(result)

    def test_read_spreadsheet_metadata_success(self):
        """Test that read_spreadsheet_metadata returns the expected metadata when successful."""
        # Create a mock service
        mock_service = MagicMock()

        # Set up the mock to return a response with sheet metadata
        mock_sheets = mock_service.spreadsheets.return_value
        mock_get = mock_sheets.get
        mock_get.return_value.execute.return_value = {
            "sheets": [
                {
                    "properties": {
                        "sheetId": "sheet1",
                        "index": 0,
                        "title": "Sheet 1",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 100, "columnCount": 26},
                    }
                },
                {
                    "properties": {
                        "sheetId": "sheet2",
                        "index": 1,
                        "title": "Sheet 2",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 200, "columnCount": 52},
                    }
                },
            ]
        }

        # Call the function with our mock
        result = read_spreadsheet_metadata(mock_service, "test_id")

        # Verify the result
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].id, "sheet1")
        self.assertEqual(result[0].title, "Sheet 1")
        self.assertEqual(result[0].grid.row_count, 100)
        self.assertEqual(result[0].grid.column_count, 26)
        self.assertEqual(result[1].id, "sheet2")
        self.assertEqual(result[1].title, "Sheet 2")

        # Verify the mock was called with the expected arguments
        mock_get.assert_called_once_with(spreadsheetId="test_id", fields=SheetProperties.api_fields())

    def test_read_spreadsheet_metadata_error(self):
        """Test that read_spreadsheet_metadata returns None when an HttpError occurs."""
        # Create a mock service
        mock_service = MagicMock()

        # Set up the mock to raise an HttpError
        mock_sheets = mock_service.spreadsheets.return_value
        mock_get = mock_sheets.get
        mock_get.return_value.execute.side_effect = HttpError(resp=MagicMock(status=404), content=b"Not Found")

        # Call the function with our mock
        result = read_spreadsheet_metadata(mock_service, "test_id")

        # Verify the result is None
        self.assertIsNone(result)

    def test_fetch_and_store_spreadsheets_success(self):
        """Test that fetch_and_store_spreadsheets fetches and stores spreadsheet info correctly."""
        # Create mock drive service and db
        mock_drive_service = MagicMock()
        mock_db = MagicMock()

        # Set up the mock to return a response with files
        mock_files_list = mock_drive_service.files.return_value.list
        mock_files_list.return_value.execute.return_value = {
            "files": [
                {
                    "id": "sheet1",
                    "name": "Test Sheet 1",
                    "modifiedTime": "2024-01-01T00:00:00Z",
                    "webViewLink": "https://example.com/sheet1",
                    "createdTime": "2023-12-01T00:00:00Z",
                    "owners": [{"displayName": "Test User"}],
                    "size": 1024,
                    "shared": True,
                }
            ],
            "nextPageToken": None,
        }

        # Call the function with our mocks
        result = fetch_and_store_spreadsheets(mock_drive_service, mock_db)

        # Verify the result
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "sheet1")
        self.assertEqual(result[0]["name"], "Test Sheet 1")

        # Verify store_spreadsheet_info was called with the expected arguments
        mock_db.store_spreadsheet_info.assert_called_once()
        call_args = mock_db.store_spreadsheet_info.call_args[0]
        self.assertEqual(call_args[0], "sheet1")  # spreadsheet_id
        self.assertEqual(call_args[1]["name"], "Test Sheet 1")
        self.assertEqual(call_args[1]["modifiedTime"], "2024-01-01T00:00:00Z")
        self.assertEqual(call_args[1]["owners"], json.dumps([{"displayName": "Test User"}]))

    def test_fetch_and_store_spreadsheets_error(self):
        """Test that fetch_and_store_spreadsheets returns None when list_spreadsheets fails."""
        # Create mock drive service and db
        mock_drive_service = MagicMock()
        mock_db = MagicMock()

        # Set up the mock to raise an HttpError
        mock_files_list = mock_drive_service.files.return_value.list
        mock_files_list.return_value.execute.side_effect = HttpError(
            resp=MagicMock(status=403), content=b"Access Denied"
        )

        # Call the function with our mocks
        result = fetch_and_store_spreadsheets(mock_drive_service, mock_db)

        # Verify the result is None
        self.assertIsNone(result)

        # Verify store_spreadsheet_info was not called
        mock_db.store_spreadsheet_info.assert_not_called()
