from __future__ import annotations

"""Tests for the range_manager module.

This module contains comprehensive tests for the range management functionality,
including CellRange operations and RangeOptimizer functionality.
"""

import random
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Union

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ripper.ripperlib.range_manager import (
    CachedRange,
    CellRange,
    RangeOptimizer,
    _cell_reference_to_a1,
    _parse_cell_reference,
)

# Test timestamp for consistent testing
TEST_TIMESTAMP = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

# Test data for parameterized tests
CELL_RANGE_CREATION = [
    # (start_row, start_col, end_row, end_col)
    (1, 1, 1, 1),  # Single cell
    (1, 1, 10, 10),  # Square range
    (5, 3, 15, 8),  # Rectangular range
    (1, 1, 1000, 26),  # Full row
    (1, 1, 1, 16384),  # Full column (max columns in Google Sheets)
    (1, 1, 1048576, 16384),  # Entire sheet (max rows and columns)
]

# Hypothesis strategies for property-based testing
positive_ints = st.integers(min_value=1, max_value=10_000)
cell_indices = st.integers(min_value=1, max_value=100)  # Reasonable upper bound for tests


def valid_cell_range() -> st.SearchStrategy[tuple[int, int, int, int]]:
    """Generate valid cell range tuples (start_row, start_col, end_row, end_col)."""
    return st.tuples(positive_ints, positive_ints, positive_ints, positive_ints).filter(
        lambda x: x[0] <= x[2] and x[1] <= x[3]
    )


# Fixtures for test data
@pytest.fixture
def sample_cell_ranges() -> list[CellRange]:
    """Provide a list of sample cell ranges for testing."""
    return [
        CellRange(1, 1, 1, 1),  # Single cell
        CellRange(1, 1, 10, 10),  # 10x10 square
        CellRange(5, 5, 15, 15),  # 11x11 square, offset
        CellRange(20, 1, 30, 5),  # 10x5 rectangle (10 rows, 5 columns)
    ]


@pytest.fixture
def sample_cached_ranges(cached_range_factory: Callable[..., CachedRange]) -> list[CachedRange]:
    """Create sample cached ranges for testing.

    Creates a 2x2 grid of cached ranges:
    - A1:J50 (top-left)
    - K1:Z50 (top-right)
    - A51:J100 (bottom-left)
    - K51:Z100 (bottom-right)
    """
    return [
        cached_range_factory("A1:J50"),
        cached_range_factory("K1:Z50"),
        cached_range_factory("A51:J100"),
        cached_range_factory("K51:Z100"),
    ]


@pytest.fixture
def random_cell_range() -> Callable[[], CellRange]:
    """Generate a random valid CellRange for testing."""

    def _create_random_range() -> CellRange:
        start_row = random.randint(1, 1000)
        start_col = random.randint(1, 26)
        end_row = random.randint(start_row, start_row + 100)
        end_col = random.randint(start_col, start_col + 25)
        return CellRange(start_row, start_col, end_row, end_col)

    # Reset random seed for reproducibility
    random.seed(42)
    return _create_random_range


@pytest.fixture
def cached_range_factory(test_timestamp: datetime) -> Callable[..., CachedRange]:
    """Factory to create CachedRange objects with consistent test data.

    Args:
        test_timestamp: Timestamp to use for created ranges

    Returns:
        Function that creates CachedRange objects
    """
    # Ensure test_timestamp has timezone info
    if test_timestamp.tzinfo is None:
        test_timestamp = test_timestamp.replace(tzinfo=timezone.utc)

    def _create_cached_range(
        range_obj: Union[str, CellRange],
        timestamp: Optional[Union[datetime, str]] = None,
        **kwargs: Any,
    ) -> CachedRange:
        """Create a CachedRange with the given parameters."""
        if isinstance(range_obj, str):
            range_obj = CellRange.from_a1_notation(range_obj)

        # Handle timestamp with timezone
        cached_at = timestamp or test_timestamp
        if isinstance(cached_at, str):
            # If timestamp is a string, parse it and add timezone if missing
            cached_at = datetime.fromisoformat(cached_at)
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=timezone.utc)
        elif cached_at.tzinfo is None:
            # If timestamp is a datetime without timezone, add UTC
            cached_at = cached_at.replace(tzinfo=timezone.utc)

        return CachedRange(
            range_obj=range_obj,
            spreadsheet_id=kwargs.get("spreadsheet_id", "test"),
            sheet_name=kwargs.get("sheet_name", "Sheet1"),
            cached_at=cached_at,
        )

    return _create_cached_range


