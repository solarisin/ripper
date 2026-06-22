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
        # 3 metadata tables + 2 caching tables + 1 data_sources + sqlite_sequence = 7
        self.assertEqual(len(tables), 7)
        self.assertIn("sheets", tables)
        self.assertIn("grid_properties", tables)
        self.assertIn("spreadsheets", tables)
        self.assertIn("sheet_data_ranges", tables)
        self.assertIn("sheet_data_cells", tables)
        self.assertIn("data_sources", tables)
        self.assertIn("sqlite_sequence", tables)  # Auto-created by SQLite for AUTOINCREMENT
        conn.close()

    def test_execute_query(self) -> None:
        """Test the execute_query method for successful and failed queries."""
        # Test successful query
        rows = self.db.execute_query("SELECT name FROM sqlite_master WHERE type='table'")
        self.assertIsNotNone(rows)
        self.assertGreater(len(rows or []), 0)

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
        rows = self.db.execute_query("SELECT spreadsheet_id FROM spreadsheets WHERE spreadsheet_id = ?", (test_id,))
        self.assertIsNotNone(rows)
        self.assertGreater(len(rows or []), 0)
        self.assertEqual((rows or [[]])[0][0], test_id)

        # Test failed query (syntax error)
        rows = self.db.execute_query("SELECT * FROM non_existent_table")
        self.assertIsNone(rows)

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

    def _store_single_grid_sheet(self, spreadsheet_id: str, sheet_id: int, title: str) -> None:
        """Store a spreadsheet with one GRID tab of the given sheetId/title."""
        self.db.store_spreadsheet_properties(
            spreadsheet_id,
            SpreadsheetProperties(
                {
                    "id": spreadsheet_id,
                    "name": spreadsheet_id,
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
                        "sheetId": sheet_id,
                        "index": 0,
                        "title": title,
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 10, "columnCount": 5},
                    }
                }
            ]
        }
        self.db.store_sheet_properties(spreadsheet_id, SheetProperties.from_api_result(metadata))

    def test_sheets_with_colliding_sheetid_across_spreadsheets(self) -> None:
        """Two spreadsheets whose tabs share a sheetId must keep independent metadata (#70)."""
        # The default first tab of every spreadsheet is sheetId 0, so collisions are common.
        self._store_single_grid_sheet("book-a", 0, "A tab")
        self._store_single_grid_sheet("book-b", 0, "B tab")

        a = self.db.get_sheet_properties_of_spreadsheet("book-a")
        b = self.db.get_sheet_properties_of_spreadsheet("book-b")

        self.assertEqual([s.title for s in a], ["A tab"])
        self.assertEqual([s.title for s in b], ["B tab"])
        # Grid dimensions stay attached to the correct spreadsheet's tab.
        self.assertEqual(a[0].grid.row_count, 10)
        self.assertEqual(b[0].grid.column_count, 5)

    def test_deleting_one_spreadsheet_keeps_other_colliding_sheet(self) -> None:
        """Re-storing one spreadsheet's sheets must not disturb another's identical sheetId (#70)."""
        self._store_single_grid_sheet("book-a", 0, "A tab")
        self._store_single_grid_sheet("book-b", 0, "B tab")

        # Re-store book-a (the delete+insert path) and confirm book-b is untouched.
        self._store_single_grid_sheet("book-a", 0, "A tab v2")

        b = self.db.get_sheet_properties_of_spreadsheet("book-b")
        self.assertEqual([s.title for s in b], ["B tab"])

    def test_legacy_sheetid_schema_is_migrated_on_create_tables(self) -> None:
        """An old single-PK sheets schema is dropped and recreated with the composite key (#70)."""
        # Recreate the legacy schema in place (sheetId-only PK, grid_properties without spreadsheet_id).
        assert self.db._conn is not None
        c = self.db._conn.cursor()
        c.execute("DROP TABLE IF EXISTS grid_properties")
        c.execute("DROP TABLE IF EXISTS sheets")
        c.execute("CREATE TABLE sheets (sheetId TEXT PRIMARY KEY, spreadsheet_id TEXT NOT NULL)")
        c.execute("CREATE TABLE grid_properties (sheetId TEXT PRIMARY KEY, rowCount INTEGER, columnCount INTEGER)")
        c.execute("INSERT INTO sheets (sheetId, spreadsheet_id) VALUES ('0', 'stale-book')")
        self.db._conn.commit()

        # Re-running create_tables must migrate (drop + recreate) to the new composite schema.
        self.db.create_tables()

        c.execute("PRAGMA table_info(grid_properties)")
        grid_cols = {row[1] for row in c.fetchall()}
        self.assertIn("spreadsheet_id", grid_cols)

        c.execute("PRAGMA table_info(sheets)")
        sheets_pk = [row[1] for row in c.fetchall() if row[5] > 0]
        self.assertEqual(set(sheets_pk), {"spreadsheet_id", "sheetId"})

        # Stale legacy rows were discarded (these caches re-populate from the API on next load).
        c.execute("SELECT COUNT(*) FROM sheets")
        self.assertEqual(c.fetchone()[0], 0)

    def test_store_sheet_properties_raises_for_missing_spreadsheet(self) -> None:
        """store_sheet_properties must reject a parent spreadsheet absent from the DB (#32)."""
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
        with self.assertRaises(ValueError):
            self.db.store_sheet_properties("nonexistent_spreadsheet", SheetProperties.from_api_result(metadata))

    def test_db_singleton_is_lazy_proxy(self) -> None:
        """`Db` is a lazy proxy (imports don't construct it) that forwards to a RipperDb (#33)."""
        import ripper.ripperlib.database as database_module

        self.assertIsInstance(database_module.Db, database_module._LazyDb)

    def test_lazy_db_proxy_injection_and_forwarding(self) -> None:
        """The proxy is lazy and forwards reads AND writes to the injected instance (#33, #66 review).

        This guards the safety regression where assignments landed on the proxy while reads
        (clean/open) hit the underlying real database. Uses an isolated temp RipperDb so the
        real application database is never targeted.
        """
        from ripper.ripperlib.database import _LazyDb

        proxy = _LazyDb()
        # Lazy: nothing constructed until first use.
        self.assertIsNone(proxy._instance)

        # Inject an isolated temp database (self.db points at a temp file).
        proxy._instance = self.db
        self.assertIs(proxy._resolve(), self.db)
        # Reads forward to the injected instance — the underlying target is the temp DB.
        self.assertEqual(proxy._db_file_path, self.db_path)
        # Writes forward to the injected instance, not the proxy.
        proxy._db_file_path = "/some/other/path.db"
        self.assertEqual(self.db._db_file_path, "/some/other/path.db")
        self.assertNotIn("_db_file_path", proxy.__dict__)

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


