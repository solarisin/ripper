import json
import os
import sqlite3
import tempfile
import unittest
from typing import Any, Dict

from ripper.ripperlib.database import RipperDb
from ripper.ripperlib.defs import SheetProperties, SpreadsheetProperties


class TestDatabaseIntegration(unittest.TestCase):
    def setUp(self) -> None:
        # Create a temporary database file
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        # Use Db with the temporary path
        self.db = RipperDb(self.db_path)
        # Ensure tables are created
        self.db.create_tables()

    def tearDown(self) -> None:
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_table_idempotent(self) -> None:
        self.db.close()
        self.db.open()

        self.db.create_tables()

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
        self.db.store_spreadsheet_properties(
            test_id,
            SpreadsheetProperties(
                {
                    "id": test_id,
                    "name": "Test",
                    "modifiedTime": "2024-01-01",
                    "createdTime": "2024-01-01",
                    "webViewLink": "",
                    "owners": [],
                    "size": 0,
                    "shared": False,
                }
            ),
        )
        cursor = self.db.execute_query("SELECT spreadsheet_id FROM spreadsheets WHERE spreadsheet_id = ?", (test_id,))
        self.assertIsNotNone(cursor)
        fetched_result = cursor.fetchone() if cursor else None
        self.assertIsNotNone(fetched_result)
        self.assertEqual(fetched_result[0], test_id)

        # Test failed query (syntax error)
        cursor = self.db.execute_query("SELECT * FROM non_existent_table")
        self.assertIsNone(cursor)

    def test_get_sheet_metadata(self) -> None:
        """Test retrieving sheet metadata from the database."""
        # Setup: Store sheet metadata
        spreadsheet_id = "test_spreadsheet_metadata"
        self.db.store_spreadsheet_properties(
            spreadsheet_id,
            SpreadsheetProperties(
                {
                    "id": spreadsheet_id,
                    "name": "Metadata Test",
                    "modifiedTime": "2024-01-01T00:00:00Z",
                    "createdTime": "2024-01-01T00:00:00Z",
                    "webViewLink": "",
                    "owners": [],
                    "size": 0,
                    "shared": False,
                }
            ),
        )
        metadata: Dict[str, Any] = {
            "sheets": [
                {
                    "properties": {
                        "sheetId": 1,
                        "index": 0,
                        "title": "Sheet 1",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 100, "columnCount": 26},
                    }
                }
            ]
        }
        self.db.store_sheet_properties(spreadsheet_id, SheetProperties.from_api_result(metadata))

        # Test: Retrieve with matching modified time (modified time is not used for sheet properties retrieval)
        retrieved_metadata = self.db.get_sheet_properties_of_spreadsheet(spreadsheet_id)
        self.assertIsNotNone(retrieved_metadata)
        self.assertEqual(len(retrieved_metadata), 1)
        sheet = retrieved_metadata[0]
        self.assertEqual(sheet.id, "1")  # Note: sheetId is an integer in the API result, stored as TEXT
        self.assertEqual(sheet.title, "Sheet 1")
        self.assertEqual(sheet.grid.row_count, 100)

        # Test: Retrieve non-existent spreadsheet
        retrieved_metadata = self.db.get_sheet_properties_of_spreadsheet("non_existent_id")
        self.assertEqual(len(retrieved_metadata), 0)

    def test_get_thumbnail_not_found(self) -> None:
        # Test retrieving thumbnail for a spreadsheet that exists but has no thumbnail data
        sid_no_thumbnail = "spreadsheet_no_thumb"
        self.db.store_spreadsheet_properties(
            sid_no_thumbnail,
            SpreadsheetProperties(
                {
                    "id": sid_no_thumbnail,
                    "name": "No Thumb",
                    "modifiedTime": "2024-01-01",
                    "createdTime": "2024-01-01",
                    "webViewLink": "",
                    "owners": [],
                    "size": 0,
                    "shared": False,
                }
            ),
        )

        retrieved_data = self.db.get_spreadsheet_thumbnail(sid_no_thumbnail)
        self.assertIsNone(retrieved_data)

    def test_store_and_get_thumbnail(self) -> None:
        sid = "sheet1"
        data = b"imgdata"
        self.db.store_spreadsheet_properties(
            sid,
            SpreadsheetProperties(
                {
                    "id": sid,
                    "name": "Thumb Test",
                    "modifiedTime": "2024-01-01",
                    "createdTime": "2024-01-01",
                    "webViewLink": "",
                    "owners": [],
                    "size": 0,
                    "shared": False,
                }
            ),
        )

        self.db.store_spreadsheet_thumbnail(sid, data)

        retrieved_thumbnail = self.db.get_spreadsheet_thumbnail(sid)
        self.assertEqual(retrieved_thumbnail, data)

        new_data = b"newimg"
        self.db.store_spreadsheet_thumbnail(sid, new_data)

        updated_thumbnail = self.db.get_spreadsheet_thumbnail(sid)
        self.assertEqual(updated_thumbnail, new_data)  # Thumbnail should be updated

    def test_store_sheet_metadata_updates_existing_sheets(self) -> None:
        spreadsheet_id = "test_spreadsheet"
        modified_time = "2024-01-01T00:00:00Z"

        self.db.store_spreadsheet_properties(
            spreadsheet_id,
            SpreadsheetProperties(
                {
                    "id": spreadsheet_id,
                    "name": "Update Test",
                    "modifiedTime": modified_time,
                    "createdTime": modified_time,
                    "webViewLink": "",
                    "owners": [],
                    "size": 0,
                    "shared": False,
                }
            ),
        )

        initial_metadata: Dict[str, Any] = {
            "sheets": [
                {
                    "properties": {
                        "sheetId": 1,
                        "index": 0,
                        "title": "Sheet 1",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 100, "columnCount": 26},
                    }
                },
                {
                    "properties": {
                        "sheetId": 2,
                        "index": 1,
                        "title": "Sheet 2",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 200, "columnCount": 52},
                    }
                },
            ]
        }

        self.db.store_sheet_properties(spreadsheet_id, SheetProperties.from_api_result(initial_metadata))

        retrieved_sheets_initial = self.db.get_sheet_properties_of_spreadsheet(spreadsheet_id)
        self.assertEqual(len(retrieved_sheets_initial), 2)
        self.assertEqual(retrieved_sheets_initial[0].title, "Sheet 1")
        self.assertEqual(retrieved_sheets_initial[1].title, "Sheet 2")

        updated_metadata: Dict[str, Any] = {
            "sheets": [
                {
                    "properties": {
                        "sheetId": 1,
                        "index": 0,
                        "title": "Sheet 1 Updated",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 150, "columnCount": 30},
                    }
                },
                {
                    "properties": {
                        "sheetId": 3,
                        "index": 2,
                        "title": "Sheet 3",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 50, "columnCount": 10},
                    }
                },
            ]
        }

        self.db.store_sheet_properties(spreadsheet_id, SheetProperties.from_api_result(updated_metadata))

        retrieved_sheets_updated = self.db.get_sheet_properties_of_spreadsheet(spreadsheet_id)
        self.assertEqual(len(retrieved_sheets_updated), 2)

        sheet1_updated = next((s for s in retrieved_sheets_updated if s.id == "1"), None)
        sheet3_new = next((s for s in retrieved_sheets_updated if s.id == "3"), None)
        sheet2_old = next((s for s in retrieved_sheets_updated if s.id == "2"), None)

        self.assertIsNotNone(sheet1_updated)
        self.assertEqual(sheet1_updated.title, "Sheet 1 Updated")
        self.assertEqual(sheet1_updated.grid.row_count, 150)
        self.assertEqual(sheet1_updated.grid.column_count, 30)

        self.assertIsNotNone(sheet3_new)
        self.assertEqual(sheet3_new.title, "Sheet 3")
        self.assertEqual(sheet3_new.grid.row_count, 50)
        self.assertEqual(sheet3_new.grid.column_count, 10)

        self.assertIsNone(sheet2_old)  # Sheet 2 should be deleted

    def test_store_spreadsheet_info(self) -> None:
        """Test storing and updating spreadsheet information."""
        spreadsheet_id = "test_spreadsheet_info"

        # Test: Store initial info
        initial_info: Dict[str, Any] = {
            "id": spreadsheet_id,
            "name": "Test Spreadsheet",
            "modifiedTime": "2024-01-01T00:00:00Z",
            "webViewLink": "https://example.com/sheet1",
            "createdTime": "2023-12-01T00:00:00Z",
            "owners": [{"displayName": "owner1"}],
            "size": 1024,
            "shared": True,
        }
        result = self.db.store_spreadsheet_properties(spreadsheet_id, SpreadsheetProperties(initial_info))
        self.assertTrue(result)

        # Verify stored info
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute(
                "SELECT name, modifiedTime, webViewLink, createdTime, owners, size, shared "
                "FROM spreadsheets WHERE spreadsheet_id = ?",
                (spreadsheet_id,),
            )
            stored_info = c.fetchone()
        finally:
            conn.close()

        self.assertIsNotNone(stored_info)
        self.assertEqual(stored_info[0], "Test Spreadsheet")
        self.assertEqual(stored_info[1], "2024-01-01T00:00:00Z")
        self.assertEqual(stored_info[2], "https://example.com/sheet1")
        self.assertEqual(stored_info[3], "2023-12-01T00:00:00Z")
        stored_owners = json.loads(stored_info[4])
        self.assertEqual(stored_owners, initial_info["owners"])
        self.assertEqual(stored_info[5], 1024)
        self.assertEqual(bool(stored_info[6]), True)

        # Test: Update partial info
        updated_info: Dict[str, Any] = {
            "id": spreadsheet_id,
            "name": "Updated Spreadsheet",
            "size": 2048,
            "modifiedTime": "2024-01-01T00:00:00Z",
        }
        existing_props_dict = {
            "id": spreadsheet_id,
            "name": "Test Spreadsheet",
            "modifiedTime": "2024-01-01T00:00:00Z",
            "webViewLink": "https://example.com/sheet1",
            "createdTime": "2023-12-01T00:00:00Z",
            "owners": [{"displayName": "owner1"}],
            "size": 1024,
            "shared": True,
            "thumbnailLink": None,  # Assume no thumbnail initially
        }
        existing_props = SpreadsheetProperties(existing_props_dict)
        existing_props.name = updated_info["name"]
        existing_props.size = updated_info["size"]
        result = self.db.store_spreadsheet_properties(spreadsheet_id, existing_props)
        self.assertTrue(result)

        # Verify updated info
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute("SELECT name, modifiedTime, size FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            updated_stored_info = c.fetchone()
        finally:
            conn.close()

        self.assertIsNotNone(updated_stored_info)
        self.assertEqual(updated_stored_info[0], "Updated Spreadsheet")
        self.assertEqual(
            updated_stored_info[1], "2024-01-01T00:00:00Z"
        )  # modifiedTime should not change if not provided in update
        self.assertEqual(updated_stored_info[2], 2048)

    def test_store_spreadsheet_info_invalidation_on_modified_time_change(self) -> None:
        """Test that sheets, grid_properties, and thumbnail are invalidated when modifiedTime changes."""

        spreadsheet_id = "invalidate_test"
        initial_info: Dict[str, Any] = {
            "id": spreadsheet_id,
            "name": "Invalidate Test",
            "modifiedTime": "2024-01-01T00:00:00Z",
            "webViewLink": "https://example.com/sheet1",
            "createdTime": "2023-12-01T00:00:00Z",
            "owners": [{"displayName": "owner1"}],
            "size": 1024,
            "shared": True,
            "thumbnailLink": "https://example.com/thumbnail.png",  # Include thumbnail link initially
        }
        # Store initial info
        result = self.db.store_spreadsheet_properties(spreadsheet_id, SpreadsheetProperties(initial_info))
        self.assertTrue(result)

        # Add some sheets and a thumbnail
        sheets_metadata: Dict[str, Any] = {
            "sheets": [
                {
                    "properties": {
                        "sheetId": 10,
                        "index": 0,
                        "title": "Sheet 10",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 50, "columnCount": 5},
                    }
                }
            ]
        }
        self.db.store_sheet_properties(spreadsheet_id, SheetProperties.from_api_result(sheets_metadata))

        # Store a thumbnail
        thumbnail_data = b"fakeimagebytes"
        self.db.store_spreadsheet_thumbnail(spreadsheet_id, thumbnail_data)

        # Verify sheets and thumbnail were stored
        retrieved_sheets_initial = self.db.get_sheet_properties_of_spreadsheet(spreadsheet_id)
        self.assertEqual(len(retrieved_sheets_initial), 1)
        retrieved_thumbnail_initial = self.db.get_spreadsheet_thumbnail(spreadsheet_id)
        self.assertEqual(retrieved_thumbnail_initial, thumbnail_data)

        # Update with new modifiedTime
        updated_info: Dict[str, Any] = {
            "id": spreadsheet_id,
            "name": "Invalidate Test Updated",
            "modifiedTime": "2024-02-01T00:00:00Z",  # Modified time changes
            "webViewLink": "https://example.com/sheet1",
            "createdTime": "2023-12-01T00:00:00Z",
            "owners": [{"displayName": "owner1"}],
            "size": 1024,
            "shared": True,
            "thumbnailLink": "https://example.com/thumbnail.png",  # Keep thumbnail link the same
        }
        result = self.db.store_spreadsheet_properties(spreadsheet_id, SpreadsheetProperties(updated_info))
        self.assertTrue(result)

        # Verify sheets and thumbnail are invalidated (deleted)
        retrieved_sheets_updated = self.db.get_sheet_properties_of_spreadsheet(spreadsheet_id)
        self.assertEqual(len(retrieved_sheets_updated), 0)
        retrieved_thumbnail_updated = self.db.get_spreadsheet_thumbnail(spreadsheet_id)
        self.assertIsNone(retrieved_thumbnail_updated)

    def test_store_spreadsheet_info_with_thumbnail_link(self) -> None:
        """Test storing and retrieving spreadsheet info with thumbnailLink."""
        spreadsheet_id = "test_spreadsheet_thumbnail_link"

        # Test: Store initial info with thumbnailLink
        initial_info: Dict[str, Any] = {
            "id": spreadsheet_id,
            "name": "Test Spreadsheet",
            "modifiedTime": "2024-01-01T00:00:00Z",
            "thumbnailLink": "https://example.com/thumbnail.png",
            "createdTime": "2024-01-01T00:00:00Z",
            "webViewLink": "",
            "owners": [],
            "size": 0,
            "shared": False,
        }
        result = self.db.store_spreadsheet_properties(spreadsheet_id, SpreadsheetProperties(initial_info))
        self.assertTrue(result)

        # Verify stored info
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute("SELECT name, thumbnailLink FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            stored_info = c.fetchone()
        finally:
            conn.close()

        self.assertIsNotNone(stored_info)
        self.assertEqual(stored_info[0], "Test Spreadsheet")
        self.assertEqual(stored_info[1], "https://example.com/thumbnail.png")

        # Test: Update thumbnailLink
        existing_props_dict = {
            "id": spreadsheet_id,
            "name": "Test Spreadsheet",  # Keep name the same
            "modifiedTime": "2024-01-01T00:00:00Z",  # Keep modifiedTime the same
            "thumbnailLink": "https://example.com/thumbnail.png",  # Existing thumbnailLink
            "createdTime": "2024-01-01T00:00:00Z",
            "webViewLink": "",
            "owners": [],
            "size": 0,
            "shared": False,
        }
        existing_props = SpreadsheetProperties(existing_props_dict)
        existing_props.thumbnail_link = "https://example.com/new_thumbnail.png"

        result = self.db.store_spreadsheet_properties(spreadsheet_id, existing_props)
        self.assertTrue(result)

        # Verify updated thumbnailLink
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute("SELECT name, thumbnailLink FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            updated_stored_info = c.fetchone()
        finally:
            conn.close()

        self.assertIsNotNone(updated_stored_info)
        self.assertEqual(updated_stored_info[0], "Test Spreadsheet")
        self.assertEqual(updated_stored_info[1], "https://example.com/new_thumbnail.png")
