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
        self.cache = SheetDataCache(self.db)  # Mock sheets service
        self.mock_sheets_service = MockSheetsService()

    def _assert_single_source(self, range_sources: list[tuple[LoadSource, str]], expected_source: LoadSource) -> None:
        """Assert that range_sources contains only one source of the expected type."""
        self.assertEqual(len(range_sources), 1)
        self.assertEqual(range_sources[0][0], expected_source)

    def _assert_mixed_sources(
        self, range_sources: list[tuple[LoadSource, str]], expected_cache_count: int, expected_api_count: int
    ) -> None:
        """Assert that range_sources contains the expected mix of cache and API sources."""
        cache_count = sum(1 for source, _ in range_sources if source == LoadSource.DATABASE)
        api_count = sum(1 for source, _ in range_sources if source == LoadSource.API)
        self.assertEqual(cache_count, expected_cache_count)
        self.assertEqual(api_count, expected_api_count)

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
        result_data, range_sources = self.cache.get_sheet_data(
            self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, range_a1
        )

        self.assertEqual(result_data, cell_data)
        self._assert_single_source(range_sources, LoadSource.DATABASE)

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
        result_data, range_sources = self.cache.get_sheet_data(
            self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, sub_range
        )

        expected_data = [["B2", "C2"], ["B3", "C3"]]
        self.assertEqual(result_data, expected_data)
        self._assert_single_source(range_sources, LoadSource.DATABASE)

    def test_get_sheet_data_cache_miss(self) -> None:
        """Test getting data when not cached (API call required)."""
        api_data = [["E5", "F5"], ["E6", "F6"]]

        with patch("ripper.ripperlib.sheets_backend.fetch_data_from_spreadsheet") as mock_fetch:
            mock_fetch.return_value = api_data

            range_a1 = "E5:F6"
            result_data, range_sources = self.cache.get_sheet_data(
                self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, range_a1
            )

            self.assertEqual(result_data, api_data)
            self._assert_single_source(range_sources, LoadSource.API)

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
            mock_fetch.side_effect = mock_fetch_side_effect  # Request larger range that partially overlaps
            range_a1 = "A1:C3"
            result_data, range_sources = self.cache.get_sheet_data(
                self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, range_a1
            )

            expected_data = [["A1", "B1", "C1"], ["A2", "B2", "C2"], ["A3", "B3", "C3"]]
            self.assertEqual(result_data, expected_data)
            # Should have mixed sources: cache and API
            self._assert_mixed_sources(range_sources, 1, 2)  # 1 cached range, 2 API ranges

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
            result_data, range_sources = self.cache.get_sheet_data(
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
            # Should have mixed sources: 2 cached ranges, 3 API ranges
            self._assert_mixed_sources(range_sources, 2, 3)

            # Verify API was called 3 times for the 3 missing ranges
            self.assertEqual(mock_fetch.call_count, 3)

    def test_get_sheet_data_invalid_range(self) -> None:
        """Test handling of invalid A1 notation falls back to API."""
        with patch("ripper.ripperlib.sheets_backend.fetch_data_from_spreadsheet") as mock_fetch:
            mock_fetch.return_value = []
            result_data, range_sources = self.cache.get_sheet_data(
                self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, "INVALID"
            )

            # Should fallback to API call when parsing fails
            self.assertEqual(result_data, [])
            self._assert_single_source(range_sources, LoadSource.API)
            mock_fetch.assert_called_once()

    def test_get_sheet_data_empty_range(self) -> None:
        """Test handling of empty range."""
        with patch("ripper.ripperlib.sheets_backend.fetch_data_from_spreadsheet") as mock_fetch:
            mock_fetch.return_value = []
            range_a1 = "Z100:Z100"
            result_data, range_sources = self.cache.get_sheet_data(
                self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, range_a1
            )

            self.assertEqual(result_data, [])
            self._assert_single_source(range_sources, LoadSource.API)

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
            self._assert_single_source(source1, LoadSource.API)
            self.assertEqual(mock_fetch.call_count, 1)

            # Second call should hit cache (mock should not be called again)
            result2, source2 = self.cache.get_sheet_data(
                self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, range_a1
            )

            self.assertEqual(result2, api_data)
            self._assert_single_source(source2, LoadSource.DATABASE)
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
            result_data, range_sources = self.cache.get_sheet_data(
                self.mock_sheets_service, self.test_spreadsheet_id, "Sheet2", range_a1
            )
            self.assertEqual(result_data, api_data)
            self._assert_single_source(range_sources, LoadSource.API)

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
        result_data, range_sources = self.cache.get_sheet_data(
            self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, "E5"
        )

        self.assertEqual(result_data, [["E5"]])
        self._assert_single_source(range_sources, LoadSource.DATABASE)

    def test_coordinate_transformation_accuracy(self) -> None:
        """Test that coordinate transformations are accurate and catch systematic offset bugs.

        This test would have caught the -13 row and -1 column offset bug that was encountered.
        """
        # Test data with known coordinates that map to specific expected values
        test_cases = [
            # (range_str, expected_data, storage_start_row,
            #  storage_start_col, storage_end_row, storage_end_col, storage_data)
            # Basic A1 cell test
            ("A1", [["A1_VALUE"]], 1, 1, 1, 1, [["A1_VALUE"]]),
            # Row 1 range test (common edge case)
            ("A1:C1", [["A1", "B1", "C1"]], 1, 1, 1, 3, [["A1", "B1", "C1"]]),
            # Column A range test (common edge case)
            ("A1:A3", [["A1"], ["A2"], ["A3"]], 1, 1, 3, 1, [["A1"], ["A2"], ["A3"]]),
            # Mid-range coordinates (where offset bugs often manifest)
            (
                "B5:D7",
                [["B5", "C5", "D5"], ["B6", "C6", "D6"], ["B7", "C7", "D7"]],
                5,
                2,
                7,
                4,
                [["B5", "C5", "D5"], ["B6", "C6", "D6"], ["B7", "C7", "D7"]],
            ),
            # High coordinates that could trigger systematic offsets
            (
                "M14:O16",
                [["M14", "N14", "O14"], ["M15", "N15", "O15"], ["M16", "N16", "O16"]],
                14,
                13,
                16,
                15,
                [["M14", "N14", "O14"], ["M15", "N15", "O15"], ["M16", "N16", "O16"]],
            ),
            # Single cell at high coordinates
            ("Z100", [["Z100_VALUE"]], 100, 26, 100, 26, [["Z100_VALUE"]]),
        ]

        for i, (range_str, expected_data, start_row, start_col, end_row, end_col, storage_data) in enumerate(
            test_cases
        ):
            with self.subTest(case=i, range_str=range_str):
                # Store test data at specific coordinates
                self.db.store_sheet_data_range(
                    self.test_spreadsheet_id,
                    f"TestSheet_{i}",  # Use different sheet for each test to avoid conflicts
                    start_row,
                    start_col,
                    end_row,
                    end_col,
                    storage_data,
                )

                # Retrieve the data
                result_data, range_sources = self.cache.get_sheet_data(
                    self.mock_sheets_service, self.test_spreadsheet_id, f"TestSheet_{i}", range_str
                )

                # Verify the data matches exactly (no coordinate offset)
                self.assertEqual(
                    result_data,
                    expected_data,
                    f"Coordinate transformation failed for range {range_str}. "
                    f"Expected {expected_data}, got {result_data}",
                )

                # Verify it came from cache
                self._assert_single_source(range_sources, LoadSource.DATABASE)

    def test_coordinate_transformation_sub_ranges(self) -> None:
        """Test coordinate transformations when requesting sub-ranges of cached data.

        This test catches bugs in the coordinate mapping logic when extracting
        sub-ranges from larger cached ranges.
        """
        # Store a large range with known coordinate values
        large_range_data = [
            ["A10", "B10", "C10", "D10", "E10"],
            ["A11", "B11", "C11", "D11", "E11"],
            ["A12", "B12", "C12", "D12", "E12"],
            ["A13", "B13", "C13", "D13", "E13"],
            ["A14", "B14", "C14", "D14", "E14"],
        ]

        self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, 10, 1, 14, 5, large_range_data  # A10:E14
        )

        # Test various sub-range extractions
        sub_range_tests = [
            # (requested_range, expected_data)
            ("B11:C12", [["B11", "C11"], ["B12", "C12"]]),  # Interior sub-range
            ("A10:A10", [["A10"]]),  # Single cell from top-left
            ("E14:E14", [["E14"]]),  # Single cell from bottom-right
            ("A10:E10", [["A10", "B10", "C10", "D10", "E10"]]),  # Top row
            ("A14:E14", [["A14", "B14", "C14", "D14", "E14"]]),  # Bottom row
            ("A10:A14", [["A10"], ["A11"], ["A12"], ["A13"], ["A14"]]),  # Left column
            ("E10:E14", [["E10"], ["E11"], ["E12"], ["E13"], ["E14"]]),  # Right column
            ("C11:D13", [["C11", "D11"], ["C12", "D12"], ["C13", "D13"]]),  # Middle rectangle
        ]

        for requested_range, expected_data in sub_range_tests:
            with self.subTest(range=requested_range):
                result_data, range_sources = self.cache.get_sheet_data(
                    self.mock_sheets_service, self.test_spreadsheet_id, self.test_sheet_name, requested_range
                )

                self.assertEqual(
                    result_data,
                    expected_data,
                    f"Sub-range extraction failed for {requested_range}. "
                    f"Expected {expected_data}, got {result_data}",
                )

                # Should come from cache
                self._assert_single_source(range_sources, LoadSource.DATABASE)

    def test_coordinate_edge_cases_that_trigger_offset_bugs(self) -> None:
        """Test coordinate edge cases that commonly trigger systematic offset bugs."""

        # Edge cases that often reveal coordinate transformation issues
        edge_cases = [
            # High row numbers (where offset bugs often manifest)
            ("A50:B51", 50, 1, 51, 2, [["A50", "B50"], ["A51", "B51"]]),
            # High column numbers
            ("Y1:Z2", 1, 25, 2, 26, [["Y1", "Z1"], ["Y2", "Z2"]]),
            # Ranges starting from common "offset" boundaries
            ("A13:B14", 13, 1, 14, 2, [["A13", "B13"], ["A14", "B14"]]),  # 13 was part of the bug
            ("B1:C2", 1, 2, 2, 3, [["B1", "C1"], ["B2", "C2"]]),  # Column offset test
            # Single cells at problematic coordinates
            ("A13", 13, 1, 13, 1, [["A13_SINGLE"]]),
            ("B1", 1, 2, 1, 2, [["B1_SINGLE"]]),
        ]

        for i, (range_str, start_row, start_col, end_row, end_col, expected_data) in enumerate(edge_cases):
            with self.subTest(case=i, range_str=range_str):
                sheet_name = f"EdgeTest_{i}"

                # Store the data
                self.db.store_sheet_data_range(
                    self.test_spreadsheet_id, sheet_name, start_row, start_col, end_row, end_col, expected_data
                )

                # Retrieve and verify
                result_data, range_sources = self.cache.get_sheet_data(
                    self.mock_sheets_service, self.test_spreadsheet_id, sheet_name, range_str
                )

                self.assertEqual(
                    result_data,
                    expected_data,
                    f"Edge case failed for {range_str} at coordinates ({start_row},{start_col}). "
                    f"Expected {expected_data}, got {result_data}",
                )

                self._assert_single_source(range_sources, LoadSource.DATABASE)


if __name__ == "__main__":
    unittest.main()
