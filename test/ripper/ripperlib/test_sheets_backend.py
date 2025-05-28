import unittest
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError

from ripper.ripperlib.defs import LoadSource, SheetProperties, SpreadsheetProperties
from ripper.ripperlib.sheets_backend import (
    fetch_sheets_of_spreadsheet,
    fetch_spreadsheets,
    retrieve_sheets_of_spreadsheet,
    retrieve_spreadsheets,
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
                {
                    "id": "sheet1",
                    "name": "Test Sheet 1",
                    "createdTime": "2023-12-01T00:00:00Z",
                    "modifiedTime": "2024-01-01T00:00:00Z",
                    "webViewLink": "https://example.com/sheet1",
                    "thumbnailLink": "https://example.com/thumbnail1",
                    "owners": [{"displayName": "Test User"}],
                    "size": 1024,
                    "shared": True,
                },
                {
                    "id": "sheet2",
                    "name": "Test Sheet 2",
                    "createdTime": "2023-12-01T00:00:00Z",
                    "modifiedTime": "2024-01-01T00:00:00Z",
                    "webViewLink": "https://example.com/sheet2",
                    "thumbnailLink": "https://example.com/thumbnail2",
                    "owners": [{"displayName": "Test User"}],
                    "size": 2048,
                    "shared": True,
                },
            ],
            "nextPageToken": None,
        }

        # Call the function
        spreadsheets = fetch_spreadsheets(mock_service)

        # Assertions
        self.assertEqual(len(spreadsheets), 2)
        self.assertEqual(spreadsheets[0].id, "sheet1")
        self.assertEqual(spreadsheets[1].id, "sheet2")
        mock_service.files.assert_called_once()
        mock_files_list.assert_called_once_with(
            q="mimeType='application/vnd.google-apps.spreadsheet'",
            spaces="drive",
            fields=f"nextPageToken, {SpreadsheetProperties.api_fields()}",
            pageToken=None,
        )

    def test_list_sheets_http_error(self):
        """Test that list_sheets handles HttpError correctly."""
        # Create a mock service that raises HttpError
        mock_service = MagicMock()
        mock_service.files.return_value.list.return_value.execute.side_effect = HttpError(
            MagicMock(status=404), b"Not Found"
        )

        # Call the function
        spreadsheets = fetch_spreadsheets(mock_service)

        # Assertions
        self.assertEqual(len(spreadsheets), 0)
        mock_service.files.assert_called_once()
        mock_service.files.return_value.list.assert_called_once()
        mock_service.files.return_value.list.return_value.execute.assert_called_once()

    def test_fetch_sheets_of_spreadsheet_success(self):
        """Test fetching sheets of a spreadsheet successfully."""
        mock_sheets_service = MagicMock()
        spreadsheet_id = "test_spreadsheet_id"
        mock_api_result = {
            "sheets": [
                {
                    "properties": {
                        "sheetId": 1,
                        "title": "Sheet1",
                        "index": 0,
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 100, "columnCount": 26},
                    }
                }
            ]
        }
        mock_sheets_service.spreadsheets.return_value.get.return_value.execute.return_value = mock_api_result

        sheets = fetch_sheets_of_spreadsheet(mock_sheets_service, spreadsheet_id)

        self.assertEqual(len(sheets), 1)
        self.assertEqual(sheets[0].id, 1)
        self.assertEqual(sheets[0].title, "Sheet1")
        self.assertEqual(sheets[0].index, 0)
        self.assertEqual(sheets[0].type, "GRID")
        self.assertEqual(sheets[0].grid.row_count, 100)
        self.assertEqual(sheets[0].grid.column_count, 26)

        mock_sheets_service.spreadsheets.assert_called_once()
        mock_sheets_service.spreadsheets.return_value.get.assert_called_once_with(
            spreadsheetId=spreadsheet_id, fields=SheetProperties.api_fields()
        )

    def test_fetch_sheets_of_spreadsheet_http_error(self):
        """Test fetching sheets of a spreadsheet with HttpError."""
        mock_sheets_service = MagicMock()
        spreadsheet_id = "test_spreadsheet_id"
        mock_sheets_service.spreadsheets.return_value.get.return_value.execute.side_effect = HttpError(
            MagicMock(status=404), b"Not Found"
        )

        sheets = fetch_sheets_of_spreadsheet(mock_sheets_service, spreadsheet_id)

        self.assertEqual(len(sheets), 0)
        mock_sheets_service.spreadsheets.assert_called_once()
        mock_sheets_service.spreadsheets.return_value.get.assert_called_once_with(
            spreadsheetId=spreadsheet_id, fields=SheetProperties.api_fields()
        )

    def test_retrieve_spreadsheets_fetches_and_stores(self):
        """Test retrieve_spreadsheets fetches from API and stores in DB when DB is empty."""
        mock_drive_service = MagicMock()
        mock_spreadsheet_props = [MagicMock(spec=SpreadsheetProperties, id="sheet1")]

        # Mock fetch_spreadsheets to return data
        with patch(
            "ripper.ripperlib.sheets_backend.fetch_spreadsheets", return_value=mock_spreadsheet_props
        ) as mock_fetch:
            # Mock Db.store_spreadsheet_properties
            with patch("ripper.ripperlib.sheets_backend.Db.store_spreadsheet_properties") as mock_store:
                spreadsheets = retrieve_spreadsheets(mock_drive_service)

                self.assertEqual(len(spreadsheets), 1)
                self.assertEqual(spreadsheets[0].id, "sheet1")
                mock_fetch.assert_called_once_with(mock_drive_service)
                mock_store.assert_called_once_with("sheet1", mock_spreadsheet_props[0])

    def test_retrieve_spreadsheets_fetch_failure(self):
        """Test retrieve_spreadsheets handles fetch failure."""
        mock_drive_service = MagicMock()
        # Mock fetch_spreadsheets to return empty list (failure)
        with patch("ripper.ripperlib.sheets_backend.fetch_spreadsheets", return_value=[]) as mock_fetch:
            # Ensure store_spreadsheet_properties is NOT called
            with patch("ripper.ripperlib.sheets_backend.Db.store_spreadsheet_properties") as mock_store:
                spreadsheets = retrieve_spreadsheets(mock_drive_service)

                self.assertEqual(len(spreadsheets), 0)
                mock_fetch.assert_called_once_with(mock_drive_service)
                mock_store.assert_not_called()

    def test_retrieve_sheets_of_spreadsheet_from_db(self):
        """Test retrieving sheets from DB when available."""
        spreadsheet_id = "test_id"
        mock_db_sheets = [MagicMock(spec=SheetProperties, id="sheet1")]

        # Mock Db.get_sheet_properties_of_spreadsheet to return data
        with patch(
            "ripper.ripperlib.sheets_backend.Db.get_sheet_properties_of_spreadsheet", return_value=mock_db_sheets
        ) as mock_get_db:
            mock_sheets_service = MagicMock()
            sheets = retrieve_sheets_of_spreadsheet(mock_sheets_service, spreadsheet_id)

            self.assertEqual(len(sheets), 1)
            self.assertEqual(sheets[0].id, "sheet1")
            self.assertEqual(sheets[0].load_source, LoadSource.DATABASE)  # Ensure load_source is set
            mock_get_db.assert_called_once_with(spreadsheet_id)

    def test_retrieve_sheets_of_spreadsheet_from_api(self):
        """Test retrieving sheets from API when DB is empty."""
        spreadsheet_id = "test_id"
        mock_api_sheets = [MagicMock(spec=SheetProperties, id="sheet1")]

        # Mock Db.get_sheet_properties_of_spreadsheet to return empty list
        with patch(
            "ripper.ripperlib.sheets_backend.Db.get_sheet_properties_of_spreadsheet", return_value=[]
        ) as mock_get_db:
            # Mock fetch_sheets_of_spreadsheet to return data
            with patch(
                "ripper.ripperlib.sheets_backend.fetch_sheets_of_spreadsheet", return_value=mock_api_sheets
            ) as mock_fetch_api:
                # Mock Db.store_sheet_properties
                with patch("ripper.ripperlib.sheets_backend.Db.store_sheet_properties") as mock_store_db:
                    mock_sheets_service = MagicMock()
                    sheets = retrieve_sheets_of_spreadsheet(mock_sheets_service, spreadsheet_id)

                    self.assertEqual(len(sheets), 1)
                    self.assertEqual(sheets[0].id, "sheet1")
                    self.assertEqual(sheets[0].load_source, LoadSource.API)  # Ensure load_source is set
                    mock_get_db.assert_called_once_with(spreadsheet_id)
                    mock_fetch_api.assert_called_once_with(mock_sheets_service, spreadsheet_id)
                    mock_store_db.assert_called_once_with(spreadsheet_id, mock_api_sheets)