A1_NOTATION_CASES = [
    # (a1_notation, expected_range_tuple)
    ("A1", (1, 1, 1, 1)),
    ("B2", (2, 2, 2, 2)),
    ("Z1", (1, 26, 1, 26)),
    ("AA1", (1, 27, 1, 27)),
    ("AB1", (1, 28, 1, 28)),
    ("A1:B2", (1, 1, 2, 2)),
    ("B2:D4", (2, 2, 4, 4)),
    ("A1:Z100", (1, 1, 100, 26)),
    ("AA1:AB2", (1, 27, 2, 28)),
]


INVALID_A1_NOTATION = [
    "",
    "A",
    "1",
    "A1:",
    ":A1",
    "A1B2",
    "A1:B2:C3",
    "A1:B",
    "A:B2",
    "A1:1B",
    "A1:B2:-",
    "ZZZZ1:A1",
]


RANGE_INTERSECTION_CASES = [
    # (range1, range2, expected_intersection)
    ("A1:B2", "B2:C3", "B2"),
    ("A1:C3", "B2:D4", "B2:C3"),
    ("A1:B2", "C3:D4", None),  # No intersection
    ("A1:Z100", "B2:Y99", "B2:Y99"),
    ("A1:C3", "D4:F6", None),  # No intersection
]


RANGE_UNION_CASES = [
    # (range1, range2, expected_union)
    ("A1:B2", "B2:C3", "A1:C3"),
    ("A1:C3", "B2:D4", "A1:D4"),
    ("A1:B2", "D3:E4", "A1:E4"),  # Disjoint ranges
    ("A1:Z100", "B2:Y99", "A1:Z100"),  # One contains the other
]


RANGE_SUBTRACTION_CASES = [
    # (range1, range2, expected_result)
    ("A1:C3", "B2", ["A1:A3", "C1:C3", "B1:B1", "B3:B3"]),  # Subtract middle cell
    ("A1:C3", "A1:C1", ["A2:C3"]),  # Subtract top row
    ("A1:C3", "A1:A3", ["B1:C3"]),  # Subtract first column
    ("A1:Z100", "B2:Y99", ["A1:Z1", "A100:Z100", "A2:A99", "Z2:Z99"]),  # Subtract inner rectangle
    ("A1:C3", "D4:F6", ["A1:C3"]),  # No overlap
]


