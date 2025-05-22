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
        self.assertIn("spreadsheet_thumbnails", tables)
        self.assertIn("sheet_metadata", tables)
        conn.close()

    def test_store_and_get_thumbnail(self):
        sid = "sheet1"
        data = b"imgdata"
        mod = "2024-01-01"
        result = self.db.store_spreadsheet_thumbnail(sid, data, mod)
        self.assertTrue(result)
        thumb = self.db.get_spreadsheet_thumbnail(sid)
        self.assertIsNotNone(thumb)
        self.assertEqual(thumb["thumbnail_data"], data)
        self.assertEqual(thumb["last_modified"], mod)
        new_data = b"newimg"
        new_mod = "2024-01-02"
        result2 = self.db.store_spreadsheet_thumbnail(sid, new_data, new_mod)
        self.assertTrue(result2)
        thumb2 = self.db.get_spreadsheet_thumbnail(sid)
        self.assertEqual(thumb2["thumbnail_data"], new_data)
        self.assertEqual(thumb2["last_modified"], new_mod)

    def test_get_thumbnail_not_found(self):
        thumb = self.db.get_spreadsheet_thumbnail("doesnotexist")
        self.assertIsNone(thumb)
