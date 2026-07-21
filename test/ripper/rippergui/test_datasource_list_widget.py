"""Tests for ``DataSourceListWidget`` (issue #59: module previously had no dedicated tests).

The widget renders persisted data sources from the database in a ``QListWidget``, emits
``source_selected`` on click and ``refresh_requested`` from its context menu, and drives
rename/delete through the injected database instance. All database access is mocked with a
typed ``MagicMock(spec=RipperDb)`` double so no real DB, keyring, or Google API is touched.
"""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QMessageBox

from ripper.rippergui.datasource_list_widget import DataSourceListWidget
from ripper.ripperlib.database import RipperDb


def _make_source(
    ds_id: int,
    name: str = "My Source",
    spreadsheet_id: str = "sheet-abc",
    spreadsheet_name: str | None = "Budget 2026",
    sheet_name: str = "Transactions",
    range_a1: str = "A1:F100",
    last_fetched_at: str | None = "2026-07-20T14:30:45.123456+00:00",
) -> dict:
    """Build a data-source record dict matching ``RipperDb.list_data_sources`` output."""
    return {
        "id": ds_id,
        "name": name,
        "spreadsheet_id": spreadsheet_id,
        "spreadsheet_name": spreadsheet_name,
        "sheet_name": sheet_name,
        "range_a1": range_a1,
        "created_at": "2026-07-01T00:00:00+00:00",
        "last_fetched_at": last_fetched_at,
    }


def _make_db(sources: list[dict]) -> MagicMock:
    """Return a mock RipperDb whose ``list_data_sources`` yields the given records."""
    db = MagicMock(spec=RipperDb)
    db.list_data_sources.return_value = sources
    return db


@pytest.mark.qt
class TestPopulation:
    """Construction, empty state, and list population."""

    def test_empty_state_hides_list_and_shows_label(self, qtbot):
        """With no sources the list is hidden and the empty-state label is shown."""
        db = _make_db([])
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        db.list_data_sources.assert_called_once()
        assert widget._list.count() == 0
        assert widget._list.isHidden()
        assert not widget._empty_label.isHidden()

    def test_populates_one_item_per_source(self, qtbot):
        """Each returned record produces exactly one list item, and the label is hidden."""
        db = _make_db([_make_source(1), _make_source(2, name="Second")])
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        assert widget._list.count() == 2
        assert not widget._list.isHidden()
        assert widget._empty_label.isHidden()

    def test_item_stores_id_in_user_role(self, qtbot):
        """The data source id is stored on the item under ``UserRole`` for later lookup."""
        db = _make_db([_make_source(42)])
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        item = widget._list.item(0)
        assert item.data(Qt.ItemDataRole.UserRole) == 42

    def test_item_text_uses_name_spreadsheet_and_trimmed_timestamp(self, qtbot):
        """Display text shows name, spreadsheet/sheet label, and a minute-trimmed sync time."""
        db = _make_db([_make_source(1, name="Groceries")])
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        text = widget._list.item(0).text()
        assert "Groceries" in text
        assert "Budget 2026 / Transactions" in text
        # Long ISO timestamp is trimmed to minute precision (first 16 chars).
        assert "2026-07-20T14:30" in text
        assert "45.123456" not in text

    def test_item_falls_back_to_spreadsheet_id_when_name_missing(self, qtbot):
        """When ``spreadsheet_name`` is absent, the raw ``spreadsheet_id`` is displayed."""
        db = _make_db([_make_source(1, spreadsheet_name=None, spreadsheet_id="raw-id-xyz")])
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        text = widget._list.item(0).text()
        assert "raw-id-xyz" in text

    def test_never_fetched_shows_never(self, qtbot):
        """A source never synced shows ``never`` rather than a timestamp."""
        db = _make_db([_make_source(1, last_fetched_at=None)])
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        assert "synced: never" in widget._list.item(0).text()

    def test_item_tooltip_contains_sheet_and_range(self, qtbot):
        """The item tooltip surfaces spreadsheet, sheet, and range details."""
        db = _make_db([_make_source(1)])
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        tooltip = widget._list.item(0).toolTip()
        assert "Budget 2026" in tooltip
        assert "Transactions" in tooltip
        assert "A1:F100" in tooltip

    def test_refresh_repopulates_after_source_list_changes(self, qtbot):
        """Calling ``refresh`` re-queries the DB and rebuilds the list from scratch."""
        db = _make_db([_make_source(1)])
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)
        assert widget._list.count() == 1

        db.list_data_sources.return_value = [_make_source(1), _make_source(2)]
        widget.refresh()
        assert widget._list.count() == 2


@pytest.mark.qt
class TestSelectionSignal:
    """The ``source_selected`` signal wiring."""

    def test_item_click_emits_source_selected_with_id(self, qtbot):
        """Clicking a list item emits ``source_selected`` carrying that source's id."""
        db = _make_db([_make_source(7)])
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        item = widget._list.item(0)
        with qtbot.waitSignal(widget.source_selected, timeout=1000) as blocker:
            widget._list.itemClicked.emit(item)
        assert blocker.args == [7]


