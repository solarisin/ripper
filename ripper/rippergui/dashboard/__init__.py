"""Dashboard module for Ripper."""

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QDialog, QMessageBox, QSizePolicy, QVBoxLayout, QWidget

from ripper.rippergui.dashboard.models import Dashboard, DashboardManager, DataSource
from ripper.rippergui.dashboard.views.dashboard_editor import DashboardEditor
from ripper.rippergui.dashboard.views.dashboard_view import DashboardView
from ripper.rippergui.dashboard.views.data_source_dialog import DataSourceDialog


class DashboardManagerWidget(QWidget):
    """Main widget for managing dashboards."""

    def __init__(self, storage_dir: Path, parent: Optional[QWidget] = None):
        """Initialize the dashboard manager.

        Args:
            storage_dir: Directory where dashboard files are stored
            parent: Parent widget
        """
        super().__init__(parent)
        self.storage_dir = storage_dir
        self.dashboard_manager = DashboardManager(storage_dir)

        # Current dashboard editor (if any)
        self.current_editor: Optional[DashboardEditor] = None

        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        self.setWindowTitle("Dashboards")

        # Main layout
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Show dashboard view by default
        self.show_dashboard_view()

    def show_dashboard_view(self) -> None:
        """Show the dashboard view."""
        # Clear current widget
        self._clear_current_widget()

        # Create and show dashboard view
        self.current_view = DashboardView(self.storage_dir, self)
        self.current_view.edit_dashboard_btn.clicked.connect(self._on_edit_dashboard)
        layout = self.layout()
        if layout is not None:
            layout.addWidget(self.current_view)

    def show_dashboard_editor(self, dashboard: Dashboard) -> None:
        """Show the dashboard editor for the given dashboard.

        Args:
            dashboard: Dashboard to edit
        """
        # Clear current widget
        self._clear_current_widget()

        # Create and show dashboard editor
        self.current_editor = DashboardEditor(dashboard, self)
        self.current_editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = self.layout()
        if layout is not None:
            layout.addWidget(self.current_editor)

    def _clear_current_widget(self) -> None:
        """Clear the current widget from the layout."""
        layout = self.layout()
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

    def _on_edit_dashboard(self) -> None:
        """Handle edit dashboard button click."""
        if hasattr(self, "current_view") and self.current_view.current_dashboard:
            self.show_dashboard_editor(self.current_view.current_dashboard)

    def add_data_source(self, data_source: DataSource) -> None:
        """Add a data source to the current dashboard.

        Args:
            data_source: Data source to add
        """
        if self.current_editor and self.current_editor.dashboard:
            try:
                self.current_editor.dashboard.add_data_source(data_source)
                # In a real app, you would update the UI to show the new data source
                QMessageBox.information(self, "Data Source Added", f"Added data source: {data_source.name}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to add data source: {e}")

    def show_data_source_dialog(
        self, data_source: Optional[DataSource] = None, available_sheets: Optional[dict] = None
    ) -> Optional[DataSource]:
        """Show the data source dialog.

        Args:
            data_source: Existing data source to edit, or None to create a new one
            available_sheets: Dictionary of available spreadsheet IDs and names

        Returns:
            The created/edited data source, or None if cancelled
        """
        dialog = DataSourceDialog(data_source, available_sheets, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.data_source
        return None
