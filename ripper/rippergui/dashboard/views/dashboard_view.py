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
    the GUI thread via :attr:`finished`, tagged with the dashboard it was started for so a stale
    result (the user switched dashboards mid-refresh) can be ignored.

    Signals:
        finished (object, object): Emitted with ``(DashboardRefreshResult, Dashboard)`` on success.
        error (str, object): Emitted with ``(message, Dashboard)`` on failure.
    """

    finished: Signal = Signal(object, object)  # type: ignore[misc]
    error: Signal = Signal(str, object)

    def __init__(self, data_service: DashboardDataService, dashboard: Dashboard):
        # Intentionally NOT parented to the view: an embedded QWidget has no reliable closeEvent,
        # so parent ownership could force-destroy this QThread mid-run when the view is torn down.
        # Lifetime is managed via _active_refresh_workers instead (see start_refresh).
        super().__init__()
        self._data_service = data_service
        self._dashboard = dashboard

    def run(self) -> None:
        """Refresh the dashboard's data sources in the background."""
        try:
            result = self._data_service.refresh_dashboard(self._dashboard)
            self.finished.emit(result, self._dashboard)
        except Exception as exc:
            logger.error(f"Dashboard refresh failed: {exc}")
            self.error.emit(str(exc), self._dashboard)


# Refresh workers that may still be running are kept alive here (a strong reference that outlives
# the view) so their QThread wrappers aren't garbage-collected — or force-destroyed with a parent
# view — while the thread is still running. Each removes itself when it finishes.
_active_refresh_workers: set[_DashboardRefreshWorker] = set()


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
        # True while a _DashboardRefreshWorker is running. Every control that can switch or mutate
        # the current dashboard is disabled while this holds, so the worker's target can't be
        # reassigned or re-refreshed mid-flight (#96). Cleared in both refresh completion slots.
        self._refresh_in_flight = False
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
            self._select_dashboard_in_combo(dashboard.id)
            self._add_dashboard_content(layout, dashboard)
        else:
            placeholder = QLabel("No dashboard selected.")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(placeholder, 1)
        self._update_control_states()

    def _update_control_states(self) -> None:
        """Derive toolbar control enablement from current state — the single source of truth.

        Centralising this keeps enablement consistent across the several places that change the
        current dashboard or start/finish a refresh, instead of toggling buttons ad hoc. While a
        refresh is in flight, every control that could switch or mutate ``current_dashboard`` (the
        combo, New Dashboard, Edit, Delete, Refresh) is disabled so the running worker's target
        cannot be reassigned or re-refreshed (#96).
        """
        has_dashboard = self.current_dashboard is not None
        in_flight = self._refresh_in_flight
        self.dashboard_combo.setEnabled(not in_flight)
        self.add_dashboard_btn.setEnabled(not in_flight)
        self.edit_dashboard_btn.setEnabled(has_dashboard and not in_flight)
        self.refresh_dashboard_btn.setEnabled(has_dashboard and not in_flight)
        self.delete_dashboard_btn.setEnabled(has_dashboard and not in_flight)

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
                # Hand the widget ONLY the category-type map for its own configured data source's
                # spreadsheet. Passing the whole per-source dict (or a cross-spreadsheet merge)
                # would let one source's transactions be classified with another spreadsheet's
                # metadata when they share a category name (issue #115). Absent map -> None ->
                # name-based fallback in TillerDataProcessor.
                source_id = widget_config.data_source_id
                category_types = self.refresh_result.category_types.get(source_id) if source_id else None
                runtime_widget.update_data(self.refresh_result.data, category_types)
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

        # Mark the refresh in flight and re-derive control states: this disables Refresh, Edit,
        # Delete, the dashboard combo, and New Dashboard together. All of these reassign, mutate, or
        # switch the current dashboard, and doing so while the worker thread is refreshing the same
        # object is a data race (#96). The flag is cleared — and controls restored — in
        # _on_refresh_finished and _on_refresh_error.
        self._refresh_in_flight = True
        self._update_control_states()
        self.status_label.setStyleSheet("")
        self.status_label.setText("Refreshing…")

        # The worker is unparented and retained in _active_refresh_workers so it is neither GC'd
        # nor force-destroyed with the view while running. Slots are bound methods, so Qt auto-
        # disconnects them if the view is destroyed before the worker finishes.
        worker = _DashboardRefreshWorker(self.data_service, self.current_dashboard)
        _active_refresh_workers.add(worker)
        worker.finished.connect(self._on_refresh_finished)
        worker.error.connect(self._on_refresh_error)
        worker.finished.connect(lambda *_, w=worker: _active_refresh_workers.discard(w))
        worker.error.connect(lambda *_, w=worker: _active_refresh_workers.discard(w))
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        worker.start()

    @Slot(object, object)
    def _on_refresh_finished(self, result: DashboardRefreshResult, dashboard: Dashboard) -> None:
        """Apply a completed refresh on the GUI thread, unless the user has switched dashboards."""
        if dashboard is not self.current_dashboard:
            # Stale: the refresh was for a dashboard the user has since navigated away from.
            # Switching is blocked while in flight, so this is a defensive #36 guard that should
            # not fire in practice; clear the flag regardless so controls can never stay stuck.
            self._refresh_in_flight = False
            self._update_control_states()
            return
        self._refresh_in_flight = False
        self.refresh_result = result
        self._show_refresh_summary()
        # _set_current_dashboard re-derives control enablement via _update_control_states, which now
        # sees the cleared in-flight flag and restores Refresh/Edit/Delete/combo/New Dashboard.
        self._set_current_dashboard(self.current_dashboard)

    @Slot(str, object)
    def _on_refresh_error(self, message: str, dashboard: Dashboard) -> None:
        """Report a failed refresh on the GUI thread, unless the user has switched dashboards."""
        if dashboard is not self.current_dashboard:
            # Defensive (see _on_refresh_finished): clear the flag so controls can't stay stuck.
            self._refresh_in_flight = False
            self._update_control_states()
            return
        self._refresh_in_flight = False
        self._update_control_states()
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
        if self._refresh_in_flight:
            # The button is disabled during a refresh; guard the slot too so a programmatic call
            # can't switch the current dashboard out from under the running worker (#96).
            return

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
        if not self.current_dashboard or self._refresh_in_flight:
            return

        from .dashboard_editor import DashboardEditor

        # Edit a deep copy so Cancel leaves the live dashboard untouched (#95). The working
        # copy is persisted and swapped in as the current dashboard only on Accept; the
        # editor's internal "Save Dashboard" button just syncs canvas state into the copy.
        working = Dashboard.from_dict(self.current_dashboard.to_dict())

        # Create and show the dashboard editor
        editor = DashboardEditor(working, self)
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
                # Persist the working copy and swap it in as the live dashboard
                self.dashboard_manager.save_dashboard(working)
                self.dashboards = self.dashboard_manager.get_all_dashboards()
                self._refresh_dashboard_combo()
                # Refresh the view
                self._set_current_dashboard(working)
                self.status_label.setStyleSheet("color: #1b5e20;")
                self.status_label.setText(f"Saved dashboard '{working.name}'.")
                self.dashboard_changed.emit()
            except Exception as e:
                logger.error(f"Error saving dashboard: {e}")
                QMessageBox.critical(self, "Error", f"Failed to save dashboard: {e}", QMessageBox.StandardButton.Ok)

    @Slot()
    def _on_delete_dashboard(self) -> None:
        """Handle the delete dashboard button click."""
        if not self.current_dashboard or self._refresh_in_flight:
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
        if self._refresh_in_flight:
            # A refresh is running against the current dashboard; switching now would reassign the
            # worker's target and strand the in-flight flag. The combo is disabled in the UI, so
            # this only guards programmatic/edge index changes — re-sync it to the current
            # dashboard and do nothing else (#96).
            if self.current_dashboard is not None:
                self._select_dashboard_in_combo(self.current_dashboard.id)
            return
        dashboard_id = self.dashboard_combo.itemData(index)
        if dashboard_id is None:
            return
        dashboard = self.dashboard_manager.get_dashboard(dashboard_id)
        if dashboard is not None and dashboard is not self.current_dashboard:
            self.refresh_result = DashboardRefreshResult()
            self.status_label.clear()
            self._set_current_dashboard(dashboard)
