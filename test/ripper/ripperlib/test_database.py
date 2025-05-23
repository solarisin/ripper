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
        self.assertEqual(len(tables), 2)
        self.assertIn("sheet_metadata", tables)
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