@pytest.mark.qt
class TestContextMenu:
    """Context-menu driven refresh, rename, and delete actions."""

    def _patch_menu(self, exec_returns_index: int):
        """Patch the module ``QMenu`` so ``exec`` returns the Nth added action.

        Returns the patch context manager; index 0=refresh, 1=rename, 2=delete.
        """
        menu = MagicMock()
        actions = [MagicMock(name="refresh"), MagicMock(name="rename"), MagicMock(name="delete")]
        menu.addAction.side_effect = actions
        menu.exec.return_value = actions[exec_returns_index]
        return patch("ripper.rippergui.datasource_list_widget.QMenu", return_value=menu)

    def test_context_menu_refresh_emits_refresh_requested(self, qtbot):
        """Choosing *Refresh* from the context menu emits ``refresh_requested`` with the id."""
        db = _make_db([_make_source(9)])
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        pos = widget._list.visualItemRect(widget._list.item(0)).center()

        with self._patch_menu(exec_returns_index=0):
            with qtbot.waitSignal(widget.refresh_requested, timeout=1000) as blocker:
                widget._show_context_menu(pos)
        assert blocker.args == [9]

    def test_context_menu_on_empty_area_does_nothing(self, qtbot):
        """Right-clicking where there is no item returns early without building a menu."""
        db = _make_db([])
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        with self._patch_menu(exec_returns_index=0) as menu_cls:
            widget._show_context_menu(QPoint(5, 5))
        menu_cls.assert_not_called()

    def test_context_menu_delete_invokes_delete_flow(self, qtbot):
        """Choosing *Delete* routes to the delete flow for the item's id."""
        db = _make_db([_make_source(3)])
        db.get_data_source.return_value = _make_source(3)
        db.delete_data_source.return_value = True
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        pos = widget._list.visualItemRect(widget._list.item(0)).center()

        with self._patch_menu(exec_returns_index=2):
            with patch(
                "ripper.rippergui.datasource_list_widget.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                widget._show_context_menu(pos)

        db.delete_data_source.assert_called_once_with(3)


@pytest.mark.qt
class TestDelete:
    """``_delete_source`` confirmation and DB wiring."""

    def test_delete_confirmed_calls_db_and_refreshes(self, qtbot):
        """Confirming deletion calls ``delete_data_source`` and reloads the list."""
        db = _make_db([_make_source(5)])
        db.get_data_source.return_value = _make_source(5)
        db.delete_data_source.return_value = True
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        with patch(
            "ripper.rippergui.datasource_list_widget.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            db.list_data_sources.return_value = []
            widget._delete_source(5)

        db.delete_data_source.assert_called_once_with(5)
        # refresh() ran after delete -> list re-queried and now empty.
        assert widget._list.count() == 0

    def test_delete_declined_does_not_call_db(self, qtbot):
        """Declining the confirmation dialog leaves the database untouched."""
        db = _make_db([_make_source(5)])
        db.get_data_source.return_value = _make_source(5)
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        with patch(
            "ripper.rippergui.datasource_list_widget.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ):
            widget._delete_source(5)

        db.delete_data_source.assert_not_called()

    def test_delete_missing_record_returns_early(self, qtbot):
        """When the record no longer exists, no confirmation is shown and no delete occurs."""
        db = _make_db([])
        db.get_data_source.return_value = None
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        with patch("ripper.rippergui.datasource_list_widget.QMessageBox.question") as question:
            widget._delete_source(999)

        question.assert_not_called()
        db.delete_data_source.assert_not_called()

    def test_delete_failure_shows_warning(self, qtbot):
        """A failed delete surfaces a warning dialog."""
        db = _make_db([_make_source(5)])
        db.get_data_source.return_value = _make_source(5)
        db.delete_data_source.return_value = False
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        with patch(
            "ripper.rippergui.datasource_list_widget.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            with patch("ripper.rippergui.datasource_list_widget.QMessageBox.warning") as warning:
                widget._delete_source(5)

        warning.assert_called_once()


@pytest.mark.qt
class TestEdit:
    """``_edit_source`` rename flow."""

    def test_edit_accepted_updates_and_refreshes(self, qtbot):
        """Accepting the rename dialog updates the source with the trimmed name."""
        db = _make_db([_make_source(8, name="Old Name")])
        db.get_data_source.return_value = _make_source(8, name="Old Name")
        db.update_data_source.return_value = True
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        with patch(
            "ripper.rippergui.datasource_list_widget.QInputDialog.getText",
            return_value=("  New Name  ", True),
        ):
            widget._edit_source(8)

        db.update_data_source.assert_called_once_with(8, name="New Name", sheet_name="Transactions", range_a1="A1:F100")

    def test_edit_cancelled_does_not_update(self, qtbot):
        """Cancelling the rename dialog leaves the source unchanged."""
        db = _make_db([_make_source(8)])
        db.get_data_source.return_value = _make_source(8)
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        with patch(
            "ripper.rippergui.datasource_list_widget.QInputDialog.getText",
            return_value=("Whatever", False),
        ):
            widget._edit_source(8)

        db.update_data_source.assert_not_called()

    def test_edit_blank_name_does_not_update(self, qtbot):
        """A whitespace-only new name is rejected and no update is performed."""
        db = _make_db([_make_source(8)])
        db.get_data_source.return_value = _make_source(8)
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        with patch(
            "ripper.rippergui.datasource_list_widget.QInputDialog.getText",
            return_value=("   ", True),
        ):
            widget._edit_source(8)

        db.update_data_source.assert_not_called()

    def test_edit_missing_record_returns_early(self, qtbot):
        """A rename for a vanished record never opens the input dialog."""
        db = _make_db([])
        db.get_data_source.return_value = None
        widget = DataSourceListWidget(db=db)
        qtbot.addWidget(widget)

        with patch("ripper.rippergui.datasource_list_widget.QInputDialog.getText") as get_text:
            widget._edit_source(999)

        get_text.assert_not_called()
        db.update_data_source.assert_not_called()
