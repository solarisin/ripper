"""
Database management for the ripper project.

This module provides the RipperDb class for managing SQLite-based storage of spreadsheet and sheet metadata,
including schema creation, CRUD operations, and thumbnail storage. It also provides a singleton instance `Db` for
application-wide use.
"""

import json
import os
import sqlite3 as sqlite
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from beartype.typing import Any, Generator, Optional
from loguru import logger

import ripper.ripperlib.defs as defs
from ripper.ripperlib.defs import SheetProperties, SpreadsheetProperties
from ripper.ripperlib.range_manager import CellRange


def default_db_path() -> Path:
    return Path(defs.get_app_data_dir()) / "ripper.db"


# Columns added to ``sheet_data_ranges`` after the initial schema, mapping name -> SQL type.
# These flag a stored range as a COMPLETE open-ended snapshot (issue #68): the range is the full
# result of an open-ended request covering columns [open_ended_start_col..open_ended_end_col]
# over the resolved rows [open_ended_start_row..open_ended_end_row]. A plain bounded store leaves
# all four NULL.
#
# ``open_ended_end_row`` records the request's RESOLVED end row so whole-row forms of different
# heights (e.g. ``2:10`` vs ``2:20``) do not collide on the same lookup key: both resolve to
# start row 2 plus the full column span, so without the end row a cached ``2:10`` would wrongly
# satisfy a ``2:20`` request and return truncated rows (P1 review on #143). ``A:Z``/``A5:Z`` and
# whole-sheet reads resolve their end row from the grid dimensions, so a repeated read resolves
# to the same end row and still hits.
#
# There is no migration framework (the DB is a rebuildable cache; see #78), so an existing DB
# predating these columns is upgraded in place via a guarded, idempotent ``ALTER TABLE ... ADD
# COLUMN`` in the open/create path. The keys here form the ONLY allowlist of identifiers ever
# interpolated into that DDL — never interpolate untrusted values into SQL.
_SHEET_DATA_RANGE_ADDED_COLUMNS: dict[str, str] = {
    "open_ended_start_row": "INTEGER",
    "open_ended_start_col": "INTEGER",
    "open_ended_end_col": "INTEGER",
    "open_ended_end_row": "INTEGER",
}

# Same guarded-ADD-COLUMN mechanism for sheet_data_cells: ``cell_type`` records the Python type of
# each cached cell so booleans and numbers survive a cache round-trip instead of being coerced to
# their ``str()`` form (#144 review). Legacy rows predating the column have ``cell_type`` NULL and
# are read back as plain strings — exactly the pre-existing behavior, so no cache rebuild is needed.
_SHEET_DATA_CELL_ADDED_COLUMNS: dict[str, str] = {
    "cell_type": "TEXT",
}


def _encode_cell_value(value: Any) -> tuple[Optional[str], Optional[str]]:
    """Serialize a Sheets cell value to ``(text, type_tag)`` preserving its Python type.

    The Sheets values API returns ``str``/``int``/``float``/``bool``; the cache column is TEXT, so
    without the tag a cached bool/number would come back as ``"True"``/``"1.5"`` on a cache hit and
    differ from a fresh read. ``None`` maps to ``(None, None)``. A numeric-looking *string* keeps
    the ``"str"`` tag, so ``"1.5"`` (string) is never confused with ``1.5`` (float) on read.
    """
    if value is None:
        return None, None
    if isinstance(value, bool):  # bool before int: bool is a subclass of int
        return ("true" if value else "false"), "bool"
    if isinstance(value, int):
        return str(value), "int"
    if isinstance(value, float):
        return repr(value), "float"  # repr round-trips float precision exactly
    return str(value), "str"


def _decode_cell_value(text: Optional[str], type_tag: Optional[str]) -> Any:
    """Inverse of :func:`_encode_cell_value`. A NULL ``type_tag`` (legacy row) yields the raw string."""
    if text is None:
        return None
    if type_tag == "bool":
        return text == "true"
    if type_tag == "int":
        return int(text)
    if type_tag == "float":
        return float(text)
    # "str" or a legacy row with no tag: return the stored text unchanged.
    return text


