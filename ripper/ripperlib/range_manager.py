"""
Range management utilities for Google Sheets caching.

This module provides classes and functions for handling A1 notation ranges,
detecting overlaps, and managing cached sheet data ranges efficiently.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from beartype.typing import Optional, Tuple


def quote_sheet_title(sheet_name: str) -> str:
    """Quote a sheet title for use in A1 notation.

    Google Sheets requires a sheet name to be single-quoted when it contains spaces or
    special characters, with any embedded apostrophe doubled. We always quote: it is valid
    for every title and is *required* for titles that would otherwise be ambiguous (e.g. a
    title that looks like a cell reference such as ``A1``, or one containing ``!``).

    Args:
        sheet_name: The raw (unquoted) sheet title.

    Returns:
        The title wrapped in single quotes with embedded apostrophes doubled.
    """
    return "'" + sheet_name.replace("'", "''") + "'"


def build_a1_range(sheet_name: str, range_a1: Optional[str] = None) -> str:
    """Build a qualified A1 range string, quoting the sheet title.

    Args:
        sheet_name: The raw (unquoted) sheet title.
        range_a1: The cell-range portion (e.g. ``A1:E10``). If falsy, the result is the
            whole-sheet reference (the quoted title alone).

    Returns:
        A qualified A1 range such as ``'Monthly Budget'!A1:E10``, or just ``'Monthly Budget'``
        when no cell range is supplied.
    """
    quoted = quote_sheet_title(sheet_name)
    if range_a1:
        return f"{quoted}!{range_a1}"
    return quoted


def split_sheet_and_range(range_name: str) -> tuple[str, Optional[str]]:
    """Split a combined A1 string into an *unquoted* sheet title and optional cell range.

    Inverse of :func:`build_a1_range`. A sheet title in valid A1 notation may be single-quoted
    (required for titles with spaces/specials; embedded apostrophes are doubled). This parses a
    quoted title as one unit — so a title that itself contains ``!`` (e.g. ``'Q1!Actuals'``) is
    not split on the internal ``!`` — and returns the raw, unquoted title so callers can re-quote
    it exactly once at the API boundary. Passing an already-quoted title straight through would
    double-quote it (e.g. ``'''Monthly Budget'''``) and desync cache keys.

    Args:
        range_name: A combined reference such as ``'Monthly Budget'!A1:B2``, ``Sheet1!A1:B2``,
            or a whole-sheet title like ``'Monthly Budget'``.

    Returns:
        ``(title, range_a1)`` where ``range_a1`` is ``None`` for a whole-sheet reference.
    """
    if range_name.startswith("'"):
        # Quoted title: scan to the closing quote, treating a doubled '' as an escaped apostrophe.
        i = 1
        while i < len(range_name):
            if range_name[i] == "'":
                if i + 1 < len(range_name) and range_name[i + 1] == "'":
                    i += 2  # escaped apostrophe inside the title
                    continue
                break  # closing quote
            i += 1
        title = range_name[1:i].replace("''", "'")
        rest = range_name[i + 1 :]
        return (title, rest[1:]) if rest.startswith("!") else (title, None)

    # Unquoted: a cell range never contains '!', so the FINAL '!' (if any) separates the
    # (possibly '!'-containing) title from the range.
    if "!" not in range_name:
        return range_name, None
    sheet_name, range_part = range_name.rsplit("!", 1)
    return sheet_name, range_part


@dataclass(frozen=True)
class CellRange:
    """
    Represents a rectangular range of cells in a spreadsheet.

    Uses 1-based indexing consistent with Google Sheets A1 notation.
    """

    start_row: int
    start_col: int
    end_row: int
    end_col: int

    def __post_init__(self) -> None:
        """Validate the range after initialization."""
        if self.start_row < 1 or self.start_col < 1 or self.end_row < 1 or self.end_col < 1:
            raise ValueError("Row and column numbers must be positive")

        if self.start_row > self.end_row or self.start_col > self.end_col:
            raise ValueError("Start cell must be before or equal to end cell")

    @classmethod
    def from_a1_notation(
        cls, range_str: str, max_row: Optional[int] = None, max_col: Optional[int] = None
    ) -> "CellRange":
        """
        Create a CellRange from A1 notation string (e.g., 'A1:B5' or 'A1').

        Supports open-ended ranges by resolving the missing bound from the sheet's grid
        dimensions:
        - column-only ``A:Z``      -> rows 1..max_row, cols A..Z
        - row-only ``2:10``        -> rows 2..10, cols 1..max_col
        - half-open ``A5:Z``       -> rows 5..max_row, cols A..Z

        Args:
            range_str: Range string in A1 notation
            max_row: Sheet row count, used to resolve an open-ended end row
            max_col: Sheet column count, used to resolve an open-ended end column

        Returns:
            CellRange instance

        Raises:
            ValueError: If the range format is invalid, or an open-ended bound cannot be
                resolved because the corresponding grid dimension was not provided.
        """
        range_str = range_str.strip()
        if ":" not in range_str:
            # Handle single cell reference (e.g., 'A1')
            row, col = _parse_cell_reference(range_str)
            return cls(row, col, row, col)

        start_cell, end_cell = range_str.split(":", 1)
        start_row, start_col = _parse_partial_cell_reference(start_cell.strip())
        end_row, end_col = _parse_partial_cell_reference(end_cell.strip())

        # Bounded range, e.g. 'A1:B5'.
        if start_row is not None and start_col is not None and end_row is not None and end_col is not None:
            return cls(start_row, start_col, end_row, end_col)
        # Whole-column range, e.g. 'A:Z' (no rows on either side).
        if start_row is None and end_row is None and start_col is not None and end_col is not None:
            if max_row is None:
                raise ValueError(f"Open-ended range {range_str!r} requires the sheet's row count to resolve")
            return cls(1, start_col, max_row, end_col)
        # Whole-row range, e.g. '2:10' (no columns on either side).
        if start_col is None and end_col is None and start_row is not None and end_row is not None:
            if max_col is None:
                raise ValueError(f"Open-ended range {range_str!r} requires the sheet's column count to resolve")
            return cls(start_row, 1, end_row, max_col)
        # Half-open column-bounded range, e.g. 'A5:Z' (full start, column-only end).
        if start_row is not None and start_col is not None and end_row is None and end_col is not None:
            if max_row is None:
                raise ValueError(f"Open-ended range {range_str!r} requires the sheet's row count to resolve")
            return cls(start_row, start_col, max_row, end_col)

        raise ValueError(f"Unsupported A1 range notation: {range_str!r}")

    def to_a1_notation(self) -> str:
        """
        Convert the range to A1 notation string.

        Returns:
            Range string in A1 notation (e.g., 'A1:B5')
        """
        start_cell = _cell_reference_to_a1(self.start_row, self.start_col)
        end_cell = _cell_reference_to_a1(self.end_row, self.end_col)
        return f"{start_cell}:{end_cell}"

    def __contains__(self, other: "CellRange") -> bool:
        """
        Support the 'in' operator for range containment.

        Args:
            other: The range to check

        Returns:
            True if this range contains the other range
        """
        return self.contains(other)

    def contains(self, other: "CellRange") -> bool:
        """
        Check if this range completely contains another range.

        Args:
            other: The range to check

        Returns:
            True if this range contains the other range
        """
        return (
            self.start_row <= other.start_row
            and self.start_col <= other.start_col
            and self.end_row >= other.end_row
            and self.end_col >= other.end_col
        )

    @property
    def row_count(self) -> int:
        """Get the number of rows in this range."""
        return self.end_row - self.start_row + 1

    @property
    def col_count(self) -> int:
        """Get the number of columns in this range."""
        return self.end_col - self.start_col + 1

    def overlaps_with(self, other: "CellRange") -> bool:
        """
        Check if this range overlaps with another range.

        Args:
            other: The range to check

        Returns:
            True if the ranges overlap
        """
        return not (
            self.end_row < other.start_row
            or self.start_row > other.end_row
            or self.end_col < other.start_col
            or self.start_col > other.end_col
        )

    def intersection(self, other: "CellRange") -> Optional["CellRange"]:
        """
        Get the intersection of this range with another range.

        Args:
            other: The range to intersect with

        Returns:
            CellRange representing the intersection, or None if no overlap
        """
        if not self.overlaps_with(other):
            return None

        start_row = max(self.start_row, other.start_row)
        start_col = max(self.start_col, other.start_col)
        end_row = min(self.end_row, other.end_row)
        end_col = min(self.end_col, other.end_col)

        return CellRange(start_row, start_col, end_row, end_col)

    def union(self, other: "CellRange") -> "CellRange":
        """
        Get the union (bounding box) of this range with another range.

        Args:
            other: The range to union with

        Returns:
            CellRange representing the bounding box of both ranges
        """
        start_row = min(self.start_row, other.start_row)
        start_col = min(self.start_col, other.start_col)
        end_row = max(self.end_row, other.end_row)
        end_col = max(self.end_col, other.end_col)

        return CellRange(start_row, start_col, end_row, end_col)

    def _subtract_single_cell(self, intersection: "CellRange") -> list["CellRange"]:
        """
        Calculate the remaining regions when a single cell is subtracted from this range.

        This method handles the special case where a single cell needs to be removed from
        a larger range. It returns up to 4 rectangular regions that represent the areas
        remaining after the cell is removed: left, right, top, and bottom parts.

        Args:
            intersection: A CellRange representing a single cell (start == end)

        Returns:
            List of CellRange objects representing the remaining rectangular areas
            after the single cell is subtracted. May return 0-4 ranges depending
            on the position of the cell within this range.
        """
        remaining_ranges = []
        row, col = intersection.start_row, intersection.start_col

        # Left part
        if col > self.start_col:
            remaining_ranges.append(CellRange(self.start_row, self.start_col, self.end_row, col - 1))
        # Right part
        if col < self.end_col:
            remaining_ranges.append(CellRange(self.start_row, col + 1, self.end_row, self.end_col))
        # Top part
        if row > self.start_row:
            remaining_ranges.append(CellRange(self.start_row, col, row - 1, col))
        # Bottom part
        if row < self.end_row:
            remaining_ranges.append(CellRange(row + 1, col, self.end_row, col))

        return remaining_ranges

    def subtract(self, other: "CellRange") -> list["CellRange"]:
        """
        Subtract another range from this range, returning remaining rectangles.

        Args:
            other: The range to subtract

        Returns:
            List of CellRange objects representing the remaining areas
        """
        if not self.overlaps_with(other):
            return [self]

        intersection = self.intersection(other)
        if intersection is None:
            return [self]

        if intersection == self:
            return []  # Complete overlap

        remaining_ranges = []

        # Special case: subtracting a single cell
        if intersection.start_row == intersection.end_row and intersection.start_col == intersection.end_col:
            return self._subtract_single_cell(intersection)

        # Original logic for non-single cell ranges
        # Top rectangle
        if self.start_row < intersection.start_row:
            remaining_ranges.append(CellRange(self.start_row, self.start_col, intersection.start_row - 1, self.end_col))

        # Bottom rectangle
        if self.end_row > intersection.end_row:
            remaining_ranges.append(CellRange(intersection.end_row + 1, self.start_col, self.end_row, self.end_col))

        # Left rectangle (only the middle section)
        if self.start_col < intersection.start_col:
            remaining_ranges.append(
                CellRange(
                    max(self.start_row, intersection.start_row),
                    self.start_col,
                    min(self.end_row, intersection.end_row),
                    intersection.start_col - 1,
                )
            )

        # Right rectangle (only the middle section)
        if self.end_col > intersection.end_col:
            remaining_ranges.append(
                CellRange(
                    max(self.start_row, intersection.start_row),
                    intersection.end_col + 1,
                    min(self.end_row, intersection.end_row),
                    self.end_col,
                )
            )

        return remaining_ranges

    def cell_count(self) -> int:
        """Get the number of cells in this range."""
        return (self.end_row - self.start_row + 1) * (self.end_col - self.start_col + 1)


@dataclass
class CachedRange:
    """
    Represents a cached range with metadata.
    """

    range_obj: CellRange
    spreadsheet_id: str
    sheet_name: str
    cached_at: datetime
    range_id: Optional[int] = None


def _parse_partial_cell_reference(cell_ref: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Parse a possibly open-ended A1 reference into (row, column).

    Either component may be ``None`` for open-ended references:
    - ``'A5'`` -> ``(5, 1)``
    - ``'A'``  -> ``(None, 1)`` (column only)
    - ``'5'``  -> ``(5, None)`` (row only)

    Args:
        cell_ref: Cell reference string (e.g., 'A1', 'A', '5')

    Returns:
        Tuple of (row, column) as 1-based integers, each possibly ``None``

    Raises:
        ValueError: If the reference format is invalid
    """
    cell_ref = cell_ref.strip()
    match = re.fullmatch(r"([A-Za-z]*)(\d*)", cell_ref)
    if not match or cell_ref == "":
        raise ValueError(f"Invalid cell reference format: {cell_ref}")

    col_str, row_str = match.group(1), match.group(2)
    if not col_str and not row_str:
        raise ValueError(f"Invalid cell reference format: {cell_ref}")

    col_num: Optional[int] = None
    if col_str:
        # Convert column letters to number (A=1, B=2, ..., Z=26, AA=27, etc.)
        col_num = 0
        for char in col_str.upper():
            col_num = col_num * 26 + (ord(char) - ord("A") + 1)

    row_num = int(row_str) if row_str else None

    return row_num, col_num