class TestDataSourceCRUD(unittest.TestCase):
    """Tests for the data_sources table CRUD methods."""

    SPREADSHEET_ID = "test_spreadsheet_ds"

    def setUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        self.db = RipperDb(self.db_path)
        # Insert a spreadsheet row so the FK constraint is satisfied.
        self.db.store_spreadsheet_properties(
            self.SPREADSHEET_ID,
            SpreadsheetProperties(
                {
                    "id": self.SPREADSHEET_ID,
                    "name": "Test Spreadsheet",
                    "modifiedTime": "2024-01-01T00:00:00Z",
                    "createdTime": "2024-01-01T00:00:00Z",
                    "webViewLink": "",
                    "owners": [],
                    "size": 0,
                    "shared": False,
                }
            ),
        )

    def tearDown(self) -> None:
        self.db.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_and_get_data_source(self) -> None:
        """create_data_source returns a valid id; get_data_source returns the record."""
        ds_id = self.db.create_data_source(
            name="Transactions",
            spreadsheet_id=self.SPREADSHEET_ID,
            sheet_name="Transactions",
            range_a1="A1:Z500",
        )
        self.assertIsNotNone(ds_id)
        assert ds_id is not None

        record = self.db.get_data_source(ds_id)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["id"], ds_id)
        self.assertEqual(record["name"], "Transactions")
        self.assertEqual(record["spreadsheet_id"], self.SPREADSHEET_ID)
        self.assertEqual(record["sheet_name"], "Transactions")
        self.assertEqual(record["range_a1"], "A1:Z500")
        self.assertIsNotNone(record["created_at"])
        self.assertIsNone(record["last_fetched_at"])

    def test_list_data_sources_empty(self) -> None:
        """list_data_sources returns an empty list when no sources exist."""
        self.assertEqual(self.db.list_data_sources(), [])

    def test_list_data_sources_ordered_by_name(self) -> None:
        """list_data_sources returns rows ordered case-insensitively by name."""
        self.db.create_data_source("Zebra", self.SPREADSHEET_ID, "Sheet1", "A1:Z10")
        self.db.create_data_source("alpha", self.SPREADSHEET_ID, "Sheet2", "A1:Z10")
        self.db.create_data_source("Budget", self.SPREADSHEET_ID, "Sheet3", "A1:Z10")

        sources = self.db.list_data_sources()
        names = [s["name"] for s in sources]
        self.assertEqual(names, sorted(names, key=str.casefold))

    def test_update_data_source(self) -> None:
        """update_data_source modifies name, sheet_name, and range_a1."""
        ds_id = self.db.create_data_source("Old Name", self.SPREADSHEET_ID, "Sheet1", "A1:Z10")
        assert ds_id is not None

        result = self.db.update_data_source(ds_id, "New Name", "Sheet2", "B2:Y50")
        self.assertTrue(result)

        record = self.db.get_data_source(ds_id)
        assert record is not None
        self.assertEqual(record["name"], "New Name")
        self.assertEqual(record["sheet_name"], "Sheet2")
        self.assertEqual(record["range_a1"], "B2:Y50")

    def test_update_data_source_nonexistent(self) -> None:
        """update_data_source returns False for a missing id."""
        self.assertFalse(self.db.update_data_source(999, "X", "S", "A1"))

    def test_delete_data_source(self) -> None:
        """delete_data_source removes the record."""
        ds_id = self.db.create_data_source("To Delete", self.SPREADSHEET_ID, "Sheet1", "A1:Z10")
        assert ds_id is not None

        self.assertTrue(self.db.delete_data_source(ds_id))
        self.assertIsNone(self.db.get_data_source(ds_id))

    def test_delete_data_source_nonexistent(self) -> None:
        """delete_data_source returns False for a missing id."""
        self.assertFalse(self.db.delete_data_source(999))

    def test_update_data_source_fetched_at(self) -> None:
        """update_data_source_fetched_at stamps last_fetched_at."""
        ds_id = self.db.create_data_source("Fetch Test", self.SPREADSHEET_ID, "Sheet1", "A1:Z10")
        assert ds_id is not None

        record_before = self.db.get_data_source(ds_id)
        assert record_before is not None
        self.assertIsNone(record_before["last_fetched_at"])

        self.assertTrue(self.db.update_data_source_fetched_at(ds_id))

        record_after = self.db.get_data_source(ds_id)
        assert record_after is not None
        self.assertIsNotNone(record_after["last_fetched_at"])

    def test_update_fetched_at_nonexistent(self) -> None:
        """update_data_source_fetched_at returns False for a missing id."""
        self.assertFalse(self.db.update_data_source_fetched_at(999))

    def test_delete_spreadsheet_cascades_to_data_sources(self) -> None:
        """Deleting a spreadsheet cascades to remove its data sources."""
        ds_id = self.db.create_data_source("Cascade Test", self.SPREADSHEET_ID, "Sheet1", "A1:Z10")
        assert ds_id is not None

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM spreadsheets WHERE spreadsheet_id = ?", (self.SPREADSHEET_ID,))
            conn.commit()
        finally:
            conn.close()

        self.assertIsNone(self.db.get_data_source(ds_id))

    def test_list_data_sources_includes_spreadsheet_name(self) -> None:
        """list_data_sources joins spreadsheets and includes spreadsheet_name."""
        self.db.create_data_source("My Source", self.SPREADSHEET_ID, "Sheet1", "A1:Z10")
        sources = self.db.list_data_sources()
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["spreadsheet_name"], "Test Spreadsheet")
