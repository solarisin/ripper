import os
import sqlite3
import logging
from pathlib import Path
from sqlite3 import Error

log = logging.getLogger("ripper:database")

def get_db_path(db_file_name="ripper.db"):
    """Get the absolute path for the database file"""
    # Use the user's app data directory for Windows
    app_data_dir = os.path.join(os.environ.get('APPDATA', ''), 'ripper')

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
    log.debug(f"Database path: {db_path}")
    return db_path


def create_connection(db_file_path):
    conn = None
    try:
        conn = sqlite3.connect(db_file_path)
    except Error as e:
        log.error(f"Database connection error: {e}")
    return conn


def create_table(db_file_path):
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
            conn.commit()
        except Error as e:
            log.error(f"Error creating tables: {e}")
        finally:
            conn.close()


def insert_transaction(transaction, db_file_path=None):
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
        except Error as e:
            log.error(f"Error inserting transaction: {e}")
        finally:
            conn.close()


def retrieve_transactions(db_file_path=None):
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


def insert_data_source(source_name, spreadsheet_id, sheet_name, cell_range, db_file_path=None):
    if db_file_path is None:
        db_file_path = get_db_path()
    conn = create_connection(db_file_path)
    if conn is not None:
        try:
            # TODO
            conn.commit()
        except Error as e:
            log.error(f"Error inserting data source: {e}")
        finally:
            conn.close()


def store_thumbnail(sheet_id, thumbnail_data, last_modified, db_file_path=None):
    """Store or update a sheet thumbnail in the database"""
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


def get_thumbnail(sheet_id, db_file_path=None):
    """Retrieve a sheet thumbnail from the database"""
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


# Create tables with absolute database file path
create_table(get_db_path())
