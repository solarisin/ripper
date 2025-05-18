import os
import sqlite3
import tempfile
import unittest

from ripper.ripperlib import database


class TestDatabaseIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        database.create_table(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_table_idempotent(self):
        database.create_table(self.db_path)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in c.fetchall()}
        self.assertIn("transactions", tables)
        self.assertIn("data_sources", tables)
        self.assertIn("sheet_thumbnails", tables)
        conn.close()

    def test_insert_and_retrieve_transaction(self):
        tx = {"date": "2023-01-01", "description": "Test", "amount": 42.0, "category": "Cat"}
        result = database.insert_transaction(tx, self.db_path)
        self.assertTrue(result)
        txs = database.retrieve_transactions(self.db_path)
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0]["description"], "Test")
        self.assertEqual(txs[0]["amount"], 42.0)

    def test_insert_transactions_bulk(self):
        txs = [
            {"date": "2023-01-01", "description": "A", "amount": 1.0, "category": "C1"},
            {"date": "2023-01-02", "description": "B", "amount": 2.0, "category": "C2"},
        ]
        result = database.insert_transactions(txs, self.db_path)
        self.assertTrue(result)
        all_txs = database.retrieve_transactions(self.db_path)
        self.assertEqual(len(all_txs), 2)
        self.assertEqual(all_txs[1]["description"], "B")

    def test_insert_data_source(self):
        result = database.insert_data_source("src", "spreadsheet", "sheet", "A1:B2", self.db_path)
        self.assertTrue(result)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT source_name, spreadsheet_id, sheet_name, cell_range FROM data_sources")
        row = c.fetchone()
        self.assertEqual(row, ("src", "spreadsheet", "sheet", "A1:B2"))
        conn.close()

    def test_store_and_get_thumbnail(self):
        sid = "sheet1"
        data = b"imgdata"
        mod = "2024-01-01"
        result = database.store_thumbnail(sid, data, mod, self.db_path)
        self.assertTrue(result)
        thumb = database.get_thumbnail(sid, self.db_path)
        self.assertIsNotNone(thumb)
        self.assertEqual(thumb["thumbnail_data"], data)
        self.assertEqual(thumb["last_modified"], mod)
        new_data = b"newimg"
        new_mod = "2024-01-02"
        result2 = database.store_thumbnail(sid, new_data, new_mod, self.db_path)
        self.assertTrue(result2)
        thumb2 = database.get_thumbnail(sid, self.db_path)
        self.assertEqual(thumb2["thumbnail_data"], new_data)
        self.assertEqual(thumb2["last_modified"], new_mod)

    def test_get_thumbnail_not_found(self):
        thumb = database.get_thumbnail("doesnotexist", self.db_path)
        self.assertIsNone(thumb)

    def test_insert_transaction_invalid(self):
        tx = {"date": "2023-01-01", "description": "Test", "amount": 42.0}
        result = database.insert_transaction(tx, self.db_path)
        self.assertFalse(result)

    def test_insert_transactions_invalid(self):
        txs = [
            {"date": "2023-01-01", "description": "A", "amount": 1.0, "category": "C1"},
            {"date": "2023-01-02", "description": "B", "amount": 2.0},
        ]
        result = database.insert_transactions(txs, self.db_path)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
