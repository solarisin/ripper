"""
Range management utilities for Google Sheets caching.

This module provides classes and functions for handling A1 notation ranges,
detecting overlaps, and managing cached sheet data ranges efficiently.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from beartype.typing import Optional, Tuple


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
    def from_a1_notation(cls, range_str: str) -> "CellRange":
        """
        Create a CellRange from A1 notation string (e.g., 'A1:B5' or 'A1').

        Args:
            range_str: Range string in A1 notation

        Returns:
            CellRange instance

        Raises:
            ValueError: If the range format is invalid
        """
        if ":" not in range_str:
            # Handle single cell reference (e.g., 'A1')
            row, col = _parse_cell_reference(range_str.strip())
            return cls(row, col, row, col)

        start_cell, end_cell = range_str.split(":", 1)
        start_row, start_col = _parse_cell_reference(start_cell.strip())
        end_row, end_col = _parse_cell_reference(end_cell.strip())

        return cls(start_row, start_col, end_row, end_col)

    def to_a1_notation(self) -> str:
        """
        Convert the range to A1 notation string.

        Returns:
            Range string in A1 notation (e.g., 'A1:B5')
        """
        start_cell = _cell_reference_to_a1(self.start_row, self.start_col)
        end_cell = _cell_reference_to_a1(self.end_row, self.end_col)
        return f"{start_cell}:{end_cell}"

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

        # Top rectangle
        if self.start_row < intersection.start_row:
            remaining_ranges.append(CellRange(self.start_row, self.start_col, intersection.start_row - 1, self.end_col))

        # Bottom rectangle
        if self.end_row > intersection.end_row:
            remaining_ranges.append(CellRange(intersection.end_row + 1, self.start_col, self.end_row, self.end_col))

        # Left rectangle (only the middle section)
        if self.start_col < intersection.start_col:
            remaining_ranges.append(
                CellRange(intersection.start_row, self.start_col, intersection.end_row, intersection.start_col - 1)
            )

        # Right rectangle (only the middle section)
        if self.end_col > intersection.end_col:
            remaining_ranges.append(
                CellRange(intersection.start_row, intersection.end_col + 1, intersection.end_row, self.end_col)
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


def _parse_cell_reference(cell_ref: str) -> Tuple[int, int]:
    """
    Parse a cell reference like 'A1' into row and column numbers.

    Args:
        cell_ref: Cell reference string (e.g., 'A1', 'BC123')

    Returns:
        Tuple of (row, column) as 1-based integers

    Raises:
        ValueError: If the cell reference format is invalid
    """
    if not re.match(r"^[A-Za-z]+\d+$", cell_ref):
        raise ValueError(f"Invalid cell reference format: {cell_ref}")

    # Separate letters and numbers
    col_str = "".join(char for char in cell_ref if char.isalpha())
    row_str = "".join(char for char in cell_ref if char.isdigit())

    if not col_str or not row_str:
        raise ValueError(f"Invalid cell reference format: {cell_ref}")

    # Convert column letters to number (A=1, B=2, ..., Z=26, AA=27, etc.)
    col_num = 0
    for char in col_str.upper():
        col_num = col_num * 26 + (ord(char) - ord("A") + 1)

    row_num = int(row_str)

    return row_num, col_num


def _cell_reference_to_a1(row: int, col: int) -> str:
    """
    Convert row and column numbers to A1 notation.

    Args:
        row: Row number (1-based)
        col: Column number (1-based)

    Returns:
        Cell reference string (e.g., 'A1', 'BC123')
    """
    col_str = ""
    col_num = col

    while col_num > 0:
        col_num -= 1
        col_str = chr(ord("A") + (col_num % 26)) + col_str
        col_num //= 26

    return f"{col_str}{row}"


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
            List of cached ranges that overlap with the requested range
        """
        overlapping = []
        for cached_range in cached_ranges:
            if cached_range.range_obj.overlaps_with(requested_range):
                overlapping.append(cached_range)
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
        return len(missing_ranges) == 0
