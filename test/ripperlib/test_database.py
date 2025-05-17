import unittest
from unittest.mock import MagicMock, patch
import os
from sqlite3 import Error


from ripperlib.database import (
    get_db_path,
    create_connection,
    create_table,
    insert_transaction,
    insert_transactions,
    retrieve_transactions,
    insert_data_source,
    store_thumbnail,
    get_thumbnail,
    init_database,
    ConnectionPool,
)


class TestConnectionPool(unittest.TestCase):
    """Test cases for the ConnectionPool class."""

    @patch("sqlite3.connect")
    def test_initialize_pool(self, mock_connect):
        """Test that the connection pool is initialized with the correct number of connections."""
        # Create a connection pool with a specific size
        pool_size = 3
        pool = ConnectionPool("test.db", pool_size)
        self.assertEqual(pool.pool_size, pool_size)
        self.assertEqual(pool.db_file_path, "test.db")

        # Check that connect was called the correct number of times
        self.assertEqual(mock_connect.call_count, pool_size)

        # Check that all calls were with the correct database file
        for call_args in mock_connect.call_args_list:
            self.assertEqual(call_args[0][0], "test.db")

    @patch("sqlite3.connect")
    def test_get_connection(self, mock_connect):
        """Test that get_connection returns a connection from the pool."""
        # Create a mock connection
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        # Create a connection pool
        pool = ConnectionPool("test.db")

        # Get a connection
        conn = pool.get_connection()

        # Check that the connection is the mock connection
        self.assertEqual(conn, mock_conn)

    @patch("sqlite3.connect")
    def test_release_connection(self, mock_connect):
        """Test that release_connection returns a connection to the pool."""
        # Create a mock connection
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        # Create a connection pool
        pool = ConnectionPool("test.db")

        # Get a connection
        conn = pool.get_connection()

        # Release the connection
        pool.release_connection(conn)

        # Get another connection and check that it's the same one
        conn2 = pool.get_connection()
        self.assertEqual(conn2, mock_conn)

    @patch("sqlite3.connect")
    def test_close_all_connections(self, mock_connect):
        """Test that close_all_connections closes all connections in the pool."""
        # Create mock connections
        mock_conns = [MagicMock() for _ in range(3)]
        mock_connect.side_effect = mock_conns

        # Create a connection pool
        pool = ConnectionPool("test.db", 3)

        # Close all connections
        pool.close_all_connections()

        # Check that close was called on each connection
        for mock_conn in mock_conns:
            mock_conn.close.assert_called_once()


