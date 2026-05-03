"""
Sidebar widget listing all saved data sources.

This module provides ``DataSourceListWidget``, a ``QWidget`` that shows all
persisted data sources from the database in a list with context-menu actions for
refreshing, editing, and deleting each source.
"""

from beartype.typing import Optional
from loguru import logger
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ripper.ripperlib.database import Db, RipperDb


class DataSourceListWidget(QWidget):
    """
    Sidebar panel that lists all saved data sources.

    Displays each data source as a two-line list item (name on the first line,
    spreadsheet + sheet + last-synced timestamp on the second).  Emits
    ``source_selected`` when the user clicks an item so the main view can load
    the corresponding cached data into the table dock.

    Signals:
        source_selected (int): Emitted with the data source ``id`` when an item
            is clicked.
        refresh_requested (int): Emitted with the data source ``id`` when the
            user chooses *Refresh* from the context menu.
    """

    source_selected: Signal = Signal(int)
    refresh_requested: Signal = Signal(int)

    def __init__(self, db: Optional[RipperDb] = None, parent: Optional[QWidget] = None) -> None:
        """
        Initialise the data source list widget.

        Args:
            db: Database instance to use.  Defaults to the application singleton.
            parent: Parent widget.
        """
        super().__init__(parent)
        self._db = db or Db
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        """Build the widget layout and list control."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._list = QListWidget(self)
        self._list.setAlternatingRowColors(True)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        self._list.itemClicked.connect(self._on_item_clicked)

        self._empty_label = QLabel("No data sources yet.\nUse File → New Source to add one.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #888; padding: 12px; font-size: 11px;")
        self._empty_label.setWordWrap(True)

        layout.addWidget(self._list)
        layout.addWidget(self._empty_label)

    def refresh(self) -> None:
        """Reload data sources from the database and repopulate the list."""
        self._list.clear()

        sources = self._db.list_data_sources()

        if not sources:
            self._list.hide()
            self._empty_label.show()
            return

        self._empty_label.hide()
        self._list.show()

        for source in sources:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, source["id"])
            item.setToolTip(
                f"Spreadsheet: {source.get('spreadsheet_name', source['spreadsheet_id'])}\n"
                f"Sheet: {source['sheet_name']}\n"
                f"Range: {source['range_a1']}"
            )
            # Build display text
            spreadsheet_label = source.get("spreadsheet_name") or source["spreadsheet_id"]
            fetched = source.get("last_fetched_at") or "never"
            # Trim timestamp to minute precision for readability
            if fetched != "never" and len(fetched) > 16:
                fetched = fetched[:16]
            item.setText(f"{source['name']}\n{spreadsheet_label} / {source['sheet_name']}  •  synced: {fetched}")
            self._list.addItem(item)

    def _current_source_id(self) -> Optional[int]:
        """Return the data source id for the currently selected list item, or None."""
        item = self._list.currentItem()
        if item is None:
            return None  # type: ignore[unreachable]
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def _source_id_at(self, pos: QPoint) -> Optional[int]:
        """Return the data source id for the item at the given viewport position."""
        item = self._list.itemAt(pos)
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else None

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Emit ``source_selected`` when the user clicks a list item."""
        ds_id = item.data(Qt.ItemDataRole.UserRole)
        if ds_id is not None:
            self.source_selected.emit(int(ds_id))

    def _show_context_menu(self, pos: QPoint) -> None:
        """
        Show the right-click context menu for data source actions.

        Args:
            pos: Mouse position in the list viewport's coordinate system.
        """
        ds_id = self._source_id_at(pos)
        if ds_id is None:
            return

        menu = QMenu(self)

        refresh_action = menu.addAction("Refresh from Google Sheets")
        edit_action = menu.addAction("Edit Name / Range")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")

        action = menu.exec(self._list.viewport().mapToGlobal(pos))

        if action == refresh_action:
            self.refresh_requested.emit(ds_id)
        elif action == edit_action:
            self._edit_source(ds_id)
        elif action == delete_action:
            self._delete_source(ds_id)

    def _edit_source(self, ds_id: int) -> None:
        """
        Open a simple dialog to rename a data source.

        Args:
            ds_id: Primary key of the data source to edit.
        """
        record = self._db.get_data_source(ds_id)
        if record is None:
            return

        new_name, ok = QInputDialog.getText(
            self,
            "Edit Data Source Name",
            "Name:",
            text=record["name"],
        )
        if not ok or not new_name.strip():
            return

        success = self._db.update_data_source(
            ds_id,
            name=new_name.strip(),
            sheet_name=record["sheet_name"],
            range_a1=record["range_a1"],
        )
        if success:
            logger.info(f"Renamed data source {ds_id} to '{new_name.strip()}'")
            self.refresh()
        else:
            QMessageBox.warning(self, "Edit Failed", "Could not update the data source name.")

    def _delete_source(self, ds_id: int) -> None:
        """
        Ask for confirmation then delete the data source.

        Args:
            ds_id: Primary key of the data source to delete.
        """
        record = self._db.get_data_source(ds_id)
        if record is None:
            return

        reply = QMessageBox.question(
            self,
            "Delete Data Source",
            f'Delete "{record["name"]}"?\n\nCached cell data will be kept.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self._db.delete_data_source(ds_id):
            logger.info(f"Deleted data source {ds_id}")
            self.refresh()
        else:
            QMessageBox.warning(self, "Delete Failed", "Could not delete the data source.")


class DataSourceBannerWidget(QWidget):
    """
    Thin horizontal banner shown above the data table inside the dock.

    Displays the data source name and the last-synced timestamp.
    """

    def __init__(self, title: str, fetched_at: str, parent: Optional[QWidget] = None) -> None:
        """
        Initialise the banner with a title and timestamp.

        Args:
            title: Data source name to display.
            fetched_at: ISO-format timestamp string (or empty string for "never").
            parent: Parent widget.
        """
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)

        timestamp = fetched_at[:16] if fetched_at and len(fetched_at) > 16 else (fetched_at or "never")
        text = f"{title}  —  last synced: {timestamp}"
        label = QLabel(text)
        label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(label)
        layout.addStretch()
