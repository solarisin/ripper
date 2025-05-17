import unittest
from unittest.mock import MagicMock
from googleapiclient.errors import HttpError
from ripperlib.sheets_backend import list_sheets, read_data_from_spreadsheet


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
        result = list_sheets(mock_service)

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
            fields="nextPageToken, files(id, name)",
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
        result = list_sheets(mock_service)

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
