import os
import sqlite3 as sqlite
from pathlib import Path

from beartype.typing import Any, Dict, Optional, Tuple
from loguru import logger

import ripper.ripperlib.defs as defs


def default_db_path() -> Path:
    return Path(defs.get_app_data_dir()) / "ripper.db"


class _db_impl:
    def __init__(self, db_file_path: str | None = None) -> None:
        """
        Initialize the database implementation.

        Args:
            db_file_path: Path to the database file
        """
        self._db_file_path = db_file_path or str(default_db_path())
        logger.info(f"Database path: {self._db_file_path}")
        self._conn: sqlite.Connection | None = None

    def migrate_schema(self) -> None:
        """
        Migrate the database schema to the latest version.
        This method should be called after creating tables to ensure all necessary columns exist.
        """
        if self._conn is None:
            raise sqlite.Error("Database not open")

        c = self._conn.cursor()
        try:
            # Check if thumbnailLink column exists in spreadsheets table
            c.execute("PRAGMA table_info(spreadsheets)")
            columns = {row[1] for row in c.fetchall()}

            if "thumbnailLink" not in columns:
                logger.info("Adding thumbnailLink column to spreadsheets table")
                c.execute("ALTER TABLE spreadsheets ADD COLUMN thumbnailLink TEXT")
                self._conn.commit()

        except sqlite.Error as e:
            logger.error(f"Error migrating database schema: {e}")
            raise

    def open(self) -> None:
        """
        Open the database connection and create tables if they don't exist.
        """
        if self._conn is not None:
            return

        # Ensure the directory exists
        os.makedirs(os.path.dirname(self._db_file_path), exist_ok=True)

        try:
            # Add timeout and enable WAL mode for better concurrency
            self._conn = sqlite.connect(self._db_file_path, timeout=20)
            self._conn.execute("PRAGMA journal_mode=WAL")  # Enable Write-Ahead Logging
            self._conn.execute("PRAGMA busy_timeout=10000")  # Set busy timeout to 10 seconds
            self._conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign key constraints
            self.create_tables()
            self.migrate_schema()
        except sqlite.Error as e:
            logger.error(f"Error opening database {self._db_file_path}: {e}")
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
            Db._current_path = None  # Reset the current path when closing

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
        """Create database tables if they don't exist."""
        if self._conn is None:
            logger.error("Database not open")
            return

        c = self._conn.cursor()
        c.execute("PRAGMA foreign_keys = ON")  # Enable foreign key constraints

        c.execute(
            """CREATE TABLE IF NOT EXISTS spreadsheets (
                spreadsheet_id TEXT PRIMARY KEY,
                name TEXT,
                modifiedTime TEXT,
                webViewLink TEXT,
                createdTime TEXT,
                owners TEXT,
                size INTEGER,
                shared INTEGER,
                thumbnail BLOB,
                thumbnailLink TEXT
            );"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS sheets (
                spreadsheet_id TEXT NOT NULL,
                sheetId TEXT PRIMARY KEY,
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
        self._conn.commit()

    def store_sheet_metadata(self, spreadsheet_id: str, metadata: dict, modified_time: str) -> bool:
        """
        Store or update metadata for all sheets within a spreadsheet in the database.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            metadata: The sheet metadata dictionary.
            modified_time: The last modified time of the spreadsheet.

        Returns:
            True if successful, False otherwise.
        """
        if self._conn is None:
            logger.error("Database not open")
            return False

        try:
            c = self._conn.cursor()

            # Check if spreadsheet exists
            c.execute("SELECT * FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            existing_spreadsheet = c.fetchone()

            if existing_spreadsheet:
                # Update only the modifiedTime if spreadsheet exists
                c.execute(
                    "UPDATE spreadsheets SET modifiedTime = ? WHERE spreadsheet_id = ?",
                    (modified_time, spreadsheet_id),
                )
            else:
                # Insert new spreadsheet with minimal data
                c.execute(
                    "INSERT INTO spreadsheets (spreadsheet_id, modifiedTime) VALUES (?, ?)",
                    (spreadsheet_id, modified_time),
                )

            # Delete existing sheets and grid_properties for this spreadsheet
            c.execute("DELETE FROM sheets WHERE spreadsheet_id = ?", (spreadsheet_id,))

            # Store new sheet metadata
            for sheet in metadata.get("sheets", []):
                sheet_id = str(sheet["sheetId"])
                c.execute(
                    """INSERT INTO sheets (spreadsheet_id, sheetId, "index", title, sheetType)
                    VALUES (?, ?, ?, ?, ?)""",
                    (
                        spreadsheet_id,
                        sheet_id,
                        sheet["index"],
                        sheet["title"],
                        sheet["sheetType"],
                    ),
                )

                # Store grid properties if present
                if "gridProperties" in sheet and isinstance(sheet["gridProperties"], dict):
                    grid_props = sheet["gridProperties"]
                    if "rowCount" in grid_props and "columnCount" in grid_props:
                        c.execute(
                            """INSERT INTO grid_properties (sheetId, rowCount, columnCount)
                            VALUES (?, ?, ?)""",
                            (sheet_id, grid_props["rowCount"], grid_props["columnCount"]),
                        )

            self._conn.commit()
            return True
        except sqlite.Error as e:
            logger.error(f"Error storing sheet metadata: {e}")
            return False

    def get_sheet_metadata(self, spreadsheet_id: str, modified_time: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve sheet metadata from the database.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            modified_time: The last modified time of the spreadsheet.

        Returns:
            Dictionary containing sheet metadata or None if not found or outdated.
        """
        if self._conn is None:
            logger.error("Database not open")
            return None

        try:
            c = self._conn.cursor()

            # Check if spreadsheet exists and modifiedTime matches
            c.execute(
                """SELECT modifiedTime FROM spreadsheets
                WHERE spreadsheet_id = ?""",
                (spreadsheet_id,),
            )
            result = c.fetchone()
            if not result or result[0] != modified_time:
                return None

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
                sheet = {
                    "sheetId": row[0],
                    "index": row[1],
                    "title": row[2],
                    "sheetType": row[3],
                }
                if row[4] is not None and row[5] is not None:  # If grid properties exist
                    sheet["gridProperties"] = {"rowCount": row[4], "columnCount": row[5]}
                sheets.append(sheet)

            return {"sheets": sheets} if sheets else None
        except sqlite.Error as e:
            logger.error(f"Error retrieving sheet metadata: {e}")
            return None

    def store_spreadsheet_thumbnail(self, spreadsheet_id: str, thumbnail_data: bytes, modified_time: str) -> bool:
        """
        Store or update a spreadsheet's thumbnail in the database.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            thumbnail_data: The binary thumbnail data.
            modified_time: The last modified time of the spreadsheet.

        Returns:
            True if successful, False otherwise.
        """
        if self._conn is None:
            logger.error("Database not open")
            return False

        try:
            c = self._conn.cursor()

            # Check if spreadsheet exists
            c.execute("SELECT * FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            existing_spreadsheet = c.fetchone()

            if existing_spreadsheet:
                # Update only the thumbnail if spreadsheet exists
                c.execute(
                    "UPDATE spreadsheets SET thumbnail = ? WHERE spreadsheet_id = ?",
                    (thumbnail_data, spreadsheet_id),
                )
            else:
                logger.warning(f"Creating new spreadsheet record for {spreadsheet_id} when storing thumbnail")
                # Insert new spreadsheet with thumbnail data and the provided modifiedTime
                # We include modifiedTime here because a spreadsheet entry should have it,
                # but the thumbnail storage doesn't imply the modifiedTime has changed.
                c.execute(
                    "INSERT INTO spreadsheets (spreadsheet_id, modifiedTime, thumbnail) VALUES (?, ?, ?)",
                    (spreadsheet_id, modified_time, thumbnail_data),
                )

            self._conn.commit()
            return True
        except sqlite.Error as e:
            logger.error(f"Error storing spreadsheet thumbnail: {e}")
            return False

    def get_spreadsheet_thumbnail(self, spreadsheet_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a spreadsheet's thumbnail from the database.

        Args:
            spreadsheet_id: The ID of the spreadsheet.

        Returns:
            Dictionary containing thumbnail data and modified time, or None if not found.
        """
        if self._conn is None:
            logger.error("Database not open")
            return None

        try:
            c = self._conn.cursor()
            c.execute(
                """SELECT thumbnail, modifiedTime FROM spreadsheets
                WHERE spreadsheet_id = ?""",
                (spreadsheet_id,),
            )
            result = c.fetchone()
            if result:
                return {"thumbnail": result[0], "modifiedTime": result[1]}
            return {"thumbnail": None, "modifiedTime": None}
        except sqlite.Error as e:
            logger.error(f"Error retrieving spreadsheet thumbnail: {e}")
            return None

    def store_spreadsheet_info(self, spreadsheet_id: str, info: Dict[str, Any]) -> bool:
        """
        Store or update spreadsheet information in the database.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            info: Dictionary containing spreadsheet information.

        Returns:
            True if successful, False otherwise.
        """
        if self._conn is None:
            logger.error("Database not open")
            return False

        try:
            c = self._conn.cursor()

            # Check if spreadsheet exists and get current modifiedTime
            c.execute("SELECT modifiedTime FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            result = c.fetchone()
            current_modified_time = result[0] if result else None

            # If modifiedTime is being updated and is different, invalidate related data
            if "modifiedTime" in info and info["modifiedTime"] != current_modified_time:
                # Delete sheets first (this will cascade to grid_properties due to ON DELETE CASCADE)
                c.execute("DELETE FROM sheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
                # Set thumbnail to NULL
                c.execute("UPDATE spreadsheets SET thumbnail = NULL WHERE spreadsheet_id = ?", (spreadsheet_id,))

            if result:
                # Update existing spreadsheet
                fields = []
                values = []
                for key, value in info.items():
                    if key != "spreadsheet_id":  # Don't update the ID
                        fields.append(f"{key} = ?")
                        values.append(value)
                values.append(spreadsheet_id)  # Add ID for WHERE clause
                update_query = f"""UPDATE spreadsheets
                    SET {', '.join(fields)}
                    WHERE spreadsheet_id = ?"""
                c.execute(update_query, tuple(values))
            else:
                # Insert new spreadsheet
                fields = ["spreadsheet_id"] + list(info.keys())
                values = [spreadsheet_id] + list(info.values())
                placeholders = ",".join("?" * len(fields))
                insert_query = f"""INSERT INTO spreadsheets ({', '.join(fields)})
                    VALUES ({placeholders})"""
                c.execute(insert_query, tuple(values))

            self._conn.commit()
            return True
        except sqlite.Error as e:
            logger.error(f"Error storing spreadsheet info: {e}")
            return False


class Db(_db_impl):
    """
    Singleton database class.
    """

    _instance: Optional["Db"] = None
    _current_path: Optional[str] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "Db":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.__initialized = False
        return cls._instance

    def __init__(self, db_file_path: str | None = None) -> None:
        if not getattr(self, "__initialized", False):
            super().__init__(db_file_path)
            self.open()
            self.__initialized = True
            Db._current_path = self._db_file_path
        elif db_file_path is not None and db_file_path != Db._current_path:
            # If a new path is provided and it's different from the current one
            # Close the current connection
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            # Initialize with the new path
            super().__init__(db_file_path)
            self.open()
            Db._current_path = self._db_file_path

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            Db._current_path = None  # Reset the current path when closing
