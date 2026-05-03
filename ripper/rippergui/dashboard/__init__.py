"""Dashboard module for Ripper."""

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QVBoxLayout, QWidget


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
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        self.setWindowTitle("Dashboards")

        # Main layout
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Show dashboard view by default
        from ripper.rippergui.dashboard.views.dashboard_view import DashboardView

        self.current_view = DashboardView(self.storage_dir, self)
        layout.addWidget(self.current_view)