def _parse_cell_reference(cell_ref: str) -> Tuple[int, int]:
    """
    Parse a fully-qualified cell reference like 'A1' into row and column numbers.

    Args:
        cell_ref: Cell reference string (e.g., 'A1', 'BC123')

    Returns:
        Tuple of (row, column) as 1-based integers

    Raises:
        ValueError: If the cell reference format is invalid or open-ended
    """
    row_num, col_num = _parse_partial_cell_reference(cell_ref)
    if row_num is None or col_num is None:
        raise ValueError(f"Invalid cell reference format: {cell_ref}")
    return row_num, col_num


def column_number_to_a1(col: int) -> str:
    """Convert a 1-based column number to its A1 column letters ('A', 'Z', 'AA', 'AD').

    Args:
        col: Column number (1-based).

    Returns:
        The A1 column-letter portion (no row), e.g. ``'AD'`` for column 30.
    """
    col_str = ""
    col_num = col

    while col_num > 0:
        col_num -= 1
        col_str = chr(ord("A") + (col_num % 26)) + col_str
        col_num //= 26

    return col_str


def _cell_reference_to_a1(row: int, col: int) -> str:
    """
    Convert row and column numbers to A1 notation.

    Args:
        row: Row number (1-based)
        col: Column number (1-based)

    Returns:
        Cell reference string (e.g., 'A1', 'BC123')
    """
    return f"{column_number_to_a1(col)}{row}"


