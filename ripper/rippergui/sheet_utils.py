"""
Utility functions and validation logic for Google Sheets selection and range parsing.
"""

import re

from beartype.typing import Tuple

from ripper.ripperlib.range_manager import CellRange

#: Maximum column index Google Sheets supports (column "ZZZ" == 18278; see
#: https://support.google.com/drive/answer/37603). This is the Sheets platform ceiling, not the
#: Excel one (XFD == 16384) — columns XFE..ZZZ are valid in Sheets. Columns beyond this are
#: rejected as invalid format so absurd input like ``ZZZZ1`` never reads as a valid range; the
#: selected sheet's actual grid width is enforced separately by ``is_range_within_bounds``.
MAX_SHEET_COLUMNS = 18278

#: Sentinel grid dimensions used only to resolve open-ended forms (e.g. ``A:Z``, ``2:10``) during a
#: format-only check, where the real sheet dimensions are not known. Bounds are verified separately
#: by :meth:`SheetRangeValidator.is_range_within_bounds` once the sheet's true dimensions are known.
_FORMAT_CHECK_MAX_ROWS = 10_000_000


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
        Check whether the input is a syntactically valid Google Sheets A1 range.

        Parsing is delegated to the canonical parser (:meth:`CellRange.from_a1_notation`) so the
        GUI accepts exactly the forms the backend understands. Accepted forms:

        - single cell: ``A1``
        - bounded range: ``A1:B5`` (including the app-generated ``A1:{col}{row}`` full ranges)
        - whole column: ``A:A``, ``A:Z``
        - whole row: ``2:10``
        - half-open: ``A1:A`` (down column B... to the last row), ``A1:B``

        Rejected: empty/whitespace, reversed ranges (``B2:A1``), structurally malformed input
        (``A1B2``, ``A1:``, ``:B2``, ``A``, ``1``, ``A:5``), and any range whose column exceeds the
        Sheets maximum (``MAX_SHEET_COLUMNS`` / column "ZZZ"), e.g. ``ZZZZ1``.

        This is a *format* check only: it does not verify the range fits a particular sheet's grid
        (see :meth:`is_range_within_bounds`).

        Returns True if the format is valid, False otherwise.
        """
        if not text.strip():
            return False
        try:
            # Resolve open-ended forms against generous sentinels so the *shape* can be validated
            # without the real sheet dimensions; column sanity is enforced explicitly below.
            cell_range = CellRange.from_a1_notation(text, max_row=_FORMAT_CHECK_MAX_ROWS, max_col=MAX_SHEET_COLUMNS)
        except ValueError:
            return False
        return cell_range.start_col <= MAX_SHEET_COLUMNS and cell_range.end_col <= MAX_SHEET_COLUMNS

    @staticmethod
    def is_range_within_bounds(text: str, sheet_row_count: int, sheet_col_count: int) -> bool:
        """
        Check whether the range fits within the given sheet dimensions.

        Delegates parsing to :meth:`CellRange.from_a1_notation`, which resolves open-ended forms
        (``A:Z``, ``2:10``, ``A1:A``) against the supplied dimensions, then verifies the resolved
        rectangle lies within ``1..sheet_row_count`` x ``1..sheet_col_count``.

        Returns True if the range is within bounds, False otherwise.
        """
        try:
            cell_range = CellRange.from_a1_notation(text, max_row=sheet_row_count, max_col=sheet_col_count)
        except ValueError:
            return False
        return (
            cell_range.start_row >= 1
            and cell_range.start_col >= 1
            and cell_range.end_row <= sheet_row_count
            and cell_range.end_col <= sheet_col_count
        )
