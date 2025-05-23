import json
import logging
import sqlite3 as sqlite
from pathlib import Path

from beartype.typing import Any, Dict, Optional, Tuple, cast

import ripper.ripperlib.defs as defs

# Create a logger for the database module
log = logging.getLogger("ripper:database")


class _db_impl:
    def __init__(self, db_file_path: str | None = None):
        self._db_file_path: str = ""
        if db_file_path is None:
            self._db_file_path = str(Path(defs.get_app_data_dir(log)) / "ripper.db")
        else:
            self._db_file_path = db_file_path

    def open(self) -> None:
        self._conn = None
        try:
            self._conn = sqlite.connect(self._db_file_path)
            if self._conn is not None:
                self._conn.row_factory = sqlite.Row
            log.debug(f"Database path: {self._db_file_path}")
            self.create_tables()
            log.debug("Database initialization complete")
        except sqlite.Error as e:
            log.critical(f"Failed to initialize database at {self._db_file_path}: {e}")
            exit(1)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def execute_query(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[sqlite.Cursor]:
        """
        Execute a SQL query with parameters.

        Args:
            conn: Database connection
            query: SQL query string
            params: Query parameters

        Returns:
            Cursor object or None if execution fails
        """
        try:
            if self._conn is None:
                raise sqlite.Error("Database not open")
            cursor: sqlite.Cursor = self._conn.cursor()
            cursor.execute(query, params)
            return cursor
        except sqlite.Error as e:
            log.error(f"Error executing query: {e}")
            return None

    def clean(self) -> None:
        """
        Clean the database by deleting the file.
        """
        if hasattr(self, "_conn") and self._conn is not None:
            self._conn.close()
        if Path(self._db_file_path).exists():
            log.info(f"Deleting database file {self._db_file_path}")
            Path(self._db_file_path).unlink()

    def create_tables(self) -> None:
        """
        Create the necessary tables in the database if they don't exist.

        Args:
            db_file_path: Path to the database file
        """
        if self._conn is None:
            raise sqlite.Error("Database not open")
        c = self._conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS spreadsheets (
                        spreadsheet_id TEXT PRIMARY KEY,
                        name TEXT,
                        last_modified TEXT,
                        webViewLink TEXT,
                        createdTime TEXT,
                        owners TEXT,
                        size INTEGER,
                        shared INTEGER,
                        thumbnail BLOB
                    );"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS sheet_metadata (
                        spreadsheet_id TEXT PRIMARY KEY,
                        metadata TEXT NOT NULL,
                        FOREIGN KEY (spreadsheet_id) REFERENCES spreadsheets(spreadsheet_id) ON DELETE CASCADE
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
        try:
            if self._conn is None:
                raise sqlite.Error("Database not open")
            c = self._conn.cursor()
            metadata_json = json.dumps(metadata)

            # Ensure spreadsheet_id exists in the spreadsheets table
            c.execute("INSERT OR IGNORE INTO spreadsheets (spreadsheet_id) VALUES (?)", (spreadsheet_id,))

            # Check if metadata already exists for this spreadsheet
            c.execute("SELECT 1 FROM sheet_metadata WHERE spreadsheet_id = ?", (spreadsheet_id,))
            if c.fetchone():
                # Update existing metadata
                c.execute(
                    """UPDATE sheet_metadata
                    SET metadata = ?
                    WHERE spreadsheet_id = ?""",
                    (metadata_json, spreadsheet_id),
                )
            else:
                # Insert new metadata
                c.execute(
                    """INSERT INTO sheet_metadata (spreadsheet_id, metadata)
                    VALUES (?, ?)""",
                    (spreadsheet_id, metadata_json),
                )
            self._conn.commit()
            return True
        except sqlite.Error as e:
            log.error(f"Error storing sheet metadata: {e}")
            return False

    def get_sheet_metadata(self, spreadsheet_id: str, modified_time: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve metadata for all sheets within a spreadsheet from the database if the modified time matches.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            modified_time: The last modified time to check against.

        Returns:
            The metadata dictionary if found and up-to-date, otherwise None.
        """
        try:
            if self._conn is None:
                raise sqlite.Error("Database not open")
            c = self._conn.cursor()
            c.execute("SELECT metadata FROM sheet_metadata WHERE spreadsheet_id = ?", (spreadsheet_id,))
            result = c.fetchone()
            if result:
                stored_metadata_json = result[0]
                return cast(Dict[str, Any], json.loads(stored_metadata_json))
            else:
                log.debug(f"No metadata found for sheets in spreadsheet {spreadsheet_id}.")
            return None
        except sqlite.Error as e:
            log.error(f"Error retrieving sheet metadata: {e}")
            return None

    def store_spreadsheet_thumbnail(self, spreadsheet_id: str, thumbnail_data: bytes, last_modified: str) -> bool:
        """
        Store or update a thumbnail for a spreadsheet in the database.

        Args:
            spreadsheet_id: ID of the Google spreadsheet
            thumbnail_data: Binary thumbnail image data
            last_modified: Timestamp of when the thumbnail was last modified

        Returns:
            True if successful, False otherwise
        """
        try:
            if self._conn is None:
                raise sqlite.Error("Database not open")
            c = self._conn.cursor()
            # Ensure spreadsheet_id exists in the spreadsheets table
            c.execute("INSERT OR IGNORE INTO spreadsheets (spreadsheet_id) VALUES (?)", (spreadsheet_id,))

            # Update last_modified in the spreadsheets table
            c.execute(
                "UPDATE spreadsheets SET last_modified = ? WHERE spreadsheet_id = ?", (last_modified, spreadsheet_id)
            )

            # Update thumbnail_data in the spreadsheets table
            c.execute(
                "UPDATE spreadsheets SET thumbnail = ? WHERE spreadsheet_id = ?", (thumbnail_data, spreadsheet_id)
            )

            self._conn.commit()
            return True
        except sqlite.Error as e:
            log.error(f"Error storing spreadsheet thumbnail: {e}")
            return False

    def get_spreadsheet_thumbnail(self, spreadsheet_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a thumbnail for a spreadsheet from the database.

        Args:
            spreadsheet_id: ID of the Google spreadsheet

        Returns:
            Dictionary containing thumbnail_data and last_modified, or None if not found
        """
        try:
            if self._conn is None:
                raise sqlite.Error("Database not open")
            c = self._conn.cursor()
            c.execute(
                "SELECT thumbnail, last_modified FROM spreadsheets WHERE spreadsheet_id = ?",
                (spreadsheet_id,),
            )
            result = c.fetchone()
            if result:
                return {"thumbnail": result[0], "last_modified": result[1]}
        except sqlite.Error as e:
            log.error(f"Error retrieving spreadsheet thumbnail: {e}")
        return None

    def store_spreadsheet_info(self, spreadsheet_id: str, info: Dict[str, Any]) -> bool:
        """
        Store or update general information for a spreadsheet in the database.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            info: A dictionary containing the spreadsheet information (e.g., name, webViewLink, etc.).

        Returns:
            True if successful, False otherwise.
        """
        try:
            if self._conn is None:
                raise sqlite.Error("Database not open")
            c = self._conn.cursor()

            # Ensure spreadsheet_id exists in the spreadsheets table
            c.execute("INSERT OR IGNORE INTO spreadsheets (spreadsheet_id) VALUES (?)", (spreadsheet_id,))

            # Prepare the update statement with only the provided fields
            update_fields = ", ".join([f"{key} = ?" for key in info.keys()])
            update_values = list(info.values()) + [spreadsheet_id]

            if update_fields:
                c.execute(
                    f"UPDATE spreadsheets SET {update_fields} WHERE spreadsheet_id = ?",
                    update_values,
                )

            self._conn.commit()
            return True
        except sqlite.Error as e:
            log.error(f"Error storing spreadsheet info for {spreadsheet_id}: {e}")
            return False


class Db(_db_impl):
    def __new__(cls, *args: Any, **kwargs: Any) -> "Db":
        if not hasattr(cls, "_instance"):
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance
