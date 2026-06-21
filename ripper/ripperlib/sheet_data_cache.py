"""
Sheet data caching service for Google Sheets integration.

This module provides the SheetDataCache class which manages intelligent caching
of Google Sheets data with range overlap detection and optimization.
"""

from datetime import datetime

from beartype.typing import Any, Optional
from loguru import logger

from ripper.ripperlib.database import Db, RipperDb
from ripper.ripperlib.defs import LoadSource, SheetData, SheetsService
from ripper.ripperlib.range_manager import CachedRange, CellRange, RangeOptimizer


class SheetDataCache:
    """
    Manages caching of Google Sheets data with intelligent range handling.

    This class handles:
    - Detecting when data can be served from cache
    - Determining what data needs to be fetched from API
    - Merging new data with existing cache
    - Optimizing API calls by minimizing redundant requests"""

    # Upper bound on the cell count of a resolved range before we decline to cache it and
    # fetch directly instead (guards against open-ended ranges on huge grids).
    _MAX_CACHEABLE_CELLS = 2_000_000

    def __init__(self, db: Optional[RipperDb] = None) -> None:
        """Initialize the sheet data cache."""
        self._db = db or Db

    def get_sheet_data(
        self, service: SheetsService, spreadsheet_id: str, sheet_name: str, range_str: str
    ) -> tuple[SheetData, list[tuple[LoadSource, str]]]:
        """
        Get sheet data from cache or API, with intelligent range optimization.

        Open-ended ranges (e.g. ``A:Z``) are resolved against the sheet's grid dimensions so
        they can use the cache; the result is trimmed of trailing empty rows/columns to match
        what a direct unbounded API read would return.

        Args:
            service: Authenticated Google Sheets API service
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: The name of the sheet
            range_str: Range in A1 notation (e.g., 'A1:C10', 'A:Z')

        Returns:
            Tuple of (sheet_data, load_source) where sheet_data is a 2D list
            and load_source indicates whether data came from cache or API
        """
        # Resolve open-ended ranges using the sheet's grid dimensions so the smart cache can
        # serve unbounded requests instead of silently falling back to the API every time.
        max_row, max_col = self._resolve_grid_dimensions(spreadsheet_id, sheet_name)
        try:
            requested_range = CellRange.from_a1_notation(range_str, max_row=max_row, max_col=max_col)
        except ValueError as e:
            # Expected for ranges we can't resolve (e.g. open-ended with unknown grid dims).
            # Fall back to a direct API read without the per-call error noise.
            logger.debug(f"Range {range_str!r} is not cacheable ({e}); fetching directly from the API")
            return self._fetch_direct(service, spreadsheet_id, sheet_name, range_str)

        cell_count = (requested_range.end_row - requested_range.start_row + 1) * (
            requested_range.end_col - requested_range.start_col + 1
        )
        if cell_count > self._MAX_CACHEABLE_CELLS:
            logger.debug(
                f"Range {range_str!r} resolves to {cell_count} cells "
                f"(> {self._MAX_CACHEABLE_CELLS}); fetching directly from the API"
            )
            return self._fetch_direct(service, spreadsheet_id, sheet_name, range_str)

        try:
            return self._load_with_cache(service, spreadsheet_id, sheet_name, range_str, requested_range)
        except Exception as e:
            logger.error(f"Error reading sheet data from cache for {range_str!r}, falling back to API: {e}")
            return self._fetch_direct(service, spreadsheet_id, sheet_name, range_str)

    def _load_with_cache(
        self,
        service: SheetsService,
        spreadsheet_id: str,
        sheet_name: str,
        range_str: str,
        requested_range: CellRange,
    ) -> tuple[SheetData, list[tuple[LoadSource, str]]]:
        """Serve a (resolved, bounded) range from cache, fetching only the missing sub-ranges."""
        cached_ranges = self._get_cached_ranges(spreadsheet_id, sheet_name)

        # Check if we can satisfy the request entirely from cache
        if RangeOptimizer.can_satisfy_from_cache(requested_range, cached_ranges):
            data = self._get_data_from_cache(spreadsheet_id, sheet_name, requested_range)
            return self._finalize(data, range_str), [(LoadSource.DATABASE, range_str)]

        # Find what ranges we need to fetch from API
        missing_ranges = RangeOptimizer.find_missing_ranges(requested_range, cached_ranges)
        overlapping_cached = RangeOptimizer.find_overlapping_cached_ranges(requested_range, cached_ranges)

        # Fetch missing data from API
        from ripper.ripperlib.sheets_backend import fetch_data_from_spreadsheet

        api_data = {}
        for missing_range in missing_ranges:
            range_notation = f"{sheet_name}!{missing_range.to_a1_notation()}"
            data = fetch_data_from_spreadsheet(service, spreadsheet_id, range_notation)
            # Store in cache regardless of whether data is empty
            api_data[missing_range] = data
            if data:  # Only store non-empty data in cache
                self._store_range_data(spreadsheet_id, sheet_name, missing_range, data)

        # Combine cached and API data to build the final result
        result_data = self._combine_range_data(
            spreadsheet_id, sheet_name, requested_range, overlapping_cached, api_data
        )

        # Build range sources list based on what was fetched
        range_sources: list[tuple[LoadSource, str]] = []
        for cached_range in overlapping_cached:
            range_sources.append((LoadSource.DATABASE, cached_range.range_obj.to_a1_notation()))
        for missing_range in missing_ranges:
            range_sources.append((LoadSource.API, missing_range.to_a1_notation()))

        # If no specific ranges, use the original request
        if not range_sources:
            source = LoadSource.DATABASE if not missing_ranges else LoadSource.API
            range_sources = [(source, range_str)]

        return self._finalize(result_data, range_str), range_sources

    def _resolve_grid_dimensions(self, spreadsheet_id: str, sheet_name: str) -> tuple[Optional[int], Optional[int]]:
        """Look up (row_count, column_count) for a sheet from stored metadata, if available."""
        try:
            sheets = self._db.get_sheet_properties_of_spreadsheet(spreadsheet_id)
        except Exception as e:
            logger.debug(f"Could not load grid dimensions for {spreadsheet_id!r}: {e}")
            return None, None
        for sheet in sheets:
            if sheet.title == sheet_name:
                return sheet.grid.row_count, sheet.grid.column_count
        return None, None

    def _fetch_direct(
        self, service: SheetsService, spreadsheet_id: str, sheet_name: str, range_str: str
    ) -> tuple[SheetData, list[tuple[LoadSource, str]]]:
        """Fetch a range directly from the API, bypassing the cache."""
        from ripper.ripperlib.sheets_backend import fetch_data_from_spreadsheet

        range_notation = f"{sheet_name}!{range_str}"
        data = fetch_data_from_spreadsheet(service, spreadsheet_id, range_notation)
        return data, [(LoadSource.API, range_str)]

    def _finalize(self, data: SheetData, range_str: str) -> SheetData:
        """Trim trailing empty rows/columns for open-ended requests to match a direct read.

        An unbounded range (e.g. ``A:Z``) is resolved to a fixed rectangle from the grid
        dimensions, but a direct API read of the same range returns ragged data with trailing
        empty rows/columns omitted. Trim both so cached and direct results are equivalent
        (and so callers like ``get_tiller_transactions`` don't see padded None columns/rows).
        """
        if self._is_open_ended(range_str):
            data = _trim_trailing_empty_rows(data)
            data = _trim_trailing_empty_columns(data)
        return data

    @staticmethod
    def _is_open_ended(range_str: str) -> bool:
        """True when the range's end omits a row or a column (e.g. 'A:Z', '2:10', 'A5:Z')."""
        if ":" not in range_str:
            return False
        _, end_cell = range_str.split(":", 1)
        end_cell = end_cell.strip()
        has_row = any(ch.isdigit() for ch in end_cell)
        has_col = any(ch.isalpha() for ch in end_cell)
        return not (has_row and has_col)

    def invalidate_cache(self, spreadsheet_id: str, sheet_name: Optional[str] = None) -> bool:
        """
        Invalidate cached data for a spreadsheet or specific sheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: The name of the sheet (if None, invalidates entire spreadsheet)

        Returns:
            True if successful, False otherwise
        """
        return self._db.invalidate_sheet_data_cache(spreadsheet_id, sheet_name)

    def _get_cached_ranges(self, spreadsheet_id: str, sheet_name: str) -> list[CachedRange]:
        """
        Get all cached ranges for a specific sheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: The name of the sheet

        Returns:
            List of CachedRange objects
        """
        # First, detect and clean up incomplete ranges
        incomplete_ranges = self._db.detect_incomplete_ranges(spreadsheet_id, sheet_name)

        if incomplete_ranges:
            logger.info(f"Found {len(incomplete_ranges)} incomplete ranges, cleaning up...")
            for range_id in incomplete_ranges:
                self._db.delete_range_data(range_id)

        # Clean up orphaned ranges
        orphaned_count = self._db.clean_orphaned_ranges(spreadsheet_id, sheet_name)
        if orphaned_count > 0:
            logger.debug(f"Cleaned up {orphaned_count} orphaned ranges")

        cached_data = self._db.get_cached_ranges(spreadsheet_id, sheet_name)

        ranges = []
        for data in cached_data:
            try:
                cell_range = CellRange(data["start_row"], data["start_col"], data["end_row"], data["end_col"])
                cached_range = CachedRange(
                    range_obj=cell_range,
                    spreadsheet_id=spreadsheet_id,
                    sheet_name=sheet_name,
                    cached_at=(
                        datetime.fromisoformat(data["cached_at"])
                        if isinstance(data["cached_at"], str)
                        else data["cached_at"]
                    ),
                    range_id=data["range_id"],
                )
                ranges.append(cached_range)
            except Exception as e:
                logger.warning(f"Error parsing cached range data: {e}")
                continue

        return ranges

    def _get_data_from_cache(self, spreadsheet_id: str, sheet_name: str, requested_range: CellRange) -> SheetData:
        """
        Get data from cache for the requested range.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: The name of the sheet
            requested_range: The range to retrieve

        Returns:
            2D list of cell values
        """
        cached_data = self._db.get_sheet_data_from_cache(
            spreadsheet_id,
            sheet_name,
            requested_range.start_row,
            requested_range.start_col,
            requested_range.end_row,
            requested_range.end_col,
        )

        if cached_data is None:
            logger.warning("Cache miss despite optimization indicating data should be available")
            return []

        return cached_data

    def _store_range_data(self, spreadsheet_id: str, sheet_name: str, cell_range: CellRange, data: SheetData) -> None:
        """
        Store range data in the cache.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: The name of the sheet
            cell_range: The range that was fetched
            data: The 2D list of cell values
        """
        range_id = self._db.store_sheet_data_range(
            spreadsheet_id,
            sheet_name,
            cell_range.start_row,
            cell_range.start_col,
            cell_range.end_row,
            cell_range.end_col,
            data,
        )

        if range_id:
            logger.debug(
                f"Successfully stored range {cell_range.to_a1_notation()}"
                f" for sheet '{sheet_name}' in spreadsheet '{spreadsheet_id}'"
            )
        else:
            logger.warning(f"Failed to store range {cell_range.to_a1_notation()}")

    def _combine_range_data(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        requested_range: CellRange,
        overlapping_cached: list[CachedRange],
        api_data: dict[CellRange, SheetData],
    ) -> SheetData:
        """
        Combine cached and API data to build the complete result.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: The name of the sheet
            requested_range: The originally requested range
            overlapping_cached: List of overlapping cached ranges
            api_data: Dictionary mapping ranges to API data

        Returns:
            2D list combining all data sources"""
        # Special case: if we only have API data for a single range and it's
        # empty, return empty list
        if not overlapping_cached and len(api_data) == 1:
            single_api_data = next(iter(api_data.values()))
            if not single_api_data:
                return []

        # Initialize result matrix
        rows = requested_range.end_row - requested_range.start_row + 1
        cols = requested_range.end_col - requested_range.start_col + 1
        result = [[None for _ in range(cols)] for _ in range(rows)]

        # Fill in cached data first
        for cached_range in overlapping_cached:
            intersection = requested_range.intersection(cached_range.range_obj)
            if intersection is None:
                continue

            cached_data = self._db.get_sheet_data_from_cache(
                spreadsheet_id,
                sheet_name,
                intersection.start_row,
                intersection.start_col,
                intersection.end_row,
                intersection.end_col,
            )

            if cached_data:
                self._fill_result_matrix(result, requested_range, intersection, cached_data)

        # Fill in API data (this can overwrite cached data if there's overlap)
        for api_range, data in api_data.items():
            intersection = requested_range.intersection(api_range)
            if intersection is None:
                continue

            # Extract the relevant portion of API data for the intersection
            api_start_row_offset = intersection.start_row - api_range.start_row
            api_start_col_offset = intersection.start_col - api_range.start_col
            api_end_row_offset = intersection.end_row - api_range.start_row
            api_end_col_offset = intersection.end_col - api_range.start_col

            intersection_data = []
            for row_idx in range(api_start_row_offset, api_end_row_offset + 1):
                if row_idx < len(data):
                    row = data[row_idx][api_start_col_offset : api_end_col_offset + 1]
                    intersection_data.append(row)
                else:
                    # Pad with empty values if API data is shorter
                    intersection_data.append([None] * (api_end_col_offset - api_start_col_offset + 1))

            self._fill_result_matrix(result, requested_range, intersection, intersection_data)

        return result

    def _fill_result_matrix(
        self, result: list[list[Any]], requested_range: CellRange, data_range: CellRange, data: SheetData
    ) -> None:
        """
        Fill a portion of the result matrix with data.

        Args:
            result: The result matrix to fill
            requested_range: The originally requested range
            data_range: The range that this data covers
            data: The 2D list of data to insert
        """
        result_start_row = data_range.start_row - requested_range.start_row
        result_start_col = data_range.start_col - requested_range.start_col

        for row_offset, row_data in enumerate(data):
            result_row = result_start_row + row_offset
            if 0 <= result_row < len(result):
                for col_offset, cell_value in enumerate(row_data):
                    result_col = result_start_col + col_offset
                    if 0 <= result_col < len(result[result_row]):
                        result[result_row][result_col] = cell_value

    def validate_cache_integrity(self, spreadsheet_id: str, sheet_name: str) -> bool:
        """
        Validate the integrity of cached data for a sheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: The name of the sheet

        Returns:
            True if cache is valid, False if there are integrity issues
        """
        try:
            # Get cached ranges
            cached_ranges = self._get_cached_ranges(spreadsheet_id, sheet_name)

            if not cached_ranges:
                return True  # Empty cache is valid

            # Validate each range has cell data
            for cached_range in cached_ranges:
                range_obj = cached_range.range_obj

                # Try to get a small sample from this range to verify it has data
                test_data = self._db.get_sheet_data_from_cache(
                    spreadsheet_id,
                    sheet_name,
                    range_obj.start_row,
                    range_obj.start_col,
                    min(range_obj.start_row + 2, range_obj.end_row),  # Just test first few rows
                    min(range_obj.start_col + 2, range_obj.end_col),  # Just test first few cols
                )

                if test_data is None:
                    logger.warning(
                        f"Cache integrity issue: Range {cached_range.range_id} "
                        f"({range_obj.to_a1_notation()}) has no accessible data"
                    )
                    return False

            return True

        except Exception as e:
            logger.error(f"Error validating cache integrity: {e}")
            return False


def _is_empty_cell(value: Any) -> bool:
    """Return True for cells that an unbounded API read would treat as absent."""
    return value is None or value == ""


def _trim_trailing_empty_rows(data: SheetData) -> SheetData:
    """Drop trailing rows whose cells are all empty (matches an unbounded API read)."""
    end = len(data)
    while end > 0 and all(_is_empty_cell(cell) for cell in data[end - 1]):
        end -= 1
    return data[:end]


def _trim_trailing_empty_columns(data: SheetData) -> SheetData:
    """Drop trailing columns whose cells are all empty across every row."""
    if not data:
        return data
    last_col = 0
    for row in data:
        for idx in range(len(row) - 1, -1, -1):
            if not _is_empty_cell(row[idx]):
                last_col = max(last_col, idx + 1)
                break
    return [row[:last_col] for row in data]
