"""
Utility functions and validation logic for Google Sheets selection and range parsing.
"""

import re

from beartype.typing import Tuple


def col_to_letter(col_index: int) -> str:
    """
    Convert column index to letter (A=1, B=2, etc.).
    """
    letter = ""
    while col_index > 0:
        col_index, remainder = divmod(col_index - 1, 26)
        letter = chr(65 + remainder) + letter
    return letter


def parse_cell(cell_text: str) -> Tuple[int, int]:
    """
    Basic parsing of cell like A1, B5.

    Args:
        cell_text: The cell text (e.g., "A1").

    Returns:
        A tuple containing the row number (1-indexed) and column number (1-indexed).

    Raises:
        ValueError: If the cell format is invalid.
    """
    if not re.match(r"^[A-Za-z]+\d+$", cell_text):
        raise ValueError("Invalid cell format")
    col_str = "".join(filter(str.isalpha, cell_text))
    row_str = "".join(filter(str.isdigit, cell_text))
    if not col_str or not row_str:
        raise ValueError("Invalid cell format")
    col_num = 0
    for char in col_str.upper():
        col_num = col_num * 26 + (ord(char) - ord("A") + 1)
    row_num = int(row_str)
    return row_num, col_num


class SheetRangeValidator:
    """
    Validation logic for Google Sheets range input.
    """

    @staticmethod
    def is_range_empty(text: str) -> bool:
        """
        Check if the range input is empty.
        Returns True if the range is NOT empty, False otherwise.
        """
        return bool(text.strip())

    @staticmethod
    def is_range_format_valid(text: str) -> bool:
        """
        Check if the range input matches the expected A1:B5 format.
        Returns True if the format is valid, False otherwise.
        """
        range_pattern = r"^[a-zA-Z]+\d+:[a-zA-Z]+\d+$"
        return bool(re.match(range_pattern, text))

    @staticmethod
    def is_range_within_bounds(text: str, sheet_row_count: int, sheet_col_count: int) -> bool:
        """
        Check if the range is within the sheet dimensions.
        Returns True if the range is within bounds, False otherwise.
        """
        try:
            parts = text.split(":")
            if len(parts) != 2:
                return False
            start_cell_text = parts[0]
            end_cell_text = parts[1]
            start_row, start_col = parse_cell(start_cell_text)
            end_row, end_col = parse_cell(end_cell_text)
            if (
                start_row < 1
                or start_col < 1
                or end_row > sheet_row_count
                or end_col > sheet_col_count
                or start_row > end_row
                or start_col > end_col
            ):
                return False
        except ValueError:
            return False
        return True
