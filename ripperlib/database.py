import logging
import os
import sqlite3
from sqlite3 import Error
from typing import Optional, Dict, List, Any
from queue import Queue
from threading import Lock

log = logging.getLogger("ripper:database")

# Flag to track if database path has been logged
_db_path_logged = False

# Connection pool
class ConnectionPool:
    def __init__(self, db_file_path: str, pool_size: int = 5):
        self.db_file_path = db_file_path
        self.pool_size = pool_size
        self.pool = Queue(maxsize=pool_size)
        self.lock = Lock()
        self._initialize_pool()

    def _initialize_pool(self):
        for _ in range(self.pool_size):
            conn = sqlite3.connect(self.db_file_path)
            self.pool.put(conn)

    def get_connection(self) -> sqlite3.Connection:
        with self.lock:
            return self.pool.get()

    def release_connection(self, conn: sqlite3.Connection):
        with self.lock:
            self.pool.put(conn)

    def close_all_connections(self):
        while not self.pool.empty():
            conn = self.pool.get()
            conn.close()

def get_db_path(db_file_name: str = "ripper.db") -> str:
    """
    Get the absolute path for the database file.

    Args:
        db_file_name: Name of the database file. Defaults to "ripper.db".

    Returns:
        The absolute path to the database file.
    """
    # Use the user's app data directory for Windows
    app_data_dir = os.path.join(os.environ.get("APPDATA", ""), "ripper")

    # Create the directory if it doesn't exist
    if not os.path.exists(app_data_dir):
        try:
            os.makedirs(app_data_dir)
            log.debug(f"Created database directory: {app_data_dir}")
        except Exception as e:
            log.error(f"Failed to create database directory: {e}")
            # Fall back to current directory if we can't create the app data directory
            app_data_dir = os.getcwd()
            log.debug(f"Using current directory for database: {app_data_dir}")

    db_path = os.path.join(app_data_dir, db_file_name)
    return db_path

# Initialize connection pool
connection_pool = ConnectionPool(get_db_path())

def create_connection(db_file_path: str) -> Optional[sqlite3.Connection]:
    """
    Create a database connection to the SQLite database specified by db_file_path.

    Args:
        db_file_path: Path to the database file

    Returns:
        Connection object or None if connection fails
    """
    global _db_path_logged
    conn = None
    try:
        conn = sqlite3.connect(db_file_path)
        # Log the database path only on the first successful connection
        if not _db_path_logged:
            log.debug(f"Database path: {db_file_path}")
            _db_path_logged = True
    except Error as e:
        log.error(f"Database connection error: {e}")
    return conn


def create_table(db_file_path: str) -> None:
    """
    Create the necessary tables in the database if they don't exist.

    Args:
        db_file_path: Path to the database file
    """
    conn = create_connection(db_file_path)
    if conn is not None:
        try:
            c = conn.cursor()
            c.execute(
                """CREATE TABLE IF NOT EXISTS transactions (
                            id INTEGER PRIMARY KEY,
                            date TEXT NOT NULL,
                            description TEXT NOT NULL,
                            amount REAL NOT NULL,
                            category TEXT NOT NULL
                        );"""
            )
            c.execute(
                """CREATE TABLE IF NOT EXISTS data_sources (
                            id INTEGER PRIMARY KEY,
                            source_name TEXT NOT NULL,
                            spreadsheet_id TEXT NOT NULL,
                            sheet_name TEXT NOT NULL,
                            cell_range TEXT NOT NULL
                        );"""
            )
            c.execute(
                """CREATE TABLE IF NOT EXISTS sheet_thumbnails (
                            sheet_id TEXT PRIMARY KEY,
                            thumbnail_data BLOB NOT NULL,
                            last_modified TEXT NOT NULL
                        );"""
            )
            # Add indexes on frequently queried columns
            c.execute("CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions (date);")
            c.execute("CREATE INDEX IF NOT EXISTS idx_transactions_description ON transactions (description);")
            c.execute("CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions (category);")
            conn.commit()
        except Error as e:
            log.error(f"Error creating tables: {e}")
        finally:
            conn.close()


def insert_transaction(transaction: Dict[str, Any], db_file_path: Optional[str] = None) -> bool:
    """
    Insert a transaction into the database.

    Args:
        transaction: Dictionary containing transaction data with keys: date, description, amount, category
        db_file_path: Path to the database file. If None, uses default path.

    Returns:
        True if successful, False otherwise
    """
    if db_file_path is None:
        db_file_path = get_db_path()
    conn = create_connection(db_file_path)
    if conn is not None:
        try:
            c = conn.cursor()
            c.execute(
                """INSERT INTO transactions (date, description, amount, category)
                         VALUES (?, ?, ?, ?)""",
                (transaction["date"], transaction["description"], transaction["amount"], transaction["category"]),
            )
            conn.commit()
            return True
        except Error as e:
            log.error(f"Error inserting transaction: {e}")
            return False
        finally:
            conn.close()
    return False


