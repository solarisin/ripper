import sqlite3 as sqlite
from pathlib import Path

from beartype.typing import Any, Dict, Optional, Tuple
from loguru import logger

import ripper.ripperlib.defs as defs


def default_db_path() -> Path:
    return Path(defs.get_app_data_dir()) / "ripper.db"


class _db_impl:
    def __init__(self, db_file_path: str | None = None):
        self._db_file_path: str = ""
        if db_file_path is None:
            self._db_file_path = str(default_db_path())
        else:
            self._db_file_path = db_file_path

    def open(self) -> None:
        self._conn = None
        try:
            self._conn = sqlite.connect(self._db_file_path)
            if self._conn is not None:
                self._conn.row_factory = sqlite.Row
            logger.debug(f"Database path: {self._db_file_path}")
            self.create_tables()
            logger.debug("Database initialization complete")
        except sqlite.Error as e:
            logger.critical(f"Failed to initialize database at {self._db_file_path}: {e}")
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
            logger.error(f"Error executing query: {e}")
            return None

    def clean(self) -> None:
        """
        Clean the database by deleting the file.
        """
        if hasattr(self, "_conn") and self._conn is not None:
            self._conn.close()
        if Path(self._db_file_path).exists():
            logger.info(f"Deleting database file {self._db_file_path}")
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
                        modifiedTime TEXT,
                        webViewLink TEXT,
                        createdTime TEXT,
                        owners TEXT,
                        size INTEGER,
                        shared INTEGER,
                        thumbnail BLOB
                    );"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS sheets (
                        spreadsheet_id TEXT,
                        sheetId TEXT,
                        "index" INTEGER,
                        title TEXT,
                        sheetType TEXT,
                        FOREIGN KEY (spreadsheet_id) REFERENCES spreadsheets(spreadsheet_id) ON DELETE CASCADE
                    );"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS grid_properties (
                        sheetId TEXT,
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
        try:
            if self._conn is None:
                raise sqlite.Error("Database not open")
            c = self._conn.cursor()

            # Ensure spreadsheet_id exists in the spreadsheets table
            c.execute(
                """INSERT OR IGNORE INTO spreadsheets (spreadsheet_id, modifiedTime)
                VALUES (?, ?)""",
                (spreadsheet_id, modified_time),
            )

            # Update modifiedTime if it exists
            c.execute(
                """UPDATE spreadsheets
                SET modifiedTime = ?
                WHERE spreadsheet_id = ?""",
                (modified_time, spreadsheet_id),
            )

            # Insert or update sheet metadata into sheets and grid_properties tables
            if "sheets" in metadata:
                for sheet in metadata["sheets"]:
                    # Check if the sheet already exists
                    c.execute(
                        """SELECT 1 FROM sheets
                        WHERE spreadsheet_id = ? AND sheetId = ?""",
                        (spreadsheet_id, sheet["sheetId"]),
                    )
                    sheet_exists = c.fetchone() is not None

                    if sheet_exists:
                        # Update existing sheet
                        c.execute(
                            """UPDATE sheets
                            SET "index" = ?, title = ?, sheetType = ?
                            WHERE spreadsheet_id = ? AND sheetId = ?""",
                            (sheet["index"], sheet["title"], sheet["sheetType"], spreadsheet_id, sheet["sheetId"]),
                        )
                    else:
                        # Insert new sheet
                        c.execute(
                            """INSERT INTO sheets (spreadsheet_id, sheetId, "index", title, sheetType)
                            VALUES (?, ?, ?, ?, ?)""",
                            (spreadsheet_id, sheet["sheetId"], sheet["index"], sheet["title"], sheet["sheetType"]),
                        )

                    # Update or insert grid_properties
                    if "gridProperties" in sheet:
                        grid_props = sheet["gridProperties"]
                        # Check if grid properties already exist
                        c.execute(
                            """SELECT 1 FROM grid_properties
                            WHERE sheetId = ?""",
                            (sheet["sheetId"],),
                        )
                        grid_exists = c.fetchone() is not None

                        if grid_exists:
                            # Update existing grid properties
                            c.execute(
                                """UPDATE grid_properties
                                SET rowCount = ?, columnCount = ?
                                WHERE sheetId = ?""",
                                (grid_props["rowCount"], grid_props["columnCount"], sheet["sheetId"]),
                            )
                        else:
                            # Insert new grid properties
                            c.execute(
                                """INSERT INTO grid_properties (sheetId, rowCount, columnCount)
                                VALUES (?, ?, ?)""",
                                (sheet["sheetId"], grid_props["rowCount"], grid_props["columnCount"]),
                            )

            self._conn.commit()
            return True
        except sqlite.Error as e:
            logger.error(f"Error storing sheet metadata: {e}")
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

            # Check if the spreadsheet exists and if the modified time matches
            c.execute(
                """SELECT modifiedTime FROM spreadsheets
                WHERE spreadsheet_id = ?""",
                (spreadsheet_id,),
            )
            result = c.fetchone()

            if not result:
                logger.debug(f"No spreadsheet found with ID {spreadsheet_id}.")
                return None

            stored_modified_time = result[0]
            if stored_modified_time != modified_time:
                logger.debug(f"Spreadsheet {spreadsheet_id} has been modified. Cached metadata is outdated.")
                return None

            # Retrieve sheets for this spreadsheet
            c.execute(
                """SELECT s.sheetId, s."index", s.title, s.sheetType,
                          g.rowCount, g.columnCount
                   FROM sheets s
                   LEFT JOIN grid_properties g ON s.sheetId = g.sheetId
                   WHERE s.spreadsheet_id = ?
                   ORDER BY s."index" """,
                (spreadsheet_id,),
            )

            sheets_data = c.fetchall()
            if not sheets_data:
                logger.debug(f"No sheets found for spreadsheet {spreadsheet_id}.")
                return None

            # Reconstruct the metadata dictionary
            sheets = []
            for sheet_data in sheets_data:
                sheet_id, index, title, sheet_type, row_count, column_count = sheet_data

                sheet_dict = {
                    "sheetId": sheet_id,
                    "index": index,
                    "title": title,
                    "sheetType": sheet_type,
                    "gridProperties": {"rowCount": row_count, "columnCount": column_count},
                }
                sheets.append(sheet_dict)

            return {"sheets": sheets}

        except sqlite.Error as e:
            logger.error(f"Error retrieving sheet metadata: {e}")
            return None

    def store_spreadsheet_thumbnail(self, spreadsheet_id: str, thumbnail_data: bytes, modifiedTime: str) -> bool:
        """
        Store or update a thumbnail for a spreadsheet in the database.

        Args:
            spreadsheet_id: ID of the Google spreadsheet
            thumbnail_data: Binary thumbnail image data
            modifiedTime: Timestamp of when the thumbnail was last modified

        Returns:
            True if successful, False otherwise
        """
        try:
            if self._conn is None:
                raise sqlite.Error("Database not open")
            c = self._conn.cursor()
            # Ensure spreadsheet_id exists in the spreadsheets table
            c.execute("INSERT OR IGNORE INTO spreadsheets (spreadsheet_id) VALUES (?)", (spreadsheet_id,))

            # Update modifiedTime in the spreadsheets table
            c.execute(
                "UPDATE spreadsheets SET modifiedTime = ? WHERE spreadsheet_id = ?", (modifiedTime, spreadsheet_id)
            )

            # Update thumbnail_data in the spreadsheets table
            c.execute(
                "UPDATE spreadsheets SET thumbnail = ? WHERE spreadsheet_id = ?", (thumbnail_data, spreadsheet_id)
            )

            self._conn.commit()
            return True
        except sqlite.Error as e:
            logger.error(f"Error storing spreadsheet thumbnail: {e}")
            return False

    def get_spreadsheet_thumbnail(self, spreadsheet_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a thumbnail for a spreadsheet from the database.

        Args:
            spreadsheet_id: ID of the Google spreadsheet

        Returns:
            Dictionary containing thumbnail_data and modifiedTime, or None if not found
        """
        try:
            if self._conn is None:
                raise sqlite.Error("Database not open")
            c = self._conn.cursor()
            c.execute(
                "SELECT thumbnail, modifiedTime FROM spreadsheets WHERE spreadsheet_id = ?",
                (spreadsheet_id,),
            )
            result = c.fetchone()
            if result:
                return {"thumbnail": result[0], "modifiedTime": result[1]}
        except sqlite.Error as e:
            logger.error(f"Error retrieving spreadsheet thumbnail: {e}")
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
            logger.error(f"Error storing spreadsheet info for {spreadsheet_id}: {e}")
            return False


class Db(_db_impl):
    def __new__(cls, *args: Any, **kwargs: Any) -> "Db":
        if not hasattr(cls, "_instance"):
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance
