"""
Database management for the ripper project.

This module provides the RipperDb class for managing SQLite-based storage of spreadsheet and sheet metadata,
including schema creation, CRUD operations, and thumbnail storage. It also provides a singleton instance `Db` for
application-wide use.
"""

import json
import os
import sqlite3 as sqlite
import uuid
from pathlib import Path

from beartype.typing import Any, Optional, Tuple
from loguru import logger

import ripper.ripperlib.defs as defs
from ripper.ripperlib.defs import SheetProperties, SpreadsheetProperties


def default_db_path() -> Path:
    return Path(defs.get_app_data_dir()) / "ripper.db"


class RipperDb:
    """
    SQLite database manager for spreadsheet and sheet metadata, thumbnails, and related data.

    Handles connection management, schema creation, and CRUD operations for the ripper application.
    """

    def __init__(self, db_file_path: str = str(default_db_path())) -> None:
        """
        Initialize the database implementation and open a connection.

        Args:
            db_file_path (str): Path to the database file.
        """
        self._db_file_path = db_file_path
        self._db_identifier = self.generate_db_identifier()
        logger.info(
            f"Creating new RipperDb instance {self._db_identifier} targeting database file: {str(self._db_file_path)}"
        )
        self._conn: sqlite.Connection | None = None
        self.open()

    @staticmethod
    def generate_db_identifier() -> str:
        """
        Generate a unique identifier for the database.
        """
        return str(uuid.uuid4())

    def open(self) -> None:
        """
        Open the database connection and create tables if they don't exist.

        Raises:
            sqlite.Error: If the database cannot be opened or initialized.
        """
        if self._conn:
            logger.debug(f"Database {self._db_file_path} already open")
            return

        # Ensure the directory exists
        os.makedirs(os.path.dirname(self._db_file_path), exist_ok=True)

        try:
            self._conn = sqlite.connect(self._db_file_path, timeout=20)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=10000")
            self._conn.execute("PRAGMA foreign_keys = ON")
            self.create_tables()
        except sqlite.Error as e:
            logger.error(f"Error opening database {self._db_file_path}: {e}")
            raise

    def close(self) -> None:
        """
        Close the database connection if open.
        """
        if self._conn:
            self._conn.close()
            self._conn = None

    def execute_query(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[sqlite.Cursor]:
        """
        Execute a SQL query with parameters.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Cursor object or None if execution fails
        """
        if self._conn is None:
            logger.error("Database not open")
            return None

        try:
            cursor = self._conn.cursor()
            cursor.execute(query, params)
            if not query.lower().startswith("select"):
                self._conn.commit()  # Commit non-SELECT queries
            return cursor
        except sqlite.Error as e:
            logger.error(f"Error executing query: {e}")
            return None

    def clean(self) -> None:
        """
        Clean the database by deleting the file.
        """
        # Close the connection if it exists
        if self._conn is not None:
            self._conn.close()
            self._conn = None

        # Delete the file if it exists
        if Path(self._db_file_path).exists():
            logger.info(f"Deleting database file {self._db_file_path}")
            try:
                Path(self._db_file_path).unlink()
            except PermissionError:
                logger.warning(f"Could not delete database file {self._db_file_path} - it may be in use")
            except Exception as e:
                logger.error(f"Error deleting database file {self._db_file_path}: {e}")

    def create_tables(self) -> None:
        """
        Create database tables if they don't exist.

        Raises:
            sqlite.Error: If there is an error creating tables.
        """
        if self._conn is None:
            logger.error("Database not open")
            return

        with self._conn:
            c = self._conn.cursor()
            c.execute("PRAGMA foreign_keys = ON")  # Enable foreign key constraints

            c.execute(
                """CREATE TABLE IF NOT EXISTS spreadsheets (
                    spreadsheet_id TEXT PRIMARY KEY,
                    name TEXT,
                    createdTime TEXT,
                    modifiedTime TEXT,
                    webViewLink TEXT,
                    owners TEXT,
                    size INTEGER,
                    shared INTEGER,
                    thumbnailLink TEXT,
                    thumbnail BLOB
                );"""
            )
            c.execute(
                """CREATE TABLE IF NOT EXISTS sheets (
                    sheetId TEXT PRIMARY KEY,
                    spreadsheet_id TEXT NOT NULL,
                    "index" INTEGER,
                    title TEXT,
                    sheetType TEXT,
                    FOREIGN KEY (spreadsheet_id) REFERENCES spreadsheets(spreadsheet_id) ON DELETE CASCADE
                );"""
            )
            c.execute(
                """CREATE TABLE IF NOT EXISTS grid_properties (
                    sheetId TEXT PRIMARY KEY,
                    rowCount INTEGER,
                    columnCount INTEGER,
                    FOREIGN KEY (sheetId) REFERENCES sheets(sheetId) ON DELETE CASCADE
                );"""
            )
            logger.info("Database tables created successfully")

    def store_sheet_properties(self, spreadsheet_id: str, sheet_properties: list[SheetProperties]) -> bool:
        """
        Store or update metadata for all sheets within a spreadsheet in the database.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            sheet_properties: List of sheet properties objects.

        Raises:
            ValueError: If the spreadsheet is not found in the database.
            ValueError: If a sheet is not a grid sheet.
            ValueError: If a sheet has no grid properties.
            sqlite.Error: If there is an error executing the query.
        """
        if self._conn is None:
            logger.error("Database not open")
            return False

        with self._conn:
            c = self._conn.cursor()

            # Check if spreadsheet exists
            c.execute("SELECT COUNT(*) FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            if c.rowcount == 0:
                raise ValueError(
                    f"""Spreadsheet {spreadsheet_id} not found in database. Cannot store sheet metadata without a
                    spreadsheet."""
                )

            # Delete existing sheets and grid_properties for this spreadsheet
            c.execute("DELETE FROM sheets WHERE spreadsheet_id = ?", (spreadsheet_id,))

            # Store new sheet metadata
            for sheet in sheet_properties:
                if sheet.type != "GRID":
                    logger.warning(f"Sheet {sheet.id} of spreadsheet {spreadsheet_id} is not a grid sheet. Skipping.")
                    continue

                grid_props = sheet.grid
                if not grid_props:
                    raise ValueError(
                        f"""Sheet {sheet.id} of spreadsheet {spreadsheet_id} is a grid sheet but has no
                        grid properties."""
                    )
                c.execute(
                    """INSERT INTO sheets (spreadsheet_id, sheetId, "index", title, sheetType)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(sheetId) DO UPDATE SET spreadsheet_id=excluded.spreadsheet_id,
                                                          "index"=excluded."index",
                                                          title=excluded.title,
                                                          sheetType=excluded.sheetType""",
                    (
                        spreadsheet_id,
                        sheet.id,
                        sheet.index,
                        sheet.title,
                        sheet.type,
                    ),
                )
                c.execute(
                    """INSERT INTO grid_properties (sheetId, rowCount, columnCount)
                       VALUES (?, ?, ?)
                       ON CONFLICT(sheetId) DO UPDATE SET rowCount=excluded.rowCount,
                                                          columnCount=excluded.columnCount""",
                    (sheet.id, grid_props.row_count, grid_props.column_count),
                )

            return True

    def get_sheet_properties_of_spreadsheet(self, spreadsheet_id: str) -> list[SheetProperties]:
        """
        Retrieve sheet metadata from the database.

        Args:
            spreadsheet_id: The ID of the spreadsheet.

        Raises:
            sqlite.Error: If there is an error executing the query.

        Returns:
            List of sheet metadata dictionaries or empty list if no sheets are found.
        """
        if self._conn is None:
            logger.error("Database not open")
            return []

        with self._conn:
            c = self._conn.cursor()

            # Get all sheets for this spreadsheet
            c.execute(
                """SELECT s.sheetId, s."index", s.title, s.sheetType,
                          g.rowCount, g.columnCount
                   FROM sheets s
                   LEFT JOIN grid_properties g ON s.sheetId = g.sheetId
                   WHERE s.spreadsheet_id = ?
                   ORDER BY s."index" """,
                (spreadsheet_id,),
            )
            sheets = []
            for row in c.fetchall():
                sheet = SheetProperties()
                sheet.id = row[0]
                sheet.index = row[1]
                sheet.title = row[2]
                sheet.type = row[3]
                if row[4] is not None and row[5] is not None:
                    sheet.grid = SheetProperties.GridProperties(row_count=row[4], column_count=row[5])
                sheets.append(sheet)

            return sheets

    def store_spreadsheet_thumbnail(self, spreadsheet_id: str, thumbnail: bytes) -> None:
        """
        Store or update a spreadsheet's thumbnail in the database.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            thumbnail: The binary thumbnail data.

        Raises:
            ValueError: If the spreadsheet is not found in the database.
            sqlite.Error: If there is an error executing the query.
        """
        if self._conn is None:
            logger.error("Database not open")
            return

        with self._conn:
            c = self._conn.cursor()

            # Check if spreadsheet exists
            c.execute("SELECT COUNT(*) FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            if c.rowcount == 0:
                raise ValueError(
                    f"Spreadsheet {spreadsheet_id} not found in database. Cannot store thumbnail without a spreadsheet."
                )

            c.execute(
                "UPDATE spreadsheets SET thumbnail = ? WHERE spreadsheet_id = ?",
                (thumbnail, spreadsheet_id),
            )

    def get_spreadsheet_thumbnail(self, spreadsheet_id: str) -> bytes | None:
        """
        Retrieve a spreadsheet's thumbnail from the database.

        Args:
            spreadsheet_id: The ID of the spreadsheet.

        Returns:
            Thumbnail data or None if not found.
        """
        if self._conn is None:
            logger.error("Database not open")
            return None

        with self._conn:
            c = self._conn.cursor()
            c.execute("SELECT thumbnail FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            result = c.fetchone()
            thumbnail = result[0] if result else None
        return thumbnail

    def store_spreadsheet_properties(self, spreadsheet_id: str, spreadsheet_properties: SpreadsheetProperties) -> bool:
        """
        Store or update spreadsheet information in the database. If the spreadsheet already esists, and the metadata
        modifiedTime is different, the sheets and thumbnail will be deleted.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            spreadsheet_properties: SpreadsheetProperties object to store.

        Raises:
            ValueError: If a required spreadsheet metadata field is missing.
            sqlite.Error: If there is an error executing the query.
        """
        if self._conn is None:
            logger.error("Database not open")
            return False

        with self._conn:
            c = self._conn.cursor()

            # Check if spreadsheet exists and get the current modifiedTime if so
            c.execute("SELECT modifiedTime FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            result = c.fetchone()
            if result:
                # If modifiedTime is being updated and is different, invalidate related data
                current_modified_time = result[0]
                if spreadsheet_properties.modified_time != current_modified_time:
                    # Delete sheets first (this will cascade to grid_properties due to ON DELETE CASCADE)
                    c.execute("DELETE FROM sheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
                    # Set thumbnail to NULL
                    c.execute("UPDATE spreadsheets SET thumbnail = NULL WHERE spreadsheet_id = ?", (spreadsheet_id,))

            # Check if spreadsheet exists and if it does, update it, otherwise insert it
            c.execute(
                """INSERT INTO spreadsheets
                   (spreadsheet_id, name, modifiedTime, createdTime, owners, size, shared, webViewLink, thumbnailLink)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(spreadsheet_id) DO UPDATE SET name=excluded.name,
                                                             modifiedTime=excluded.modifiedTime,
                                                             createdTime=excluded.createdTime,
                                                             owners=excluded.owners,
                                                             size=excluded.size,
                                                             shared=excluded.shared,
                                                             webViewLink=excluded.webViewLink,
                                                             thumbnailLink=excluded.thumbnailLink""",
                (
                    spreadsheet_id,
                    spreadsheet_properties.name,
                    spreadsheet_properties.modified_time,
                    spreadsheet_properties.created_time,
                    json.dumps(spreadsheet_properties.owners),
                    spreadsheet_properties.size,
                    spreadsheet_properties.shared,
                    spreadsheet_properties.web_view_link,
                    spreadsheet_properties.thumbnail_link,
                ),
            )
        return True


# Primary database instance
Db = RipperDb()
