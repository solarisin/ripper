import os
import sqlite3
import tempfile
import unittest

from ripper.ripperlib.database import _db_impl


class TestDatabaseIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        self.db = _db_impl(self.db_path)
        self.db.open()

    def tearDown(self):
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_table_idempotent(self):
        self.db.close()
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in c.fetchall()}
        self.assertEqual(len(tables), 3)
        self.assertIn("sheets", tables)
        self.assertIn("grid_properties", tables)
        self.assertIn("spreadsheets", tables)
        conn.close()

    def test_store_and_get_thumbnail(self):
        sid = "sheet1"
        data = b"imgdata"
        mod = "2024-01-01"
        result = self.db.store_spreadsheet_thumbnail(sid, data, mod)
        self.assertTrue(result)
        # After storing thumbnail, verify the data and modified time in the spreadsheets table
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute("SELECT thumbnail, modifiedTime FROM spreadsheets WHERE spreadsheet_id = ?", (sid,))
            stored_data = c.fetchone()
        finally:
            conn.close()

        self.assertIsNotNone(stored_data)
        self.assertEqual(stored_data[0], data)
        self.assertEqual(stored_data[1], mod)

        new_data = b"newimg"
        new_mod = "2024-01-02"
        result2 = self.db.store_spreadsheet_thumbnail(sid, new_data, new_mod)
        self.assertTrue(result2)
        # After updating thumbnail, verify the new data and modified time in the spreadsheets table
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute("SELECT thumbnail, modifiedTime FROM spreadsheets WHERE spreadsheet_id = ?", (sid,))
            updated_data = c.fetchone()
        finally:
            conn.close()

        self.assertIsNotNone(updated_data)
        self.assertEqual(updated_data[0], new_data)
        self.assertEqual(updated_data[1], new_mod)

    def test_get_thumbnail_not_found(self):
        # Test retrieving thumbnail for a spreadsheet that exists but has no thumbnail data
        sid_no_thumbnail = "spreadsheet_no_thumb"
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute("INSERT OR IGNORE INTO spreadsheets (spreadsheet_id) VALUES (?)", (sid_no_thumbnail,))
            conn.commit()
        finally:
            conn.close()

        retrieved_data = self.db.get_spreadsheet_thumbnail(sid_no_thumbnail)
        self.assertIsNotNone(retrieved_data)
        self.assertIsNone(retrieved_data["thumbnail"])
        self.assertIsNone(retrieved_data["modifiedTime"])

    def test_store_sheet_metadata_updates_existing_sheets(self):
        # Test that store_sheet_metadata updates existing sheets instead of deleting them
        spreadsheet_id = "test_spreadsheet"
        modified_time = "2024-01-01T00:00:00Z"

        # Initial metadata with two sheets
        initial_metadata = {
            "sheets": [
                {
                    "sheetId": "sheet1",
                    "index": 0,
                    "title": "Sheet 1",
                    "sheetType": "GRID",
                    "gridProperties": {
                        "rowCount": 100,
                        "columnCount": 26
                    }
                },
                {
                    "sheetId": "sheet2",
                    "index": 1,
                    "title": "Sheet 2",
                    "sheetType": "GRID",
                    "gridProperties": {
                        "rowCount": 200,
                        "columnCount": 52
                    }
                }
            ]
        }

        # Store initial metadata
        result = self.db.store_sheet_metadata(spreadsheet_id, initial_metadata, modified_time)
        self.assertTrue(result)

        # Verify initial metadata was stored correctly
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            # Check sheets table
            query = "SELECT sheetId, title FROM sheets WHERE spreadsheet_id = ? ORDER BY \"index\""
            c.execute(query, (spreadsheet_id,))
            sheets = c.fetchall()
            self.assertEqual(len(sheets), 2)
            self.assertEqual(sheets[0][0], "sheet1")
            self.assertEqual(sheets[0][1], "Sheet 1")
            self.assertEqual(sheets[1][0], "sheet2")
            self.assertEqual(sheets[1][1], "Sheet 2")

            # Check grid_properties table
            c.execute("SELECT sheetId, rowCount, columnCount FROM grid_properties ORDER BY sheetId")
            grid_props = c.fetchall()
            self.assertEqual(len(grid_props), 2)
            self.assertEqual(grid_props[0][0], "sheet1")
            self.assertEqual(grid_props[0][1], 100)
            self.assertEqual(grid_props[0][2], 26)
            self.assertEqual(grid_props[1][0], "sheet2")
            self.assertEqual(grid_props[1][1], 200)
            self.assertEqual(grid_props[1][2], 52)
        finally:
            conn.close()

        # Updated metadata with modified values for sheet1 and a new sheet3
        updated_metadata = {
            "sheets": [
                {
                    "sheetId": "sheet1",
                    "index": 0,
                    "title": "Updated Sheet 1",  # Title changed
                    "sheetType": "GRID",
                    "gridProperties": {
                        "rowCount": 150,  # Row count changed
                        "columnCount": 26
                    }
                },
                {
                    "sheetId": "sheet3",  # New sheet
                    "index": 2,
                    "title": "Sheet 3",
                    "sheetType": "GRID",
                    "gridProperties": {
                        "rowCount": 300,
                        "columnCount": 78
                    }
                }
            ]
        }

        # Update with new metadata
        new_modified_time = "2024-01-02T00:00:00Z"
        result = self.db.store_sheet_metadata(spreadsheet_id, updated_metadata, new_modified_time)
        self.assertTrue(result)

        # Verify sheets were updated, not deleted
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            # Check sheets table - should have 3 sheets now (sheet1 updated, sheet2 unchanged, sheet3 new)
            c.execute("SELECT sheetId, title FROM sheets WHERE spreadsheet_id = ? ORDER BY sheetId", (spreadsheet_id,))
            sheets = c.fetchall()
            self.assertEqual(len(sheets), 3)

            # Check sheet1 was updated
            c.execute("SELECT title FROM sheets WHERE sheetId = ?", ("sheet1",))
            sheet1 = c.fetchone()
            self.assertEqual(sheet1[0], "Updated Sheet 1")

            # Check sheet2 still exists and is unchanged
            c.execute("SELECT title FROM sheets WHERE sheetId = ?", ("sheet2",))
            sheet2 = c.fetchone()
            self.assertEqual(sheet2[0], "Sheet 2")

            # Check sheet3 was added
            c.execute("SELECT title FROM sheets WHERE sheetId = ?", ("sheet3",))
            sheet3 = c.fetchone()
            self.assertEqual(sheet3[0], "Sheet 3")

            # Check grid_properties were updated
            c.execute("SELECT rowCount FROM grid_properties WHERE sheetId = ?", ("sheet1",))
            grid_prop1 = c.fetchone()
            self.assertEqual(grid_prop1[0], 150)  # Updated row count

            # Check grid_properties for sheet3 were added
            c.execute("SELECT rowCount, columnCount FROM grid_properties WHERE sheetId = ?", ("sheet3",))
            grid_prop3 = c.fetchone()
            self.assertEqual(grid_prop3[0], 300)
            self.assertEqual(grid_prop3[1], 78)
        finally:
            conn.close()
