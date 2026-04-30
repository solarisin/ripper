"""Main dashboard view implementation."""

from pathlib import Path
from typing import Optional

from loguru import logger
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
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


class DashboardView(QWidget):
    """Main dashboard view that displays and manages dashboards."""

    dashboard_changed = Signal()

    def __init__(self, storage_dir: Path, parent: Optional[QWidget] = None):
        """Initialize the dashboard view.

        Args:
            storage_dir: Directory where dashboard files are stored
            parent: Parent widget
        """
        super().__init__(parent)
        self.storage_dir = storage_dir
        self.current_dashboard: Optional[Dashboard] = None
        self.dashboard_manager = DashboardManager(storage_dir)
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

        # Dashboard selection dropdown will be added here
        self.dashboard_label = QLabel("No dashboard selected")
        toolbar.addWidget(self.dashboard_label)

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

        # Delete dashboard button
        self.delete_dashboard_btn = QPushButton("Delete")
        self.delete_dashboard_btn.setEnabled(False)
        self.delete_dashboard_btn.clicked.connect(self._on_delete_dashboard)
        toolbar.addWidget(self.delete_dashboard_btn)

        # Dashboard content area
        self.content_widget = QWidget()
        self.content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.content_widget)

        # Load dashboards
        self._load_dashboards()

    def _load_dashboards(self) -> None:
        """Load dashboards from the storage directory."""
        self.dashboards = self.dashboard_manager.get_all_dashboards()

        # If we have dashboards, load the first one
        if self.dashboards:
            self._set_current_dashboard(self.dashboards[0])

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

        # Clear the current content
        layout = self.content_widget.layout()
        if layout:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.setParent(None)
                    widget.deleteLater()
        else:
            layout = QVBoxLayout()
            self.content_widget.setLayout(layout)

        if dashboard:
            self.dashboard_label.setText(f"Dashboard: {dashboard.name}")
            self.edit_dashboard_btn.setEnabled(True)
            self.delete_dashboard_btn.setEnabled(True)

            # Create a scroll area for the dashboard content
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)

            # Create container widget for the dashboard
            container = QWidget()
            container_layout = QGridLayout(container)
            container_layout.setContentsMargins(10, 10, 10, 10)
            container_layout.setSpacing(10)

            # Add widgets to the dashboard with validation
            grid_size = (12, 12)  # Match the canvas grid size
            for widget_id, widget_obj in dashboard.widgets.items():
                try:
                    # Dashboard.widgets is Dict[str, BaseWidget] but mypy doesn't infer this correctly
                    widget = widget_obj  # type: ignore[assignment]
                    widget_view = widget.create_widget(container)  # type: ignore[attr-defined]
                    if widget_view:
                        # Validate and adjust position/size
                        pos, size = self._validate_widget_position(
                            widget.config.position,
                            widget.config.size,
                            grid_size,  # type: ignore[attr-defined]
                        )
                        # Update widget config with validated values
                        widget.config.position = pos  # type: ignore[attr-defined]
                        widget.config.size = size  # type: ignore[attr-defined]
                        container_layout.addWidget(
                            widget_view,
                            pos[0],  # row
                            pos[1],  # column
                            size[1],  # rowSpan (height)
                            size[0],  # columnSpan (width)
                        )
                except Exception as e:
                    logger.error(f"Failed to create widget {widget_id}: {e}")
                    error_label = QLabel(f"Error loading widget: {str(e)}")
                    error_label.setStyleSheet("color: red;")
                    container_layout.addWidget(error_label)

            scroll.setWidget(container)
            layout.addWidget(scroll, 1)  # type: ignore[call-arg]
        else:
            self.dashboard_label.setText("No dashboard selected")
            self.edit_dashboard_btn.setEnabled(False)
            self.delete_dashboard_btn.setEnabled(False)

            # Add a placeholder for no dashboard selected
            placeholder = QLabel("No dashboard selected. Create a new one or select an existing one.")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(placeholder, 1)  # type: ignore[call-arg]

    def refresh(self) -> None:
        """Refresh the dashboard view."""
        if self.current_dashboard:
            self._set_current_dashboard(self.current_dashboard)

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
        dialog.setMinimumSize(1024, 768)

        # Setup layout
        layout = QVBoxLayout(dialog)
        layout.addWidget(editor)

        # Add dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            dialog,
        )
        button_box.accepted.connect(editor.save_dashboard)  # Use editor's save method
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # Show the dialog
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                # Save the dashboard
                self.dashboard_manager.save_dashboard(self.current_dashboard)
                # Refresh the view
                self._set_current_dashboard(self.current_dashboard)
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