class RangeOptimizer:
    """
    Utilities for optimizing range operations.
    """

    @staticmethod
    def find_missing_ranges(requested_range: CellRange, cached_ranges: list[CachedRange]) -> list[CellRange]:
        """
        Find the ranges that need to be fetched from the API.

        Args:
            requested_range: The range that was requested
            cached_ranges: List of cached ranges that might overlap

        Returns:
            List of CellRange objects that need to be fetched
        """
        if not cached_ranges:
            return [requested_range]

        # Start with the full requested range
        missing_ranges = [requested_range]

        # Subtract each cached range from the missing ranges
        for cached_range in cached_ranges:
            if not cached_range.range_obj.overlaps_with(requested_range):
                continue

            # Apply subtraction to all current missing ranges
            new_missing_ranges = []
            for missing_range in missing_ranges:
                new_missing_ranges.extend(missing_range.subtract(cached_range.range_obj))
            missing_ranges = new_missing_ranges

        return missing_ranges

    @staticmethod
    def find_overlapping_cached_ranges(
        requested_range: CellRange, cached_ranges: list[CachedRange]
    ) -> list[CachedRange]:
        """
        Find cached ranges that overlap with the requested range.

        Args:
            requested_range: The range that was requested
            cached_ranges: List of all cached ranges

        Returns:
            List of cached ranges that overlap with the requested range,
            sorted by most recent first (descending order of cached_at)
        """
        overlapping = []
        for cached_range in cached_ranges:
            if cached_range.range_obj.overlaps_with(requested_range):
                overlapping.append(cached_range)

        # Sort by most recent first (descending order of cached_at)
        overlapping.sort(key=lambda x: x.cached_at, reverse=True)
        return overlapping

    @staticmethod
    def can_satisfy_from_cache(requested_range: CellRange, cached_ranges: list[CachedRange]) -> bool:
        """
        Check if the requested range can be completely satisfied from cache.

        Args:
            requested_range: The range that was requested
            cached_ranges: List of cached ranges

        Returns:
            True if the requested range can be completely satisfied from cache
        """
        missing_ranges = RangeOptimizer.find_missing_ranges(requested_range, cached_ranges)

        # Be more conservative - if there are any missing ranges, don't claim it can be satisfied from cache
        # This helps avoid issues where ranges exist but don't have cell data
        if len(missing_ranges) > 0:
            return False

        # Additional validation: ensure cached ranges actually overlap meaningfully
        # Check that we have overlapping ranges that cover the entire requested area
        overlapping = RangeOptimizer.find_overlapping_cached_ranges(requested_range, cached_ranges)
        if not overlapping:
            return False

        # Create a union of all overlapping ranges to see if they fully contain the requested range
        if len(overlapping) == 1:
            return overlapping[0].range_obj.contains(requested_range)

        # For multiple ranges, we rely on the missing_ranges calculation
        # If missing_ranges is empty, then the ranges should cover everything
        return True