def insert_transactions(transactions: List[Dict[str, Any]], db_file_path: Optional[str] = None) -> bool:
    """
    Insert multiple transactions into the database in a single transaction.

    Args:
        transactions: List of dictionaries containing transaction data with keys: date, description, amount, category
        db_file_path: Path to the database file. If None, uses default path.

    Returns:
        True if successful, False otherwise
    """
    if db_file_path is None:
        db_file_path = get_db_path()
    conn = create_connection(db_file_path)
    if conn is not None:
        try:
            c = conn.cursor()
            c.executemany(
                """INSERT INTO transactions (date, description, amount, category)
                         VALUES (?, ?, ?, ?)""",
                [(t["date"], t["description"], t["amount"], t["category"]) for t in transactions],
            )
            conn.commit()
            return True
        except Error as e:
            log.error(f"Error inserting transactions: {e}")
            return False
        finally:
            conn.close()
    return False


def retrieve_transactions(db_file_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieve all transactions from the database.

    Args:
        db_file_path: Path to the database file. If None, uses default path.

    Returns:
        List of dictionaries containing transaction data
    """
    if db_file_path is None:
        db_file_path = get_db_path()
    conn = create_connection(db_file_path)
    transactions = []
    if conn is not None:
        try:
            c = conn.cursor()
            c.execute("SELECT * FROM transactions")
            rows = c.fetchall()
            for row in rows:
                transaction = {"date": row[1], "description": row[2], "amount": row[3], "category": row[4]}
                transactions.append(transaction)
        except Error as e:
            log.error(f"Error retrieving transactions: {e}")
        finally:
            conn.close()
    return transactions


def insert_data_source(
    source_name: str, spreadsheet_id: str, sheet_name: str, cell_range: str, db_file_path: Optional[str] = None
) -> bool:
    """
    Insert a data source into the database.

    Args:
        source_name: Name of the data source
        spreadsheet_id: ID of the Google spreadsheet
        sheet_name: Name of the sheet within the spreadsheet
        cell_range: Range of cells to read (e.g., 'A1:Z100')
        db_file_path: Path to the database file. If None, uses default path.

    Returns:
        True if successful, False otherwise
    """
    if db_file_path is None:
        db_file_path = get_db_path()
    conn = create_connection(db_file_path)
    if conn is not None:
        try:
            c = conn.cursor()
            c.execute(
                """INSERT INTO data_sources (source_name, spreadsheet_id, sheet_name, cell_range)
                   VALUES (?, ?, ?, ?)""",
                (source_name, spreadsheet_id, sheet_name, cell_range),
            )
            conn.commit()
            return True
        except Error as e:
            log.error(f"Error inserting data source: {e}")
            return False
        finally:
            conn.close()
    return False


def store_thumbnail(
    sheet_id: str, thumbnail_data: bytes, last_modified: str, db_file_path: Optional[str] = None
) -> bool:
    """
    Store or update a sheet thumbnail in the database.

    Args:
        sheet_id: ID of the Google sheet
        thumbnail_data: Binary thumbnail image data
        last_modified: Timestamp of when the thumbnail was last modified
        db_file_path: Path to the database file. If None, uses default path.

    Returns:
        True if successful, False otherwise
    """
    if db_file_path is None:
        db_file_path = get_db_path()
    conn = create_connection(db_file_path)
    if conn is not None:
        try:
            c = conn.cursor()
            # Check if the thumbnail already exists
            c.execute("SELECT 1 FROM sheet_thumbnails WHERE sheet_id = ?", (sheet_id,))
            if c.fetchone():
                # Update existing thumbnail
                c.execute(
                    """UPDATE sheet_thumbnails 
                       SET thumbnail_data = ?, last_modified = ?
                       WHERE sheet_id = ?""",
                    (thumbnail_data, last_modified, sheet_id),
                )
            else:
                # Insert new thumbnail
                c.execute(
                    """INSERT INTO sheet_thumbnails (sheet_id, thumbnail_data, last_modified)
                       VALUES (?, ?, ?)""",
                    (sheet_id, thumbnail_data, last_modified),
                )
            conn.commit()
            return True
        except Error as e:
            log.error(f"Error storing thumbnail: {e}")
            return False
        finally:
            conn.close()
    return False


def get_thumbnail(sheet_id: str, db_file_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve a sheet thumbnail from the database.

    Args:
        sheet_id: ID of the Google sheet
        db_file_path: Path to the database file. If None, uses default path.

    Returns:
        Dictionary containing thumbnail_data and last_modified, or None if not found
    """
    if db_file_path is None:
        db_file_path = get_db_path()
    conn = create_connection(db_file_path)
    if conn is not None:
        try:
            c = conn.cursor()
            c.execute("SELECT thumbnail_data, last_modified FROM sheet_thumbnails WHERE sheet_id = ?", (sheet_id,))
            result = c.fetchone()
            if result:
                return {"thumbnail_data": result[0], "last_modified": result[1]}
            return None
        except Error as e:
            log.error(f"Error retrieving thumbnail: {e}")
            return None
        finally:
            conn.close()
    return None


def init_database():
    """Initialize the database by creating necessary tables."""
    create_table(get_db_path())


# Initialize database when module is imported
init_database()
