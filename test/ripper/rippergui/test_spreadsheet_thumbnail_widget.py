"""Tests for SpreadsheetThumbnailWidget (issue #59: module previously had no dedicated tests).

Focus of this module is issue #47: the widget must elide a too-wide spreadsheet name only for
its display label and must never write the elided text back onto the shared
``SpreadsheetProperties`` instance, which is emitted via ``spreadsheet_selected`` and consumed
downstream for the details panel and the auto-generated data-source name.
"""

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QWidget

from ripper.rippergui.spreadsheet_thumbnail_widget import SpreadsheetThumbnailWidget
from ripper.ripperlib.defs import SpreadsheetProperties


def _make_properties(name: str) -> MagicMock:
    """Build a SpreadsheetProperties test double with a ``thumbnail_link`` that starts no loader."""
    props = MagicMock(spec=SpreadsheetProperties)
    props.id = "test_id"
    props.name = name
    props.modified_time = "2024-01-01T00:00:00Z"
    props.created_time = "2023-12-01T00:00:00Z"
    props.thumbnail_link = ""  # empty -> constructor takes the no-network branch
    return props


@pytest.mark.qt
class TestSpreadsheetThumbnailWidgetNameMutation:
    """Regression tests for issue #47 (shared-model mutation via elided display text)."""

    def test_long_name_not_mutated_on_shared_properties(self, qtbot):
        """A too-wide name must remain intact on the model; only the label may be elided (#47)."""
        # Long enough that it is guaranteed to exceed the ~170px label width on any platform.
        long_name = "A Very Long Spreadsheet Name That Will Definitely Be Elided " * 4
        props = _make_properties(long_name)

        parent = QWidget()
        qtbot.addWidget(parent)

        widget = SpreadsheetThumbnailWidget(props, parent)
        qtbot.addWidget(widget)

        # The shared model data must be untouched...
        assert props.name == long_name
        assert widget.spreadsheet_properties.name == long_name
        # ...while the label shows a shorter, elided string.
        assert widget.name_label.text() != long_name
        assert len(widget.name_label.text()) < len(long_name)

    def test_short_name_shown_verbatim(self, qtbot):
        """A name that fits needs no elision and is shown as-is, model unchanged."""
        name = "Budget"
        props = _make_properties(name)

        parent = QWidget()
        qtbot.addWidget(parent)

        widget = SpreadsheetThumbnailWidget(props, parent)
        qtbot.addWidget(widget)

        assert props.name == name
        assert widget.name_label.text() == name
