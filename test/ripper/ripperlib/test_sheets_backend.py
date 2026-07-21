import unittest
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError

from ripper.ripperlib.database import RipperDb
from ripper.ripperlib.defs import LoadSource, SheetProperties, SpreadsheetProperties
from ripper.ripperlib.range_manager import split_sheet_and_range
from ripper.ripperlib.sheets_backend import (
    fetch_sheets_of_spreadsheet,
    fetch_spreadsheets,
    fetch_thumbnail,
    get_tiller_budget,
    get_tiller_categories,
    get_tiller_transactions,
    retrieve_sheet_data,
    retrieve_sheet_data_for,
    retrieve_sheets_of_spreadsheet,
    retrieve_spreadsheets,
    retrieve_thumbnail,
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


class TestRetrieveSheetDataParsing(unittest.TestCase):
    """Tests for sheet-name parsing and quoting in retrieve_sheet_data (#72)."""

    def test_whole_sheet_title_with_bang_via_separate_args(self) -> None:
        """A whole-sheet load of a '!'-containing title stays a whole-sheet reference (#72 review).

        Passing sheet_name and range separately avoids the combined-string ambiguity where
        'Q1!Actuals' (no range) would be misparsed as sheet 'Q1' + range 'Actuals'.
        """
        mock_service = MagicMock()
        with patch("ripper.ripperlib.sheets_backend.fetch_data_from_spreadsheet") as mock_fetch:
            mock_fetch.return_value = []
            retrieve_sheet_data_for(mock_service, "book", "Q1!Actuals", None)
            mock_fetch.assert_called_once_with(mock_service, "book", "'Q1!Actuals'")

    def test_empty_range_is_treated_as_whole_sheet(self) -> None:
        """An empty range_a1 (whole-sheet load) quotes the title rather than appending '!'."""
        mock_service = MagicMock()
        with patch("ripper.ripperlib.sheets_backend.fetch_data_from_spreadsheet") as mock_fetch:
            mock_fetch.return_value = []
            retrieve_sheet_data_for(mock_service, "book", "Monthly Budget", "")
            mock_fetch.assert_called_once_with(mock_service, "book", "'Monthly Budget'")

    def test_ranged_separate_args_go_through_cache(self) -> None:
        """With a range supplied, the bare title + range are handed to the cache verbatim."""
        mock_service = MagicMock()
        with patch("ripper.ripperlib.sheet_data_cache.SheetDataCache.get_sheet_data") as mock_get:
            mock_get.return_value = ([], [])
            retrieve_sheet_data_for(mock_service, "book", "Q1!Actuals", "A1:B5")
            mock_get.assert_called_once_with(mock_service, "book", "Q1!Actuals", "A1:B5")

    def test_title_containing_bang_is_parsed_on_last_separator(self) -> None:
        """A sheet title that legitimately contains '!' must be split on the LAST '!'.

        Cell ranges never contain '!', so the final '!' always separates title from range.
        The title is then passed (unquoted) to the cache, which quotes at the API boundary.
        """
        mock_service = MagicMock()
        with patch("ripper.ripperlib.sheet_data_cache.SheetDataCache.get_sheet_data") as mock_get:
            mock_get.return_value = ([], [])
            retrieve_sheet_data(mock_service, "book", "Q1!Actuals!A1:B5")

            mock_get.assert_called_once_with(mock_service, "book", "Q1!Actuals", "A1:B5")

    def test_whole_sheet_bare_title_is_quoted_for_api(self) -> None:
        """A bare sheet title (no cell range, e.g. a whole-sheet load) must be quoted for the API."""
        mock_service = MagicMock()
        with patch("ripper.ripperlib.sheets_backend.fetch_data_from_spreadsheet") as mock_fetch:
            mock_fetch.return_value = []
            retrieve_sheet_data(mock_service, "book", "Monthly Budget")

            mock_fetch.assert_called_once_with(mock_service, "book", "'Monthly Budget'")

    def test_fallback_quotes_special_title(self) -> None:
        """If the cache path raises, the direct fallback must still quote the title for the API."""
        mock_service = MagicMock()
        with patch("ripper.ripperlib.sheet_data_cache.SheetDataCache.get_sheet_data") as mock_get:
            mock_get.side_effect = RuntimeError("boom")
            with patch("ripper.ripperlib.sheets_backend.fetch_data_from_spreadsheet") as mock_fetch:
                mock_fetch.return_value = []
                retrieve_sheet_data(mock_service, "book", "Monthly Budget!A1:E10")

                mock_fetch.assert_called_once_with(mock_service, "book", "'Monthly Budget'!A1:E10")

    def test_already_quoted_combined_title_is_not_double_quoted(self) -> None:
        """A combined string whose title is ALREADY quoted must not be quoted again (#75 review).

        Valid A1 may quote the title, e.g. "'Monthly Budget'!A1:B2". The wrapper must dequote it
        so the cache is keyed under the bare title and the API boundary quotes it exactly once —
        not "'''Monthly Budget'''!A1:B2".
        """
        mock_service = MagicMock()
        with patch("ripper.ripperlib.sheet_data_cache.SheetDataCache.get_sheet_data") as mock_get:
            mock_get.return_value = ([], [])
            retrieve_sheet_data(mock_service, "book", "'Monthly Budget'!A1:B2")

            mock_get.assert_called_once_with(mock_service, "book", "Monthly Budget", "A1:B2")

    def test_already_quoted_combined_title_fallback_quotes_once(self) -> None:
        """On the cache-miss fallback, an already-quoted combined title resolves to a single quoting."""
        mock_service = MagicMock()
        with patch("ripper.ripperlib.sheet_data_cache.SheetDataCache.get_sheet_data") as mock_get:
            mock_get.side_effect = RuntimeError("boom")
            with patch("ripper.ripperlib.sheets_backend.fetch_data_from_spreadsheet") as mock_fetch:
                mock_fetch.return_value = []
                retrieve_sheet_data(mock_service, "book", "'Monthly Budget'!A1:B2")

                mock_fetch.assert_called_once_with(mock_service, "book", "'Monthly Budget'!A1:B2")


class TestThumbnail(unittest.TestCase):
    """Thumbnail download hardening and non-empty-only caching (#40)."""

    @patch("ripper.ripperlib.sheets_backend.urllib.request.urlopen")
    def test_fetch_thumbnail_refuses_non_https(self, mock_urlopen):
        """Non-HTTPS URLs are refused without any network call."""
        for url in ("http://example.com/t.png", "file:///etc/passwd", "ftp://x/y"):
            self.assertEqual(fetch_thumbnail(url), b"")
        mock_urlopen.assert_not_called()

    @patch("ripper.ripperlib.sheets_backend.urllib.request.urlopen")
    def test_fetch_thumbnail_success_uses_timeout(self, mock_urlopen):
        """A successful HTTPS download returns the bytes and passes a timeout."""
        mock_urlopen.return_value.__enter__.return_value.read.return_value = b"image-bytes"
        result = fetch_thumbnail("https://example.com/t.png")
        self.assertEqual(result, b"image-bytes")
        _, kwargs = mock_urlopen.call_args
        self.assertIn("timeout", kwargs)
        self.assertGreater(kwargs["timeout"], 0)

    @patch("ripper.ripperlib.sheets_backend.urllib.request.urlopen")
    def test_fetch_thumbnail_timeout_returns_empty(self, mock_urlopen):
        """A read/connect timeout is caught and returns empty bytes, never raised."""
        mock_urlopen.side_effect = TimeoutError("timed out")
        self.assertEqual(fetch_thumbnail("https://example.com/t.png"), b"")

    @patch("ripper.ripperlib.sheets_backend.urllib.request.urlopen")
    def test_fetch_thumbnail_urlerror_returns_empty(self, mock_urlopen):
        """A URL/HTTP error is caught and returns empty bytes."""
        from urllib.error import URLError

        mock_urlopen.side_effect = URLError("boom")
        self.assertEqual(fetch_thumbnail("https://example.com/t.png"), b"")

    @patch("ripper.ripperlib.sheets_backend.Db")
    def test_retrieve_thumbnail_cache_hit(self, mock_db):
        """A cached thumbnail is returned from the DB without downloading."""
        mock_db.get_spreadsheet_thumbnail.return_value = b"cached"
        with patch("ripper.ripperlib.sheets_backend.fetch_thumbnail") as mock_fetch:
            data, source = retrieve_thumbnail("book", "https://example.com/t.png")
        self.assertEqual((data, source), (b"cached", LoadSource.DATABASE))
        mock_fetch.assert_not_called()
        mock_db.store_spreadsheet_thumbnail.assert_not_called()

    @patch("ripper.ripperlib.sheets_backend.Db")
    def test_retrieve_thumbnail_miss_stores_nonempty(self, mock_db):
        """On a cache miss, a non-empty download is cached and returned."""
        mock_db.get_spreadsheet_thumbnail.return_value = None
        with patch("ripper.ripperlib.sheets_backend.fetch_thumbnail", return_value=b"img") as mock_fetch:
            data, source = retrieve_thumbnail("book", "https://example.com/t.png")
        self.assertEqual((data, source), (b"img", LoadSource.API))
        mock_fetch.assert_called_once_with("https://example.com/t.png")
        mock_db.store_spreadsheet_thumbnail.assert_called_once_with("book", b"img")

    @patch("ripper.ripperlib.sheets_backend.Db")
    def test_retrieve_thumbnail_failure_is_not_cached(self, mock_db):
        """A failed (empty) download must NOT be stored, so it isn't permanently cached (#40)."""
        mock_db.get_spreadsheet_thumbnail.return_value = None
        with patch("ripper.ripperlib.sheets_backend.fetch_thumbnail", return_value=b""):
            data, source = retrieve_thumbnail("book", "https://example.com/t.png")
        self.assertEqual((data, source), (b"", LoadSource.API))
        mock_db.store_spreadsheet_thumbnail.assert_not_called()


def _column_letters_to_number(letters: str) -> int:
    """Convert A1 column letters ('A' -> 1, 'Z' -> 26, 'AD' -> 30) to a 1-based number."""
    number = 0
    for char in letters.upper():
        number = number * 26 + (ord(char) - ord("A") + 1)
    return number


def _requested_column_bound(range_name: str) -> float:
    """Highest column index the requested A1 string can return; ``inf`` when unbounded.

    A whole-sheet reference (no cell-range part), or a range whose end omits the column, is
    unbounded and therefore cannot truncate. Anything else is bounded by its end column.
    """
    _, range_part = split_sheet_and_range(range_name)
    if not range_part:
        return float("inf")
    end_cell = range_part.split(":")[-1].strip()
    letters = "".join(char for char in end_cell if char.isalpha())
    if not letters:
        return float("inf")
    return _column_letters_to_number(letters)


class TestTillerWideSheets(unittest.TestCase):
    """Tiller getters must not truncate sheets wider than column Z (#104)."""

    GETTERS = (
        (get_tiller_transactions, "Transactions"),
        (get_tiller_categories, "Categories"),
        (get_tiller_budget, "Budget"),
    )

    @staticmethod
    def _mock_service(values):
        """Build a mocked Sheets service that records every requested A1 range.

        No live API call is made; the mock mirrors ``service.spreadsheets().values().get(...)``.
        """
        requested: list[str] = []

        def _get(**kwargs):
            requested.append(kwargs["range"])
            request = MagicMock()
            request.execute.return_value = {"values": values}
            return request

        service = MagicMock()
        service.spreadsheets.return_value.values.return_value.get.side_effect = _get
        return service, requested

    @staticmethod
    def _grid(column_count, row_count=3):
        """Build a header row plus data rows for a sheet ``column_count`` columns wide."""
        headers = [f"col_{i}" for i in range(column_count)]
        rows = [[f"r{r}c{c}" for c in range(column_count)] for r in range(1, row_count)]
        return [headers, *rows]

    def _run(self, getter, sheet_name, values):
        """Invoke a Tiller getter against the mocked service, isolating the cache from the real DB."""
        service, requested = self._mock_service(values)
        # Keep the test hermetic if the call ever routes through SheetDataCache (which reads
        # stored grid properties); no real database or API is touched.
        mock_db = MagicMock(spec=RipperDb)
        mock_db.get_sheet_properties_of_spreadsheet.return_value = []
        with patch("ripper.ripperlib.sheet_data_cache.Db", mock_db):
            result = getter(service, "book", sheet_name)
        self.assertTrue(requested, "expected at least one API read")
        return result, requested

    def test_wide_sheet_columns_are_not_truncated(self) -> None:
        """A 30-column Tiller sheet keeps every column: the request is never bounded at Z."""
        column_count = 30
        values = self._grid(column_count)
        for getter, sheet_name in self.GETTERS:
            with self.subTest(getter=getter.__name__):
                rows, requested = self._run(getter, sheet_name, values)

                for range_name in requested:
                    self.assertGreaterEqual(
                        _requested_column_bound(range_name),
                        column_count,
                        f"requested range {range_name!r} truncates a {column_count}-column sheet",
                    )

                self.assertEqual(len(rows), len(values) - 1)
                expected_headers = [f"col_{i}" for i in range(column_count)]
                for row in rows:
                    self.assertEqual(list(row.keys()), expected_headers)
                self.assertEqual(rows[0]["col_29"], "r1c29")

    def test_narrow_sheet_still_works(self) -> None:
        """A <=26-column sheet is unaffected (no regression)."""
        values = [
            ["Date", "Description", "Amount"],
            ["2026-01-01", "Coffee", "-4.50"],
            ["2026-01-02", "Salary", "1000.00"],
        ]
        for getter, sheet_name in self.GETTERS:
            with self.subTest(getter=getter.__name__):
                rows, _ = self._run(getter, sheet_name, values)
                self.assertEqual(
                    rows,
                    [
                        {"date": "2026-01-01", "description": "Coffee", "amount": "-4.50"},
                        {"date": "2026-01-02", "description": "Salary", "amount": "1000.00"},
                    ],
                )
