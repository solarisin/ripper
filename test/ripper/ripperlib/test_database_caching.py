"""Tests for database caching functionality."""

import os
import sqlite3
import tempfile
import unittest
from typing import Any

from ripper.ripperlib.database import RipperDb
from ripper.ripperlib.defs import SpreadsheetProperties
from ripper.ripperlib.range_manager import CellRange


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
        # The range id must stay STABLE across re-caches of the same extent (ON CONFLICT upsert)
        self.assertEqual(range_id1, range_id2)

        # Verify new data is stored
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT cell_value FROM sheet_data_cells WHERE range_id = ? ORDER BY row_num, col_num", (range_id2,))
        values = [row[0] for row in c.fetchall()]
        self.assertEqual(values, ["New1", "New2", "New3", "New4"])
        conn.close()

    def test_recaching_same_extent_keeps_stable_range_id(self) -> None:
        """Re-caching the SAME range extent twice must keep the SAME range id (#51 core regression)."""
        start_row, start_col = 1, 1
        end_row, end_col = 2, 2

        range_id_first = self.db.store_sheet_data_range(
            self.test_spreadsheet_id,
            self.test_sheet_name,
            start_row,
            start_col,
            end_row,
            end_col,
            [["A1", "B1"], ["A2", "B2"]],
        )
        self.assertIsNotNone(range_id_first)

        # Confirm exactly one range row exists and capture its id from the table itself.
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """SELECT id FROM sheet_data_ranges
               WHERE spreadsheet_id = ? AND sheet_name = ?
                 AND start_row = ? AND start_col = ? AND end_row = ? AND end_col = ?""",
            (self.test_spreadsheet_id, self.test_sheet_name, start_row, start_col, end_row, end_col),
        )
        rows = c.fetchall()
        self.assertEqual(len(rows), 1)
        id_before = rows[0][0]
        conn.close()

        # Re-cache the identical extent (fresh values).
        range_id_second = self.db.store_sheet_data_range(
            self.test_spreadsheet_id,
            self.test_sheet_name,
            start_row,
            start_col,
            end_row,
            end_col,
            [["X1", "Y1"], ["X2", "Y2"]],
        )

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """SELECT id FROM sheet_data_ranges
               WHERE spreadsheet_id = ? AND sheet_name = ?
                 AND start_row = ? AND start_col = ? AND end_row = ? AND end_col = ?""",
            (self.test_spreadsheet_id, self.test_sheet_name, start_row, start_col, end_row, end_col),
        )
        rows = c.fetchall()
        self.assertEqual(len(rows), 1, "re-caching must not create a second range row")
        id_after = rows[0][0]
        conn.close()

        self.assertEqual(range_id_first, range_id_second)
        self.assertEqual(id_before, id_after)
        self.assertEqual(id_before, range_id_second)

    def test_recaching_replaces_stale_cells(self) -> None:
        """Re-caching a same-extent range with new values must leave NO stale cells behind (#51)."""
        start_row, start_col = 1, 1
        end_row, end_col = 2, 2

        # Seed the extent with value X everywhere.
        self.db.store_sheet_data_range(
            self.test_spreadsheet_id,
            self.test_sheet_name,
            start_row,
            start_col,
            end_row,
            end_col,
            [["X", "X"], ["X", "X"]],
        )

        # Re-store the identical extent with value Y everywhere.
        range_id = self.db.store_sheet_data_range(
            self.test_spreadsheet_id,
            self.test_sheet_name,
            start_row,
            start_col,
            end_row,
            end_col,
            [["Y", "Y"], ["Y", "Y"]],
        )

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        # No X cell may survive anywhere in the table.
        c.execute("SELECT COUNT(*) FROM sheet_data_cells WHERE cell_value = 'X'")
        self.assertEqual(c.fetchone()[0], 0, "stale cells from the previous cache survived")
        # The stable range must hold exactly the four Y cells.
        c.execute("SELECT cell_value FROM sheet_data_cells WHERE range_id = ?", (range_id,))
        values = [row[0] for row in c.fetchall()]
        self.assertEqual(len(values), 4)
        self.assertTrue(all(v == "Y" for v in values))
        conn.close()

    def test_store_retrieve_round_trip_multi_row(self) -> None:
        """A normal store + retrieve round-trip returns correct data for a 3x3 range (executemany path)."""
        start_row, start_col = 1, 1
        end_row, end_col = 3, 3
        cell_data = [
            ["A1", "B1", "C1"],
            ["A2", "B2", "C2"],
            ["A3", "B3", "C3"],
        ]

        range_id = self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, start_row, start_col, end_row, end_col, cell_data
        )
        self.assertIsNotNone(range_id)

        cached_data = self.db.get_sheet_data_from_cache(
            self.test_spreadsheet_id, self.test_sheet_name, start_row, start_col, end_row, end_col
        )
        self.assertEqual(cached_data, cell_data)

        # Verify all 9 cells landed at the correct coordinates.
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT row_num, col_num, cell_value FROM sheet_data_cells WHERE range_id = ? ORDER BY row_num, col_num",
            (range_id,),
        )
        cells = c.fetchall()
        self.assertEqual(len(cells), 9)
        expected = [(r, col, cell_data[r - 1][col - 1]) for r in range(1, 4) for col in range(1, 4)]
        self.assertEqual(cells, expected)
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
            self.test_spreadsheet_id,
            self.test_sheet_name,
            1,
            1,
            3,
            3,  # Extends to row 3, col 3
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

    def _extent(self, spreadsheet_id: str, sheet_name: str) -> set[tuple[int, int, int, int]]:
        """Return the (start_row, start_col, end_row, end_col) tuples currently cached for a sheet."""
        return {
            (r["start_row"], r["start_col"], r["end_row"], r["end_col"])
            for r in self.db.get_cached_ranges(spreadsheet_id, sheet_name)
        }

    def test_invalidate_sheet_data_range_leaves_non_overlapping_sibling(self) -> None:
        """Regression (#80): scoped invalidation must not evict a sibling source's disjoint cache.

        Two sources share Sheet1 with non-overlapping extents A1:E10 and G1:K10. Invalidating the
        first source's range must delete only its cached rows, leaving the second source's cache
        intact so a later load is still served from the DB rather than re-fetched from the API.
        """
        # Source 1: A1:E10 -> rows 1-10, cols 1-5
        self.db.store_sheet_data_range(self.test_spreadsheet_id, "Sheet1", 1, 1, 10, 5, [["x"] * 5 for _ in range(10)])
        # Source 2: G1:K10 -> rows 1-10, cols 7-11
        self.db.store_sheet_data_range(self.test_spreadsheet_id, "Sheet1", 1, 7, 10, 11, [["y"] * 5 for _ in range(10)])

        success = self.db.invalidate_sheet_data_range(self.test_spreadsheet_id, "Sheet1", CellRange(1, 1, 10, 5))
        self.assertTrue(success)

        extents = self._extent(self.test_spreadsheet_id, "Sheet1")
        self.assertNotIn((1, 1, 10, 5), extents)  # refreshed source's range removed
        self.assertIn((1, 7, 10, 11), extents)  # sibling's range survives

        # Sibling is still fully served from the DB cache.
        sibling_data = self.db.get_sheet_data_from_cache(self.test_spreadsheet_id, "Sheet1", 1, 7, 10, 11)
        self.assertIsNotNone(sibling_data)

    def test_invalidate_sheet_data_range_removes_overlapping_range(self) -> None:
        """Scoped invalidation removes the cached range for the refreshed source itself."""
        self.db.store_sheet_data_range(self.test_spreadsheet_id, "Sheet1", 1, 1, 10, 5, [["x"] * 5 for _ in range(10)])

        self.db.invalidate_sheet_data_range(self.test_spreadsheet_id, "Sheet1", CellRange(1, 1, 10, 5))

        self.assertEqual(self._extent(self.test_spreadsheet_id, "Sheet1"), set())
        self.assertIsNone(self.db.get_sheet_data_from_cache(self.test_spreadsheet_id, "Sheet1", 1, 1, 10, 5))

    def test_invalidate_sheet_data_range_removes_overlapping_but_not_identical(self) -> None:
        """A cached range that merely intersects the invalidated extent is evicted (not just exact matches)."""
        # Cached A1:E10; invalidate C5:H20 -> overlaps at C5:E10 but is not identical.
        self.db.store_sheet_data_range(self.test_spreadsheet_id, "Sheet1", 1, 1, 10, 5, [["x"] * 5 for _ in range(10)])
        # A truly disjoint cached range in the same sheet must be untouched.
        self.db.store_sheet_data_range(self.test_spreadsheet_id, "Sheet1", 30, 1, 31, 2, [["z", "z"], ["z", "z"]])

        self.db.invalidate_sheet_data_range(self.test_spreadsheet_id, "Sheet1", CellRange(5, 3, 20, 8))

        extents = self._extent(self.test_spreadsheet_id, "Sheet1")
        self.assertNotIn((1, 1, 10, 5), extents)  # overlapping range evicted
        self.assertIn((30, 1, 31, 2), extents)  # disjoint range preserved

    def test_invalidate_sheet_data_range_database_closed(self) -> None:
        """Scoped invalidation returns False when the database is closed."""
        self.db.close()
        success = self.db.invalidate_sheet_data_range(self.test_spreadsheet_id, "Sheet1", CellRange(1, 1, 10, 5))
        self.assertFalse(success)

    def test_sheet_wide_invalidation_still_nukes_everything(self) -> None:
        """The sheet-wide method (used by the modifiedTime path) still clears every range on the tab."""
        self.db.store_sheet_data_range(self.test_spreadsheet_id, "Sheet1", 1, 1, 10, 5, [["x"] * 5 for _ in range(10)])
        self.db.store_sheet_data_range(self.test_spreadsheet_id, "Sheet1", 1, 7, 10, 11, [["y"] * 5 for _ in range(10)])

        self.assertTrue(self.db.invalidate_sheet_data_cache(self.test_spreadsheet_id, "Sheet1"))

        self.assertEqual(self._extent(self.test_spreadsheet_id, "Sheet1"), set())

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

    def test_clean_orphaned_ranges_removes_ranges_without_cells(self) -> None:
        """Test that orphaned range records are removed using the actual range primary key."""
        valid_range_id = self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]]
        )
        self.assertIsNotNone(valid_range_id)

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            """INSERT INTO sheet_data_ranges
               (spreadsheet_id, sheet_name, start_row, start_col, end_row, end_col)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (self.test_spreadsheet_id, self.test_sheet_name, 10, 1, 10, 2),
        )
        orphaned_range_id = c.lastrowid
        conn.commit()
        conn.close()

        deleted_count = self.db.clean_orphaned_ranges(self.test_spreadsheet_id, self.test_sheet_name)

        self.assertEqual(deleted_count, 1)
        ranges = self.db.get_cached_ranges(self.test_spreadsheet_id, self.test_sheet_name)
        remaining_ids = {range_info["range_id"] for range_info in ranges}
        self.assertIn(valid_range_id, remaining_ids)
        self.assertNotIn(orphaned_range_id, remaining_ids)

    def test_validate_cached_range_data_uses_range_primary_key(self) -> None:
        """Test cache validation queries sheet_data_ranges.id, not a non-existent range_id column."""
        self.db.store_sheet_data_range(
            self.test_spreadsheet_id, self.test_sheet_name, 1, 1, 2, 2, [["A1", "B1"], ["A2", "B2"]]
        )

        self.assertTrue(self.db.validate_cached_range_data(self.test_spreadsheet_id, self.test_sheet_name))

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