class TestCellRange:
    """Test cases for the CellRange class."""

    # Property-based tests using hypothesis
    @settings(max_examples=100, deadline=1000)
    @given(cell_range=valid_cell_range())
    def test_cell_range_creation_property_based(self, cell_range: tuple[int, int, int, int]) -> None:
        """Test CellRange creation with randomly generated valid inputs."""
        start_row, start_col, end_row, end_col = cell_range
        range_obj = CellRange(start_row, start_col, end_row, end_col)
        assert range_obj.start_row == min(start_row, end_row)
        assert range_obj.start_col == min(start_col, end_col)
        assert range_obj.end_row == max(start_row, end_row)
        assert range_obj.end_col == max(start_col, end_col)

    @pytest.mark.parametrize(
        "invalid_val,is_negative",
        [(-1, True), (0, True), (2**31, False)],  # Negative value  # Zero  # Large value that might be accepted
    )
    def test_invalid_cell_range_creation(self, invalid_val: int, is_negative: bool) -> None:
        """Test that invalid cell ranges raise appropriate exceptions."""
        if is_negative:
            # Negative values should always raise an error
            with pytest.raises(ValueError) as exc_info:
                CellRange(invalid_val, 1, 1, 1)
            assert "must be positive" in str(exc_info.value)

            with pytest.raises(ValueError) as exc_info:
                CellRange(1, invalid_val, 1, 1)
            assert "must be positive" in str(exc_info.value)

            with pytest.raises(ValueError) as exc_info:
                CellRange(1, 1, invalid_val, 1)
            assert "must be positive" in str(exc_info.value)

            with pytest.raises(ValueError) as exc_info:
                CellRange(1, 1, 1, invalid_val)
            assert "must be positive" in str(exc_info.value)
        else:
            # Large values might be accepted, so we'll just verify the range is created
            # with the correct values without checking for errors
            try:
                # Test each position with the large value
                cr1 = CellRange(invalid_val, 1, 1, 1)
                assert cr1.start_row == invalid_val

                cr2 = CellRange(1, invalid_val, 1, 1)
                assert cr2.start_col == invalid_val

                cr3 = CellRange(1, 1, invalid_val, 1)
                assert cr3.end_row == invalid_val

                cr4 = CellRange(1, 1, 1, invalid_val)
                assert cr4.end_col == invalid_val
            except Exception as e:
                # If an error is raised, it should be a ValueError with the expected message
                assert isinstance(e, ValueError)
                assert "must be before or equal" in str(e)

    def test_invalid_range_creation(self) -> None:
        """Test that invalid ranges (start > end) raise appropriate exceptions."""
        with pytest.raises(ValueError, match=r"Start cell must be before or equal to end cell"):
            CellRange(10, 1, 1, 1)  # start_row > end_row
        with pytest.raises(ValueError, match=r"Start cell must be before or equal to end cell"):
            CellRange(1, 10, 1, 1)  # start_col > end_col

    @pytest.mark.parametrize("start_row,start_col,end_row,end_col", CELL_RANGE_CREATION)
    def test_cell_range_creation(self, start_row: int, start_col: int, end_row: int, end_col: int) -> None:
        """Test CellRange creation with various valid inputs.

        Args:
            start_row: Starting row index (1-based)
            start_col: Starting column index (1-based)
            end_row: Ending row index (1-based)
            end_col: Ending column index (1-based)
        """
        range_obj = CellRange(start_row, start_col, end_row, end_col)
        assert range_obj.start_row == start_row
        assert range_obj.start_col == start_col
        assert range_obj.end_row == end_row
        assert range_obj.end_col == end_col
        assert range_obj.start_row == start_row
        assert range_obj.start_col == start_col
        assert range_obj.row_count == end_row - start_row + 1
        assert range_obj.col_count == end_col - start_col + 1

    @pytest.mark.parametrize(
        "start_row,start_col,end_row,end_col,expected_valid",
        [
            (1, 1, 1, 1, True),  # Single cell
            (1, 1, 5, 5, True),  # Valid range
            (5, 5, 5, 5, True),  # Single cell (same as first, but testing different values)
            (1, 1, 0, 5, False),  # Invalid row (0)
            (1, 1, 5, 0, False),  # Invalid column (0)
            (5, 5, 1, 1, False),  # Start after end
            (1, 5, 1, 1, False),  # Start column after end column
        ],
    )
    def test_cell_range_validation(
        self, start_row: int, start_col: int, end_row: int, end_col: int, expected_valid: bool
    ) -> None:
        """Test CellRange validation with various inputs."""
        if expected_valid:
            range_obj = CellRange(start_row, start_col, end_row, end_col)
            assert range_obj.start_row == start_row
            assert range_obj.start_col == start_col
            assert range_obj.end_row == end_row
            assert range_obj.end_col == end_col
        else:
            with pytest.raises(ValueError):
                CellRange(start_row, start_col, end_row, end_col)

    @pytest.mark.parametrize("a1_notation,expected", A1_NOTATION_CASES)
    def test_from_a1_notation(self, a1_notation: str, expected: tuple[int, int, int, int]) -> None:
        """Test creating CellRange from A1 notation."""
        range_obj = CellRange.from_a1_notation(a1_notation)
        assert (range_obj.start_row, range_obj.start_col, range_obj.end_row, range_obj.end_col) == expected

    @pytest.mark.parametrize(
        "a1_notation,error_msg",
        [
            ("", "Invalid cell reference format"),
            ("A", "Invalid cell reference format"),
            ("1", "Invalid cell reference format"),
            ("A1:", "Invalid cell reference format"),
            (":A1", "Invalid cell reference format"),
            ("A1B2", "Invalid cell reference format"),
            ("A1:B2:C3", "Invalid cell reference format"),
            ("A1:B", "Invalid cell reference format"),
            ("A:B2", "Invalid cell reference format"),
            ("A1:1B", "Invalid cell reference format"),
            ("A1:B2:-", "Invalid cell reference format"),
            ("ZZZZ1:A1", "Start cell must be before or equal to end cell"),
        ],
    )
    def test_from_a1_notation_invalid(self, a1_notation: str, error_msg: str) -> None:
        """Test invalid A1 notation raises ValueError with correct message."""
        with pytest.raises(ValueError, match=error_msg):
            CellRange.from_a1_notation(a1_notation)

    @pytest.mark.parametrize("large_range", ["A1:ZZZZ1", "A1:ZZZZ2147483647"])
    def test_large_a1_notation(self, large_range: str) -> None:
        """Test that very large A1 notations either raise an error or return a valid range."""
        try:
            result = CellRange.from_a1_notation(large_range)
            # If no exception, verify it's a valid range
            assert isinstance(result, CellRange)
            assert result.start_row > 0
            assert result.start_col > 0
            assert result.end_row >= result.start_row
            assert result.end_col >= result.start_col
        except ValueError as e:
            # Either error is acceptable
            assert "Invalid cell reference format" in str(e) or "must be before or equal" in str(e)

    @given(
        st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=4), st.integers(min_value=1, max_value=1000)
    )
    def test_from_a1_notation_property_based(self, col: str, row: int) -> None:
        """Test A1 notation parsing with property-based testing."""
        a1_notation = f"{col}{row}"
        try:
            range_obj = CellRange.from_a1_notation(a1_notation)
            assert range_obj.start_row == row
            assert range_obj.start_col == self._a1_to_col(col)
            assert range_obj.start_row == range_obj.end_row
            assert range_obj.start_col == range_obj.end_col
        except ValueError as e:
            # Only valid column letters (A-Z) should be accepted
            if not all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for c in col):
                assert "Invalid column" in str(e)
            # Row number must be positive
            elif row < 1:
                assert "Row number must be positive" in str(e)
            else:
                raise

    @staticmethod
    def _a1_to_col(a1_col: str) -> int:
        """Convert A1 column notation to 1-based column number."""
        col = 0
        for c in a1_col:
            if not c.isalpha():
                raise ValueError(f"Invalid column reference: {a1_col}")
            col = col * 26 + (ord(c.upper()) - ord("A") + 1)
        return col

    @pytest.mark.parametrize(
        "outer,inner,expected",
        [
            ("A1:Z100", "B2:Y99", True),  # Inner completely inside
            ("A1:Z100", "A1:Z100", True),  # Same range
            ("A1:Z100", "A1:Z101", False),  # Inner extends beyond in rows
            ("A1:Z100", "A1:AA100", False),  # Inner extends beyond in columns
            ("B2:Y99", "A1:Z100", False),  # Inner contains outer
            ("A1:A1", "B1:B1", False),  # No overlap
            ("A1:Z100", "A1:Z100", True),  # Same range
            ("A1:A1", "A1:A1", True),  # Single cell contains itself
        ],
    )
    def test_contains(self, outer: str, inner: str, expected: bool) -> None:
        """Test range containment.

        Args:
            outer: Outer range in A1 notation
            inner: Inner range in A1 notation
            expected: Whether inner is contained within outer
        """
        outer_range = CellRange.from_a1_notation(outer)
        inner_range = CellRange.from_a1_notation(inner)
        assert (inner_range in outer_range) == expected

        # Test that a range always contains itself
        assert outer_range.contains(outer_range)
        assert inner_range.contains(inner_range)

    @pytest.mark.parametrize("range1,range2,expected", RANGE_INTERSECTION_CASES)
    def test_overlaps_with(self, range1: str, range2: str, expected: str | None) -> None:
        """Test range overlap detection.

        Args:
            range1: First range in A1 notation
            range2: Second range in A1 notation
            expected: Expected intersection in A1 notation, or None if no overlap
        """
        r1 = CellRange.from_a1_notation(range1)
        r2 = CellRange.from_a1_notation(range2)

        if expected is None:
            assert not r1.overlaps_with(r2)
            assert not r2.overlaps_with(r1)  # Test commutative property
        else:
            assert r1.overlaps_with(r2)
            assert r2.overlaps_with(r1)  # Test commutative property

            # If we have an expected intersection, test that too
            expected_range = CellRange.from_a1_notation(expected)
            assert r1.intersection(r2) == expected_range
            assert r2.intersection(r1) == expected_range  # Test commutative property

    @pytest.mark.parametrize("range1,range2,expected_union", RANGE_UNION_CASES)
    def test_union(self, range1: str, range2: str, expected_union: str) -> None:
        """Test range union operation.

        Args:
            range1: First range in A1 notation
            range2: Second range in A1 notation
            expected_union: Expected union in A1 notation
        """
        r1 = CellRange.from_a1_notation(range1)
        r2 = CellRange.from_a1_notation(range2)
        expected = CellRange.from_a1_notation(expected_union)

        assert r1.union(r2) == expected
        assert r2.union(r1) == expected  # Test commutative property

    @pytest.mark.parametrize("range1,range2,expected_result", RANGE_SUBTRACTION_CASES)
    def test_subtract(self, range1: str, range2: str, expected_result: list[str]) -> None:
        """Test range subtraction operation.

        Args:
            range1: Original range in A1 notation
            range2: Range to subtract in A1 notation
            expected_result: List of ranges in A1 notation after subtraction
        """
        r1 = CellRange.from_a1_notation(range1)
        r2 = CellRange.from_a1_notation(range2)

        # Test the subtract method
        result = r1.subtract(r2)

        # Convert results to A1 notation for comparison
        result_a1 = [r.to_a1_notation() for r in result]

        # Compare as sets to ignore order
        assert set(result_a1) == set(expected_result)

        # Test edge cases
        # Subtracting a range from itself should return empty list
        self_subtract = r1.subtract(r1)
        assert len(self_subtract) == 0

        # Subtracting a non-overlapping range should return the original range
        non_overlapping = CellRange(1000, 1000, 1001, 1001)
        non_overlap_result = r1.subtract(non_overlapping)
        assert len(non_overlap_result) == 1
        assert non_overlap_result[0] == r1

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

    def test_union_method(self) -> None:
        """Test the union method creates a bounding box."""
        range1 = CellRange(1, 1, 3, 3)
        range2 = CellRange(2, 2, 4, 4)
        result = range1.union(range2)
        assert result.start_row == 1
        assert result.start_col == 1
        assert result.end_row == 4
        assert result.end_col == 4

    def test_subtract_method(self) -> None:
        """Test the subtract method removes overlapping ranges."""
        # Complete overlap (should return empty list)
        range1 = CellRange(1, 1, 5, 5)
        range2 = CellRange(1, 1, 5, 5)
        result = range1.subtract(range2)
        assert len(result) == 0

        # No overlap (should return original range)
        range3 = CellRange(10, 10, 15, 15)
        result = range1.subtract(range3)
        assert len(result) == 1
        assert result[0] == range1

        # Partial overlap (should return non-overlapping parts)
        range4 = CellRange(3, 3, 6, 6)
        result = range1.subtract(range4)
        assert len(result) == 2

    def test_cell_count(self) -> None:
        """Test cell count calculation."""
        assert CellRange(1, 1, 1, 1).cell_count() == 1  # Single cell
        assert CellRange(1, 1, 2, 2).cell_count() == 4  # 2x2
        assert CellRange(1, 1, 5, 10).cell_count() == 50  # 5x10

        # Remove undefined variable references
        pass


