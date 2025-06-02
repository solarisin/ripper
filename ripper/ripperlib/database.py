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
            f"Creating new RipperDb instance {self._db_identifier}"
            f" targeting database file: {str(self._db_file_path)}"
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
            # Enable foreign key constraints
            c.execute("PRAGMA foreign_keys = ON")

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
            c.execute(
                """CREATE TABLE IF NOT EXISTS sheet_data_ranges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    spreadsheet_id TEXT NOT NULL,
                    sheet_name TEXT NOT NULL,
                    start_row INTEGER NOT NULL,
                    start_col INTEGER NOT NULL,
                    end_row INTEGER NOT NULL,
                    end_col INTEGER NOT NULL,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (spreadsheet_id) REFERENCES spreadsheets(spreadsheet_id) ON DELETE CASCADE,
                    UNIQUE(spreadsheet_id, sheet_name, start_row, start_col, end_row, end_col)
                );"""
            )
            c.execute(
                """CREATE TABLE IF NOT EXISTS sheet_data_cells (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    range_id INTEGER NOT NULL,
                    row_num INTEGER NOT NULL,
                    col_num INTEGER NOT NULL,
                    cell_value TEXT,
                    FOREIGN KEY (range_id) REFERENCES sheet_data_ranges(id) ON DELETE CASCADE,
                    UNIQUE(range_id, row_num, col_num)
                );"""
            )
            # Create indices for efficient querying
            c.execute(
                """CREATE INDEX IF NOT EXISTS idx_sheet_data_ranges_lookup
                   ON sheet_data_ranges(spreadsheet_id, sheet_name);"""
            )
            c.execute(
                """CREATE INDEX IF NOT EXISTS idx_sheet_data_cells_position
                   ON sheet_data_cells(range_id, row_num, col_num);"""
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
                        f"Sheet {sheet.id} of spreadsheet {spreadsheet_id}"
                        " is a grid sheet but has no grid properties."
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
                    f"Spreadsheet {spreadsheet_id} not found in database. "
                    "Cannot store thumbnail without a spreadsheet."
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

            # Check if spreadsheet exists and get the current modifiedTime if
            # so
            c.execute("SELECT modifiedTime FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            result = c.fetchone()
            if result:
                # If modifiedTime is being updated and is different, invalidate
                # related data
                current_modified_time = result[0]
                if spreadsheet_properties.modified_time != current_modified_time:
                    # Delete sheets first (this will cascade to grid_properties
                    # due to ON DELETE CASCADE)
                    c.execute("DELETE FROM sheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
                    # Set thumbnail to NULL
                    c.execute("UPDATE spreadsheets SET thumbnail = NULL WHERE spreadsheet_id = ?", (spreadsheet_id,))
                    # Invalidate sheet data cache
                    c.execute("DELETE FROM sheet_data_ranges WHERE spreadsheet_id = ?", (spreadsheet_id,))

            # Check if spreadsheet exists and if it does, update it, otherwise
            # insert it
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

    def store_sheet_data_range(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        start_row: int,
        start_col: int,
        end_row: int,
        end_col: int,
        cell_data: list[list[Any]],
    ) -> Optional[int]:
        """
        Store sheet data for a specific range in the database.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: The name of the sheet
            start_row: Starting row (1-based)
            start_col: Starting column (1-based)
            end_row: Ending row (1-based)
            end_col: Ending column (1-based)
            cell_data: 2D list of cell values

        Returns:
            Range ID if successful, None otherwise
        """
        if self._conn is None:
            logger.error("Database not open")
            return None

        try:
            with self._conn:
                c = self._conn.cursor()

                # Insert or update the range record
                c.execute(
                    """INSERT OR REPLACE INTO sheet_data_ranges
                       (spreadsheet_id, sheet_name, start_row, start_col, end_row, end_col, cached_at)
                       VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                    (spreadsheet_id, sheet_name, start_row, start_col, end_row, end_col),
                )

                range_id = c.lastrowid

                # Delete existing cell data for this range
                c.execute("DELETE FROM sheet_data_cells WHERE range_id = ?", (range_id,))

                # Insert cell data
                for row_offset, row_data in enumerate(cell_data):
                    for col_offset, cell_value in enumerate(row_data):
                        row_num = start_row + row_offset
                        col_num = start_col + col_offset

                        # Convert cell value to string for storage
                        cell_str = str(cell_value) if cell_value is not None else None

                        c.execute(
                            """INSERT INTO sheet_data_cells (range_id, row_num, col_num, cell_value)
                               VALUES (?, ?, ?, ?)""",
                            (range_id, row_num, col_num, cell_str),
                        )

                logger.debug(
                    f"Stored sheet data range {start_row},{start_col}:{end_row},{end_col} "
                    f"for {spreadsheet_id}!{sheet_name}"
                )
                return range_id

        except sqlite.Error as e:
            logger.error(f"Error storing sheet data range: {e}")
            return None

    def get_cached_ranges(self, spreadsheet_id: str, sheet_name: str) -> list[dict[str, Any]]:
        """
        Get all cached ranges for a specific sheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: The name of the sheet

        Returns:
            List of range dictionaries with metadata
        """
        if self._conn is None:
            logger.error("Database not open")
            return []

        try:
            with self._conn:
                c = self._conn.cursor()
                c.execute(
                    """SELECT id, start_row, start_col, end_row, end_col, cached_at
                       FROM sheet_data_ranges
                       WHERE spreadsheet_id = ? AND sheet_name = ?
                       ORDER BY cached_at DESC""",
                    (spreadsheet_id, sheet_name),
                )

                ranges = []
                for row in c.fetchall():
                    ranges.append(
                        {
                            "range_id": row[0],
                            "start_row": row[1],
                            "start_col": row[2],
                            "end_row": row[3],
                            "end_col": row[4],
                            "cached_at": row[5],
                        }
                    )

                return ranges

        except sqlite.Error as e:
            logger.error(f"Error getting cached ranges: {e}")
            return []

    def get_sheet_data_from_cache(
        self, spreadsheet_id: str, sheet_name: str, start_row: int, start_col: int, end_row: int, end_col: int
    ) -> Optional[list[list[Any]]]:
        """
        Retrieve sheet data from cache for a specific range.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: The name of the sheet
            start_row: Starting row (1-based)
            start_col: Starting column (1-based)
            end_row: Ending row (1-based)
            end_col: Ending column (1-based)        Returns:
            2D list of cell values, or None if not fully cached
        """
        if self._conn is None:
            logger.error("Database not open")
            return None

        try:
            with self._conn:
                c = self._conn.cursor()

                # Find all ranges that intersect with the requested range
                c.execute(
                    """SELECT id, start_row, start_col, end_row, end_col
                       FROM sheet_data_ranges
                       WHERE spreadsheet_id = ? AND sheet_name = ?
                       AND NOT (end_row < ? OR start_row > ? OR end_col < ? OR start_col > ?)""",
                    (spreadsheet_id, sheet_name, start_row, end_row, start_col, end_col),
                )

                overlapping_ranges = c.fetchall()

                if not overlapping_ranges:
                    return None

                # Initialize result matrix
                rows = end_row - start_row + 1
                cols = end_col - start_col + 1
                result = [[None for _ in range(cols)] for _ in range(rows)]
                covered = [[False for _ in range(cols)] for _ in range(rows)]

                # Fill in data from overlapping ranges
                for range_row in overlapping_ranges:
                    range_id = range_row[0]
                    range_start_row, range_start_col, range_end_row, range_end_col = range_row[1:5]

                    # Get cell data for this range that intersects with
                    # requested range
                    c.execute(
                        """SELECT row_num, col_num, cell_value
                           FROM sheet_data_cells
                           WHERE range_id = ?
                           AND row_num BETWEEN ? AND ?
                           AND col_num BETWEEN ? AND ?""",
                        (range_id, start_row, end_row, start_col, end_col),
                    )

                    cells = c.fetchall()

                    if len(cells) == 0:
                        # Check if this range should have cells in the requested area
                        expected_rows = min(range_end_row, end_row) - max(range_start_row, start_row) + 1
                        expected_cols = min(range_end_col, end_col) - max(range_start_col, start_col) + 1
                        expected_cells = expected_rows * expected_cols
                        actual_start_row = max(range_start_row, start_row)
                        actual_end_row = min(range_end_row, end_row)
                        actual_start_col = max(range_start_col, start_col)
                        actual_end_col = min(range_end_col, end_col)
                        logger.warning(
                            f"Range {range_id} has no cell data but should cover {expected_cells} cells. "
                            f"Expected boundaries: rows {actual_start_row}-{actual_end_row} "
                            f"({expected_rows} rows), cols {actual_start_col}-{actual_end_col} "
                            f"({expected_cols} cols). Range definition: rows {range_start_row}-{range_end_row}, "
                            f"cols {range_start_col}-{range_end_col}"
                        )

                    for cell_row in cells:
                        cell_row_num, cell_col_num, cell_value = cell_row
                        result_row = cell_row_num - start_row
                        result_col = cell_col_num - start_col

                        if 0 <= result_row < rows and 0 <= result_col < cols:
                            result[result_row][result_col] = cell_value
                            covered[result_row][result_col] = True  # Check if the entire requested range is covered
                all_covered = all(all(row) for row in covered)
                if not all_covered:
                    return None  # Not fully cached

                return result

        except sqlite.Error as e:
            logger.error(f"Error getting sheet data from cache: {e}")
            return None

    def invalidate_sheet_data_cache(self, spreadsheet_id: str, sheet_name: Optional[str] = None) -> bool:
        """
        Invalidate cached sheet data for a spreadsheet or specific sheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: The name of the sheet (if None, invalidates all sheets)

        Returns:
            True if successful, False otherwise
        """
        if self._conn is None:
            logger.error("Database not open")
            return False

        try:
            with self._conn:
                c = self._conn.cursor()

                if sheet_name is None:
                    # Invalidate all sheets for this spreadsheet
                    c.execute("DELETE FROM sheet_data_ranges WHERE spreadsheet_id = ?", (spreadsheet_id,))
                    logger.debug(f"Invalidated all sheet data cache for spreadsheet {spreadsheet_id}")
                else:
                    # Invalidate specific sheet
                    c.execute(
                        "DELETE FROM sheet_data_ranges WHERE spreadsheet_id = ? AND sheet_name = ?",
                        (spreadsheet_id, sheet_name),
                    )
                    logger.debug(f"Invalidated sheet data cache for {spreadsheet_id}!{sheet_name}")

                return True

        except sqlite.Error as e:
            logger.error(f"Error invalidating sheet data cache: {e}")
            return False

    def validate_cached_range_data(self, spreadsheet_id: str, sheet_name: str) -> bool:
        """
        Validate that all cached ranges have corresponding cell data.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: The name of the sheet

        Returns:
            True if all ranges have cell data, False otherwise
        """
        if self._conn is None:
            logger.error("Database not open")
            return False

        try:
            with self._conn:
                c = self._conn.cursor()

                # Get all ranges for this sheet
                c.execute(
                    """SELECT range_id, start_row, start_col, end_row, end_col
                       FROM sheet_data_ranges
                       WHERE spreadsheet_id = ? AND sheet_name = ?""",
                    (spreadsheet_id, sheet_name),
                )

                ranges = c.fetchall()
                all_valid = True

                for range_row in ranges:
                    range_id, start_row, start_col, end_row, end_col = range_row

                    # Count cells in this range
                    c.execute(
                        """SELECT COUNT(*)
                           FROM sheet_data_cells
                           WHERE range_id = ?""",
                        (range_id,),
                    )

                    cell_count = c.fetchone()[0]
                    expected_cells = (end_row - start_row + 1) * (end_col - start_col + 1)

                    if cell_count == 0 and expected_cells > 0:
                        logger.warning(
                            f"Range {range_id} has no cell data but should have {expected_cells} cells "
                            f"(rows {start_row}-{end_row}, cols {start_col}-{end_col})"
                        )
                        all_valid = False
                    elif cell_count < expected_cells:
                        logger.warning(
                            f"Range {range_id} has only {cell_count}/{expected_cells} cells "
                            f"(rows {start_row}-{end_row}, cols {start_col}-{end_col})"
                        )
                        # This might be OK if the range had empty cells

                return all_valid

        except sqlite.Error as e:
            logger.error(f"Error validating cached range data: {e}")
            return False

    def clean_orphaned_ranges(self, spreadsheet_id: str, sheet_name: str) -> int:
        """
        Remove ranges that have no corresponding cell data.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: The name of the sheet

        Returns:
            Number of ranges removed
        """
        if self._conn is None:
            logger.error("Database not open")
            return 0

        try:
            with self._conn:
                c = self._conn.cursor()

                # Find ranges with no cell data
                c.execute(
                    """SELECT r.range_id
                       FROM sheet_data_ranges r
                       LEFT JOIN sheet_data_cells c ON r.range_id = c.range_id
                       WHERE r.spreadsheet_id = ? AND r.sheet_name = ?
                       GROUP BY r.range_id
                       HAVING COUNT(c.range_id) = 0""",
                    (spreadsheet_id, sheet_name),
                )

                orphaned_ranges = c.fetchall()

                if not orphaned_ranges:
                    return 0

                # Delete orphaned ranges
                orphaned_ids = [row[0] for row in orphaned_ranges]
                placeholders = ",".join("?" for _ in orphaned_ids)

                c.execute(f"DELETE FROM sheet_data_ranges WHERE range_id IN ({placeholders})", orphaned_ids)

                deleted_count = len(orphaned_ids)
                logger.info(f"Cleaned up {deleted_count} orphaned ranges for {spreadsheet_id}!{sheet_name}")

                return deleted_count

        except sqlite.Error as e:
            logger.error(f"Error cleaning orphaned ranges: {e}")
            return 0

    def detect_incomplete_ranges(self, spreadsheet_id: str, sheet_name: str) -> list[int]:
        """
        Detect ranges that have significantly fewer cells than expected.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: The name of the sheet

        Returns:
            List of range IDs that appear to be incomplete
        """
        if self._conn is None:
            logger.error("Database not open")
            return []

        try:
            with self._conn:
                c = self._conn.cursor()

                # Get all ranges with their expected and actual cell counts
                c.execute(
                    """SELECT r.id, r.start_row, r.start_col, r.end_row, r.end_col,
                              COUNT(c.range_id) as actual_cells
                       FROM sheet_data_ranges r
                       LEFT JOIN sheet_data_cells c ON r.id = c.range_id
                       WHERE r.spreadsheet_id = ? AND r.sheet_name = ?
                       GROUP BY r.id, r.start_row, r.start_col, r.end_row, r.end_col""",
                    (spreadsheet_id, sheet_name),
                )

                incomplete_ranges = []

                for row in c.fetchall():
                    range_id, start_row, start_col, end_row, end_col, actual_cells = row
                    expected_cells = (end_row - start_row + 1) * (end_col - start_col + 1)

                    # Consider a range incomplete if it has less than 50% of expected cells
                    # and the missing amount is significant (more than 5 cells)
                    if actual_cells < expected_cells * 0.5 and (expected_cells - actual_cells) > 5:
                        logger.warning(
                            f"Range {range_id} appears incomplete: "
                            f"{actual_cells}/{expected_cells} cells "
                            f"(rows {start_row}-{end_row}, cols {start_col}-{end_col})"
                        )
                        incomplete_ranges.append(range_id)

                return incomplete_ranges

        except sqlite.Error as e:
            logger.error(f"Error detecting incomplete ranges: {e}")
            return []

    def delete_range_data(self, range_id: int) -> bool:
        """
        Delete a specific range and all its cell data.

        Args:
            range_id: The ID of the range to delete

        Returns:
            True if successful, False otherwise
        """
        if self._conn is None:
            logger.error("Database not open")
            return False

        try:
            with self._conn:
                c = self._conn.cursor()

                # Delete the range (cells will be deleted by CASCADE)
                c.execute("DELETE FROM sheet_data_ranges WHERE id = ?", (range_id,))

                deleted_count = c.rowcount
                if deleted_count > 0:
                    logger.info(f"Deleted range {range_id}")
                    return True
                else:
                    logger.warning(f"Range {range_id} not found for deletion")
                    return False

        except sqlite.Error as e:
            logger.error(f"Error deleting range {range_id}: {e}")
            return False


# Global singleton instance for application-wide use
Db = RipperDb()