class TestDatabaseFunctions(unittest.TestCase):
    """Test cases for the database functions."""

    @patch("os.environ.get")
    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_get_db_path_existing_dir(self, mock_makedirs, mock_exists, mock_environ_get):
        """Test that get_db_path returns the correct path when the directory exists."""
        # Set up the mocks
        mock_environ_get.return_value = "/app_data"
        mock_exists.return_value = True

        # Call get_db_path
        result = get_db_path("test.db")

        # Check that the result is correct
        expected_path = os.path.join("/app_data", "ripper", "test.db")
        self.assertEqual(result, expected_path)

        # Check that makedirs was not called
        mock_makedirs.assert_not_called()

    @patch("os.environ.get")
    @patch("os.path.exists")
    @patch("os.makedirs")
    def test_get_db_path_create_dir(self, mock_makedirs, mock_exists, mock_environ_get):
        """Test that get_db_path creates the directory when it doesn't exist."""
        # Set up the mocks
        mock_environ_get.return_value = "/app_data"
        mock_exists.return_value = False

        # Call get_db_path
        result = get_db_path("test.db")

        # Check that the result is correct
        expected_path = os.path.join("/app_data", "ripper", "test.db")
        self.assertEqual(result, expected_path)

        # Check that makedirs was called with the correct path
        mock_makedirs.assert_called_once_with(os.path.join("/app_data", "ripper"))

    @patch("os.environ.get")
    @patch("os.path.exists")
    @patch("os.makedirs")
    @patch("os.getcwd")
    def test_get_db_path_makedirs_error(self, mock_getcwd, mock_makedirs, mock_exists, mock_environ_get):
        """Test that get_db_path falls back to the current directory when makedirs fails."""
        # Set up the mocks
        mock_environ_get.return_value = "/app_data"
        mock_exists.return_value = False
        mock_makedirs.side_effect = Exception("Failed to create directory")
        mock_getcwd.return_value = "/current_dir"

        # Call get_db_path
        result = get_db_path("test.db")

        # Check that the result is correct
        expected_path = os.path.join("/current_dir", "test.db")
        self.assertEqual(result, expected_path)

    @patch("sqlite3.connect")
    def test_create_connection_success(self, mock_connect):
        """Test that create_connection returns a connection when successful."""
        # Set up the mock
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        # Call create_connection
        result = create_connection("test.db")

        # Check that the result is the mock connection
        self.assertEqual(result, mock_conn)

        # Check that connect was called with the correct path
        mock_connect.assert_called_once_with("test.db")

    @patch("sqlite3.connect")
    def test_create_connection_error(self, mock_connect):
        """Test that create_connection returns None when an error occurs."""
        # Set up the mock to raise an error
        mock_connect.side_effect = Error("Connection error")

        # Call create_connection
        result = create_connection("test.db")

        # Check that the result is None
        self.assertIsNone(result)

    @patch("ripperlib.database.create_connection")
    def test_create_table(self, mock_create_connection):
        """Test that create_table creates the necessary tables."""
        # Set up the mock connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_create_connection.return_value = mock_conn

        # Call create_table
        create_table("test.db")

        # Check that create_connection was called with the correct path
        mock_create_connection.assert_called_once_with("test.db")

        # Check that cursor was called
        mock_conn.cursor.assert_called_once()

        # Check that execute was called for each table creation and index
        self.assertEqual(mock_cursor.execute.call_count, 6)

        # Check that commit was called
        mock_conn.commit.assert_called_once()

        # Check that close was called
        mock_conn.close.assert_called_once()

    @patch("ripperlib.database.create_connection")
    def test_create_table_no_connection(self, mock_create_connection):
        """Test that create_table handles the case when no connection can be created."""
        # Set up the mock to return None
        mock_create_connection.return_value = None

        # Call create_table
        create_table("test.db")

        # Check that create_connection was called with the correct path
        mock_create_connection.assert_called_once_with("test.db")

    @patch("ripperlib.database.create_connection")
    def test_create_table_error(self, mock_create_connection):
        """Test that create_table handles errors during table creation."""
        # Set up the mock connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Error("Table creation error")
        mock_conn.cursor.return_value = mock_cursor
        mock_create_connection.return_value = mock_conn

        # Call create_table
        create_table("test.db")

        # Check that close was called
        mock_conn.close.assert_called_once()

    @patch("ripperlib.database.get_db_path")
    @patch("ripperlib.database.create_connection")
    def test_insert_transaction_success(self, mock_create_connection, mock_get_db_path):
        """Test that insert_transaction inserts a transaction successfully."""
        # Set up the mocks
        mock_get_db_path.return_value = "test.db"
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_create_connection.return_value = mock_conn

        # Create a test transaction
        transaction = {"date": "2023-01-01", "description": "Test Transaction", "amount": 100.0, "category": "Test"}

        # Call insert_transaction
        result = insert_transaction(transaction)

        # Check that the result is True
        self.assertTrue(result)

        # Check that get_db_path was called
        mock_get_db_path.assert_called_once()

        # Check that create_connection was called with the correct path
        mock_create_connection.assert_called_once_with("test.db")

        # Check that cursor was called
        mock_conn.cursor.assert_called_once()

        # Check that execute was called with the correct SQL and parameters
        mock_cursor.execute.assert_called_once_with(
            """INSERT INTO transactions (date, description, amount, category)
                         VALUES (?, ?, ?, ?)""",
            ("2023-01-01", "Test Transaction", 100.0, "Test"),
        )

        # Check that commit was called
        mock_conn.commit.assert_called_once()

        # Check that close was called
        mock_conn.close.assert_called_once()

    @patch("ripperlib.database.get_db_path")
    @patch("ripperlib.database.create_connection")
    def test_insert_transaction_no_connection(self, mock_create_connection, mock_get_db_path):
        """Test that insert_transaction returns False when no connection can be created."""
        # Set up the mocks
        mock_get_db_path.return_value = "test.db"
        mock_create_connection.return_value = None

        # Create a test transaction
        transaction = {"date": "2023-01-01", "description": "Test Transaction", "amount": 100.0, "category": "Test"}

        # Call insert_transaction
        result = insert_transaction(transaction)

        # Check that the result is False
        self.assertFalse(result)

    @patch("ripperlib.database.get_db_path")
    @patch("ripperlib.database.create_connection")
    def test_insert_transaction_error(self, mock_create_connection, mock_get_db_path):
        """Test that insert_transaction handles errors during insertion."""
        # Set up the mocks
        mock_get_db_path.return_value = "test.db"
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Error("Insertion error")
        mock_conn.cursor.return_value = mock_cursor
        mock_create_connection.return_value = mock_conn

        # Create a test transaction
        transaction = {"date": "2023-01-01", "description": "Test Transaction", "amount": 100.0, "category": "Test"}

        # Call insert_transaction
        result = insert_transaction(transaction)

        # Check that the result is False
        self.assertFalse(result)

        # Check that close was called
        mock_conn.close.assert_called_once()

    @patch("ripperlib.database.get_db_path")
    @patch("ripperlib.database.create_connection")
    def test_insert_transactions_success(self, mock_create_connection, mock_get_db_path):
        """Test that insert_transactions inserts multiple transactions successfully."""
        # Set up the mocks
        mock_get_db_path.return_value = "test.db"
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_create_connection.return_value = mock_conn

        # Create test transactions
        transactions = [
            {"date": "2023-01-01", "description": "Test Transaction 1", "amount": 100.0, "category": "Test"},
            {"date": "2023-01-02", "description": "Test Transaction 2", "amount": 200.0, "category": "Test"},
        ]

        # Call insert_transactions
        result = insert_transactions(transactions)

        # Check that the result is True
        self.assertTrue(result)

        # Check that get_db_path was called
        mock_get_db_path.assert_called_once()

        # Check that create_connection was called with the correct path
        mock_create_connection.assert_called_once_with("test.db")

        # Check that cursor was called
        mock_conn.cursor.assert_called_once()

        # Check that executemany was called with the correct SQL and parameters
        mock_cursor.executemany.assert_called_once_with(
            """INSERT INTO transactions (date, description, amount, category)
                         VALUES (?, ?, ?, ?)""",
            [("2023-01-01", "Test Transaction 1", 100.0, "Test"), ("2023-01-02", "Test Transaction 2", 200.0, "Test")],
        )

        # Check that commit was called
        mock_conn.commit.assert_called_once()

        # Check that close was called
        mock_conn.close.assert_called_once()

    @patch("ripperlib.database.get_db_path")
    @patch("ripperlib.database.create_connection")
    def test_retrieve_transactions_success(self, mock_create_connection, mock_get_db_path):
        """Test that retrieve_transactions retrieves transactions successfully."""
        # Set up the mocks
        mock_get_db_path.return_value = "test.db"
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, "2023-01-01", "Test Transaction 1", 100.0, "Test"),
            (2, "2023-01-02", "Test Transaction 2", 200.0, "Test"),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_create_connection.return_value = mock_conn

        # Call retrieve_transactions
        result = retrieve_transactions()

        # Check that the result contains the expected transactions
        expected_transactions = [
            {"date": "2023-01-01", "description": "Test Transaction 1", "amount": 100.0, "category": "Test"},
            {"date": "2023-01-02", "description": "Test Transaction 2", "amount": 200.0, "category": "Test"},
        ]
        self.assertEqual(result, expected_transactions)

        # Check that get_db_path was called
        mock_get_db_path.assert_called_once()

        # Check that create_connection was called with the correct path
        mock_create_connection.assert_called_once_with("test.db")

        # Check that cursor was called
        mock_conn.cursor.assert_called_once()

        # Check that execute was called with the correct SQL
        mock_cursor.execute.assert_called_once_with("SELECT * FROM transactions")

        # Check that fetchall was called
        mock_cursor.fetchall.assert_called_once()

        # Check that close was called
        mock_conn.close.assert_called_once()

    @patch("ripperlib.database.get_db_path")
    @patch("ripperlib.database.create_connection")
    def test_retrieve_transactions_no_connection(self, mock_create_connection, mock_get_db_path):
        """Test that retrieve_transactions returns an empty list when no connection can be created."""
        # Set up the mocks
        mock_get_db_path.return_value = "test.db"
        mock_create_connection.return_value = None

        # Call retrieve_transactions
        result = retrieve_transactions()

        # Check that the result is an empty list
        self.assertEqual(result, [])

    @patch("ripperlib.database.get_db_path")
    @patch("ripperlib.database.create_connection")
    def test_retrieve_transactions_error(self, mock_create_connection, mock_get_db_path):
        """Test that retrieve_transactions handles errors during retrieval."""
        # Set up the mocks
        mock_get_db_path.return_value = "test.db"
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Error("Retrieval error")
        mock_conn.cursor.return_value = mock_cursor
        mock_create_connection.return_value = mock_conn

        # Call retrieve_transactions
        result = retrieve_transactions()

        # Check that the result is an empty list
        self.assertEqual(result, [])

        # Check that close was called
        mock_conn.close.assert_called_once()

    @patch("ripperlib.database.get_db_path")
    @patch("ripperlib.database.create_connection")
    def test_insert_data_source_success(self, mock_create_connection, mock_get_db_path):
        """Test that insert_data_source inserts a data source successfully."""
        # Set up the mocks
        mock_get_db_path.return_value = "test.db"
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_create_connection.return_value = mock_conn

        # Call insert_data_source
        result = insert_data_source("Test Source", "test_id", "Sheet1", "A1:Z100")

        # Check that the result is True
        self.assertTrue(result)

        # Check that get_db_path was called
        mock_get_db_path.assert_called_once()

        # Check that create_connection was called with the correct path
        mock_create_connection.assert_called_once_with("test.db")

        # Check that cursor was called
        mock_conn.cursor.assert_called_once()

        # Check that execute was called with the correct SQL and parameters
        mock_cursor.execute.assert_called_once_with(
            """INSERT INTO data_sources (source_name, spreadsheet_id, sheet_name, cell_range)
                   VALUES (?, ?, ?, ?)""",
            ("Test Source", "test_id", "Sheet1", "A1:Z100"),
        )

        # Check that commit was called
        mock_conn.commit.assert_called_once()

        # Check that close was called
        mock_conn.close.assert_called_once()

    @patch("ripperlib.database.get_db_path")
    @patch("ripperlib.database.create_connection")
    def test_store_thumbnail_insert_success(self, mock_create_connection, mock_get_db_path):
        """Test that store_thumbnail inserts a new thumbnail successfully."""
        # Set up the mocks
        mock_get_db_path.return_value = "test.db"
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # No existing thumbnail
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_create_connection.return_value = mock_conn

        # Call store_thumbnail
        result = store_thumbnail("test_id", b"thumbnail_data", "2023-01-01")

        # Check that the result is True
        self.assertTrue(result)

        # Check that get_db_path was called
        mock_get_db_path.assert_called_once()

        # Check that create_connection was called with the correct path
        mock_create_connection.assert_called_once_with("test.db")

        # Check that cursor was called
        self.assertEqual(mock_conn.cursor.call_count, 1)

        # Check that execute was called with the correct SQL and parameters for checking existence
        mock_cursor.execute.assert_any_call("SELECT 1 FROM sheet_thumbnails WHERE sheet_id = ?", ("test_id",))

        # Check that execute was called with the correct SQL and parameters for insertion
        mock_cursor.execute.assert_any_call(
            """INSERT INTO sheet_thumbnails (sheet_id, thumbnail_data, last_modified)
                       VALUES (?, ?, ?)""",
            ("test_id", b"thumbnail_data", "2023-01-01"),
        )

        # Check that commit was called
        mock_conn.commit.assert_called_once()

        # Check that close was called
        mock_conn.close.assert_called_once()

    @patch("ripperlib.database.get_db_path")
    @patch("ripperlib.database.create_connection")
    def test_store_thumbnail_update_success(self, mock_create_connection, mock_get_db_path):
        """Test that store_thumbnail updates an existing thumbnail successfully."""
        # Set up the mocks
        mock_get_db_path.return_value = "test.db"
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Existing thumbnail
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value = mock_cursor
        mock_create_connection.return_value = mock_conn

        # Call store_thumbnail
        result = store_thumbnail("test_id", b"thumbnail_data", "2023-01-01")

        # Check that the result is True
        self.assertTrue(result)

        # Check that get_db_path was called
        mock_get_db_path.assert_called_once()

        # Check that create_connection was called with the correct path
        mock_create_connection.assert_called_once_with("test.db")

        # Check that cursor was called
        self.assertEqual(mock_conn.cursor.call_count, 1)

        # Check that execute was called with the correct SQL and parameters for checking existence
        mock_cursor.execute.assert_any_call("SELECT 1 FROM sheet_thumbnails WHERE sheet_id = ?", ("test_id",))

        # Check that execute was called with the correct SQL and parameters for update
        mock_cursor.execute.assert_any_call(
            """UPDATE sheet_thumbnails
                       SET thumbnail_data = ?, last_modified = ?
                       WHERE sheet_id = ?""",
            (b"thumbnail_data", "2023-01-01", "test_id"),
        )

        # Check that commit was called
        mock_conn.commit.assert_called_once()

        # Check that close was called
        mock_conn.close.assert_called_once()

    @patch("ripperlib.database.get_db_path")
    @patch("ripperlib.database.create_connection")
    def test_get_thumbnail_success(self, mock_create_connection, mock_get_db_path):
        """Test that get_thumbnail retrieves a thumbnail successfully."""
        # Set up the mocks
        mock_get_db_path.return_value = "test.db"
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (b"thumbnail_data", "2023-01-01")
        mock_conn.cursor.return_value = mock_cursor
        mock_create_connection.return_value = mock_conn

        # Call get_thumbnail
        result = get_thumbnail("test_id")

        # Check that the result contains the expected data
        expected_result = {"thumbnail_data": b"thumbnail_data", "last_modified": "2023-01-01"}
        self.assertEqual(result, expected_result)

        # Check that get_db_path was called
        mock_get_db_path.assert_called_once()

        # Check that create_connection was called with the correct path
        mock_create_connection.assert_called_once_with("test.db")

        # Check that cursor was called
        mock_conn.cursor.assert_called_once()

        # Check that execute was called with the correct SQL and parameters
        mock_cursor.execute.assert_called_once_with(
            "SELECT thumbnail_data, last_modified FROM sheet_thumbnails WHERE sheet_id = ?", ("test_id",)
        )

        # Check that fetchone was called
        mock_cursor.fetchone.assert_called_once()

        # Check that close was called
        mock_conn.close.assert_called_once()

    @patch("ripperlib.database.get_db_path")
    @patch("ripperlib.database.create_connection")
    def test_get_thumbnail_not_found(self, mock_create_connection, mock_get_db_path):
        """Test that get_thumbnail returns None when the thumbnail is not found."""
        # Set up the mocks
        mock_get_db_path.return_value = "test.db"
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_create_connection.return_value = mock_conn

        # Call get_thumbnail
        result = get_thumbnail("test_id")

        # Check that the result is None
        self.assertIsNone(result)

    @patch("ripperlib.database.create_table")
    @patch("ripperlib.database.get_db_path")
    def test_init_database(self, mock_get_db_path, mock_create_table):
        """Test that init_database calls create_table with the correct path."""
        # Set up the mock
        mock_get_db_path.return_value = "test.db"

        # Call init_database
        init_database()

        # Check that get_db_path was called
        mock_get_db_path.assert_called_once()

        # Check that create_table was called with the correct path
        mock_create_table.assert_called_once_with("test.db")
