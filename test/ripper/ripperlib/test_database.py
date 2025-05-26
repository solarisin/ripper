import os
import sqlite3
import tempfile
import unittest
from typing import Any, Dict, cast

from ripper.ripperlib.database import Db


class TestDatabaseIntegration(unittest.TestCase):
    def setUp(self) -> None:
        # Create a temporary database file
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        # Use Db with the temporary path
        self.db = Db(self.db_path)
        # Ensure tables are created
        self.db.create_tables()

    def tearDown(self) -> None:
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_table_idempotent(self) -> None:
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

    def test_execute_query(self) -> None:
        """Test the execute_query method for successful and failed queries."""
        # Test successful query
        cursor = self.db.execute_query("SELECT name FROM sqlite_master WHERE type='table'")
        self.assertIsNotNone(cursor)
        tables = cursor.fetchall() if cursor else []
        self.assertGreater(len(tables), 0)

        # Test query with parameters
        test_id = "test_id"
        self.db.execute_query("INSERT INTO spreadsheets (spreadsheet_id) VALUES (?)", (test_id,))
        cursor = self.db.execute_query("SELECT spreadsheet_id FROM spreadsheets WHERE spreadsheet_id = ?", (test_id,))
        self.assertIsNotNone(cursor)
        result = cursor.fetchone() if cursor else None
        self.assertIsNotNone(result)
        self.assertEqual(result[0], test_id)

        # Test failed query (syntax error)
        cursor = self.db.execute_query("SELECT * FROM non_existent_table")
        self.assertIsNone(cursor)

    def test_get_sheet_metadata(self) -> None:
        """Test retrieving sheet metadata from the database."""
        # Setup: Store sheet metadata
        spreadsheet_id = "test_spreadsheet_metadata"
        modified_time = "2024-01-01T00:00:00Z"
        metadata: Dict[str, Any] = {
            "sheets": [
                {
                    "sheetId": "sheet1",
                    "index": 0,
                    "title": "Sheet 1",
                    "sheetType": "GRID",
                    "gridProperties": {"rowCount": 100, "columnCount": 26},
                }
            ]
        }
        self.db.store_sheet_metadata(spreadsheet_id, metadata, modified_time)

        # Test: Retrieve with matching modified time
        retrieved_metadata = self.db.get_sheet_metadata(spreadsheet_id, modified_time)
        self.assertIsNotNone(retrieved_metadata)
        self.assertIn("sheets", retrieved_metadata)
        sheets = cast(Dict[str, Any], retrieved_metadata)["sheets"]
        self.assertEqual(len(sheets), 1)
        sheet = sheets[0]
        self.assertEqual(sheet["sheetId"], "sheet1")
        self.assertEqual(sheet["title"], "Sheet 1")
        self.assertEqual(sheet["gridProperties"]["rowCount"], 100)

        # Test: Retrieve with non-matching modified time (should return None)
        different_time = "2024-01-02T00:00:00Z"
        retrieved_metadata = self.db.get_sheet_metadata(spreadsheet_id, different_time)
        self.assertIsNone(retrieved_metadata)

        # Test: Retrieve non-existent spreadsheet
        retrieved_metadata = self.db.get_sheet_metadata("non_existent_id", modified_time)
        self.assertIsNone(retrieved_metadata)

    def test_get_thumbnail_not_found(self) -> None:
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

    def test_store_and_get_thumbnail(self) -> None:
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
        # Use a new modified time, but expect the one stored during initial insert to persist
        new_mod = "2024-01-02"
        result2 = self.db.store_spreadsheet_thumbnail(sid, new_data, new_mod)
        self.assertTrue(result2)
        # After updating thumbnail, verify the new data and the original modified time
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute("SELECT thumbnail, modifiedTime FROM spreadsheets WHERE spreadsheet_id = ?", (sid,))
            updated_data = c.fetchone()
        finally:
            conn.close()

        self.assertIsNotNone(updated_data)
        self.assertEqual(updated_data[0], new_data)  # Thumbnail should be updated
        self.assertEqual(updated_data[1], mod)  # Modified time should remain the initial one

    def test_store_sheet_metadata_updates_existing_sheets(self) -> None:
        # Test that store_sheet_metadata updates existing sheets instead of deleting them
        spreadsheet_id = "test_spreadsheet"
        modified_time = "2024-01-01T00:00:00Z"

        # Initial metadata with two sheets
        initial_metadata: Dict[str, Any] = {
            "sheets": [
                {
                    "sheetId": "sheet1",
                    "index": 0,
                    "title": "Sheet 1",
                    "sheetType": "GRID",
                    "gridProperties": {"rowCount": 100, "columnCount": 26},
                },
                {
                    "sheetId": "sheet2",
                    "index": 1,
                    "title": "Sheet 2",
                    "sheetType": "GRID",
                    "gridProperties": {"rowCount": 200, "columnCount": 52},
                },
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
            query = 'SELECT sheetId, title FROM sheets WHERE spreadsheet_id = ? ORDER BY "index"'
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
        updated_metadata: Dict[str, Any] = {
            "sheets": [
                {
                    "sheetId": "sheet1",
                    "index": 0,
                    "title": "Updated Sheet 1",  # Title changed
                    "sheetType": "GRID",
                    "gridProperties": {"rowCount": 150, "columnCount": 26},  # Row count changed
                },
                {
                    "sheetId": "sheet3",  # New sheet
                    "index": 2,
                    "title": "Sheet 3",
                    "sheetType": "GRID",
                    "gridProperties": {"rowCount": 300, "columnCount": 78},
                },
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
            # Check sheets table - should have 2 sheets now (sheet1 updated, sheet3 new)
            c.execute("SELECT sheetId, title FROM sheets WHERE spreadsheet_id = ? ORDER BY sheetId", (spreadsheet_id,))
            sheets = c.fetchall()
            self.assertEqual(len(sheets), 2)

            # Check sheet1 was updated
            c.execute("SELECT title FROM sheets WHERE sheetId = ?", ("sheet1",))
            sheet1 = c.fetchone()
            self.assertEqual(sheet1[0], "Updated Sheet 1")

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

    def test_store_spreadsheet_info(self) -> None:
        """Test storing and updating spreadsheet information."""
        spreadsheet_id = "test_spreadsheet_info"

        # Test: Store initial info
        initial_info: Dict[str, Any] = {
            "name": "Test Spreadsheet",
            "modifiedTime": "2024-01-01T00:00:00Z",
            "webViewLink": "https://example.com/sheet1",
            "createdTime": "2023-12-01T00:00:00Z",
            "owners": '["owner1"]',
            "size": 1024,
            "shared": 1,
        }
        result = self.db.store_spreadsheet_info(spreadsheet_id, initial_info)
        self.assertTrue(result)

        # Verify stored info
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute("SELECT name, modifiedTime, size FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            stored_info = c.fetchone()
            self.assertIsNotNone(stored_info)
            self.assertEqual(stored_info[0], "Test Spreadsheet")
            self.assertEqual(stored_info[1], "2024-01-01T00:00:00Z")
            self.assertEqual(stored_info[2], 1024)
        finally:
            conn.close()

        # Test: Update partial info
        updated_info: Dict[str, Any] = {"name": "Updated Spreadsheet", "size": 2048}
        result = self.db.store_spreadsheet_info(spreadsheet_id, updated_info)
        self.assertTrue(result)

        # Verify updated info (only specified fields should change)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute("SELECT name, modifiedTime, size FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            updated_stored_info = c.fetchone()
            self.assertIsNotNone(updated_stored_info)
            self.assertEqual(updated_stored_info[0], "Updated Spreadsheet")  # Updated
            self.assertEqual(updated_stored_info[1], "2024-01-01T00:00:00Z")  # Unchanged
            self.assertEqual(updated_stored_info[2], 2048)  # Updated
        finally:
            conn.close()

    def test_store_spreadsheet_info_invalidation_on_modified_time_change(self) -> None:
        """Test that sheets, grid_properties, and thumbnail are invalidated when modifiedTime changes."""
        spreadsheet_id = "invalidate_test"
        initial_info: Dict[str, Any] = {
            "name": "Invalidate Test",
            "modifiedTime": "2024-01-01T00:00:00Z",
            "webViewLink": "https://example.com/sheet1",
            "createdTime": "2023-12-01T00:00:00Z",
            "owners": '["owner1"]',
            "size": 1024,
            "shared": 1,
        }
        # Store initial info
        result = self.db.store_spreadsheet_info(spreadsheet_id, initial_info)
        self.assertTrue(result)

        # Store sheet metadata
        metadata: Dict[str, Any] = {
            "sheets": [
                {
                    "sheetId": "sheet1",
                    "index": 0,
                    "title": "Sheet 1",
                    "sheetType": "GRID",
                    "gridProperties": {"rowCount": 100, "columnCount": 26},
                }
            ]
        }
        result = self.db.store_sheet_metadata(spreadsheet_id, metadata, initial_info["modifiedTime"])
        self.assertTrue(result)

        # Store a thumbnail
        thumbnail_data = b"fakeimagebytes"
        result = self.db.store_spreadsheet_thumbnail(spreadsheet_id, thumbnail_data, initial_info["modifiedTime"])
        self.assertTrue(result)

        # Confirm all are present
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            # Enable foreign key constraints
            c.execute("PRAGMA foreign_keys = ON")

            # Check spreadsheet exists
            c.execute("SELECT modifiedTime FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            self.assertEqual(c.fetchone()[0], initial_info["modifiedTime"])

            # Check sheet exists
            c.execute("SELECT COUNT(*) FROM sheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            self.assertEqual(c.fetchone()[0], 1)

            # Check grid properties exist
            c.execute("SELECT COUNT(*) FROM grid_properties")
            self.assertGreaterEqual(c.fetchone()[0], 1)

            # Check thumbnail exists
            c.execute("SELECT thumbnail FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            self.assertIsNotNone(c.fetchone()[0])
        finally:
            conn.close()

        # Update with new modifiedTime
        updated_info: Dict[str, Any] = {"name": "Invalidate Test Updated", "modifiedTime": "2024-02-01T00:00:00Z"}
        result = self.db.store_spreadsheet_info(spreadsheet_id, updated_info)
        self.assertTrue(result)

        # Confirm sheets and grid_properties are deleted, and thumbnail is NULL
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            # Enable foreign key constraints
            c.execute("PRAGMA foreign_keys = ON")

            # Check sheets are deleted
            c.execute("SELECT COUNT(*) FROM sheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            self.assertEqual(c.fetchone()[0], 0)

            # Check grid_properties are deleted
            c.execute("SELECT COUNT(*) FROM grid_properties")
            self.assertEqual(c.fetchone()[0], 0)

            # Check thumbnail is NULL
            c.execute("SELECT thumbnail FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            self.assertIsNone(c.fetchone()[0])
        finally:
            conn.close()

    def test_store_spreadsheet_info_with_thumbnail_link(self) -> None:
        """Test storing and retrieving spreadsheet info with thumbnailLink."""
        spreadsheet_id = "test_spreadsheet_thumbnail_link"

        # Test: Store initial info with thumbnailLink
        initial_info: Dict[str, Any] = {
            "name": "Test Spreadsheet",
            "modifiedTime": "2024-01-01T00:00:00Z",
            "thumbnailLink": "https://example.com/thumbnail.png",
        }
        result = self.db.store_spreadsheet_info(spreadsheet_id, initial_info)
        self.assertTrue(result)

        # Verify stored info
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute("SELECT name, thumbnailLink FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            stored_info = c.fetchone()
            self.assertIsNotNone(stored_info)
            self.assertEqual(stored_info[0], "Test Spreadsheet")
            self.assertEqual(stored_info[1], "https://example.com/thumbnail.png")
        finally:
            conn.close()

        # Test: Update thumbnailLink
        updated_info: Dict[str, Any] = {"thumbnailLink": "https://example.com/new_thumbnail.png"}
        result = self.db.store_spreadsheet_info(spreadsheet_id, updated_info)
        self.assertTrue(result)

        # Verify updated info
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute("SELECT name, thumbnailLink FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            updated_stored_info = c.fetchone()
            self.assertIsNotNone(updated_stored_info)
            self.assertEqual(updated_stored_info[0], "Test Spreadsheet")  # Unchanged
            self.assertEqual(updated_stored_info[1], "https://example.com/new_thumbnail.png")  # Updated
        finally:
            conn.close()


class TestDatabaseSingleton(unittest.TestCase):
    """Test cases for the Db singleton class."""

    def setUp(self) -> None:
        # Create two temporary database paths
        self.temp_db1 = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path1 = self.temp_db1.name
        self.temp_db1.close()

        self.temp_db2 = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path2 = self.temp_db2.name
        self.temp_db2.close()

        # Reset the Db singleton state
        Db._instance = None
        Db._current_path = None

    def tearDown(self) -> None:
        # Reset the Db singleton state
        if Db._instance is not None:
            Db._instance.close()
            Db._instance = None
            Db._current_path = None

        # Remove temporary database files
        try:
            if os.path.exists(self.db_path1):
                os.remove(self.db_path1)
        except PermissionError:
            pass  # Ignore permission errors during cleanup

        try:
            if os.path.exists(self.db_path2):
                os.remove(self.db_path2)
        except PermissionError:
            pass  # Ignore permission errors during cleanup

    def test_singleton_instance(self) -> None:
        """Test that Db maintains a single instance."""
        db1 = Db(self.db_path1)
        db2 = Db(self.db_path1)
        self.assertIs(db1, db2)

    def test_path_switching(self) -> None:
        """Test that the database path can be switched."""
        # Create first database and store some data
        db1 = Db(self.db_path1)

        # Verify tables are created in first database
        tables1 = db1.execute_query("SELECT name FROM sqlite_master WHERE type='table'")
        table_names1 = {row[0] for row in tables1.fetchall()} if tables1 else set()
        self.assertEqual(len(table_names1), 3)
        self.assertIn("sheets", table_names1)
        self.assertIn("grid_properties", table_names1)
        self.assertIn("spreadsheets", table_names1)

        # Store data in first database
        db1.store_spreadsheet_info("test_id1", {"name": "Test1", "modifiedTime": "2024-01-01"})

        # Create second database with different path
        db2 = Db(self.db_path2)

        # Verify tables are created in second database
        tables2 = db2.execute_query("SELECT name FROM sqlite_master WHERE type='table'")
        table_names2 = {row[0] for row in tables2.fetchall()} if tables2 else set()
        self.assertEqual(len(table_names2), 3)
        self.assertIn("sheets", table_names2)
        self.assertIn("grid_properties", table_names2)
        self.assertIn("spreadsheets", table_names2)

        # Store data in second database
        db2.store_spreadsheet_info("test_id2", {"name": "Test2", "modifiedTime": "2024-01-02"})

        # Switch back to first database to verify its data
        db1 = Db(self.db_path1)
        db1_data = db1.execute_query("SELECT name FROM spreadsheets WHERE spreadsheet_id = ?", ("test_id1",))
        result1 = db1_data.fetchone() if db1_data else None
        self.assertIsNotNone(result1)
        self.assertEqual(result1[0], "Test1")

        # Switch back to second database to verify its data
        db2 = Db(self.db_path2)
        db2_data = db2.execute_query("SELECT name FROM spreadsheets WHERE spreadsheet_id = ?", ("test_id2",))
        result2 = db2_data.fetchone() if db2_data else None
        self.assertIsNotNone(result2)
        self.assertEqual(result2[0], "Test2")

        # Verify data doesn't leak between databases
        db1 = Db(self.db_path1)
        db1_data = db1.execute_query("SELECT name FROM spreadsheets WHERE spreadsheet_id = ?", ("test_id2",))
        result1 = db1_data.fetchone() if db1_data else None
        self.assertIsNone(result1)

        db2 = Db(self.db_path2)
        db2_data = db2.execute_query("SELECT name FROM spreadsheets WHERE spreadsheet_id = ?", ("test_id1",))
        result2 = db2_data.fetchone() if db2_data else None
        self.assertIsNone(result2)

    def test_connection_switching(self) -> None:
        """Test that database connections are properly managed when switching paths."""
        # Create first database
        db1 = Db(self.db_path1)

        # Store the first connection
        conn1 = db1._conn

        # Switch to second database
        db2 = Db(self.db_path2)

        # Verify the connection has changed
        self.assertIsNot(db1._conn, conn1)
        self.assertIs(db1._conn, db2._conn)  # Since they're the same instance

        # Verify both databases are usable
        db1.store_spreadsheet_info("test_id1", {"name": "Test1", "modifiedTime": "2024-01-01"})
        db2.store_spreadsheet_info("test_id2", {"name": "Test2", "modifiedTime": "2024-01-02"})

        # Verify data was stored in the correct databases
        db1_data = db1.execute_query("SELECT name FROM spreadsheets WHERE spreadsheet_id = ?", ("test_id1",))
        result1 = db1_data.fetchone() if db1_data else None
        self.assertIsNotNone(result1)
        self.assertEqual(result1[0], "Test1")

        db2_data = db2.execute_query("SELECT name FROM spreadsheets WHERE spreadsheet_id = ?", ("test_id2",))
        result2 = db2_data.fetchone() if db2_data else None
        self.assertIsNotNone(result2)
        self.assertEqual(result2[0], "Test2")
