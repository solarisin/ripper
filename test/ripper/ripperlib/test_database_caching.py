"""Tests for database caching functionality."""

import os
import sqlite3
import tempfile
import unittest
from typing import Any

from ripper.ripperlib.database import RipperDb
from ripper.ripperlib.defs import SpreadsheetProperties


class TestDatabaseCaching(unittest.TestCase):
    """Test database caching methods for sheet data."""

    def setUp(self) -> None:
        """Set up test database."""
        # Create a temporary database file
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        # Initialize database
        self.db = RipperDb(self.db_path)
        self.db.create_tables()

        # Test data
        self.test_spreadsheet_id = "test_spreadsheet_123"
        self.test_sheet_name = "Sheet1"
        self.test_spreadsheet_props = SpreadsheetProperties(
            {
                "id": self.test_spreadsheet_id,
                "name": "Test Spreadsheet",
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

    def tearDown(self) -> None:
        """Clean up test database."""
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_store_sheet_data_range_basic(self) -> None:
        """Test storing a basic sheet data range."""
        # Test data
        start_row, start_col = 1, 1
        end_row, end_col = 2, 2
        cell_data = [["A1", "B1"], ["A2", "B2"]]

        # Store range
        range_id = self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, start_row, start_col, end_row, end_col, cell_data
        )

        # Verify range was stored
        self.assertIsNotNone(range_id)
        self.assertIsInstance(range_id, int)

        # Verify range metadata in database
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """SELECT spreadsheet_id, sheet_name, start_row, start_col, end_row, end_col
            FROM sheet_data_ranges
            WHERE id = ?""",
            (range_id,),
        )
        row = c.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], self.test_spreadsheet_id)
        self.assertEqual(row[1], self.test_sheet_name)
        self.assertEqual(row[2], start_row)
        self.assertEqual(row[3], start_col)
        self.assertEqual(row[4], end_row)
        self.assertEqual(row[5], end_col)

        # Verify cell data in database
        c.execute(
            "SELECT row_num, col_num, cell_value FROM sheet_data_cells WHERE range_id = ? ORDER BY row_num, col_num",
            (range_id,),
        )
        cells = c.fetchall()
        self.assertEqual(len(cells), 4)  # 2x2 grid

        expected_cells = [(1, 1, "A1"), (1, 2, "B1"), (2, 1, "A2"), (2, 2, "B2")]
        for i, (row_num, col_num, cell_value) in enumerate(cells):
            self.assertEqual((row_num, col_num, cell_value), expected_cells[i])

        conn.close()

    def test_store_sheet_data_range_with_none_values(self) -> None:
        """Test storing sheet data with None values."""
        start_row, start_col = 1, 1
        end_row, end_col = 2, 2
        cell_data = [["A1", None], [None, "B2"]]

        range_id = self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, start_row, start_col, end_row, end_col, cell_data
        )

        self.assertIsNotNone(range_id)

        # Verify None values are stored correctly
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT row_num, col_num, cell_value FROM sheet_data_cells WHERE range_id = ? ORDER BY row_num, col_num",
            (range_id,),
        )
        cells = c.fetchall()

        expected_cells = [(1, 1, "A1"), (1, 2, None), (2, 1, None), (2, 2, "B2")]
        for i, (row_num, col_num, cell_value) in enumerate(cells):
            self.assertEqual((row_num, col_num, cell_value), expected_cells[i])

        conn.close()

    def test_store_sheet_data_range_replace_existing(self) -> None:
        """Test that storing a range with same coordinates replaces existing data."""
        start_row, start_col = 1, 1
        end_row, end_col = 2, 2

        # Store initial data
        initial_data = [["Old1", "Old2"], ["Old3", "Old4"]]
        range_id1 = self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, start_row, start_col, end_row, end_col, initial_data
        )

        # Store new data with same coordinates
        new_data = [["New1", "New2"], ["New3", "New4"]]
        range_id2 = self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, start_row, start_col, end_row, end_col, new_data
        )
        # Should get different range_id due to REPLACE creating new row
        self.assertNotEqual(range_id1, range_id2)

        # Verify new data is stored
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT cell_value FROM sheet_data_cells WHERE range_id = ? ORDER BY row_num, col_num", (range_id2,))
        values = [row[0] for row in c.fetchall()]
        self.assertEqual(values, ["New1", "New2", "New3", "New4"])
        conn.close()

    def test_store_sheet_data_range_empty_data(self) -> None:
        """Test storing empty cell data."""
        start_row, start_col = 1, 1
        end_row, end_col = 1, 1
        cell_data: list[list[Any]] = [[]]

        range_id = self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, start_row, start_col, end_row, end_col, cell_data
        )

        self.assertIsNotNone(range_id)

        # Verify no cell data was stored
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM sheet_data_cells WHERE range_id = ?", (range_id,))
        count = c.fetchone()[0]
        self.assertEqual(count, 0)
        conn.close()

    def test_store_sheet_data_range_database_closed(self) -> None:
        """Test storing range when database is closed."""
        self.db.close()

        range_id = self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]]
        )

        self.assertIsNone(range_id)

    def test_get_cached_ranges_empty(self) -> None:
        """Test getting cached ranges when none exist."""
        ranges = self.db.get_cached_ranges(self.test_spreadsheet_id, self.test_sheet_name)
        self.assertEqual(ranges, [])

    def test_get_cached_ranges_multiple(self) -> None:
        """Test getting multiple cached ranges."""
        # Store multiple ranges
        ranges_data = [
            (1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]]),
            (3, 3, 4, 4, [["C3", "D3"], ["C4", "D4"]]),
            (5, 1, 6, 2, [["A5", "B5"], ["A6", "B6"]]),
        ]

        stored_range_ids = []
        for start_row, start_col, end_row, end_col, cell_data in ranges_data:
            range_id = self.db.store_sheet_data_range(
                self.test_spreadsheet_id, self.test_sheet_name, start_row, start_col, end_row, end_col, cell_data
            )
            stored_range_ids.append(range_id)
        # Get cached ranges
        ranges = self.db.get_cached_ranges(self.test_spreadsheet_id, self.test_sheet_name)

        # Should have 3 ranges
        self.assertEqual(len(ranges), 3)

        # Verify all expected ranges are present (order may vary due to
        # timestamp precision)
        expected_coords = {(5, 1, 6, 2), (3, 3, 4, 4), (1, 1, 2, 2)}
        actual_coords = {(r["start_row"], r["start_col"], r["end_row"], r["end_col"]) for r in ranges}
        self.assertEqual(actual_coords, expected_coords)

        # Verify each range has required fields
        for range_info in ranges:
            self.assertIn("range_id", range_info)
            self.assertIn("cached_at", range_info)

    def test_get_cached_ranges_different_sheets(self) -> None:
        """Test that cached ranges are sheet-specific."""
        # Store range in first sheet
        self.db.store_sheet_data_range(self.test_spreadsheet_id, "Sheet1", 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]])

        # Store range in second sheet
        self.db.store_sheet_data_range(self.test_spreadsheet_id, "Sheet2", 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]])

        # Get ranges for each sheet
        ranges_sheet1 = self.db.get_cached_ranges(self.test_spreadsheet_id, "Sheet1")
        ranges_sheet2 = self.db.get_cached_ranges(self.test_spreadsheet_id, "Sheet2")

        self.assertEqual(len(ranges_sheet1), 1)
        self.assertEqual(len(ranges_sheet2), 1)

    def test_get_cached_ranges_database_closed(self) -> None:
        """Test getting cached ranges when database is closed."""
        self.db.close()

        ranges = self.db.get_cached_ranges(self.test_spreadsheet_id, self.test_sheet_name)
        self.assertEqual(ranges, [])

    def test_get_sheet_data_from_cache_exact_match(self) -> None:
        """Test getting data from cache with exact range match."""
        # Store test data
        start_row, start_col = 2, 3
        end_row, end_col = 4, 5
        cell_data = [["C2", "D2", "E2"], ["C3", "D3", "E3"], ["C4", "D4", "E4"]]

        self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, start_row, start_col, end_row, end_col, cell_data
        )

        # Retrieve exact same range
        cached_data = self.db.get_sheet_data_from_cache(
            self.test_spreadsheet_id, self.test_sheet_name, start_row, start_col, end_row, end_col
        )

        self.assertIsNotNone(cached_data)
        self.assertEqual(cached_data, cell_data)

    def test_get_sheet_data_from_cache_sub_range(self) -> None:
        """Test getting a sub-range from cached data."""
        # Store larger range
        self.db.store_sheet_data_range(
            self.test_spreadsheet_id,
            self.test_sheet_name,
            1,
            1,
            3,
            3,
            [["A1", "B1", "C1"], ["A2", "B2", "C2"], ["A3", "B3", "C3"]],
        )

        # Request sub-range (2x2 in middle)
        cached_data = self.db.get_sheet_data_from_cache(self.test_spreadsheet_id, self.test_sheet_name, 2, 2, 3, 3)

        self.assertIsNotNone(cached_data)
        expected = [["B2", "C2"], ["B3", "C3"]]
        self.assertEqual(cached_data, expected)

    def test_get_sheet_data_from_cache_partial_overlap(self) -> None:
        """Test getting data that is only partially cached."""
        # Store partial data
        self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]]
        )

        # Request larger range that extends beyond cached data
        cached_data = self.db.get_sheet_data_from_cache(
            self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 3, 3  # Extends to row 3, col 3
        )

        # Should return None because not fully cached
        self.assertIsNone(cached_data)

    def test_get_sheet_data_from_cache_multiple_ranges(self) -> None:
        """Test getting data that spans multiple cached ranges."""
        # Store two adjacent ranges
        self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]]
        )
        self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, 1, 3, 2, 4, [["C1", "D1"], ["C2", "D2"]]
        )

        # Request range that spans both cached ranges
        cached_data = self.db.get_sheet_data_from_cache(self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 2, 4)

        self.assertIsNotNone(cached_data)
        expected = [["A1", "B1", "C1", "D1"], ["A2", "B2", "C2", "D2"]]
        self.assertEqual(cached_data, expected)

    def test_get_sheet_data_from_cache_no_overlap(self) -> None:
        """Test getting data with no cached overlap."""
        # Store data in one area
        self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]]
        )

        # Request data in different area
        cached_data = self.db.get_sheet_data_from_cache(self.test_spreadsheet_id, self.test_sheet_name, 5, 5, 6, 6)

        self.assertIsNone(cached_data)

    def test_get_sheet_data_from_cache_database_closed(self) -> None:
        """Test getting data when database is closed."""
        self.db.close()

        cached_data = self.db.get_sheet_data_from_cache(self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 2, 2)

        self.assertIsNone(cached_data)

    def test_invalidate_sheet_data_cache_specific_sheet(self) -> None:
        """Test invalidating cache for a specific sheet."""
        # Store data in multiple sheets
        self.db.store_sheet_data_range(self.test_spreadsheet_id, "Sheet1", 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]])
        self.db.store_sheet_data_range(self.test_spreadsheet_id, "Sheet2", 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]])

        # Invalidate only Sheet1
        success = self.db.invalidate_sheet_data_cache(self.test_spreadsheet_id, "Sheet1")
        self.assertTrue(success)

        # Verify Sheet1 is cleared but Sheet2 remains
        ranges_sheet1 = self.db.get_cached_ranges(self.test_spreadsheet_id, "Sheet1")
        ranges_sheet2 = self.db.get_cached_ranges(self.test_spreadsheet_id, "Sheet2")

        self.assertEqual(len(ranges_sheet1), 0)
        self.assertEqual(len(ranges_sheet2), 1)

    def test_invalidate_sheet_data_cache_all_sheets(self) -> None:
        """Test invalidating cache for all sheets in a spreadsheet."""
        # Store data in multiple sheets
        self.db.store_sheet_data_range(self.test_spreadsheet_id, "Sheet1", 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]])
        self.db.store_sheet_data_range(self.test_spreadsheet_id, "Sheet2", 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]])

        # Invalidate all sheets (sheet_name=None)
        success = self.db.invalidate_sheet_data_cache(self.test_spreadsheet_id, None)
        self.assertTrue(success)

        # Verify both sheets are cleared
        ranges_sheet1 = self.db.get_cached_ranges(self.test_spreadsheet_id, "Sheet1")
        ranges_sheet2 = self.db.get_cached_ranges(self.test_spreadsheet_id, "Sheet2")

        self.assertEqual(len(ranges_sheet1), 0)
        self.assertEqual(len(ranges_sheet2), 0)

    def test_invalidate_sheet_data_cache_database_closed(self) -> None:
        """Test invalidating cache when database is closed."""
        self.db.close()

        success = self.db.invalidate_sheet_data_cache(self.test_spreadsheet_id, self.test_sheet_name)
        self.assertFalse(success)

    def test_foreign_key_constraints(self) -> None:
        """Test that foreign key constraints are enforced."""
        # Store range data
        range_id = self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]]
        )
        self.assertIsNotNone(range_id)

        # Delete spreadsheet (should cascade delete range and cell data)
        conn = sqlite3.connect(self.db_path)
        # Enable foreign keys for this test
        conn.execute("PRAGMA foreign_keys = ON")
        c = conn.cursor()
        c.execute("DELETE FROM spreadsheets WHERE spreadsheet_id = ?", (self.test_spreadsheet_id,))
        conn.commit()

        # Verify range data was deleted
        c.execute("SELECT COUNT(*) FROM sheet_data_ranges WHERE spreadsheet_id = ?", (self.test_spreadsheet_id,))
        range_count = c.fetchone()[0]
        self.assertEqual(range_count, 0)

        # Verify cell data was deleted
        c.execute("SELECT COUNT(*) FROM sheet_data_cells WHERE range_id = ?", (range_id,))
        cell_count = c.fetchone()[0]
        self.assertEqual(cell_count, 0)

        conn.close()

    def test_table_creation_includes_new_tables(self) -> None:
        """Test that create_tables creates the new caching tables."""
        # Check that new tables exist
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in c.fetchall()}

        # Verify all expected tables exist
        expected_tables = {"spreadsheets", "sheets", "grid_properties", "sheet_data_ranges", "sheet_data_cells"}
        self.assertTrue(expected_tables.issubset(tables))

        # Verify indices exist
        c.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indices = {row[0] for row in c.fetchall()}

        expected_indices = {"idx_sheet_data_ranges_lookup", "idx_sheet_data_cells_position"}
        # Note: SQLite may also create automatic indices, so we check subset
        self.assertTrue(expected_indices.issubset(indices))

        conn.close()


if __name__ == "__main__":
    unittest.main()
