"""Tests for the SheetDataCache service."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from beartype.typing import Any

from ripper.ripperlib.database import RipperDb
from ripper.ripperlib.defs import LoadSource, SpreadsheetProperties
from ripper.ripperlib.sheet_data_cache import SheetDataCache


class MockSheetsService:
    """Mock implementation of SheetsService protocol for testing."""

    def __init__(self) -> None:
        self._spreadsheets = MagicMock()
        self._values = MagicMock()

    def spreadsheets(self) -> Any:
        return self._spreadsheets

    def values(self) -> Any:
        return self._values

    def get(self, spreadsheetId: str) -> Any:
        return MagicMock()

    def batchUpdate(self, spreadsheetId: str, body: dict[str, Any]) -> Any:
        return MagicMock()


class TestSheetDataCache(unittest.TestCase):
    """Test the SheetDataCache service."""

    def setUp(self) -> None:
        """Set up test environment."""
        # Create temporary database
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        # Initialize database
        self.db = RipperDb(self.db_path)
        self.db.create_tables()

        # Test data
        self.test_spreadsheet_id = "test_spreadsheet_456"
        self.test_sheet_name = "TestSheet"
        self.test_spreadsheet_props = SpreadsheetProperties(
            {
                "id": self.test_spreadsheet_id,
                "name": "Test Spreadsheet for Cache",
                "modifiedTime": "2024-01-01T00:00:00Z",
                "createdTime": "2024-01-01T00:00:00Z",
                "webViewLink": "https://example.com",
                "owners": [],
                "size": 1000,
                "shared": False,
            }
        )

        # Store spreadsheet for foreign key constraint
        self.db.store_spreadsheet_properties(self.test_spreadsheet_id, self.test_spreadsheet_props)

        # Initialize cache service
        self.cache = SheetDataCache(self.db)

        # Mock sheets service
        self.mock_sheets_service = MockSheetsService()

    def tearDown(self) -> None:
        """Clean up test environment."""
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_get_sheet_data_exact_cache_hit(self) -> None:
        """Test getting data when exact range is cached."""
        # Store test data in cache
        range_a1 = "B2:D4"
        cell_data = [["B2", "C2", "D2"], ["B3", "C3", "D3"], ["B4", "C4", "D4"]]
        self.db.store_sheet_data_range(self.test_spreadsheet_id, self.test_sheet_name, 2, 2, 4, 4, cell_data)
        # Request exact same range
        result_data, load_source = self.cache.get_sheet_data(
            self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, range_a1
        )

        self.assertEqual(result_data, cell_data)
        self.assertEqual(load_source, LoadSource.DATABASE)

    def test_get_sheet_data_sub_range_cache_hit(self) -> None:
        """Test getting sub-range from cached data."""
        # Store larger range in cache
        cell_data = [
            ["A1", "B1", "C1", "D1"],
            ["A2", "B2", "C2", "D2"],
            ["A3", "B3", "C3", "D3"],
            ["A4", "B4", "C4", "D4"],
        ]
        self.db.store_sheet_data_range(self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 4, 4, cell_data)

        # Request sub-range
        sub_range = "B2:C3"
        result_data, load_source = self.cache.get_sheet_data(
            self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, sub_range
        )

        expected_data = [["B2", "C2"], ["B3", "C3"]]
        self.assertEqual(result_data, expected_data)
        self.assertEqual(load_source, LoadSource.DATABASE)

    def test_get_sheet_data_cache_miss(self) -> None:
        """Test getting data when not cached (API call required)."""
        api_data = [["E5", "F5"], ["E6", "F6"]]

        with patch("ripper.ripperlib.sheets_backend.fetch_data_from_spreadsheet") as mock_fetch:
            mock_fetch.return_value = api_data

            range_a1 = "E5:F6"
            result_data, load_source = self.cache.get_sheet_data(
                self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, range_a1
            )

            self.assertEqual(result_data, api_data)
            self.assertEqual(load_source, LoadSource.API)

            # Verify API was called with correct parameters
            mock_fetch.assert_called_once_with(
                self.mock_sheets_service,
                self.test_spreadsheet_id,
                f"{self.test_sheet_name}!{range_a1}",
            )

            # Verify data was cached
            cached_data = self.db.get_sheet_data_from_cache(self.test_spreadsheet_id, self.test_sheet_name, 5, 5, 6, 6)
            self.assertEqual(cached_data, api_data)

    def test_get_sheet_data_partial_overlap_combined(self) -> None:
        """Test getting data with partial cache overlap requiring API call and merge."""
        # Store partial data in cache (A1:B2)
        cached_data = [["A1", "B1"], ["A2", "B2"]]
        self.db.store_sheet_data_range(self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 2, 2, cached_data)

        # Mock to return appropriate data for each missing range
        def mock_fetch_side_effect(service: Any, spreadsheet_id: str, range_notation: str) -> list[list[str]]:
            if "A3:C3" in range_notation:
                return [["A3", "B3", "C3"]]
            elif "C1:C2" in range_notation:
                return [["C1"], ["C2"]]
            else:
                return []

        with patch("ripper.ripperlib.sheets_backend.fetch_data_from_spreadsheet") as mock_fetch:
            mock_fetch.side_effect = mock_fetch_side_effect

            # Request larger range that partially overlaps
            range_a1 = "A1:C3"
            result_data, load_source = self.cache.get_sheet_data(
                self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, range_a1
            )

            expected_data = [["A1", "B1", "C1"], ["A2", "B2", "C2"], ["A3", "B3", "C3"]]
            self.assertEqual(result_data, expected_data)
            # Fallback to API when overlap detected
            self.assertEqual(load_source, LoadSource.API)

            # Verify API was called twice for the two missing ranges
            self.assertEqual(mock_fetch.call_count, 2)

    def test_get_sheet_data_multiple_ranges_combined(self) -> None:
        """Test getting data that spans multiple cached ranges."""
        # Store two separate ranges
        self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]]
        )
        self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, 4, 4, 5, 5, [["D4", "E4"], ["D5", "E5"]]
        )

        # Mock to return appropriate data for each missing range
        def mock_fetch_side_effect(service: Any, spreadsheet_id: str, range_notation: str) -> list[list[str]]:
            if "A3:E3" in range_notation:
                return [["A3", "B3", "C3", "D3", "E3"]]
            elif "A4:C5" in range_notation:
                return [["A4", "B4", "C4"], ["A5", "B5", "C5"]]
            elif "C1:E2" in range_notation:
                return [["C1", "D1", "E1"], ["C2", "D2", "E2"]]
            else:
                return []

        with patch("ripper.ripperlib.sheets_backend.fetch_data_from_spreadsheet") as mock_fetch:
            mock_fetch.side_effect = mock_fetch_side_effect

            # Request range that spans both cached ranges plus gaps
            range_a1 = "A1:E5"
            result_data, load_source = self.cache.get_sheet_data(
                self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, range_a1
            )

            expected_data = [
                ["A1", "B1", "C1", "D1", "E1"],
                ["A2", "B2", "C2", "D2", "E2"],
                ["A3", "B3", "C3", "D3", "E3"],
                ["A4", "B4", "C4", "D4", "E4"],
                ["A5", "B5", "C5", "D5", "E5"],
            ]
            self.assertEqual(result_data, expected_data)
            # Falls back to API due to gaps
            self.assertEqual(load_source, LoadSource.API)

            # Verify API was called 3 times for the 3 missing ranges
            self.assertEqual(mock_fetch.call_count, 3)

    def test_get_sheet_data_invalid_range(self) -> None:
        """Test handling of invalid A1 notation falls back to API."""
        with patch("ripper.ripperlib.sheets_backend.fetch_data_from_spreadsheet") as mock_fetch:
            mock_fetch.return_value = []
            result_data, load_source = self.cache.get_sheet_data(
                self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, "INVALID"
            )

            # Should fallback to API call when parsing fails
            self.assertEqual(result_data, [])
            self.assertEqual(load_source, LoadSource.API)
            mock_fetch.assert_called_once()

    def test_get_sheet_data_empty_range(self) -> None:
        """Test handling of empty range."""
        with patch("ripper.ripperlib.sheets_backend.fetch_data_from_spreadsheet") as mock_fetch:
            mock_fetch.return_value = []
            range_a1 = "Z100:Z100"
            result_data, load_source = self.cache.get_sheet_data(
                self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, range_a1
            )

            self.assertEqual(result_data, [])
            self.assertEqual(load_source, LoadSource.API)

    def test_get_sheet_data_api_failure(self) -> None:
        """Test handling of API failure."""
        with patch("ripper.ripperlib.sheets_backend.fetch_data_from_spreadsheet") as mock_fetch:
            mock_fetch.side_effect = Exception("API Error")

            range_a1 = "A1:B2"

            with self.assertRaises(Exception):
                self.cache.get_sheet_data(
                    self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, range_a1
                )

    def test_get_sheet_data_caching_behavior(self) -> None:
        """Test that API results are properly cached."""
        api_data = [["X1", "Y1"], ["X2", "Y2"]]
        range_a1 = "X1:Y2"

        with patch("ripper.ripperlib.sheets_backend.fetch_data_from_spreadsheet") as mock_fetch:
            mock_fetch.return_value = api_data

            # First call should hit API
            result1, source1 = self.cache.get_sheet_data(
                self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, range_a1
            )

            self.assertEqual(result1, api_data)
            self.assertEqual(source1, LoadSource.API)
            self.assertEqual(mock_fetch.call_count, 1)

            # Second call should hit cache (mock should not be called again)
            result2, source2 = self.cache.get_sheet_data(
                self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, range_a1
            )

            self.assertEqual(result2, api_data)
            self.assertEqual(source2, LoadSource.DATABASE)
            # API should not be called again
            self.assertEqual(mock_fetch.call_count, 1)

    def test_get_sheet_data_different_sheets(self) -> None:
        """Test that caching is sheet-specific."""
        # Store data for Sheet1
        self.db.store_sheet_data_range(
            self.test_spreadsheet_id, "Sheet1", 1, 1, 2, 2, [["S1A1", "S1B1"], ["S1A2", "S1B2"]]
        )

        # Request same range from Sheet2 (should hit API)
        api_data = [["S2A1", "S2B1"], ["S2A2", "S2B2"]]

        with patch("ripper.ripperlib.sheets_backend.fetch_data_from_spreadsheet") as mock_fetch:
            mock_fetch.return_value = api_data

            range_a1 = "A1:B2"
            result_data, load_source = self.cache.get_sheet_data(
                self.mock_sheets_service, self.test_spreadsheet_id, "Sheet2", range_a1
            )
            self.assertEqual(result_data, api_data)
            self.assertEqual(load_source, LoadSource.API)

            # Verify API was called for Sheet2
            mock_fetch.assert_called_once_with(self.mock_sheets_service, self.test_spreadsheet_id, f"Sheet2!{range_a1}")

    def test_invalidate_cache(self) -> None:
        """Test cache invalidation."""
        # Store some data
        self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]]
        )

        # Verify data is cached
        cached_data = self.db.get_sheet_data_from_cache(self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 2, 2)
        self.assertIsNotNone(cached_data)

        # Invalidate cache
        self.cache.invalidate_cache(self.test_spreadsheet_id, self.test_sheet_name)

        # Verify data is no longer cached
        cached_data_after = self.db.get_sheet_data_from_cache(
            self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 2, 2
        )
        self.assertIsNone(cached_data_after)

    def test_invalidate_all_cache(self) -> None:
        """Test invalidating all cache for a spreadsheet."""
        # Store data in multiple sheets
        self.db.store_sheet_data_range(self.test_spreadsheet_id, "Sheet1", 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]])
        self.db.store_sheet_data_range(self.test_spreadsheet_id, "Sheet2", 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]])

        # Invalidate all
        self.cache.invalidate_cache(self.test_spreadsheet_id)

        # Verify all data is gone
        ranges1 = self.db.get_cached_ranges(self.test_spreadsheet_id, "Sheet1")
        ranges2 = self.db.get_cached_ranges(self.test_spreadsheet_id, "Sheet2")

        self.assertEqual(len(ranges1), 0)
        self.assertEqual(len(ranges2), 0)

    def test_edge_case_single_cell(self) -> None:
        """Test handling of single cell ranges."""
        # Store single cell
        self.db.store_sheet_data_range(self.test_spreadsheet_id, self.test_sheet_name, 5, 5, 5, 5, [["E5"]])
        # Request same cell
        result_data, load_source = self.cache.get_sheet_data(
            self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, "E5"
        )

        self.assertEqual(result_data, [["E5"]])
        self.assertEqual(load_source, LoadSource.DATABASE)

    @patch("ripper.ripperlib.sheet_data_cache.logger")
    def test_logging_behavior(self, mock_logger: MagicMock) -> None:
        """Test that appropriate log messages are generated."""
        # Store test data
        self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]]
        )

        # Test cache hit
        result_data, load_source = self.cache.get_sheet_data(
            self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, "A1:B2"
        )

        # Verify debug log was called for cache hit
        mock_logger.debug.assert_called()
        debug_calls = [call.args[0] for call in mock_logger.debug.call_args_list]
        cache_hit_logged = any("Request can be satisfied entirely from cache" in msg for msg in debug_calls)
        self.assertTrue(cache_hit_logged, "Expected cache hit log message not found")


if __name__ == "__main__":
    unittest.main()
