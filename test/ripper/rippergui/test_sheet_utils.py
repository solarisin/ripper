import pytest

from ripper.rippergui.sheet_utils import SheetRangeValidator, col_to_letter, parse_cell


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


def test_is_range_format_valid():
    assert SheetRangeValidator.is_range_format_valid("A1:B2") is True
    assert SheetRangeValidator.is_range_format_valid("A1B2") is False
    assert SheetRangeValidator.is_range_format_valid("") is False
    assert SheetRangeValidator.is_range_format_valid("A:B") is False


def test_is_range_within_bounds():
    # Valid range
    assert SheetRangeValidator.is_range_within_bounds("A1:B2", 10, 10) is True
    # Out of bounds
    assert SheetRangeValidator.is_range_within_bounds("A1:Z100", 10, 10) is False
    # Invalid format
    assert SheetRangeValidator.is_range_within_bounds("A1B2", 10, 10) is False
    # Start > end
    assert SheetRangeValidator.is_range_within_bounds("B2:A1", 10, 10) is False
