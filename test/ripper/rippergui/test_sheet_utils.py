import pytest

from ripper.rippergui.sheet_utils import (
    MAX_SHEET_COLUMNS,
    SheetRangeValidator,
    col_to_letter,
    parse_cell,
)


def test_col_to_letter():
    assert col_to_letter(1) == "A"
    assert col_to_letter(26) == "Z"
    assert col_to_letter(27) == "AA"
    assert col_to_letter(52) == "AZ"
    assert col_to_letter(53) == "BA"
    assert col_to_letter(702) == "ZZ"
    assert col_to_letter(703) == "AAA"


def test_parse_cell():
    assert parse_cell("A1") == (1, 1)
    assert parse_cell("Z10") == (10, 26)
    assert parse_cell("AA1") == (1, 27)
    assert parse_cell("AB20") == (20, 28)
    with pytest.raises(ValueError):
        parse_cell("1A")  # Invalid format
    with pytest.raises(ValueError):
        parse_cell("A")  # Missing row
    with pytest.raises(ValueError):
        parse_cell("1")  # Missing column


def test_is_range_empty():
    assert SheetRangeValidator.is_range_empty("A1:B2") is True
    assert SheetRangeValidator.is_range_empty("") is False
    assert SheetRangeValidator.is_range_empty("   ") is False


class TestIsRangeFormatValid:
    """The accepted-A1 contract for :meth:`SheetRangeValidator.is_range_format_valid`.

    Format validity is delegated to the canonical parser (``CellRange.from_a1_notation``) so the
    GUI accepts exactly the forms the backend understands. Accepted forms: single cell (``A1``),
    bounded (``A1:B5``), whole column (``A:A``/``A:Z``), whole row (``2:10``), and half-open
    (``A1:A``/``A1:B``). Reversed, empty, structurally malformed, and over-limit-column inputs are
    rejected.
    """

    def test_single_cell_accepted(self):
        assert SheetRangeValidator.is_range_format_valid("A1") is True
        assert SheetRangeValidator.is_range_format_valid("XFD1048576") is True

    def test_bounded_range_accepted(self):
        assert SheetRangeValidator.is_range_format_valid("A1:B5") is True
        # The app itself generates ``A1:{col}{row}`` full ranges; these must stay valid.
        assert SheetRangeValidator.is_range_format_valid("A1:Z100") is True

    def test_whole_column_accepted(self):
        assert SheetRangeValidator.is_range_format_valid("A:A") is True
        assert SheetRangeValidator.is_range_format_valid("A:Z") is True

    def test_whole_row_accepted(self):
        assert SheetRangeValidator.is_range_format_valid("2:10") is True

    def test_half_open_accepted(self):
        assert SheetRangeValidator.is_range_format_valid("A1:A") is True
        assert SheetRangeValidator.is_range_format_valid("A1:B") is True

    def test_whitespace_is_tolerated(self):
        assert SheetRangeValidator.is_range_format_valid("  A1:B5  ") is True

    def test_empty_rejected(self):
        assert SheetRangeValidator.is_range_format_valid("") is False
        assert SheetRangeValidator.is_range_format_valid("   ") is False

    def test_structurally_malformed_rejected(self):
        assert SheetRangeValidator.is_range_format_valid("A1B2") is False
        assert SheetRangeValidator.is_range_format_valid("A1:") is False
        assert SheetRangeValidator.is_range_format_valid(":B2") is False
        assert SheetRangeValidator.is_range_format_valid("A") is False
        assert SheetRangeValidator.is_range_format_valid("1") is False
        assert SheetRangeValidator.is_range_format_valid("A:5") is False

    def test_reversed_range_rejected(self):
        assert SheetRangeValidator.is_range_format_valid("B2:A1") is False

    def test_over_limit_columns_rejected(self):
        # ``ZZZZ1`` far exceeds the Sheets column limit and must not read as valid format.
        assert SheetRangeValidator.is_range_format_valid("ZZZZ1") is False
        # Boundary: Google Sheets supports up to column "ZZZ" (18278) — NOT the Excel "XFD"
        # (16384) ceiling — so the last valid column is accepted and one past it (AAAA) is not.
        assert col_to_letter(MAX_SHEET_COLUMNS) == "ZZZ"
        assert col_to_letter(MAX_SHEET_COLUMNS + 1) == "AAAA"
        assert SheetRangeValidator.is_range_format_valid(f"{col_to_letter(MAX_SHEET_COLUMNS)}1") is True
        assert SheetRangeValidator.is_range_format_valid(f"{col_to_letter(MAX_SHEET_COLUMNS + 1)}1") is False
        # Columns between the Excel and Sheets ceilings (XFE..ZZZ) are valid in Sheets.
        assert SheetRangeValidator.is_range_format_valid("XFE1") is True
        # Over-limit column in an open-ended form is rejected too.
        assert SheetRangeValidator.is_range_format_valid(f"A:{col_to_letter(MAX_SHEET_COLUMNS + 1)}") is False


class TestIsRangeWithinBounds:
    """Bounds checking resolves open-ended forms against the known sheet grid dimensions."""

    def test_bounded_in_and_out_of_range(self):
        assert SheetRangeValidator.is_range_within_bounds("A1:B2", 10, 10) is True
        assert SheetRangeValidator.is_range_within_bounds("A1:Z100", 10, 10) is False

    def test_single_cell(self):
        assert SheetRangeValidator.is_range_within_bounds("B2", 10, 10) is True
        assert SheetRangeValidator.is_range_within_bounds("B20", 10, 10) is False

    def test_malformed_and_reversed_are_out_of_bounds(self):
        assert SheetRangeValidator.is_range_within_bounds("A1B2", 10, 10) is False
        assert SheetRangeValidator.is_range_within_bounds("B2:A1", 10, 10) is False

    def test_open_ended_forms_resolved_against_dimensions(self):
        # Whole column: end column must fit within the sheet's column count.
        assert SheetRangeValidator.is_range_within_bounds("A:Z", 100, 26) is True
        assert SheetRangeValidator.is_range_within_bounds("A:AA", 100, 26) is False
        # Half-open: end row resolves to the sheet's row count and fits.
        assert SheetRangeValidator.is_range_within_bounds("A1:A", 100, 26) is True
        # Whole row: end row must fit within the sheet's row count.
        assert SheetRangeValidator.is_range_within_bounds("2:10", 100, 26) is True
        assert SheetRangeValidator.is_range_within_bounds("2:200", 100, 26) is False
