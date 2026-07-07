"""Main dashboard view implementation."""

from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ripper.rippergui.dashboard.models import DashboardManager
from ripper.rippergui.dashboard.models.dashboard import Dashboard
from ripper.rippergui.dashboard.models.registry import get_widget_class
from ripper.rippergui.dashboard.services import DashboardDataService, DashboardRefreshResult


class _DashboardRefreshWorker(QThread):
    """Background worker that refreshes a dashboard's data off the GUI thread.

    ``DashboardDataService.refresh_dashboard`` authenticates with Google and fetches sheet
    ranges over the network; running it on the UI thread freezes the app (and can block on
    OAuth). This worker runs it in the background and hands the plain-dataclass result back to
    the GUI thread via :attr:`finished`.

    Signals:
        finished (object): Emitted with the ``DashboardRefreshResult`` on success.
        error (str): Emitted with a human-readable message on failure.
    """

    finished: Signal = Signal(object)  # type: ignore[misc]
    error: Signal = Signal(str)

    def __init__(self, data_service: DashboardDataService, dashboard: Dashboard, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._data_service = data_service
        self._dashboard = dashboard

    def run(self) -> None:
        """Refresh the dashboard's data sources in the background."""
        try:
            result = self._data_service.refresh_dashboard(self._dashboard)
            self.finished.emit(result)
        except Exception as exc:
            logger.error(f"Dashboard refresh failed: {exc}")
            self.error.emit(str(exc))


class DashboardView(QWidget):
    """Main dashboard view that displays and manages dashboards."""

    dashboard_changed = Signal()

    def __init__(
        self,
        storage_dir: Path,
        parent: Optional[QWidget] = None,
        data_service: Optional[DashboardDataService] = None,
        records_fn: Optional[Callable[[str, str, str], list[dict[str, Any]] | None]] = None,
    ):
        """Initialize the dashboard view.

        Args:
            storage_dir: Directory where dashboard files are stored
            parent: Parent widget
            data_service: Optional pre-configured data service (used in tests).
            records_fn: Optional callable ``(spreadsheet_id, sheet_name, range_a1)
                -> list[dict] | None`` forwarded to :class:`DashboardDataService`
                as its ``records_provider``.  Ignored when *data_service* is
                supplied directly.
        """
        super().__init__(parent)
        self.storage_dir = storage_dir
        self.current_dashboard: Optional[Dashboard] = None
        self.dashboard_manager = DashboardManager(storage_dir)
        if data_service is not None:
            self.data_service = data_service
        else:
            self.data_service = DashboardDataService(records_provider=records_fn)
        self.refresh_result = DashboardRefreshResult()
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        self.setWindowTitle("Dashboard")

        # Main layout
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Toolbar
        toolbar = QHBoxLayout()
        layout.addLayout(toolbar)

        toolbar.addWidget(QLabel("Dashboard:"))
        self.dashboard_combo = QComboBox()
        self.dashboard_combo.setMinimumWidth(240)
        self.dashboard_combo.currentIndexChanged.connect(self._on_dashboard_selected)
        toolbar.addWidget(self.dashboard_combo)

        # Add spacer
        toolbar.addStretch()

        # Add dashboard button
        self.add_dashboard_btn = QPushButton("New Dashboard")
        self.add_dashboard_btn.clicked.connect(self._on_add_dashboard)
        toolbar.addWidget(self.add_dashboard_btn)

        # Edit dashboard button
        self.edit_dashboard_btn = QPushButton("Edit")
        self.edit_dashboard_btn.setEnabled(False)
        self.edit_dashboard_btn.clicked.connect(self._on_edit_dashboard)
        toolbar.addWidget(self.edit_dashboard_btn)

        self.refresh_dashboard_btn = QPushButton("Refresh")
        self.refresh_dashboard_btn.setEnabled(False)
        self.refresh_dashboard_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_dashboard_btn)

        # Delete dashboard button
        self.delete_dashboard_btn = QPushButton("Delete")
        self.delete_dashboard_btn.setEnabled(False)
        self.delete_dashboard_btn.clicked.connect(self._on_delete_dashboard)
        toolbar.addWidget(self.delete_dashboard_btn)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Dashboard content area
        self.content_widget = QWidget()
        self.content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.content_widget)

        # Load dashboards
        self._load_dashboards()

    def _load_dashboards(self) -> None:
        """Load dashboards from the storage directory."""
        self.dashboards = self.dashboard_manager.get_all_dashboards()
        if not self.dashboards:
            dashboard = self.dashboard_manager.create_dashboard("My Dashboard")
            self.dashboard_manager.save_dashboard(dashboard)
            self.dashboards = self.dashboard_manager.get_all_dashboards()

        self._refresh_dashboard_combo()

        # If we have dashboards, load the first one
        if self.dashboards:
            self._set_current_dashboard(self.dashboards[0])

    def _refresh_dashboard_combo(self) -> None:
        """Refresh the dashboard selector."""
        current_id = self.current_dashboard.id if self.current_dashboard else None
        self.dashboard_combo.blockSignals(True)
        self.dashboard_combo.clear()
        for dashboard in self.dashboards:
            self.dashboard_combo.addItem(dashboard.name, dashboard.id)
        if current_id:
            index = self.dashboard_combo.findData(current_id)
            if index >= 0:
                self.dashboard_combo.setCurrentIndex(index)
        self.dashboard_combo.blockSignals(False)

    def _validate_widget_position(
        self, pos: tuple[int, int], size: tuple[int, int], grid: tuple[int, int]
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        """Validate and adjust widget position and size to fit within grid.

        Args:
            pos: Original (row, col) position
            size: Original (width, height) size
            grid: (rows, cols) of the grid

        Returns:
            Tuple of (validated_position, validated_size)
        """
        row, col = pos
        width, height = size
        max_rows, max_cols = grid
        row = max(0, min(row, max_rows - 1))
        col = max(0, min(col, max_cols - 1))
        width = max(1, min(width, max_cols - col))
        height = max(1, min(height, max_rows - row))
        return (row, col), (width, height)

    def _set_current_dashboard(self, dashboard: Optional[Dashboard]) -> None:
        """Set the current dashboard to display.

        Args:
            dashboard: Dashboard to display, or None to clear the view
        """
        self.current_dashboard = dashboard
        layout = self._content_layout()

        if dashboard:
            self.edit_dashboard_btn.setEnabled(True)
            self.refresh_dashboard_btn.setEnabled(True)
            self.delete_dashboard_btn.setEnabled(True)
            self._select_dashboard_in_combo(dashboard.id)
            self._add_dashboard_content(layout, dashboard)
        else:
            self.edit_dashboard_btn.setEnabled(False)
            self.refresh_dashboard_btn.setEnabled(False)
            self.delete_dashboard_btn.setEnabled(False)
            placeholder = QLabel("No dashboard selected.")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(placeholder, 1)

    def _select_dashboard_in_combo(self, dashboard_id: str) -> None:
        index = self.dashboard_combo.findData(dashboard_id)
        if index >= 0 and index != self.dashboard_combo.currentIndex():
            self.dashboard_combo.blockSignals(True)
            self.dashboard_combo.setCurrentIndex(index)
            self.dashboard_combo.blockSignals(False)

    def _content_layout(self) -> QVBoxLayout:
        """Return the content layout after clearing it."""
        layout = self.content_widget.layout()
        if layout:
            while layout.count():
                item = layout.takeAt(0)
                if item is not None:
                    widget = item.widget()
                    if widget:
                        widget.setParent(None)
                        widget.deleteLater()
        else:
            layout = QVBoxLayout()
            self.content_widget.setLayout(layout)
        return layout  # type: ignore[return-value]

    def _add_dashboard_content(self, layout: QVBoxLayout, dashboard: Dashboard) -> None:
        """Add rendered widgets for a dashboard to the content layout."""
        if not dashboard.widgets:
            empty = QLabel("No widgets yet. Click Edit, then add widgets from the palette.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #666; font-size: 14px; padding: 24px;")
            layout.addWidget(empty, 1)
            return

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        container_layout = QGridLayout(container)
        container_layout.setContentsMargins(10, 10, 10, 10)
        container_layout.setSpacing(10)

        for widget_id, widget_config in dashboard.widgets.items():
            pos, size = self._validate_widget_position(widget_config.position, widget_config.size, dashboard.grid_size)
            try:
                widget_class = get_widget_class(widget_config.type)
                if widget_class is None:
                    raise ValueError(f"Unknown widget type: {widget_config.type.value}")
                runtime_widget = widget_class(widget_config, dashboard)
                widget_view = runtime_widget.create_widget(container)
                runtime_widget.update_data(self.refresh_result.data)
                container_layout.addWidget(widget_view, pos[0], pos[1], size[1], size[0])
            except Exception as e:
                logger.error(f"Failed to create widget {widget_id}: {e}")
                error_label = QLabel(f"Error loading widget: {str(e)}")
                error_label.setStyleSheet("color: red;")
                container_layout.addWidget(error_label, pos[0], pos[1], size[1], size[0])

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

    def refresh(self) -> None:
        """Refresh the dashboard's data in the background, then re-render.

        Authentication and network I/O run on a :class:`_DashboardRefreshWorker` thread so the
        UI never freezes; the result is applied in :meth:`_on_refresh_finished` on the GUI thread.
        """
        if not self.current_dashboard:
            return

        self.refresh_dashboard_btn.setEnabled(False)
        self.status_label.setStyleSheet("")
        self.status_label.setText("Refreshing…")

        # parent=self keeps the QThread alive (Qt ownership) until it finishes; deleteLater then
        # reaps it. The Refresh button is disabled for the duration, so there is no re-entry.
        worker = _DashboardRefreshWorker(self.data_service, self.current_dashboard, self)
        worker.finished.connect(self._on_refresh_finished)
        worker.error.connect(self._on_refresh_error)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        worker.start()

    @Slot(object)
    def _on_refresh_finished(self, result: DashboardRefreshResult) -> None:
        """Apply a completed refresh on the GUI thread."""
        self.refresh_result = result
        self.refresh_dashboard_btn.setEnabled(True)
        self._show_refresh_summary()
        if self.current_dashboard:
            self._set_current_dashboard(self.current_dashboard)

    @Slot(str)
    def _on_refresh_error(self, message: str) -> None:
        """Report a failed refresh on the GUI thread."""
        self.refresh_dashboard_btn.setEnabled(True)
        self.status_label.setStyleSheet("color: #b00020;")
        self.status_label.setText(f"Refresh failed: {message}")

    def _show_refresh_summary(self) -> None:
        """Show a concise refresh summary."""
        if not self.refresh_result.statuses:
            return
        failures = [status for status in self.refresh_result.statuses.values() if not status.ok]
        if failures:
            self.status_label.setStyleSheet("color: #b00020;")
            self.status_label.setText("; ".join(status.message for status in failures))
            return
        total_rows = sum(status.row_count for status in self.refresh_result.statuses.values())
        self.status_label.setStyleSheet("color: #1b5e20;")
        self.status_label.setText(f"Refresh complete. Loaded {total_rows} rows.")

    @Slot()
    def _on_add_dashboard(self) -> None:
        """Handle the add dashboard button click."""
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(
            self, "New Dashboard", "Enter dashboard name:", text=f"Dashboard {len(self.dashboards) + 1}"
        )

        if ok and name:
            try:
                dashboard = self.dashboard_manager.create_dashboard(name)
                self.dashboard_manager.save_dashboard(dashboard)
                self._load_dashboards()
                self._set_current_dashboard(dashboard)
                self.status_label.setText(f"Created dashboard '{dashboard.name}'.")
                self.dashboard_changed.emit()
            except Exception as e:
                logger.error(f"Error creating dashboard: {e}")
                QMessageBox.critical(self, "Error", f"Failed to create dashboard: {e}")

    @Slot()
    def _on_edit_dashboard(self) -> None:
        """Handle the edit dashboard button click."""
        if not self.current_dashboard:
            return

        from .dashboard_editor import DashboardEditor

        # Create and show the dashboard editor
        editor = DashboardEditor(self.current_dashboard, self)
        # Connect the dashboard_saved signal to refresh the view
        editor.signals.dashboard_saved.connect(lambda: self._set_current_dashboard(self.current_dashboard))
        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit Dashboard: {self.current_dashboard.name}")
        dialog.setMinimumSize(900, 650)
        dialog.setSizeGripEnabled(True)
        dialog.resize(1100, 720)

        # Setup layout
        layout = QVBoxLayout(dialog)
        layout.addWidget(editor)

        # Add dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            dialog,
        )
        button_box.accepted.connect(editor.apply_canvas_state)  # sync canvas positions to model
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # Show the dialog
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                # Save the dashboard
                self.dashboard_manager.save_dashboard(self.current_dashboard)
                self.dashboards = self.dashboard_manager.get_all_dashboards()
                self._refresh_dashboard_combo()
                # Refresh the view
                self._set_current_dashboard(self.current_dashboard)
                self.status_label.setStyleSheet("color: #1b5e20;")
                self.status_label.setText(f"Saved dashboard '{self.current_dashboard.name}'.")
                self.dashboard_changed.emit()
            except Exception as e:
                logger.error(f"Error saving dashboard: {e}")
                QMessageBox.critical(self, "Error", f"Failed to save dashboard: {e}", QMessageBox.StandardButton.Ok)

    @Slot()
    def _on_delete_dashboard(self) -> None:
        """Handle the delete dashboard button click."""
        if not self.current_dashboard:
            return

        reply = QMessageBox.question(
            self,
            "Delete Dashboard",
            f"Are you sure you want to delete the dashboard '{self.current_dashboard.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                dashboard_id = self.current_dashboard.id
                if self.dashboard_manager.delete_dashboard(dashboard_id):
                    # Clear the current dashboard
                    self.current_dashboard = None
                    self._load_dashboards()

                    # Set the first dashboard as current if available
                    if self.dashboards:
                        self._set_current_dashboard(self.dashboards[0])
                    else:
                        self._set_current_dashboard(None)

                    self.dashboard_changed.emit()
            except Exception as e:
                logger.error(f"Error deleting dashboard: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete dashboard: {e}")

    @Slot(int)
    def _on_dashboard_selected(self, index: int) -> None:
        """Switch to the dashboard selected in the combo box."""
        dashboard_id = self.dashboard_combo.itemData(index)
        if dashboard_id is None:
            return
        dashboard = self.dashboard_manager.get_dashboard(dashboard_id)
        if dashboard is not None and dashboard is not self.current_dashboard:
            self.refresh_result = DashboardRefreshResult()
            self.status_label.clear()
            self._set_current_dashboard(dashboard)