class RipperDb:
    """
    SQLite database manager for spreadsheet and sheet metadata, thumbnails, and related data.

    Handles connection management, schema creation, and CRUD operations for the ripper application.
    """

    def __init__(self, db_file_path: Optional[str] = None) -> None:
        """
        Initialize the database implementation and open a connection.

        Args:
            db_file_path (str): Path to the database file. Defaults to the application data
                location, resolved here (not at import) so the default path is computed lazily.
        """
        self._db_file_path = db_file_path if db_file_path is not None else str(default_db_path())
        self._db_identifier = self.generate_db_identifier()
        logger.info(
            f"Creating new RipperDb instance {self._db_identifier} targeting database file: {str(self._db_file_path)}"
        )
        self._conn: sqlite.Connection | None = None
        self._lock = threading.RLock()
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
        with self._lock:
            if self._conn:
                logger.debug(f"Database {self._db_file_path} already open")
                return

            # Ensure the directory exists
            os.makedirs(os.path.dirname(self._db_file_path), exist_ok=True)

            try:
                self._conn = sqlite.connect(self._db_file_path, timeout=20, check_same_thread=False)
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
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    @contextmanager
    def _transaction(self) -> Generator[None, None, None]:
        """
        Context manager that serialises DB access across threads.

        Acquires the instance-level RLock and wraps the body in a SQLite
        transaction (``with self._conn:``).  All methods that write to or
        read from the database should use this instead of touching
        ``self._conn`` directly.
        """
        with self._lock:
            if self._conn is None:
                raise sqlite.ProgrammingError("Database is not open")
            with self._conn:
                yield

    def clean(self) -> None:
        """
        Clean the database by closing the connection and deleting the file.

        Acquires ``self._lock`` (mirroring ``open``/``close``) so a concurrent thread mid
        ``_transaction`` is not hit when the connection is closed and the file unlinked out
        from under it.
        """
        with self._lock:
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

        with self._transaction():
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
            # A Google Sheets sheetId is unique only WITHIN its parent spreadsheet (the first
            # tab of every spreadsheet is sheetId 0), so the primary key is composite.
            c.execute(
                """CREATE TABLE IF NOT EXISTS sheets (
                    sheetId TEXT NOT NULL,
                    spreadsheet_id TEXT NOT NULL,
                    "index" INTEGER,
                    title TEXT,
                    sheetType TEXT,
                    PRIMARY KEY (spreadsheet_id, sheetId),
                    FOREIGN KEY (spreadsheet_id) REFERENCES spreadsheets(spreadsheet_id) ON DELETE CASCADE
                );"""
            )
            c.execute(
                """CREATE TABLE IF NOT EXISTS grid_properties (
                    sheetId TEXT NOT NULL,
                    spreadsheet_id TEXT NOT NULL,
                    rowCount INTEGER,
                    columnCount INTEGER,
                    PRIMARY KEY (spreadsheet_id, sheetId),
                    FOREIGN KEY (spreadsheet_id, sheetId)
                        REFERENCES sheets(spreadsheet_id, sheetId) ON DELETE CASCADE
                );"""
            )
            # open_ended_* columns flag a range as a complete open-ended snapshot (issue #68);
            # NULL on ordinary bounded stores. Existing DBs predating them are upgraded below.
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
                    open_ended_start_row INTEGER,
                    open_ended_start_col INTEGER,
                    open_ended_end_col INTEGER,
                    open_ended_end_row INTEGER,
                    FOREIGN KEY (spreadsheet_id) REFERENCES spreadsheets(spreadsheet_id) ON DELETE CASCADE,
                    UNIQUE(spreadsheet_id, sheet_name, start_row, start_col, end_row, end_col)
                );"""
            )
            # Upgrade existing (pre-#68) databases in place: add any missing marker columns.
            self._ensure_sheet_data_range_columns(c)
            c.execute(
                """CREATE TABLE IF NOT EXISTS sheet_data_cells (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    range_id INTEGER NOT NULL,
                    row_num INTEGER NOT NULL,
                    col_num INTEGER NOT NULL,
                    cell_value TEXT,
                    cell_type TEXT,
                    FOREIGN KEY (range_id) REFERENCES sheet_data_ranges(id) ON DELETE CASCADE,
                    UNIQUE(range_id, row_num, col_num)
                );"""
            )
            # Upgrade existing (pre-#144-review) databases in place: add the cell_type column.
            self._ensure_sheet_data_cell_columns(c)
            # Create indices for efficient querying
            c.execute(
                """CREATE INDEX IF NOT EXISTS idx_sheet_data_ranges_lookup
                   ON sheet_data_ranges(spreadsheet_id, sheet_name);"""
            )
            c.execute(
                """CREATE INDEX IF NOT EXISTS idx_sheet_data_cells_position
                   ON sheet_data_cells(range_id, row_num, col_num);"""
            )
            c.execute(
                """CREATE TABLE IF NOT EXISTS data_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    spreadsheet_id TEXT NOT NULL,
                    sheet_name TEXT NOT NULL,
                    range_a1 TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_fetched_at TIMESTAMP,
                    FOREIGN KEY (spreadsheet_id) REFERENCES spreadsheets(spreadsheet_id) ON DELETE CASCADE
                );"""
            )
            c.execute(
                """CREATE INDEX IF NOT EXISTS idx_data_sources_spreadsheet
                   ON data_sources(spreadsheet_id);"""
            )
            logger.info("Database tables created successfully")

    def _ensure_sheet_data_range_columns(self, c: sqlite.Cursor) -> None:
        """Add any missing ``sheet_data_ranges`` marker columns to a pre-existing table.

        Idempotent and additive: on a freshly created table the columns already exist and this
        is a no-op; on a DB predating them (see :data:`_SHEET_DATA_RANGE_ADDED_COLUMNS`) each is
        added via ``ALTER TABLE ... ADD COLUMN``. SQLite DDL cannot bind identifiers, so the
        column name and type are interpolated — but ONLY from the module-level allowlist, never
        from untrusted input.

        Args:
            c: An open cursor participating in the caller's transaction.
        """
        existing = {row[1] for row in c.execute("PRAGMA table_info(sheet_data_ranges)").fetchall()}
        for column, col_type in _SHEET_DATA_RANGE_ADDED_COLUMNS.items():
            if column in existing:
                continue
            # column/col_type come exclusively from the allowlist above (safe to interpolate).
            c.execute(f"ALTER TABLE sheet_data_ranges ADD COLUMN {column} {col_type}")
            logger.info(f"Added column '{column}' to sheet_data_ranges (schema upgrade)")

    def _ensure_sheet_data_cell_columns(self, c: sqlite.Cursor) -> None:
        """Add the ``sheet_data_cells.cell_type`` column to a pre-existing table (idempotent).

        Same guarded, additive pattern as :meth:`_ensure_sheet_data_range_columns`: the column name
        and type are interpolated only from :data:`_SHEET_DATA_CELL_ADDED_COLUMNS`, never from
        untrusted input.

        Args:
            c: An open cursor participating in the caller's transaction.
        """
        existing = {row[1] for row in c.execute("PRAGMA table_info(sheet_data_cells)").fetchall()}
        for column, col_type in _SHEET_DATA_CELL_ADDED_COLUMNS.items():
            if column in existing:
                continue
            # column/col_type come exclusively from the allowlist above (safe to interpolate).
            c.execute(f"ALTER TABLE sheet_data_cells ADD COLUMN {column} {col_type}")
            logger.info(f"Added column '{column}' to sheet_data_cells (schema upgrade)")

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

        with self._transaction():
            c = self._conn.cursor()

            # Check if spreadsheet exists. SELECT leaves cursor.rowcount at -1, so the
            # count must be read from the result row (matching store_spreadsheet_thumbnail).
            c.execute("SELECT COUNT(*) FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            row = c.fetchone()
            if row is None or row[0] == 0:
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
                        f"Sheet {sheet.id} of spreadsheet {spreadsheet_id} is a grid sheet but has no grid properties."
                    )
                c.execute(
                    """INSERT INTO sheets (spreadsheet_id, sheetId, "index", title, sheetType)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(spreadsheet_id, sheetId) DO UPDATE SET "index"=excluded."index",
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
                    """INSERT INTO grid_properties (spreadsheet_id, sheetId, rowCount, columnCount)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(spreadsheet_id, sheetId) DO UPDATE SET rowCount=excluded.rowCount,
                                                                          columnCount=excluded.columnCount""",
                    (spreadsheet_id, sheet.id, grid_props.row_count, grid_props.column_count),
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

        with self._transaction():
            c = self._conn.cursor()

            # Get all sheets for this spreadsheet
            c.execute(
                """SELECT s.sheetId, s."index", s.title, s.sheetType,
                          g.rowCount, g.columnCount
                   FROM sheets s
                   LEFT JOIN grid_properties g
                          ON s.spreadsheet_id = g.spreadsheet_id AND s.sheetId = g.sheetId
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

        with self._transaction():
            c = self._conn.cursor()

            # Check if spreadsheet exists
            c.execute("SELECT COUNT(*) FROM spreadsheets WHERE spreadsheet_id = ?", (spreadsheet_id,))
            row = c.fetchone()
            if row is None or row[0] == 0:
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

        with self._transaction():
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

        with self._transaction():
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
        open_ended_start_row: Optional[int] = None,
        open_ended_start_col: Optional[int] = None,
        open_ended_end_col: Optional[int] = None,
        open_ended_end_row: Optional[int] = None,
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
            open_ended_start_row: If set (together with the three below), marks this range as the
                COMPLETE result of an open-ended request whose resolved columns are
                [open_ended_start_col..open_ended_end_col] over the resolved rows
                [open_ended_start_row..open_ended_end_row] (issue #68).
            open_ended_start_col: Resolved start column of the open-ended request (see above).
            open_ended_end_col: Resolved end column of the open-ended request (see above).
            open_ended_end_row: Resolved end row of the open-ended request. Recorded so whole-row
                forms of different heights (``2:10`` vs ``2:20``) don't collide on the same lookup
                key; ``A:Z``/``A5:Z``/whole-sheet reads resolve this to the grid row count.

        Returns:
            Range ID if successful, None otherwise
        """
        if self._conn is None:
            logger.error("Database not open")
            return None

        try:
            with self._transaction():
                c = self._conn.cursor()

                # Upsert the range record. On the UNIQUE(extent) conflict we keep the existing
                # row (and its id) rather than deleting/reinserting, so any externally-held
                # range_id stays valid across re-caches. RETURNING id yields the stable id on
                # both the insert-new and update-existing paths.
                #
                # The open_ended_* marker is always written (NULL for ordinary bounded stores),
                # including on the ON CONFLICT update: a later bounded re-store of the SAME extent
                # deliberately CLEARS a prior open-ended marker, since a bounded write does not
                # prove the whole open-ended column span is still complete (correctness first).
                c.execute(
                    """INSERT INTO sheet_data_ranges
                       (spreadsheet_id, sheet_name, start_row, start_col, end_row, end_col, cached_at,
                        open_ended_start_row, open_ended_start_col, open_ended_end_col, open_ended_end_row)
                       VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
                       ON CONFLICT(spreadsheet_id, sheet_name, start_row, start_col, end_row, end_col)
                           DO UPDATE SET cached_at=CURRENT_TIMESTAMP,
                                         open_ended_start_row=excluded.open_ended_start_row,
                                         open_ended_start_col=excluded.open_ended_start_col,
                                         open_ended_end_col=excluded.open_ended_end_col,
                                         open_ended_end_row=excluded.open_ended_end_row
                       RETURNING id""",
                    (
                        spreadsheet_id,
                        sheet_name,
                        start_row,
                        start_col,
                        end_row,
                        end_col,
                        open_ended_start_row,
                        open_ended_start_col,
                        open_ended_end_col,
                        open_ended_end_row,
                    ),
                )
                range_id = int(c.fetchone()[0])

                # Load-bearing: with a stable id the ON CONFLICT path no longer cascade-deletes
                # the previous cells, so we must clear them explicitly before re-inserting to
                # avoid stale cells surviving a re-cache.
                c.execute("DELETE FROM sheet_data_cells WHERE range_id = ?", (range_id,))

                # Batch-insert the new cell data (one executemany instead of a statement per cell).
                # Each cell is stored with its type tag so bool/number values survive the round-trip
                # instead of being coerced to str() (#144 review).
                cell_rows = [
                    (range_id, start_row + row_offset, start_col + col_offset, *_encode_cell_value(cell_value))
                    for row_offset, row_data in enumerate(cell_data)
                    for col_offset, cell_value in enumerate(row_data)
                ]
                if cell_rows:
                    c.executemany(
                        """INSERT INTO sheet_data_cells (range_id, row_num, col_num, cell_value, cell_type)
                           VALUES (?, ?, ?, ?, ?)""",
                        cell_rows,
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
            with self._transaction():
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
            with self._transaction():
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
                        """SELECT row_num, col_num, cell_value, cell_type
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
                        cell_row_num, cell_col_num, cell_value, cell_type = cell_row
                        result_row = cell_row_num - start_row
                        result_col = cell_col_num - start_col

                        if 0 <= result_row < rows and 0 <= result_col < cols:
                            result[result_row][result_col] = _decode_cell_value(cell_value, cell_type)
                            covered[result_row][result_col] = True  # Check if the entire requested range is covered
                all_covered = all(all(row) for row in covered)
                if not all_covered:
                    return None  # Not fully cached

                return result

        except sqlite.Error as e:
            logger.error(f"Error getting sheet data from cache: {e}")
            return None

    def get_open_ended_coverage(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        open_ended_start_row: int,
        open_ended_start_col: int,
        open_ended_end_col: int,
        open_ended_end_row: int,
    ) -> Optional[list[list[Any]]]:
        """Return the complete open-ended snapshot for a matching request, or ``None`` (issue #68).

        Looks for a ``sheet_data_ranges`` row flagged as the COMPLETE result of an open-ended
        request whose resolved identity COVERS this request, and, if found, reconstructs that
        stored range's rectangle from its own cells. A cached snapshot qualifies only when it
        spans at least the requested rows: it shares the request's resolved start row and column
        span, and its resolved end row is >= the request's resolved end row. This is what keeps
        whole-row forms of different heights from colliding — a cached ``2:10`` (end row 10) does
        NOT satisfy ``2:20`` (end row 20), while a repeated ``2:10`` (or an ``A:Z``/whole-sheet
        read resolving to the same grid end row) still hits (P1 review on #143).

        Only rows carrying the marker qualify (the columns are NULL on a plain bounded store), so
        a seeded ``A1:B2`` can never masquerade as ``A:Z``.

        When a taller cached snapshot serves a shorter request, the reconstructed rectangle is
        trimmed to the requested end row so no rows beyond the request are returned. The result
        is padded (``None`` for absent cells); the caller reproduces the same trailing-empty
        trimming a fresh API read would receive.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            sheet_name: The name of the sheet.
            open_ended_start_row: Resolved start row of the open-ended request.
            open_ended_start_col: Resolved start column of the open-ended request.
            open_ended_end_col: Resolved end column of the open-ended request.
            open_ended_end_row: Resolved end row of the open-ended request. A cached marker
                satisfies the request only when its own resolved end row is >= this value.

        Returns:
            2D list of cell values for the snapshot's extent (trimmed to the requested rows), or
            ``None`` if no fresh complete-coverage marker covers this request.
        """
        if self._conn is None:
            logger.error("Database not open")
            return None

        try:
            with self._transaction():
                c = self._conn.cursor()
                # Match the resolved start row + column span exactly, and require the cached
                # marker to cover at least the requested rows (its resolved end row >= ours). The
                # marker columns are NULL on bounded stores, so those never match. Prefer the most
                # recent qualifying snapshot.
                c.execute(
                    """SELECT id, start_row, start_col, end_row, end_col
                       FROM sheet_data_ranges
                       WHERE spreadsheet_id = ? AND sheet_name = ?
                       AND open_ended_start_row = ? AND open_ended_start_col = ? AND open_ended_end_col = ?
                       AND open_ended_end_row >= ?
                       ORDER BY cached_at DESC
                       LIMIT 1""",
                    (
                        spreadsheet_id,
                        sheet_name,
                        open_ended_start_row,
                        open_ended_start_col,
                        open_ended_end_col,
                        open_ended_end_row,
                    ),
                )
                marker = c.fetchone()
                if marker is None:
                    return None

                range_id, start_row, start_col, end_row, end_col = marker
                # A taller cached snapshot may extend past the requested rows; cap the stored
                # extent at the requested end row so we never return rows beyond the request. The
                # stored start row equals the (exactly-matched) resolved start row.
                end_row = min(end_row, open_ended_end_row)
                if end_row < start_row:
                    return None
                rows = end_row - start_row + 1
                cols = end_col - start_col + 1
                result: list[list[Any]] = [[None for _ in range(cols)] for _ in range(rows)]

                c.execute(
                    "SELECT row_num, col_num, cell_value, cell_type FROM sheet_data_cells WHERE range_id = ?",
                    (range_id,),
                )
                for cell_row_num, cell_col_num, cell_value, cell_type in c.fetchall():
                    result_row = cell_row_num - start_row
                    result_col = cell_col_num - start_col
                    if 0 <= result_row < rows and 0 <= result_col < cols:
                        result[result_row][result_col] = _decode_cell_value(cell_value, cell_type)

                return result

        except sqlite.Error as e:
            logger.error(f"Error getting open-ended coverage: {e}")
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
            with self._transaction():
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

    def invalidate_sheet_data_range(self, spreadsheet_id: str, sheet_name: str, cell_range: CellRange) -> bool:
        """
        Invalidate only the cached ranges on a sheet that OVERLAP a given extent.

        Unlike :meth:`invalidate_sheet_data_cache` (which drops *every* cached range for the
        tab), this deletes only the ``sheet_data_ranges`` rows whose extent intersects
        ``cell_range``. It is used by the Refresh action so re-fetching one data source does not
        evict sibling sources caching non-overlapping regions of the same tab (issue #80).
        Deleted ranges' cells cascade away via the ``sheet_data_cells`` ``ON DELETE CASCADE`` FK.

        The overlap predicate matches :meth:`get_sheet_data_from_cache`: a stored range overlaps
        when it is NOT entirely above, below, left, or right of ``cell_range``.

        Args:
            spreadsheet_id: The ID of the spreadsheet.
            sheet_name: The name of the sheet.
            cell_range: The (bounded) extent whose overlapping cached ranges should be dropped.

        Returns:
            True if successful, False otherwise.
        """
        if self._conn is None:
            logger.error("Database not open")
            return False

        try:
            with self._transaction():
                c = self._conn.cursor()
                c.execute(
                    """DELETE FROM sheet_data_ranges
                       WHERE spreadsheet_id = ? AND sheet_name = ?
                       AND NOT (end_row < ? OR start_row > ? OR end_col < ? OR start_col > ?)""",
                    (
                        spreadsheet_id,
                        sheet_name,
                        cell_range.start_row,
                        cell_range.end_row,
                        cell_range.start_col,
                        cell_range.end_col,
                    ),
                )
                extent_dropped = c.rowcount

                # Also drop any open-ended complete-coverage marker whose COLUMN span overlaps the
                # refreshed columns, even if its (narrower) stored extent did not overlap above
                # (issue #68). An open-ended snapshot claims completeness for every row of its
                # column span, so a refresh touching any of those columns — e.g. a column with new
                # data beyond the previously-cached extent — could make the snapshot stale. Rows
                # overlap because the snapshot is unbounded downward from open_ended_start_row, so
                # any refresh reaching row >= open_ended_start_row is relevant. Over-dropping is
                # safe (the next open-ended read simply re-fetches); under-dropping risks stale data.
                c.execute(
                    """DELETE FROM sheet_data_ranges
                       WHERE spreadsheet_id = ? AND sheet_name = ?
                       AND open_ended_start_col IS NOT NULL AND open_ended_end_col IS NOT NULL
                       AND open_ended_start_row IS NOT NULL
                       AND NOT (open_ended_end_col < ? OR open_ended_start_col > ?)
                       AND open_ended_start_row <= ?""",
                    (
                        spreadsheet_id,
                        sheet_name,
                        cell_range.start_col,
                        cell_range.end_col,
                        cell_range.end_row,
                    ),
                )
                logger.debug(
                    f"Invalidated {extent_dropped} cached range(s) and {c.rowcount} open-ended "
                    f"marker(s) overlapping {cell_range.to_a1_notation()} for {spreadsheet_id}!{sheet_name}"
                )
                return True

        except sqlite.Error as e:
            logger.error(f"Error invalidating sheet data range: {e}")
            return False

    def validate_cached_range_data(self, spreadsheet_id: str, sheet_name: str) -> bool:
        """
        Check cached ranges for the corruption case of a non-empty extent with zero stored cells.

        Contract: a range is INVALID only when it declares a non-empty extent
        (``rows * cols > 0``) yet has **no** stored cells at all — a signal of an orphaned or
        corrupt range record, not real data. Under-filled ranges (fewer stored cells than the
        extent's area) are **valid**: empty cells are intentionally not persisted (see
        ``store_sheet_data_range``/the cache layer), so a legitimately sparse range stores fewer
        cells than its bounding rectangle contains. This method therefore never fails on
        under-fill — doing so would reject valid sparse data.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: The name of the sheet

        Returns:
            True if every range either has an empty extent or at least one stored cell; False if
            any range declares a non-empty extent but has zero stored cells.
        """
        if self._conn is None:
            logger.error("Database not open")
            return False

        try:
            with self._transaction():
                c = self._conn.cursor()

                # Get all ranges for this sheet. The range primary key is
                # sheet_data_ranges.id; sheet_data_cells.range_id references it.
                c.execute(
                    """SELECT id, start_row, start_col, end_row, end_col
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
                        # Non-empty extent with zero stored cells: the only case treated as
                        # invalid (orphaned/corrupt range record).
                        logger.warning(
                            f"Range {range_id} has no cell data but should have {expected_cells} cells "
                            f"(rows {start_row}-{end_row}, cols {start_col}-{end_col})"
                        )
                        all_valid = False
                    elif cell_count < expected_cells:
                        # Under-fill is expected and valid: empty cells are not persisted, so a
                        # sparse range legitimately stores fewer cells than its extent's area.
                        logger.debug(
                            f"Range {range_id} sparsely filled with {cell_count}/{expected_cells} cells "
                            f"(rows {start_row}-{end_row}, cols {start_col}-{end_col}); "
                            f"expected for sparse data (empty cells are not stored)"
                        )

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
            with self._transaction():
                c = self._conn.cursor()

                # Find ranges with no cell data. The range primary key is
                # sheet_data_ranges.id; sheet_data_cells.range_id references it.
                c.execute(
                    """SELECT r.id
                       FROM sheet_data_ranges r
                       LEFT JOIN sheet_data_cells c ON r.id = c.range_id
                       WHERE r.spreadsheet_id = ? AND r.sheet_name = ?
                       GROUP BY r.id
                       HAVING COUNT(c.range_id) = 0""",
                    (spreadsheet_id, sheet_name),
                )

                orphaned_ranges = c.fetchall()

                if not orphaned_ranges:
                    return 0

                # Delete orphaned ranges
                orphaned_ids = [row[0] for row in orphaned_ranges]
                placeholders = ",".join("?" for _ in orphaned_ids)

                c.execute(f"DELETE FROM sheet_data_ranges WHERE id IN ({placeholders})", orphaned_ids)

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
            with self._transaction():
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
            with self._transaction():
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

    # ---- Data source CRUD -------------------------------------------------------

    def create_data_source(
        self,
        name: str,
        spreadsheet_id: str,
        sheet_name: str,
        range_a1: str,
    ) -> Optional[int]:
        """
        Insert a new named data source record.

        Args:
            name: Human-readable label for this data source.
            spreadsheet_id: Google Sheets spreadsheet ID (must exist in spreadsheets table).
            sheet_name: Name of the sheet tab within the spreadsheet.
            range_a1: Range in A1 notation (e.g. ``A1:Z500``).

        Returns:
            The new row's ``id`` on success, or ``None`` on failure.
        """
        if self._conn is None:
            logger.error("Database not open")
            return None

        try:
            with self._transaction():
                c = self._conn.cursor()
                c.execute(
                    """INSERT INTO data_sources (name, spreadsheet_id, sheet_name, range_a1)
                       VALUES (?, ?, ?, ?)""",
                    (name, spreadsheet_id, sheet_name, range_a1),
                )
                last_row_id = c.lastrowid
                if last_row_id is None:
                    logger.error(f"INSERT for data source '{name}' returned no row id")
                    return None
                row_id: int = last_row_id
                logger.info(f"Created data source '{name}' (id={row_id})")
                return row_id
        except sqlite.Error as e:
            logger.error(f"Error creating data source '{name}': {e}")
            return None

    def list_data_sources(self) -> list[dict[str, Any]]:
        """
        Return all saved data sources ordered by name.

        Returns:
            List of dicts with keys: ``id``, ``name``, ``spreadsheet_id``,
            ``sheet_name``, ``range_a1``, ``created_at``, ``last_fetched_at``.
        """
        if self._conn is None:
            logger.error("Database not open")
            return []

        try:
            with self._transaction():
                c = self._conn.cursor()
                c.execute(
                    """SELECT ds.id, ds.name, ds.spreadsheet_id, ds.sheet_name,
                              ds.range_a1, ds.created_at, ds.last_fetched_at,
                              sp.name AS spreadsheet_name
                       FROM data_sources ds
                       LEFT JOIN spreadsheets sp ON ds.spreadsheet_id = sp.spreadsheet_id
                       ORDER BY ds.name COLLATE NOCASE"""
                )
                rows = c.fetchall()
                columns = [desc[0] for desc in c.description]
                return [dict(zip(columns, row)) for row in rows]
        except sqlite.Error as e:
            logger.error(f"Error listing data sources: {e}")
            return []

    def get_data_source(self, data_source_id: int) -> Optional[dict[str, Any]]:
        """
        Fetch a single data source by its primary key.

        Args:
            data_source_id: Primary key of the data source row.

        Returns:
            Dict with data source fields, or ``None`` if not found.
        """
        if self._conn is None:
            logger.error("Database not open")
            return None

        try:
            with self._transaction():
                c = self._conn.cursor()
                c.execute(
                    """SELECT ds.id, ds.name, ds.spreadsheet_id, ds.sheet_name,
                              ds.range_a1, ds.created_at, ds.last_fetched_at,
                              sp.name AS spreadsheet_name
                       FROM data_sources ds
                       LEFT JOIN spreadsheets sp ON ds.spreadsheet_id = sp.spreadsheet_id
                       WHERE ds.id = ?""",
                    (data_source_id,),
                )
                row = c.fetchone()
                if row is None:
                    return None
                columns = [desc[0] for desc in c.description]
                return dict(zip(columns, row))
        except sqlite.Error as e:
            logger.error(f"Error fetching data source {data_source_id}: {e}")
            return None

    def update_data_source(
        self,
        data_source_id: int,
        name: str,
        sheet_name: str,
        range_a1: str,
    ) -> bool:
        """
        Update the editable fields of a data source.

        Args:
            data_source_id: Primary key of the row to update.
            name: New human-readable label.
            sheet_name: New sheet tab name.
            range_a1: New range in A1 notation.

        Returns:
            ``True`` on success, ``False`` otherwise.
        """
        if self._conn is None:
            logger.error("Database not open")
            return False

        try:
            with self._transaction():
                c = self._conn.cursor()
                c.execute(
                    """UPDATE data_sources
                       SET name = ?, sheet_name = ?, range_a1 = ?
                       WHERE id = ?""",
                    (name, sheet_name, range_a1, data_source_id),
                )
                if c.rowcount == 0:
                    logger.warning(f"Data source {data_source_id} not found for update")
                    return False
                logger.info(f"Updated data source {data_source_id} → '{name}'")
                return True
        except sqlite.Error as e:
            logger.error(f"Error updating data source {data_source_id}: {e}")
            return False

    def delete_data_source(self, data_source_id: int) -> bool:
        """
        Delete a data source record.

        The raw cell cache (``sheet_data_ranges`` / ``sheet_data_cells``) is left
        intact because it may be shared by other sources or future refreshes.

        Args:
            data_source_id: Primary key of the data source to delete.

        Returns:
            ``True`` on success, ``False`` otherwise.
        """
        if self._conn is None:
            logger.error("Database not open")
            return False

        try:
            with self._transaction():
                c = self._conn.cursor()
                c.execute("DELETE FROM data_sources WHERE id = ?", (data_source_id,))
                if c.rowcount == 0:
                    logger.warning(f"Data source {data_source_id} not found for deletion")
                    return False
                logger.info(f"Deleted data source {data_source_id}")
                return True
        except sqlite.Error as e:
            logger.error(f"Error deleting data source {data_source_id}: {e}")
            return False

    def update_data_source_fetched_at(self, data_source_id: int) -> bool:
        """
        Stamp ``last_fetched_at`` with the current UTC time for a data source.

        Called after a successful data fetch so the sidebar can show when the
        data was last synced from Google Sheets.

        Args:
            data_source_id: Primary key of the data source to update.

        Returns:
            ``True`` on success, ``False`` otherwise.
        """
        if self._conn is None:
            logger.error("Database not open")
            return False

        try:
            with self._transaction():
                c = self._conn.cursor()
                c.execute(
                    "UPDATE data_sources SET last_fetched_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (data_source_id,),
                )
                if c.rowcount == 0:
                    logger.warning(f"Data source {data_source_id} not found when stamping fetch time")
                    return False
                return True
        except sqlite.Error as e:
            logger.error(f"Error stamping fetch time for data source {data_source_id}: {e}")
            return False


class _LazyDb:
    """Lazy proxy for the application-wide ``RipperDb`` singleton.

    The real ``RipperDb`` (which opens a connection, creates directories and runs migrations)
    is constructed on first *use*, not when this module — or any consumer doing
    ``from ripper.ripperlib.database import Db`` — is imported. This keeps imports free of
    filesystem/DB side effects (important for test isolation) while leaving every existing
    ``Db.<method>()`` call site unchanged.

    Both reads and writes are forwarded to the underlying instance so that, e.g.,
    ``Db._db_file_path = ...`` mutates the real RipperDb rather than silently diverging on the
    proxy. Tests can inject an isolated database with ``Db._instance = RipperDb(tmp_path)``
    (the only attribute kept on the proxy itself), guaranteeing the real user database is
    never touched.
    """

    def __init__(self) -> None:
        # Set via object.__setattr__ so these land on the proxy, not a forwarded RipperDb.
        object.__setattr__(self, "_instance", None)
        object.__setattr__(self, "_lock", threading.Lock())

    def _resolve(self) -> RipperDb:
        instance: Optional[RipperDb] = object.__getattribute__(self, "_instance")
        if instance is None:
            # Double-checked locking: without the lock two threads racing the first access
            # could each construct their own RipperDb (separate sqlite connection + create_tables),
            # and the loser's instance — and its lock — would be silently discarded (#105).
            lock = object.__getattribute__(self, "_lock")
            with lock:
                instance = object.__getattribute__(self, "_instance")
                if instance is None:
                    instance = RipperDb()
                    object.__setattr__(self, "_instance", instance)
        return instance

    def __getattr__(self, name: str) -> Any:
        # Only reached for attributes not defined on the proxy itself; forward to the real Db.
        return getattr(self._resolve(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        # `_instance`/`_lock` are the proxy's own backing slots (`_instance` allows test injection);
        # everything else is forwarded to the underlying RipperDb so assignments don't diverge
        # from reads.
        if name in ("_instance", "_lock"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._resolve(), name, value)

    def __delattr__(self, name: str) -> None:
        # Forward deletes to the underlying too, so set/delete stay symmetric (e.g. mock.patch
        # sets an attribute then deletes it on teardown).
        if name in ("_instance", "_lock"):
            object.__delattr__(self, name)
        else:
            delattr(self._resolve(), name)


if TYPE_CHECKING:
    # Let static checkers treat the module-level `Db` as a RipperDb (its runtime behaviour
    # via the proxy is attribute-identical).
    Db: RipperDb
else:
    Db = _LazyDb()
