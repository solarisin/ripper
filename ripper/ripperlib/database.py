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
            self._db_file_path = Path(defs.get_app_data_dir(log)) / "ripper.db"
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
            """CREATE TABLE IF NOT EXISTS spreadsheet_thumbnails (
                        spreadsheet_id TEXT PRIMARY KEY,
                        thumbnail_data BLOB NOT NULL,
                        last_modified TEXT NOT NULL
                    );"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS sheet_metadata (
                        spreadsheet_id TEXT PRIMARY KEY,
                        modified_time TEXT NOT NULL,
                        metadata TEXT NOT NULL
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

            # Check if metadata already exists for this spreadsheet
            c.execute("SELECT 1 FROM sheet_metadata WHERE spreadsheet_id = ?", (spreadsheet_id,))
            if c.fetchone():
                # Update existing metadata
                c.execute(
                    """UPDATE sheet_metadata
                    SET modified_time = ?, metadata = ?
                    WHERE spreadsheet_id = ?""",
                    (modified_time, metadata_json, spreadsheet_id),
                )
            else:
                # Insert new metadata
                c.execute(
                    """INSERT INTO sheet_metadata (spreadsheet_id, modified_time, metadata)
                    VALUES (?, ?, ?)""",
                    (spreadsheet_id, modified_time, metadata_json),
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
            c.execute("SELECT modified_time, metadata FROM sheet_metadata WHERE spreadsheet_id = ?", (spreadsheet_id,))
            result = c.fetchone()
            if result:
                stored_modified_time, stored_metadata_json = result
                if stored_modified_time == modified_time:
                    return cast(Dict[str, Any], json.loads(stored_metadata_json))
                else:
                    log.debug(f"Metadata for sheets in spreadsheet {spreadsheet_id} is outdated.")
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
            # Check if the thumbnail already exists
            c.execute("SELECT 1 FROM spreadsheet_thumbnails WHERE spreadsheet_id = ?", (spreadsheet_id,))
            if c.fetchone():
                # Update existing thumbnail
                c.execute(
                    """UPDATE spreadsheet_thumbnails
                    SET thumbnail_data = ?, last_modified = ?
                    WHERE spreadsheet_id = ?""",
                    (thumbnail_data, last_modified, spreadsheet_id),
                )
            else:
                # Insert new thumbnail
                c.execute(
                    """INSERT INTO spreadsheet_thumbnails (spreadsheet_id, thumbnail_data, last_modified)
                    VALUES (?, ?, ?)""",
                    (spreadsheet_id, thumbnail_data, last_modified),
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
                "SELECT thumbnail_data, last_modified FROM spreadsheet_thumbnails WHERE spreadsheet_id = ?",
                (spreadsheet_id,),
            )
            result = c.fetchone()
            if result:
                return {"thumbnail_data": result[0], "last_modified": result[1]}
        except sqlite.Error as e:
            log.error(f"Error retrieving spreadsheet thumbnail: {e}")
        return None


class Db(_db_impl):
    def __new__(cls, *args: Any, **kwargs: Any) -> "Db":
        if not hasattr(cls, "_instance"):
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance
