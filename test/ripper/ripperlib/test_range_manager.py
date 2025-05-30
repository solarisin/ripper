"""
Tests for the range_manager module.
"""

from datetime import datetime

import pytest

from ripper.ripperlib.range_manager import (
    CachedRange,
    CellRange,
    RangeOptimizer,
    _cell_reference_to_a1,
    _parse_cell_reference,
)


class TestCellRange:
    """Test cases for the CellRange class."""

    def test_cell_range_creation(self) -> None:
        """Test basic CellRange creation."""
        range_obj = CellRange(1, 1, 5, 5)
        assert range_obj.start_row == 1
        assert range_obj.start_col == 1
        assert range_obj.end_row == 5
        assert range_obj.end_col == 5

    def test_cell_range_validation(self) -> None:
        """Test CellRange validation."""
        # Valid ranges
        CellRange(1, 1, 1, 1)  # Single cell
        CellRange(1, 1, 10, 10)  # Normal range

        # Invalid ranges
        with pytest.raises(ValueError):
            CellRange(0, 1, 5, 5)  # Zero row

        with pytest.raises(ValueError):
            CellRange(1, 0, 5, 5)  # Zero column

        with pytest.raises(ValueError):
            CellRange(5, 1, 1, 5)  # Start row > end row

        with pytest.raises(ValueError):
            CellRange(1, 5, 5, 1)  # Start col > end col

    def test_from_a1_notation(self) -> None:
        """Test creating CellRange from A1 notation."""
        # Basic ranges
        range_obj = CellRange.from_a1_notation("A1:B2")
        assert range_obj.start_row == 1
        assert range_obj.start_col == 1
        assert range_obj.end_row == 2
        assert range_obj.end_col == 2

        # Complex ranges
        range_obj = CellRange.from_a1_notation("C5:Z100")
        assert range_obj.start_row == 5
        assert range_obj.start_col == 3
        assert range_obj.end_row == 100
        assert range_obj.end_col == 26

        # Multi-letter columns
        range_obj = CellRange.from_a1_notation("AA1:AB2")
        assert range_obj.start_col == 27  # AA = 27
        assert range_obj.end_col == 28  # AB = 28

        # Invalid formats
        with pytest.raises(ValueError):
            CellRange.from_a1_notation("A1B2")  # Missing colon

        with pytest.raises(ValueError):
            CellRange.from_a1_notation("A1:")  # Missing end

    def test_to_a1_notation(self) -> None:
        """Test converting CellRange to A1 notation."""
        assert CellRange(1, 1, 2, 2).to_a1_notation() == "A1:B2"
        assert CellRange(5, 3, 100, 26).to_a1_notation() == "C5:Z100"
        assert CellRange(1, 27, 2, 28).to_a1_notation() == "AA1:AB2"

    def test_contains(self) -> None:
        """Test range containment."""
        outer = CellRange(1, 1, 10, 10)
        inner = CellRange(2, 2, 5, 5)
        non_overlapping = CellRange(15, 15, 20, 20)
        overlapping = CellRange(5, 5, 15, 15)

        assert outer.contains(inner)
        assert not outer.contains(non_overlapping)
        assert not outer.contains(overlapping)
        assert outer.contains(outer)  # Self-containment

    def test_overlaps_with(self) -> None:
        """Test range overlap detection."""
        range1 = CellRange(1, 1, 5, 5)
        range2 = CellRange(3, 3, 7, 7)  # Overlaps
        range3 = CellRange(6, 6, 10, 10)  # No overlap
        range4 = CellRange(5, 5, 8, 8)  # Touching corner

        assert range1.overlaps_with(range2)
        assert range2.overlaps_with(range1)
        assert not range1.overlaps_with(range3)
        assert range1.overlaps_with(range4)  # Corner overlap

    def test_intersection(self) -> None:
        """Test range intersection."""
        range1 = CellRange(1, 1, 5, 5)
        range2 = CellRange(3, 3, 7, 7)
        range3 = CellRange(6, 6, 10, 10)  # No overlap

        intersection = range1.intersection(range2)
        assert intersection is not None
        assert intersection.start_row == 3
        assert intersection.start_col == 3
        assert intersection.end_row == 5
        assert intersection.end_col == 5

        no_intersection = range1.intersection(range3)
        assert no_intersection is None

    def test_union(self) -> None:
        """Test range union (bounding box)."""
        range1 = CellRange(1, 1, 3, 3)
        range2 = CellRange(5, 5, 7, 7)

        union = range1.union(range2)
        assert union.start_row == 1
        assert union.start_col == 1
        assert union.end_row == 7
        assert union.end_col == 7

    def test_subtract(self) -> None:
        """Test range subtraction."""
        # Complete overlap (should return empty list)
        range1 = CellRange(1, 1, 5, 5)
        range2 = CellRange(1, 1, 5, 5)
        result = range1.subtract(range2)
        assert len(result) == 0

        # No overlap (should return original range)
        range3 = CellRange(10, 10, 15, 15)
        result = range1.subtract(range3)
        assert len(result) == 1
        assert result[0] == range1  # Partial overlap
        range4 = CellRange(3, 3, 7, 7)
        result = range1.subtract(range4)
        assert len(result) == 2  # Should create 2 remaining rectangles (top and left)

    def test_cell_count(self) -> None:
        """Test cell count calculation."""
        assert CellRange(1, 1, 1, 1).cell_count() == 1  # Single cell
        assert CellRange(1, 1, 2, 2).cell_count() == 4  # 2x2
        assert CellRange(1, 1, 5, 10).cell_count() == 50  # 5x10


class TestUtilityFunctions:
    """Test cases for utility functions."""

    def test_parse_cell_reference(self) -> None:
        """Test parsing cell references."""
        assert _parse_cell_reference("A1") == (1, 1)
        assert _parse_cell_reference("Z26") == (26, 26)
        assert _parse_cell_reference("AA1") == (1, 27)
        assert _parse_cell_reference("AB123") == (123, 28)

        # Invalid formats
        with pytest.raises(ValueError):
            _parse_cell_reference("1A")

        with pytest.raises(ValueError):
            _parse_cell_reference("A")

        with pytest.raises(ValueError):
            _parse_cell_reference("123")

    def test_cell_reference_to_a1(self) -> None:
        """Test converting coordinates to A1 notation."""
        assert _cell_reference_to_a1(1, 1) == "A1"
        assert _cell_reference_to_a1(26, 26) == "Z26"
        assert _cell_reference_to_a1(1, 27) == "AA1"
        assert _cell_reference_to_a1(123, 28) == "AB123"


class TestRangeOptimizer:
    """Test cases for the RangeOptimizer class."""

    def test_find_missing_ranges_no_cache(self) -> None:
        """Test finding missing ranges when no cache exists."""
        requested = CellRange(1, 1, 5, 5)
        cached_ranges = []

        missing = RangeOptimizer.find_missing_ranges(requested, cached_ranges)
        assert len(missing) == 1
        assert missing[0] == requested

    def test_find_missing_ranges_full_cache(self) -> None:
        """Test finding missing ranges when fully cached."""
        requested = CellRange(2, 2, 4, 4)
        cached_range = CachedRange(
            range_obj=CellRange(1, 1, 5, 5), spreadsheet_id="test", sheet_name="Sheet1", cached_at=datetime.now()
        )

        missing = RangeOptimizer.find_missing_ranges(requested, [cached_range])
        assert len(missing) == 0

    def test_find_missing_ranges_partial_cache(self) -> None:
        """Test finding missing ranges with partial cache coverage."""
        requested = CellRange(1, 1, 10, 10)
        cached_range = CachedRange(
            range_obj=CellRange(3, 3, 7, 7), spreadsheet_id="test", sheet_name="Sheet1", cached_at=datetime.now()
        )

        missing = RangeOptimizer.find_missing_ranges(requested, [cached_range])
        assert len(missing) > 0  # Should have some missing ranges

    def test_find_overlapping_cached_ranges(self) -> None:
        """Test finding overlapping cached ranges."""
        requested = CellRange(3, 3, 7, 7)

        cached_ranges = [
            CachedRange(
                range_obj=CellRange(1, 1, 5, 5),  # Overlaps
                spreadsheet_id="test",
                sheet_name="Sheet1",
                cached_at=datetime.now(),
            ),
            CachedRange(
                range_obj=CellRange(10, 10, 15, 15),  # No overlap
                spreadsheet_id="test",
                sheet_name="Sheet1",
                cached_at=datetime.now(),
            ),
            CachedRange(
                range_obj=CellRange(5, 5, 9, 9),  # Overlaps
                spreadsheet_id="test",
                sheet_name="Sheet1",
                cached_at=datetime.now(),
            ),
        ]

        overlapping = RangeOptimizer.find_overlapping_cached_ranges(requested, cached_ranges)
        assert len(overlapping) == 2  # Two ranges overlap

    def test_can_satisfy_from_cache(self) -> None:
        """Test checking if a range can be satisfied from cache."""
        requested = CellRange(2, 2, 4, 4)

        # Fully covering cache
        full_cache = [
            CachedRange(
                range_obj=CellRange(1, 1, 5, 5), spreadsheet_id="test", sheet_name="Sheet1", cached_at=datetime.now()
            )
        ]
        assert RangeOptimizer.can_satisfy_from_cache(requested, full_cache)

        # Partial cache
        partial_cache = [
            CachedRange(
                range_obj=CellRange(3, 3, 6, 6), spreadsheet_id="test", sheet_name="Sheet1", cached_at=datetime.now()
            )
        ]
        assert not RangeOptimizer.can_satisfy_from_cache(requested, partial_cache)

        # No cache
        assert not RangeOptimizer.can_satisfy_from_cache(requested, [])