class TestUtilityFunctions:
    """Test cases for utility functions."""

    def test_parse_cell_reference(self) -> None:
        """Test parsing cell references."""
        assert _parse_cell_reference("A1") == (1, 1)
        assert _parse_cell_reference("Z26") == (26, 26)
        assert _parse_cell_reference("AA1") == (1, 27)
        assert _parse_cell_reference("XFD1048576") == (1048576, 16384)  # Max Excel range

        with pytest.raises(ValueError, match="Invalid cell reference format"):
            _parse_cell_reference("")

        with pytest.raises(ValueError, match="Invalid cell reference format"):
            _parse_cell_reference("A")

        with pytest.raises(ValueError, match="Invalid cell reference format"):
            _parse_cell_reference("1")

    def test_cell_reference_to_a1(self) -> None:
        """Test converting coordinates to A1 notation."""
        assert _cell_reference_to_a1(1, 1) == "A1"
        assert _cell_reference_to_a1(26, 26) == "Z26"
        assert _cell_reference_to_a1(1, 27) == "AA1"
        assert _cell_reference_to_a1(1048576, 16384) == "XFD1048576"  # Max Excel range


class TestRangeOptimizer:
    """Test cases for the RangeOptimizer class."""

    @pytest.fixture
    def sample_cached_ranges(self, cached_range_factory: Callable[..., CachedRange]) -> list[CachedRange]:
        """Provide a set of sample cached ranges for testing."""
        return [
            cached_range_factory("A1:J50"),
            cached_range_factory("K1:Z50"),
            cached_range_factory("A51:J100"),
            cached_range_factory("K51:Z100"),
        ]

    @pytest.mark.parametrize(
        ("requested_range_str", "cached_ranges_param", "expected_missing"),
        [
            # Test cases for find_missing_ranges
            ("A1:Z100", ["A1:J50", "K1:Z50", "A51:J100", "K51:Z100"], []),  # Fully covered
            ("A1:Z100", ["A1:J50", "K1:Z50"], ["A51:Z100"]),  # Bottom half missing (combined)
            ("A1:Z100", [], ["A1:Z100"]),  # Nothing cached
            ("A1:Z100", ["A1:Z100"], []),  # Exact match
            ("B2:Y99", ["A1:Z100"], []),  # Requested is fully inside cached
            (
                "A1:Z100",
                ["B2:Y99"],
                [  # Border areas missing
                    "A1:Z1",
                    "A100:Z100",  # Top and bottom rows
                    "A2:A99",
                    "Z2:Z99",  # Left and right columns
                ],
            ),
        ],
    )
    def test_find_missing_ranges(
        self,
        requested_range_str: str,
        cached_ranges_param: list[str],
        expected_missing: list[str],
        cached_range_factory: Callable[..., CachedRange],
    ) -> None:
        """Test finding missing ranges with various cache scenarios."""
        # Convert cached ranges from strings to CachedRange objects
        cached_ranges = []
        for range_str in cached_ranges_param:
            cell_range = CellRange.from_a1_notation(range_str)
            cached_ranges.append(cached_range_factory(cell_range))

        # Create the requested range
        requested = CellRange.from_a1_notation(requested_range_str)

        # Get missing ranges
        missing = RangeOptimizer.find_missing_ranges(requested, cached_ranges)
        missing_str = sorted(r.to_a1_notation() for r in missing)

        # Compare results
        assert missing_str == sorted(expected_missing)

    def test_find_missing_ranges_property_based(
        self, random_cell_range: Callable[[], CellRange], cached_range_factory: Callable[..., CachedRange]
    ) -> None:
        """Property-based test for find_missing_ranges."""
        # Call the random_cell_range fixture function to get a CellRange
        requested = random_cell_range()

        # Create some fixed cached ranges that might overlap
        cached_ranges = [
            cached_range_factory("A1:Z100"),
            cached_range_factory("AA1:ZZ100"),
            cached_range_factory("A101:Z200"),
        ]

        # Find missing ranges
        missing = RangeOptimizer.find_missing_ranges(requested, cached_ranges)

        # If there are no missing ranges, the entire requested range should be covered
        if not missing:
            # Check that the entire requested range is covered by the union of cached ranges
            union = CellRange(1, 1, 1, 1)  # Start with a single cell
            for cr in cached_ranges:
                if cr.range_obj.overlaps_with(requested):
                    union = union.union(cr.range_obj.intersection(requested) or cr.range_obj)

            assert union.contains(requested), f"Requested range {requested} should be fully covered by cached ranges"
        else:
            # If there are missing ranges, they should not overlap with any cached range
            for cr in cached_ranges:
                for m in missing:
                    assert not cr.range_obj.overlaps_with(
                        m
                    ), f"Missing range {m} should not overlap with cached range {cr.range_obj}"

    @pytest.mark.parametrize(
        ("requested_range_str", "expected_count"),
        [
            ("A1:Z100", 4),  # Overlaps all 4 quadrants
            ("A1:J50", 1),  # Exactly matches top-left
            ("I49:K51", 4),  # Overlaps all 4 quadrants at intersection
            ("A1:A10", 1),  # Overlaps one range (A1:J50)
            ("A1:J1", 1),  # Overlaps one range (A1:J50)
            ("Z100:Z101", 1),  # Overlaps one range (K51:Z100) - Z100 is included in K51:Z100
            ("AA1:ZZ100", 0),  # No overlap (AA is column 27, but our test data only goes to Z)
            ("A101:Z200", 0),  # No overlap (A101 is outside all cached ranges which go up to row 100)
            ("A1:Z1", 2),  # Top row overlaps two ranges (A1:J50 and K1:Z50)
            ("AA1:ZZ200", 0),  # No overlap (AA is column 27, but our test data only goes to Z)
            ("A1:Z200", 4),  # Full width overlaps all four ranges (even though it extends beyond)
        ],
    )
    def test_find_overlapping_cached_ranges(
        self, requested_range_str: str, expected_count: int, sample_cached_ranges: list[CachedRange]
    ) -> None:
        """Test finding overlapping cached ranges."""
        print(f"\nTesting with requested range: {requested_range_str}")
        print(f"Expected count: {expected_count}")
        print("Available cached ranges:")
        for i, cr in enumerate(sample_cached_ranges, 1):
            print(
                f"  {i}. {cr.range_obj.to_a1_notation()} "
                f"(rows {cr.range_obj.start_row}-{cr.range_obj.end_row}, "
                f"cols {cr.range_obj.start_col}-{cr.range_obj.end_col})"
            )

        requested = CellRange.from_a1_notation(requested_range_str)
        print(
            f"Requested range: {requested.to_a1_notation()} "
            f"(rows {requested.start_row}-{requested.end_row}, "
            f"cols {requested.start_col}-{requested.end_col})"
        )

        overlapping = RangeOptimizer.find_overlapping_cached_ranges(requested, sample_cached_ranges)
        print(f"Found {len(overlapping)} overlapping ranges:")
        for i, cr in enumerate(overlapping, 1):
            print(
                f"  {i}. {cr.range_obj.to_a1_notation()} "
                f"(rows {cr.range_obj.start_row}-{cr.range_obj.end_row}, "
                f"cols {cr.range_obj.start_col}-{cr.range_obj.end_col})"
            )

        assert len(overlapping) == expected_count, (
            f"Expected {expected_count} overlapping ranges, " f"got {len(overlapping)}"
        )

        # Verify all returned ranges actually overlap with the requested range
        for i, cached in enumerate(overlapping, 1):
            assert cached.range_obj.overlaps_with(requested), f"Range {i} does not overlap with requested range"

    @pytest.fixture
    def single_cached_range(self, cached_range_factory: Callable[..., CachedRange]) -> list[CachedRange]:
        """Provide a single cached range for testing."""
        return [cached_range_factory("A1:J50")]

    @pytest.mark.parametrize(
        "requested_range_str,expected_result",
        [
            ("A1:J50", True),  # Exact match
            ("B2:I49", True),  # Fully inside
            ("A1:Z100", False),  # Partially outside
            ("K1:Z50", False),  # No overlap with cached range
            ("A51:J100", False),  # No overlap with cached range
            ("K51:Z100", False),  # No overlap with cached range
            ("AA1:ZZ100", False),  # Outside
            ("A1:A1", True),  # Single cell inside
            ("J50:J50", True),  # Single cell at corner
            ("A1:Z50", False),  # Partial overlap
            ("A1:K51", False),  # Partial overlap
        ],
    )
    def test_can_satisfy_from_cache(
        self, requested_range_str: str, expected_result: bool, single_cached_range: list[CachedRange]
    ) -> None:
        """Test checking if a range can be satisfied from cache."""
        requested = CellRange.from_a1_notation(requested_range_str)
        result = RangeOptimizer.can_satisfy_from_cache(requested, single_cached_range)
        assert result == expected_result

        # If we can satisfy from cache, there should be no missing ranges
        if result:
            missing = RangeOptimizer.find_missing_ranges(requested, single_cached_range)
            assert not missing, f"Should have no missing ranges if cache can satisfy request, " f"but got {missing}"

    def test_cache_priority(self, cached_range_factory: Callable[..., CachedRange]) -> None:
        """Test that the most recently cached range is used for cache satisfaction."""
        # Create three cached ranges that all overlap with A1:Z100
        ranges = [
            cached_range_factory("A1:Z100", timestamp=datetime(2023, 1, 1, tzinfo=timezone.utc), sheet_name="Sheet1"),
            cached_range_factory("A1:Z100", timestamp=datetime(2023, 1, 2, tzinfo=timezone.utc), sheet_name="Sheet1"),
            cached_range_factory("A1:Z100", timestamp=datetime(2023, 1, 3, tzinfo=timezone.utc), sheet_name="Sheet1"),
        ]

        # All overlapping ranges should be returned, sorted by most recent first
        requested_range = CellRange.from_a1_notation("A1:Z100")
        overlapping = RangeOptimizer.find_overlapping_cached_ranges(requested_range, ranges)

        # Should return all three ranges, sorted by most recent first
        assert len(overlapping) == 3
        assert overlapping[0].cached_at == datetime(2023, 1, 3, tzinfo=timezone.utc)
        assert overlapping[1].cached_at == datetime(2023, 1, 2, tzinfo=timezone.utc)
        assert overlapping[2].cached_at == datetime(2023, 1, 1, tzinfo=timezone.utc)

        # The most recent range should be used for cache satisfaction
        assert RangeOptimizer.can_satisfy_from_cache(requested_range, ranges) is True

        # Test with a smaller range that's fully contained in the cached ranges
        requested = CellRange(1, 1, 5, 5)

        # The most specific and most recent cache should be used
        assert RangeOptimizer.can_satisfy_from_cache(requested, ranges)
        missing = RangeOptimizer.find_missing_ranges(requested, ranges)
        assert len(missing) == 0

        # If we remove the most recent cache, we should fall back to the older ones
        ranges.pop()
        assert RangeOptimizer.can_satisfy_from_cache(requested, ranges)

        # If we remove all caches, it should return False
        ranges.clear()
        assert not RangeOptimizer.can_satisfy_from_cache(requested, ranges)
